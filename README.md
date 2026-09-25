# AutoStack IN

Local-first business-automation platform for Indian SMEs: describe an office workflow in
plain English, review an AI-drafted plan, test the generated automation against real
fixture data in an isolated sandbox, approve it, and run it on a schedule, on a file
change, or from an inbound webhook — with a tamper-evident audit trail and role-based
access control throughout.

This repository is a working spike (SIH 2026) with a production-shaped architecture:

| Component          | Tech                          | Address                    |
|--------------------|-------------------------------|----------------------------|
| Worker (API, auth, runs, governance) | FastAPI + SQLAlchemy 2 | `http://127.0.0.1:8747` |
| Automation runtime | Node-RED 4.1.1 (embedded)     | `http://127.0.0.1:18790`   |
| UI                 | React 19 + Vite 8             | `http://127.0.0.1:5173`    |
| Database           | SQLite (WAL, FKs on)          | `artifacts/spike/spike.db` |

Everything binds to loopback (`127.0.0.1`) only and every route except `/api/health`,
`/auth/*` and webhooks requires a bearer token.

---

## How it works

```
Browser (React, :5173)
   │  fetch + SSE-style poll, bearer token
   ▼
Worker (FastAPI, :8747) ──► SQLite (workflows, runs, events, audit hash-chain)
   │  plan → generate → sandbox test → approve → run
   ▼
Node-RED (embedded, :18790)
   │  compiled flow calls back per step
   ▼
Worker step endpoints (read-due / update-row / draft-create / notify → run complete)
```

1. **Capture** — file watchers or manual staging turn CSV drops into `Event`s
   (`source="saved_file_comparison"`, actions `row.added` / `row.removed` / `row.updated`,
   redacted `record_key` like `clients:ID`).
2. **Plan** — an AI adapter (mock, or Gemini when `AUTOSTACK_AI_PROVIDER=gemini` +
   `AUTOSTACK_GEMINI_API_KEY` are set) turns the event into a structured plan
   (`field_mappings`, `eligibility`, `action`, `destinations`). Plans are reviewed by a
   human before any code exists.
3. **Generate** — the plan compiles to a small Python module (`run(rows, ctx)`) that is
   statically validated (module allowlist, banned constructs, size cap) before it is
   ever executed.
4. **Test** — the artifact runs in a hardened sandbox: a fresh Python subprocess with a
   startup guard that hard-blocks sockets and strips `open`/`exec`/`eval`/`compile` from
   the generated code's builtins, POSIX rlimits (CPU/AS/NPROC/FSIZE) and a wall-clock
   kill. Reports carry a `sha256` content digest of policy + result.
5. **Approve** — activation needs an explicit approval referencing both the artifact and
   its passing test job. Published templates are versioned in a registry with consent
   gating and secret scanning; imports arrive as untrusted drafts.
6. **Run** — approved workflows execute through the real graph executor with per-node
   steps, idempotency, cancel/rollback/reconcile, and one hash-chained audit entry per
   action (SHA-256 linked; `GET /api/audit` verifies the chain).

---

## Quick start

Prerequisites: Python 3.11+ (a `.venv` is expected at the repo root), Node.js 18+.

```bash
# 1 — worker (auth token: env AUTOSTACK_TOKEN wins; otherwise the persisted
#     artifacts/spike/token is reused so restarts never 401 the stack)
.venv/Scripts/python.exe scripts/run_worker.py          # Windows Git Bash
# .venv/bin/python scripts/run_worker.py                # Linux/macOS

# 2 — embedded Node-RED runtime (needs the worker up first)
TOK=$(cat artifacts/spike/token)
node desktop/red-embed.js http://127.0.0.1:8747 "$TOK" desktop/spike-flow.json

# 3 — UI
cd frontend && npm install && npm run dev               # http://127.0.0.1:5173
```

Open `http://127.0.0.1:5173`, register the first user (it becomes the org **owner/admin**),
then use **Discovery** → **Create Automation** to go from an event to a tested, approved
workflow.

### Smoke-test the whole stack

```bash
TOK=$(cat artifacts/spike/token)
AUTOSTACK_TOKEN="$TOK" .venv/Scripts/python.exe scripts/qa_probe.py   # 57 checks
.venv/Scripts/python.exe -m pytest tests/ -q                          # 120 tests + 29 subtests
```

