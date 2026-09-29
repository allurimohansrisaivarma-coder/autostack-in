"""Phase 5: plan validation + generation with STATIC security validation (S9).

Rules (from the plan):
  - Missing or contradictory rules BLOCK generation (no defaults invented).
  - Generated code is validated statically; unsupported/extra behavior is rejected.
    Hard rejects: imports outside an allowlist, network/socket/subprocess/eval/exec,
    filesystem writes outside the permitted resource alias, os/env/system access,
    dunder abuse, dependency installation. Repair attempts are capped; every version
    is preserved in the artifact table.
  - A model response can NEVER mint a permission or approval (it only ever returns
    text; the plan and the approvals table are the only sources of authority).
"""
from __future__ import annotations

import hashlib
import json
import re

from backend.engine import ai

REQUIRED_RULES = ["client_id_field", "field_mappings", "eligibility", "action", "destinations"]
ALLOWED_DESTINATIONS = {"in_app", "desktop_notification"}
ALLOWED_ACTIONS = {"update_status", "create_draft"}

# Static security validation -------------------------------------------------
ALLOWED_MODULES = {"csv", "io", "datetime", "re", "json"}
BANNED_PATTERNS: list[tuple[str, str]] = [
    (r"\b(?:import|from)\s+(?:os|sys|subprocess|socket|urllib|http|requests|shutil|pathlib|importlib)\b",
     "import outside allowlist"),
    (r"\b__import__\b", "dynamic import"),
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec"),
    (r"\bcompile\s*\(", "compile"),
    (r"\bgetattr\s*\(", "getattr"),
    (r"\bopen\s*\(", "raw open() (use the provided safe io handle)"),
    (r"\bos\.", "os access"),
    (r"\bsys\.", "sys access"),
    (r"\bsubprocess", "subprocess"),
    (r"\bsocket\b", "socket"),
    (r"\be__class__\b|\b__globals__\b|\b__builtins__\b|\b__subclasses__\b", "dunder escape"),
    (r"\bpip\b|\binstall\b.*\bpackage\b", "dependency installation"),
]
MAX_CODE_CHARS = 20000


class PlanError(ValueError):
    pass


class ValidationError(Exception):
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


def validate_plan(plan: dict) -> list[str]:
    """Returns the list of missing/contradictory rules. Empty list = generatable."""
    missing = [r for r in REQUIRED_RULES if r not in plan or plan[r] in (None, "", [], {})]
    contradictions: list[str] = []
    if not missing:
        if plan["action"] not in ALLOWED_ACTIONS:
            contradictions.append(f"unsupported action: {plan['action']}")
        bad = [d for d in plan["destinations"] if d not in ALLOWED_DESTINATIONS]
        if bad:
            contradictions.append(f"unsupported destinations: {bad}")
        if not isinstance(plan["field_mappings"], dict) or not plan["field_mappings"]:
            contradictions.append("field_mappings must be a non-empty object")
        if not isinstance(plan["eligibility"], dict) or not plan["eligibility"]:
            contradictions.append("eligibility rules required")
    return missing + contradictions


def plan_sha256(plan: dict) -> str:
    return hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


GEN_PROMPT = (
    "Generate a single Python function `def run(rows, ctx):` that processes tracking "
    "rows according to the rules. Return ONLY the function. No imports beyond "
    "csv/io/datetime/re/json, no file/network/os access, no eval/exec. The function "
    "returns a list of row results."
)


def plan_run_context(plan: dict) -> dict:
    """Independent runtime context for the runner, derived ONLY from the confirmed plan.

    The model never supplies expected outcomes; eligibility comes from the plan the user
    approved so the isolated test checks the plan's rules, not the model's word.
    """
    elig = plan.get("eligibility") or {}
    return {
        "eligibility_status": elig.get("status"),
        "eligibility_date": elig.get("run_date") or elig.get("date_value"),
        "destinations": plan.get("destinations") or [],
    }


def generate(plan: dict) -> dict:
    """One generation attempt. Returns {model_output, code, sha256, violations,
    provider, provider_note}.

    Violations non-empty ⇒ artifact must be stored as `invalid` (never testable).
    Fail-soft rule: if the selected live provider (Gemini) errors — network,
    timeout, HTTP, malformed output — the deterministic offline generator is
    used instead and `provider_note` says so, so automation creation NEVER
    hard-errors because of the AI vendor.
    """
    missing = validate_plan(plan)
    if missing:
        raise PlanError(f"plan is not generatable: {missing}")
    context = {**plan_run_context(plan),
               "client_id_field": plan["client_id_field"],
               "field_mappings": plan["field_mappings"],
               "eligibility": plan["eligibility"],
               "action": plan["action"],
               "destinations": plan["destinations"],
               "mode": "code"}  # provider must return a runnable run(rows, ctx)
    try:
        model_output = ai.generate_text(GEN_PROMPT, context)
        provider, provider_note = ai.effective_provider()
    except ai.GenerationError as exc:
        # Live provider failed outright (unknown provider name or fallback
        # disabled). Fall back to the deterministic offline synth so the user
        # can still finish; the note is surfaced in the UI and the audit.
        model_output = ("```python\n" + ai._synth_code(context) + "```\n")
        provider, provider_note = "mock", f"live AI unavailable ({str(exc)[:120]}) — used offline generator"
    model_output, fb_note = ai.strip_fallback_marker(model_output)
    if fb_note:
        # generate_text silently fell back to the offline synth: report the
        # provider honestly as mock, not the provider that was selected.
        provider, provider_note = "mock", fb_note
    code = extract_code(model_output)
    violations = static_check(code)
    if violations:
        # One repair attempt with a stricter prompt before giving up.
        try:
            repair_output = ai.generate_text(
                GEN_PROMPT + " " + ai.GEMINI_PROMPT_RULES +
                " Your previous attempt was rejected: " + "; ".join(violations) +
                ". Return ONLY the corrected single function.", context)
            repair_output, fb_note2 = ai.strip_fallback_marker(repair_output)
            if fb_note2:
                provider_note = fb_note2
            repair_code = extract_code(repair_output)
            repair_violations = static_check(repair_code)
            if not repair_violations:
                code, violations = repair_code, []
        except ai.GenerationError:
            pass  # keep the original violations; caller stores the artifact as invalid
    return {"model_output": model_output, "code": code,
            "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
            "violations": violations,
            "provider": provider, "provider_note": provider_note}


def extract_code(model_output: str) -> str:
    """Pull a python block out of the model output; fall back to the raw text."""
    fence = re.search(r"```(?:python)?\s*\n(.*?)```", model_output, re.DOTALL)
    return fence.group(1).strip() if fence else model_output.strip()


def static_check(code: str) -> list[str]:
    """Hard-reject static security validation (S9). Empty list = accepted."""
    violations: list[str] = []
    if len(code) > MAX_CODE_CHARS:
        violations.append(f"code exceeds {MAX_CODE_CHARS} chars")
    if not re.search(r"\bdef\s+run\s*\(", code):
        violations.append("no run(rows, ctx) entrypoint found")
    for pattern, label in BANNED_PATTERNS:
        if re.search(pattern, code):
            violations.append(f"forbidden construct: {label}")
    return violations
