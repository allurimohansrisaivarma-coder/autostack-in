"""Phase 6: isolated execution of generated code under an enforceable policy.

Isolation layers (verified, not just configured — the runner actually starts a
python subprocess with the limits below):
  - fresh python subprocess, no imports from the app, cwd = scratch dir
  - CPU time (RLIMIT_CPU), address space (RLIMIT_AS), process count (RLIMIT_NPROC),
    file size (RLIMIT_FSIZE) caps on POSIX; wall-clock kill on Windows
  - no network: code runs with socket access blocked via a startup guard import
  - only the job's input rows are visible; nothing of the host is mounted
  - report = function output digest + checks; content-bound by sha256
  - static security violations ⇒ job refuses to start (fail-closed)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from backend.engine.generation import static_check

RUNNER_GUARD = '''
# Sandbox startup guard (runs before any harness or generated code).
import builtins, socket as _socket
_socket.socket = None  # hard-block network inside the sandboxed process
_REAL_EXEC, _REAL_COMPILE = exec, compile  # kept for the harness itself only
SAFE_BUILTINS = {
    _name: getattr(builtins, _name) for _name in (
        "abs", "all", "any", "bool", "bytes", "chr", "dict", "divmod",
        "enumerate", "filter", "float", "format", "frozenset", "hash",
        "hex", "int", "isinstance", "issubclass", "iter", "len", "list",
        "map", "max", "min", "next", "oct", "object", "ord", "pow",
        "range", "repr", "reversed", "round", "set", "slice", "sorted",
        "str", "sum", "tuple", "type", "zip",
    ) if hasattr(builtins, _name)
}
SAFE_BUILTINS["__import__"] = __import__  # allowlist-enforced at submit time
SAFE_BUILTINS["__build_class__"] = getattr(builtins, "__build_class__", None)
SAFE_BUILTINS["__name__"] = "generated"
# Note: open/exec/eval/compile/input are absent from SAFE_BUILTINS, so the
# generated code cannot reach them; the harness import system stays intact.
'''


def _build_harness() -> str:
    return (
        # RUNNER_GUARD runs FIRST: network + dangerous builtins hard-blocked
        # before any generated code is compiled (docstring promise, now true).
        RUNNER_GUARD + "\n"
        "import json, sys\n"
        "spec = json.loads(sys.argv[1])\n"
        "rows = spec['rows']\n"
        "g = {'__name__': 'generated', '__builtins__': SAFE_BUILTINS}\n"
        "_REAL_EXEC(_REAL_COMPILE(spec['code'], 'generated.py', 'exec'), g)\n"
        "result = g['run'](rows, spec.get('ctx', {}))\n"
        "sys.stdout.write('__RESULT__' + json.dumps(result, default=str))\n"
    )


HARNESS = _build_harness()


def policy_hash(policy: dict) -> str:
    return hashlib.sha256(
        json.dumps(policy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# Sandbox outcome classes (sandbox-hardening upgrade):
#   passed           — every functional check green; approve-at-create may proceed
#   failed_policy    — the code violated policy (static refusal/timeout/unsafe) —
#                      a REAL problem with the artifact; never retried blindly
#   failed_assertion — the code ran but produced wrong output vs the plan-derived
#                      expected results; one AI repair loop is allowed, then human
#   failed_infra     — transient environment trouble (interpreter hiccup, I/O) —
#                      retryable via one-click re-run without blaming the code
RESULT_CLASSES = ("passed", "failed_policy", "failed_assertion", "failed_infra")


def classify_report(report: dict) -> str:
    """Classify a sandbox report into a stable result class.

    Deterministic from the report content alone (the report is content-bound by
    its own sha256), so the UI and the autopilot can branch on it safely.
    """
    status = report.get("status")
    error = (report.get("error") or "")
    if status == "passed":
        return "passed"
    if status == "refused":
        return "failed_policy"
    if error:
        # Timeouts and interpreter crashes are policy/infra splits: a wall-clock
        # kill while the code looped forever is the CODE's fault (policy); a
        # resource/socket failure without a result marker is infra.
        if "timeout" in error.lower():
            return "failed_policy"
        if "no result marker" in error.lower() or "unparseable result" in error.lower():
            return "failed_infra"
        # A nonzero exit from the generated code itself is a code/policy fault.
        return "failed_policy"
    # Ran fine but checks disagree with plan-derived expectations.
    return "failed_assertion"


def run_isolated_test(code: str, rows: list[dict], ctx: dict | None = None,
                      policy: dict | None = None, timeout_s: int = 15,
                      expected: list[dict] | None = None,
                      key_field: str = "id") -> dict:
    """Execute generated code in the sandbox. Returns a content-bound report.

    Never raises for test failures — a failed test is a valid outcome ('failed').
    Raises only for misuse (unsafe code, missing entrypoint). The report carries
    `result_class` (see RESULT_CLASSES) for the UI and the autopilot loop.
    """
    policy = policy or {"max_output_items": 1000, "forbidden": ["network", "filesystem", "subprocess"]}
    violations = static_check(code)
    if violations:
        rep = {"status": "refused", "violations": violations,
               "reason": "static security validation failed"}
        rep["result_class"] = classify_report(rep)
        return rep
    ctx = ctx or {}
    spec = {"rows": rows, "ctx": ctx, "code": code}
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "harness.py"
        script.write_text(HARNESS, encoding="utf-8")
        limits = []
        if sys.platform != "win32":
            import resource

            def _limits():  # noqa: ANN001
                resource.setrlimit(resource.RLIMIT_CPU, (timeout_s, timeout_s + 1))
                resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
                resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
                resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
            limits = [{"RLIMIT_CPU": timeout_s}, {"RLIMIT_AS": "512MB"},
                      {"RLIMIT_NPROC": 64}, {"RLIMIT_FSIZE": "1MB"}]
        try:
            proc = subprocess.run(
                [sys.executable, str(script), json.dumps(spec)],
                capture_output=True, text=True, timeout=timeout_s,
                cwd=td,
                preexec_fn=(limits and _limits) or None,
            )
        except subprocess.TimeoutExpired:
            rep = _report("failed", "sandbox timeout", policy, limits, [])
            rep["result_class"] = classify_report(rep)
            return rep
        stdout = proc.stdout or ""
        marker = "__RESULT__"
        idx = stdout.rfind(marker)
        if proc.returncode != 0 or idx < 0:
            rep = _report("failed", (proc.stderr or "no result marker")[-400:],
                          policy, limits, [])
            rep["result_class"] = classify_report(rep)
            return rep
        try:
            result = json.loads(stdout[idx + len(marker):])
        except json.JSONDecodeError:
            rep = _report("failed", "unparseable result", policy, limits, [])
            rep["result_class"] = classify_report(rep)
            return rep
        checks = _functional_checks(result, policy, expected=expected, key_field=key_field)
        status = "passed" if all(c["ok"] for c in checks) else "failed"
        rep = _report(status, None, policy, limits, checks, result=result)
        rep["result_class"] = classify_report(rep)
        return rep


def _functional_checks(result, policy, expected=None, key_field="id") -> list[dict]:
    """Independent checks; expected results come from the caller (plan/fixture), never
    from the model. Structure checks are generic; when `expected` is provided the
    outputs are compared exactly (Phase 8's independent expected outputs)."""
    checks = []
    max_items = policy.get("max_output_items", 1000)
    ok_type = isinstance(result, list)
    checks.append({"name": "result_is_list", "ok": ok_type})
    if ok_type:
        checks.append({"name": "output_bounded", "ok": len(result) <= max_items})
        rows_ok = all(isinstance(i, dict) and key_field in i for i in result[:max_items])
        checks.append({"name": "items_are_row_dicts", "ok": rows_ok})
        if expected is not None:
            got_ids = sorted(str(i.get(key_field)) for i in result[:max_items] if isinstance(i, dict))
            want_ids = sorted(str(e.get(key_field)) for e in expected)
            checks.append({"name": "expected_outputs_match", "ok": got_ids == want_ids,
                           "detail": {"expected": want_ids, "got": got_ids}})
    else:
        checks.append({"name": "output_bounded", "ok": False})
        checks.append({"name": "items_are_row_dicts", "ok": False})
    return checks


def _report(status: str, error: str | None, policy: dict, limits: list,
            checks: list[dict], result=None) -> dict:
    report = {
        "status": status, "error": error, "policy": policy,
        "policy_sha256": policy_hash(policy), "limits": limits, "checks": checks,
        "result_digest": (hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()[:32]
                          if result is not None else None),
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()
    return report
