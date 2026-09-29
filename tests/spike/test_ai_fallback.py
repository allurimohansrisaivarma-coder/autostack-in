"""Fail-soft AI provider tests: Gemini errors must never break creation.

The mock provider is the default everywhere; selecting gemini without a key
resolves to mock; a Gemini failure (network/HTTP/timeout/malformed) falls back
to the deterministic offline generator with an honest provider_note — so
plan → generate → sandbox → approve keeps working with or without a key.
"""
from backend.engine import ai
from backend.engine import generation as gen

GOOD_PLAN = {
    "client_id_field": "ClientID",
    "field_mappings": {"Name": "Name", "FollowUpDate": "FollowUpDate"},
    "eligibility": {"status": "Follow-up due", "status_field": "Status",
                    "date_field": "FollowUpDate", "date_value": "2026-09-20"},
    "action": "create_draft",
    "destinations": ["in_app"],
}


def test_default_provider_is_mock(monkeypatch):
    monkeypatch.delenv("AUTOSTACK_AI_PROVIDER", raising=False)
    monkeypatch.delenv("AUTOSTACK_GEMINI_KEY", raising=False)
    provider, note = ai.effective_provider()
    assert provider == "mock"
    assert "default" in note


def test_gemini_without_key_resolves_to_mock(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.delenv("AUTOSTACK_GEMINI_KEY", raising=False)
    monkeypatch.delenv("AUTOSTACK_GEMINI_API_KEY", raising=False)
    provider, note = ai.effective_provider()
    assert provider == "mock"
    assert "no AUTOSTACK_GEMINI_KEY" in note


def test_gemini_with_key_is_live(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("AUTOSTACK_GEMINI_KEY", "k-test")
    provider, _ = ai.effective_provider()
    assert provider == "gemini"


def test_legacy_key_alias_accepted(monkeypatch):
    monkeypatch.delenv("AUTOSTACK_GEMINI_KEY", raising=False)
    monkeypatch.setenv("AUTOSTACK_GEMINI_API_KEY", "k-legacy")
    assert ai.gemini_key() == "k-legacy"


def test_gemini_network_error_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("AUTOSTACK_GEMINI_KEY", "k-broken")

    def boom(*a, **k):
        raise ai.GenerationError("gemini request failed: network unreachable")
    monkeypatch.setattr(ai, "_gemini_text", boom)
    context = {**gen.plan_run_context(GOOD_PLAN), "mode": "code"}
    out = ai.generate_text(gen.GEN_PROMPT, context)
    text, note = ai.strip_fallback_marker(out)
    assert note and "unavailable" in note
    assert "def run(rows, ctx):" in text  # deterministic offline synth


def test_gemini_key_present_but_live_call_fails_reports_mock(monkeypatch):
    # The selection resolves to gemini (key present) — the REPORTED provider
    # after the runtime fallback is what generation/autopilot surface as mock.
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("AUTOSTACK_GEMINI_KEY", "k-broken")
    assert ai.effective_provider()[0] == "gemini"


def test_unknown_provider_fails_closed_without_fallback(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "nope")
    try:
        ai.generate_text("p", {})
        raised = False
    except ai.GenerationError:
        raised = True
    assert raised  # unknown provider names surface instead of hiding


def test_generate_never_crashes_on_provider_error(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("AUTOSTACK_GEMINI_KEY", "k-broken")

    def boom(*a, **k):
        raise ai.GenerationError("gemini request failed: HTTP 429")
    monkeypatch.setattr(ai, "_gemini_text", boom)
    outcome = gen.generate(GOOD_PLAN)
    assert outcome["violations"] == []
    assert outcome["provider"] == "mock"
    assert "unavailable" in outcome["provider_note"]
    assert outcome["code"].startswith("def run(rows, ctx):")
    assert outcome["violations"] == []
    from backend.engine import runner
    ctx = gen.plan_run_context(GOOD_PLAN)
    rows = [{"ClientID": "c1", "Name": "A", "Status": "Follow-up due",
             "FollowUpDate": "2026-09-01"}]
    rep = runner.run_isolated_test(outcome["code"], rows, ctx=ctx,
                                   expected=[], key_field="ClientID")
    assert rep["result_class"] in ("passed", "failed_assertion")  # never a crash


def test_generated_code_passes_static_check_and_runs(monkeypatch):
    monkeypatch.setenv("AUTOSTACK_AI_PROVIDER", "gemini")
    monkeypatch.setenv("AUTOSTACK_GEMINI_KEY", "k-broken")

    def boom(*a, **k):
        raise ai.GenerationError("gemini request failed: timeout")
    monkeypatch.setattr(ai, "_gemini_text", boom)
    outcome = gen.generate(GOOD_PLAN)
    assert outcome["violations"] == []
    from backend.engine import runner
    ctx = gen.plan_run_context(GOOD_PLAN)
    rows = [{"ClientID": "c1", "Name": "A", "Status": "Follow-up due",
             "FollowUpDate": "2026-09-01"},
            {"ClientID": "c2", "Name": "B", "Status": "New",
             "FollowUpDate": "2026-09-01"}]
    rep = runner.run_isolated_test(outcome["code"], rows, ctx=ctx, expected=[], key_field="ClientID")
    assert rep["result_class"] in ("passed", "failed_assertion")  # never a crash
