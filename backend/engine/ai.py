"""AI draft-generation adapter (Spike S7).

Provider pattern so the rest of the engine never touches a vendor SDK:
  - provider "mock": deterministic offline generation (hash-seeded, no network).
    Guarantees identical output for identical context — CI/test safe.
  - provider "gemini": Google Gemini REST API (generativelanguage.googleapis.com),
    enabled only when settings expose an API key. Milestone C adds keyring storage.

Fail-closed rule: an AI provider error NEVER corrupts a run — callers get
GenerationError and the run path can fall back to the static template pack.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
TIMEOUT_S = 20


def gemini_key() -> str:
    """The configured Gemini API key ('' when absent). Keys only ever come from
    the environment — never from the DB, the UI, or a committed file.
    AUTOSTACK_GEMINI_API_KEY is accepted as a legacy alias."""
    return (os.environ.get("AUTOSTACK_GEMINI_KEY", "")
            or os.environ.get("AUTOSTACK_GEMINI_API_KEY", ""))


def effective_provider() -> tuple[str, str]:
    """(provider, reason) actually in use after the selection rules.

    Gemini is used ONLY when explicitly selected AND a non-empty key exists;
    every other configuration resolves to the offline mock, so CI and no-key
    environments are always deterministic."""
    selected = os.environ.get("AUTOSTACK_AI_PROVIDER", "mock")
    if selected == "gemini":
        if gemini_key():
            return "gemini", "gemini selected with an API key"
        return "mock", "gemini selected but no AUTOSTACK_GEMINI_KEY — offline generator"
    return "mock", "default offline provider"


class GenerationError(RuntimeError):
    """Raised when the selected provider cannot produce text (fail-closed)."""


def _mock_text(prompt: str, context: dict) -> str:
    """Deterministic stand-in generation: stable hash of (prompt, context).

    Mirrors the shape of a real completion (header + referenced fields) so
    downstream rendering code is exercised identically in tests and offline demos.
    """
    seed = hashlib.sha256(
        (prompt + "\n\x00\n" + json.dumps(context, sort_keys=True, default=str)).encode()
    ).hexdigest()
    fields = ", ".join(f"{k}={context[k]}" for k in sorted(context)) or "no fields"
    return (
        f"[mock:{seed[:12]}] Draft generated for context: {fields}. "
        f"This offline output is deterministic and safe for the judge demo; "
        f"configure a Gemini key in Settings to switch to live generation."
    )


def _synth_code(context: dict) -> str:
    """Deterministic code synthesis from the plan rules (mock provider, Phase 5).

    The generated function is REAL: it applies exactly the rules the user confirmed —
    eligibility from ctx (set by the runner from the plan), action, and destinations —
    reading nothing else. No network, no filesystem, only builtins; passes static_check.
    Different plans produce different code (field names/action branch on plan content).
    """
    id_field = context.get("client_id_field", "ClientID")
    action = context.get("action", "create_draft")
    if action not in ("create_draft", "update_status"):
        action = "create_draft"  # ALLOWED_ACTIONS gate already blocked others upstream
    elig = context.get("eligibility") or {}
    date_field = elig.get("date_field") or "FollowUpDate"
    return (
        "def run(rows, ctx):\n"
        "    out = []\n"
        "    status = ctx.get('eligibility_status')\n"
        "    run_date = ctx.get('eligibility_date')\n"
        f"    id_field = {id_field!r}\n"
        "    for row in rows:\n"
        "        if status is not None and row.get('Status') != status:\n"
        "            continue\n"
        "        if run_date is not None:\n"
        f"            due = row.get({date_field!r})\n"
        "            if due is None or str(due) > str(run_date):\n"
        "                continue\n"
        f"        if {action!r} == 'update_status':\n"
        f"            out.append({{{id_field!r}: row.get(id_field), 'effect': 'update_status'}})\n"
        "        else:\n"
        f"            out.append({{{id_field!r}: row.get(id_field), 'effect': 'create_draft'}})\n"
        "    return out\n"
    )


def _gemini_text(prompt: str, context: dict, api_key: str) -> str:
    payload = {
        "contents": [{
            "parts": [{"text": prompt + "\n\n" + GEMINI_PROMPT_RULES +
                       "\n\nCONTEXT (only these confirmed plan rules and retrieved "
                       "tools — never a full catalog): " +
                       json.dumps(context, sort_keys=True, default=str)}],
        }],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 512,
                             "stopSequences": ["```end", "</code>"]},
    }
    req = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=GEMINI_MODEL, key=api_key),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
            data = json.loads(res.read().decode())
    except Exception as exc:  # network, HTTP, JSON — all fail closed
        raise GenerationError(f"gemini request failed: {exc}") from exc
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GenerationError(f"gemini response malformed: {json.dumps(data)[:200]}") from exc


GEMINI_PROMPT_RULES = (
    "Return ONLY one Python function `def run(rows, ctx):` and nothing else — no "
    "prose, no imports beyond the allowlist csv/io/datetime/re/json, no network, "
    "no filesystem access, no eval/exec/compile/getattr, no subprocess or os/sys. "
    "The function filters `rows` (list of dicts) by the eligibility rules in ctx "
    "and returns a list of small result dicts keyed by the client id field."
)


def generate_text(prompt: str, context: dict | None = None, *, provider: str | None = None,
                  api_key: str | None = None, fallback: bool = True) -> str:
    """Generate text through the configured provider.

    Selection rules: the default provider is the offline deterministic mock; the
    Gemini provider is used only when explicitly selected AND a key is present.
    With fallback=True (the engine path), any Gemini failure — network, HTTP,
    timeout, malformed JSON, bad content — silently degrades to the mock so a
    misconfigured or rate-limited key can NEVER break automation creation.
    The returned text is prefixed "[fallback:...]" when a fallback occurred so
    callers can surface an honest note; strip it with strip_fallback_marker().
    """
    context = context or {}
    if provider or api_key is not None:
        # Explicit caller override (tests): run exactly the requested provider,
        # errors surface as GenerationError instead of a silent mock fallback.
        text, used = _generate_with(prompt, context, provider or "mock", api_key or "")
        return text
    selected = os.environ.get("AUTOSTACK_AI_PROVIDER", "mock")
    try:
        text, _ = _generate_with(prompt, context, selected, gemini_key())
        return text
    except GenerationError as exc:
        if selected != "gemini" or not fallback:
            raise
        note = f"live AI unavailable ({str(exc)[:120]}) — used offline generator"
        mock_text, _ = _generate_with(prompt, context, "mock", "")
        return f"[fallback:{note}]\n{mock_text}"


def strip_fallback_marker(text: str) -> tuple[str, str | None]:
    """Split a leading '[fallback:...]' marker off generated text.

    Returns (clean_text, note). The note is UI-safe and never contains the key
    or a stack trace — just the short reason recorded in the audit trail."""
    if text.startswith("[fallback:"):
        end = text.find("]")
        if end > 0:
            return text[end + 1:].lstrip("\n"), text[len("[fallback:"):end]
    return text, None


def _generate_with(prompt: str, context: dict, provider: str, api_key: str) -> tuple[str, str]:
    """Single provider attempt. Returns (text, provider_used)."""
    if provider == "mock":
        if context.get("mode") == "code":
            return "```python\n" + _synth_code(context) + "```\n", "mock"
        return _mock_text(prompt, context), "mock"
    if provider == "gemini":
        if not api_key:
            raise GenerationError("provider gemini selected but no API key configured")
        return _gemini_text(prompt, context, api_key), "gemini"
    raise GenerationError(f"unknown AI provider: {provider}")