---

## Environment variables

| Variable                   | Default                  | Purpose                                                        |
|----------------------------|--------------------------|----------------------------------------------------------------|
| `AUTOSTACK_TOKEN`          | persisted token file     | Service bearer token for the worker API. Env wins; otherwise `artifacts/spike/token` is loaded or created (mode `0600`, gitignored). |
| `AUTOSTACK_AI_PROVIDER`    | `mock`                   | `mock` (deterministic, offline) or `gemini`.                    |
| `AUTOSTACK_GEMINI_API_KEY` | unset                    | Required when the provider is `gemini`; without a key the adapter fails closed with `GenerationError`. |

The AI key is read at request time and is never written to the database or logs.
`artifacts/` (database, token, Node-RED user dir, logs) is fully gitignored.

## Commands

| Command                                              | What it does                                   |
|------------------------------------------------------|------------------------------------------------|
| `.venv/Scripts/python.exe scripts/run_worker.py`     | Start worker + in-process trigger loop (`:8747`) |
| `node desktop/red-embed.js <workerUrl> <token> <flow>` | Embed Node-RED, deploy flow (`:18790`)       |
| `node desktop/main.js` (or `npm run desktop` in `desktop/`) | Electron shell                          |
| `cd frontend && npm run dev`                         | Vite dev server (`:5173`)                      |
| `cd frontend && npm run build`                       | Production UI bundle                           |
| `.venv/Scripts/python.exe -m pytest tests/ -q`       | Full test suite (isolated throwaway DBs)       |
| `AUTOSTACK_TOKEN=… .venv/Scripts/python.exe scripts/qa_probe.py` | 57-check live-stack probe          |
| `.venv/Scripts/python.exe scripts/measure_budgets.py`| Performance budget measurements                |

Tests never touch the dev database: `tests/spike/conftest.py` swaps in a throwaway SQLite
engine per test (module), so the dev DB row counts are identical before and after a run.

---

## Using the app

The UI is a hash-routed shell (`#/dashboard` is the default). Groups map to the lifecycle:

- **Work** — `Dashboard` (live run/event/heartbeat status), `Discovery` (detected
  candidates from events), `Create Automation` (plan → generate → sandbox test → approve
  stepper, backend-gated at each step), `Workflows` (list, runs, parameter schemas,
  delete), `Notifications` (in-app feed with read/read-all).
- **Trust** — `Registry` (versioned template publish/import/withdraw with consent +
  secret scan), `Trust Log` (hash-chained audit with chain verification and SIEM-style
  export), `Data & Privacy` (processing ledger, retention windows in whole days,
  subject export).
- **Operate** — `Connectors`, `Scheduling` (per-workflow triggers with enable/disable and
  a manual **tick**), `Runners` (pairing/confirm/revoke lifecycle).
- **Account** — `Home`, `Teams` (members, invitations, role changes), `Profile`
  (`/auth/me`, API tokens with create/revoke), `Settings`.

### Roles

Four org roles gate every mutating route: **observer** (read-only) < **operator** (run /
stage / create workflows) < **approver** (test / activate / publish) < **owner** (admin:
tier, members, delete, triggers). Service tokens (the worker token) pass at owner level;
user tokens are resolved through team membership. First registered local user becomes
owner. Concretely: an observer gets `403` on `POST /api/workflows` or `/api/runs`; only
an owner can `DELETE /api/workflows/{id}` or change the org tier.

### Running a workflow three ways

- **Run now** — from Workflows or via `POST /api/runs` with a `workflow_id`.
- **Schedule / file triggers** — enable a trigger (Scheduling page or `POST /api/triggers`)
  and either wait for the 30 s in-process loop (started by `scripts/run_worker.py`) or
  force a pass with `POST /api/triggers/tick`. Schedule triggers store `time_of_day`
  (`HH:MM` UTC), optional `days_of_week`, and a once-per-day `last_fired_utc` stamp;
  file triggers fire when a watcher event matches alias + action (+ optional
  `record_key_prefix`).
- **Webhook** — `POST /api/webhook/{trigger_id}` with header `X-AutoStack-Secret`.
  Rate-limited (60 s window), audited, and the response reports the **final** run status
  (`passed`/`failed`) — the run really executes, it is never left dangling.

---

## API surface (essentials)

All responses JSON; all errors are `{"detail": {"error": …}}`. Auth:
`Authorization: Bearer <token>` (service token or user token from `POST /auth/tokens`).

| Area | Endpoints |
|------|-----------|
| Auth | `POST /auth/register`, `POST /auth/login`, `POST/GET /auth/tokens`, `POST /auth/tokens/{id}/revoke`, `GET /auth/me`, `GET /me/capabilities` |
| Health | `GET /api/health`, `POST /api/ping` |
| Events | `POST /api/events`, `GET /api/candidates`, `POST /api/capture/poll`, `POST /api/candidates/{id}/dismiss` |
| Plans / artifacts | `POST /api/plans`, `POST /api/artifacts/generate`, `POST /api/test-jobs`, `POST /api/approvals/activation`, `POST /api/plan/{id}/create-workflow` |
| Workflows | `GET/POST /api/workflows`, `GET /api/workflows/{id}`, `DELETE /api/workflows/{id}` (soft delete; owner-only; in-flight runs → 409), `POST /api/workflows/{id}/parameters` |
| Runs | `POST /api/runs`, `GET /api/runs/list`, `GET /api/runs/{id}`, `POST …/cancel|rollback|complete`, `POST /api/runs/reconcile`, `POST /api/runs/bridge-start`, `GET /api/runs/{id}/nodes|gates` |
| Node callbacks | `POST /api/nodes/read-due|update-row|draft-create|notify` |
| Triggers | `GET/POST /api/triggers`, `POST /api/triggers/{id}/enable|disable`, `POST /api/triggers/tick`, `POST /api/webhook/{trigger_id}` |
| Compare | `POST /api/compare/run` |
| Governance | `GET /api/audit`, `GET /governance/audit-export`, `GET /governance/siem/stream`, `GET /governance/compliance-bundle`, `GET/POST /gates/{id}/decide` via `/gates/...` |
| Privacy | `GET /privacy/ledger`, `GET/POST /privacy/retention`, `POST /privacy/export` |
| Registry | `POST /api/registry/publish|import|withdraw`, `GET /api/registry/templates`, template review/signals, import run recording |
| Teams / org | `GET/POST /team/members`, role change/remove, invitations, `POST /org/tier`, `GET /org/sso`, `GET /runners` + runner pair/confirm/revoke |

### Example: end-to-end via curl

```bash
TOK=$(cat artifacts/spike/token)
H="Authorization: Bearer $TOK"
B=http://127.0.0.1:8747

# register + login a user (first user = owner)
curl -s -X POST $B/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"owner","password":"strong-pass-1","display_name":"Owner"}'

# stage an event and inspect candidates
curl -s -X POST $B/api/events -H "$H" -H 'Content-Type: application/json' \
  -d '{"source":"saved_file_comparison","action":"row.updated","resource":"clients",
       "record_key":"clients:C001"}'
curl -s "$B/api/candidates" -H "$H"

# plan → generate → sandbox-test → approve (see Create Automation UI for the payloads)
```

---

## Security model

- **Transport/binding** — loopback-only listeners; CORS restricted to the two local UI
  origins (`localhost:5173`, `localhost:4173`), no credentials, no wildcards.
- **Auth** — bearer tokens: persisted service token (0600 file, gitignored) and
  per-user API tokens (hashed at rest, create/revoke via API). Passwords: PBKDF2-HMAC,
  200 000 iterations, per-user salt; comparisons via `hmac.compare_digest`.
- **Authorization** — role model (observer/operator/approver/owner) enforced on every
  mutating route, including all legacy workflow/run routes; admin org actions are
  owner-only.
- **Sandbox** — generated code is statically validated (module allowlist, banned
  constructs, 20 KB cap) *and* executed in a fresh subprocess whose guard blocks sockets
  and strips `open`/`exec`/`eval`/`compile` from the generated code's builtins; POSIX
  rlimits + wall-clock timeout; results content-bound by SHA-256.
- **Webhooks** — secret header checked (constant-time compare) before any rate-limiter
  state is recorded, so unauthenticated probes cannot grow state; limiter map is capped
  with idle eviction.
- **Integrity** — every meaningful action appends to a SHA-256 hash-chained audit log
  with chain verification; SIEM stream + compliance bundle for export.
- **Secrets hygiene** — the tracked flow template (`desktop/spike-flow.json`) contains
  only `__WORKER_TOKEN__` placeholders; live credentials are injected at deploy time and
  persisted exclusively to the gitignored Node-RED user dir
  (`artifacts/spike/red-userdir/runtime-flow.json`). No secrets are committed.
- **Dependencies** — `npm audit`: 0 vulnerabilities; `pip-audit`: clean (tooling only).

## Data handling

SQLite in WAL mode with foreign keys ON, single file at `artifacts/spike/spike.db`.
Deletion of a workflow is a **soft delete** (`deleted_at` timestamp): runs, versions and
audit history are retained; triggers are disabled; repeat deletes 404; deleting with
in-flight runs returns 409. Privacy surfaces: processing-purpose ledger, per-category
retention windows (integer days, validated), and subject data export. Backups are a file
copy of `artifacts/spike/` while the worker is stopped (WAL checkpoint on clean exit).

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| UI stuck on "Connecting to worker…" | Worker not running, or token mismatch. Start the worker (`scripts/run_worker.py`); `curl -H "Authorization: Bearer $(cat artifacts/spike/token)" http://127.0.0.1:8747/api/workflows` must return 200. |
| `401 {"detail":{"error":"unauthorized"}}` everywhere | `AUTOSTACK_TOKEN` env differs from the persisted file. Run the worker without the env var, or export the file's value. |
| Node-RED: `SELF_PROBE` fails or flows not deployed | Worker must already listen on `:8747` before `red-embed.js` starts. Check `artifacts/spike/red.log`. |
| Port already in use (`8747`/`18790`/`5173`) | A previous instance is alive: `netstat -ano | findstr :8747` then `taskkill //F //PID <pid>`. |
| `no such column: workflows.deleted_at` | One-time migration for pre-existing dev DBs: `sqlite3 artifacts/spike/spike.db "ALTER TABLE workflows ADD COLUMN deleted_at DATETIME"`. Fresh databases are created correctly by `create_all`. |
| Trigger didn't fire | Triggers must be enabled, the workflow non-deleted, and the loop running (only `scripts/run_worker.py` starts it). Force one pass: `POST /api/triggers/tick`. |
| AI generation errors | Without `AUTOSTACK_GEMINI_API_KEY`, provider `gemini` fails closed by design. Use the default `mock` provider for offline work. |
| Sandbox job `failed` with `NoneType object is not callable` | The generated code tried a blocked builtin (`socket`/`open`/`exec`…). This is the guard working; fix the code, or check `static_check` violations on the artifact. |
| Tests "pollute" the dev DB | They don't — `tests/spike/conftest.py` isolates every test in a throwaway DB. Verify: workflow count is unchanged after `pytest`. |

## Repository layout

```
backend/           FastAPI worker (app.py, roadmap_routes.py, engine/, security/, teams, models, db)
frontend/          React 19 + Vite UI (src/main.jsx shell, page modules, shared primitives)
desktop/           Node-RED embed (red-embed.js) + Electron shell (main.js)
scripts/           run_worker.py, qa_probe.py (57 checks), measure_budgets.py
tests/spike/       120 pytest tests + 29 subtests; isolated-DB conftest
docs/              test report & fix plan, spike evidence, product roadmap
artifacts/spike/   runtime state: spike.db, token, red-userdir, logs (gitignored)
```

## Status

- **Tests**: 120 passed + 29 subtests (throwaway-DB isolated; zero dev-DB pollution).
- **Live probe**: 57/57 checks against a running stack (worker + Node-RED + UI).
- **Known limitations (by spike design)**: loopback-only single-machine deployment,
  SQLite storage, mock AI provider by default, Electron shell optional.
- Roadmap and evidence: `docs/product-roadmap.md`, `docs/spike-evidence.md`,
  `docs/test-report-and-fix-plan.md`.
