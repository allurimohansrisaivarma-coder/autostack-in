# AutoStack IN

Local-first business-automation platform for Indian SMEs: describe an office workflow in
plain English, review an AI-drafted plan, test the generated automation against real
fixture data in an isolated sandbox, approve it, and run it on a schedule, on a file
change, or from an inbound webhook — with a tamper-evident audit trail and role-based
access control throughout.

**The problem:** repetitive office work (follow-ups, PO matching, filing reminders) is
tracked in spreadsheets and done by hand. Cloud automation tools can't see local files
and don't fit Indian SME compliance workflows.

**The solution:** a local worker that watches your files, drafts automations from real
observed patterns, proves them safe in a sandbox before activation, and executes them
with exactly-once guarantees — all on your machine.

---

## Documentation

| Getting started | |
|---|---|
| [Quick start](#quick-start) | Run the whole stack in three commands |
| [Environment variables](#environment-variables) | Token + AI provider configuration |
| [Commands](#commands) | Every script and what it does |

| Architecture & features | |
|---|---|
| [How it works](#how-it-works) | Component diagram + the lifecycle of an automation |
| [Using the app](#using-the-app) | Page-by-page guide, roles, trigger types |
| [API surface](#api-surface-essentials) | Endpoint tables + curl walkthrough |
| [UI theme system](#ui-theme-system) | Dark / light / system behavior |

| Verification & development | |
|---|---|
| [Testing](#testing) | Unit, integration, live battery, budgets |
| [Security model](#security-model) | Auth, sandbox, audit chain, secrets hygiene |
| [Troubleshooting](#troubleshooting) | Symptom → fix table |

| Repository documents | |
|---|---|
| [`docs/contracts.md`](docs/contracts.md) | Event/plan/artifact contract notes (Phase 1) |
| [`docs/phase-1.md`](docs/phase-1.md) · [`docs/phase-1-status.md`](docs/phase-1-status.md) | Stage-0 spike plan and closure status |
| [`docs/spike-evidence.md`](docs/spike-evidence.md) | Spike-by-spike verdicts with evidence |
| [`docs/platform-matrix.md`](docs/platform-matrix.md) | Measured OS/runtime feature matrix |
| [`docs/product-roadmap.md`](docs/product-roadmap.md) | Planned, additive roadmap work |
| [`docs/test-report-and-fix-plan.md`](docs/test-report-and-fix-plan.md) | QA rounds 1–6: every bug found, root cause, fix |
| [`docs/budgets.json`](docs/budgets.json) | Measured performance budgets (machine-local) |

---

## How it works

```
Browser (React, :5173)
   │  fetch + live poll, bearer token
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
   the generated code's builtins, POSIX rlimits and a wall-clock kill. Reports carry a
   `sha256` content digest of policy + result.
5. **Approve** — activation needs an explicit approval referencing both the artifact and
   its passing test job. Published templates are versioned in a registry with consent
   gating and secret scanning; imports arrive as untrusted drafts.
6. **Run** — approved workflows execute through the real graph executor with per-node
   steps, idempotency, cancel/rollback/reconcile, and one hash-chained audit entry per
   action (SHA-256 linked; `GET /api/audit?verify=1` verifies the chain).

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
AUTOSTACK_TOKEN="$TOK" .venv/Scripts/python.exe scripts/qa_probe.py          # 57 checks
AUTOSTACK_TOKEN="$TOK" .venv/Scripts/python.exe scripts/scenario_battery.py  # 31 checks
.venv/Scripts/python.exe -m pytest tests/ -q                                 # 132 tests + 29 subtests
```

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
| `npm run desktop` (in `desktop/`)                    | Electron shell (worker + Node-RED + UI)        |
| `cd frontend && npm run dev`                         | Vite dev server (`:5173`)                      |
| `cd frontend && npm run build`                       | Production UI bundle                           |
| `.venv/Scripts/python.exe -m pytest tests/ -q`       | Full test suite (isolated throwaway DBs)       |
| `AUTOSTACK_TOKEN=… .venv/Scripts/python.exe scripts/qa_probe.py` | 57-check live-stack probe          |
| `AUTOSTACK_TOKEN=… .venv/Scripts/python.exe scripts/scenario_battery.py` | 31-check live behavioral battery (failure paths, concurrency, triggers, RBAC; self-cleaning) |
| `AUTOSTACK_TOKEN=… .venv/Scripts/python.exe scripts/authz_matrix.py` | 147-check live authorization matrix: one real account per role drives every protected endpoint; escalation/IDOR/token-lifecycle checks |
| `AUTOSTACK_TOKEN=… .venv/Scripts/python.exe scripts/cleanup_dev_junk.py [--apply]` | Soft-delete historical test-junk workflows (dry-run by default) |
| `.venv/Scripts/python.exe scripts/measure_budgets.py`| Performance budget measurements                |

Tests never touch the dev database: `tests/spike/conftest.py` swaps in a throwaway SQLite
engine per test (module), so the dev DB row counts are identical before and after a run.

---

## Using the app

The UI is a hash-routed shell (`#/dashboard` is the default; unknown links render a
recovery page) with light/dark/system theme. Anonymous visitors get a cinematic landing
page (scroll-expansion hero, container-scroll product reveal, bento capability grid,
pipeline, trust chapter, structured footer) and a hero-split sign-in — authorization is
unchanged and still enforced server-side.

Navigation is a **floating top bar, not a sidebar**. On desktop it is a centered pill:
logo (click → landing homepage) · Product / Operate / Trust dropdowns (grouped panels
with icons and descriptions) · worker status dot · ⌘K search · notifications · account
menu.
At ≤860px the groups collapse into a hamburger that opens a grouped, accordion
navigation sheet (with focus trap, Escape, backdrop); the top bar carries only
burger · logo · account. Dropdowns close on outside click, Escape, and route change.
In-page navigation groups:

- **Product** (daily use) — `Dashboard` (live run/event/heartbeat status, honest "not
  measured" metrics), `Workflows` (list, runs, parameter schemas, delete),
  `Discovery` (detected candidates from real repeated patterns, evidence-only),
  `Create` (plan → generate → sandbox test → approve stepper, backend-gated at each step).
- **Operate** (workspace tooling) — `Scheduling` (per-workflow triggers with
  enable/disable and a manual **tick**), `Runners` (pairing/confirm/revoke lifecycle),
  `Connectors` (honest per-integration status).
- **Trust** (governance) — `Registry` (versioned template publish/import/withdraw with
  consent + secret scan), `Trust Log` (hash-chained audit with chain verification and
  SIEM-style export), `Data & Privacy` (processing ledger, retention windows in whole
  days, subject export). Notifications live in the top-bar bell, not the nav.

Personal and administrative screens live in the **account menu** (top right): Account
& tokens, Members & organization (owner only), Settings, an Appearance switch, and
Sign out. `Settings` (`#/settings`, sub-links like `#/settings/security`) is a
dedicated context (General / Profile / Appearance / Security, plus **Organization**
for owners: tier, retention, SSO, member links); the backend stays authoritative for
every administrative action, and non-owners see read-only state plus the requirement.

### Design system

Frontend motion is centrally gated (`frontend/src/motion.js`): level 0 static
(prefers-reduced-motion) → level 3 cinematic. Premium materials — glass navbar,
spotlight cards, ambient hero fields — live in `frontend/src/styles-premium.css`
with reusable primitives (`GlassSurface`, `PremiumCard`, `MagneticButton`,
`Reveal`, `ScrollText`, `ContainerScroll`, `BentoGrid`, `SpringPopover`,
`PageTransition`) in `frontend/src/premium.jsx`. The brand lockup (`brand.jsx`)
follows the theme — black-text metallic variant in light mode, white-text
metallic variant in dark mode — on every surface including the floating nav
(assets are full-opacity, filter-free PNGs regenerated by
`scripts/process_logos.py`).

### Roles

Four org roles gate every mutating route: **observer** (read-only) < **operator** (run /
stage / create workflows / manage triggers / drive bridge callbacks) < **approver**
(sandbox-test + activate automations) < **owner** (publish / withdraw from registry,
admin: tier, members, runners, delete workflows). Service tokens (the worker token)
pass at owner level; user tokens are resolved through team membership. First
registered local user becomes owner; subsequent registrations join as operator
(local-first self-serve design) — observers are granted deliberately by an owner.

Enforcement is server-side on every route (verified endpoint-by-endpoint with real
role accounts — `scripts/authz_matrix.py`): observers get `403` on all writes
including node callbacks and the trigger tick; operators cannot test/activate or
publish; approvers cannot publish or administer; only an owner can
`DELETE /api/workflows/{id}`, publish, or change the org tier. A soft-deleted workflow id can
never be reused (no silent resurrection). Token lifecycle: user tokens are issued
per-user, scoped to that user for revocation, and die immediately on revoke.

### Organization context: org types, departments, process types

Workflows (and processes) carry a classification context chosen in Create → Context:
**organization type** (corporate / government / individual / nonprofit / education),
**size** (small / medium / large; individuals are solo), **department** (per org
type — e.g. finance, revenue, licensing, personal), and **process type** (per
department — e.g. accounts_payable, tax_filing, license_renewal). The cascading
selectors in the create wizard are driven by `GET /api/org/catalog` (one source of
truth shared with the server-side validator), so incoherent combinations are
refused with a 422 both at bind time (`POST /api/plan/{id}/create-workflow`) and
when creating processes or setting the workspace profile (`/api/org/profile`,
owner-only). Classification shows on the workflow detail panel and free-text
"Other" process types are supported for contexts outside the catalog.

### Running a workflow three ways

- **Run now** — from Workflows or via `POST /api/runs` with a `workflow_id`.
- **Schedule / file triggers** — enable a trigger (Scheduling page or `POST /api/triggers`)
  and either wait for the 30 s in-process loop (started by `scripts/run_worker.py`) or
  force a pass with `POST /api/triggers/tick`. Trigger creation is evidence-gated by
  design (repeated observed patterns); schedule triggers store `time_of_day` (`HH:MM`
  UTC), optional `days_of_week`, and a once-per-day `last_fired_utc` stamp; file triggers
  fire when a watcher event matches alias + action (+ optional `record_key_prefix`).
- **Webhook** — `POST /api/webhook/{trigger_id}` with header `X-AutoStack-Secret`.
  Rate-limited (60 s window), audited, and the response reports the **final** run status
  (`passed`/`failed`) — the run really executes, it is never left dangling.

## API surface (essentials)

All responses JSON; errors are `{"detail": {"error": …}}`. Auth:
`Authorization: Bearer <token>` (service token or user token from `POST /api/auth/tokens`).

| Area | Endpoints |
|------|-----------|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `POST/GET /api/auth/tokens`, `POST /api/auth/tokens/{id}/revoke`, `GET /api/auth/me`, `GET /api/me/capabilities` |
| Health | `GET /api/health`, `POST /api/ping` |
| Events | `POST /api/events`, `GET /api/candidates`, `POST /api/capture/poll`, `POST /api/candidates/{id}/dismiss` |
| Plans / artifacts | `POST /api/plans`, `POST /api/artifacts/generate`, `POST /api/test-jobs`, `POST /api/approvals/activation`, `POST /api/plan/{id}/create-workflow` |
| Workflows | `GET/POST /api/workflows`, `GET /api/workflows/{id}`, `DELETE /api/workflows/{id}` (soft delete; owner-only; in-flight runs → 409), `POST /api/workflows/{id}/parameters` |
| Runs | `POST /api/runs`, `GET /api/runs/list`, `GET /api/runs/{id}`, `POST …/cancel\|rollback\|complete`, `POST /api/runs/reconcile`, `POST /api/runs/bridge-start`, `GET /api/runs/{id}/nodes\|gates` |
| Node callbacks | `POST /api/nodes/read-due\|update-row\|draft-create\|notify` |
| Triggers | `GET/POST /api/triggers`, `POST /api/triggers/{id}/enable\|disable`, `POST /api/triggers/tick`, `POST /api/webhook/{trigger_id}` |
| Compare | `POST /api/compare/run` |
| Governance | `GET /api/audit?verify=1`, `GET /api/governance/audit-export`, `GET /api/governance/siem/stream`, `GET /api/governance/compliance-bundle`, `POST /api/gates/{id}/decide` |
| Privacy | `GET /api/privacy/ledger`, `GET/POST /api/privacy/retention`, `POST /api/privacy/export` |
| Registry | `POST /api/registry/publish\|import\|withdraw`, `GET /api/registry/templates`, template review/signals, import run recording |
| Teams / org | `GET/POST /api/team/members`, role change/remove, invitations, `POST /api/org/tier`, `GET /api/org/sso`, `GET /api/runners` + runner pair/confirm/revoke |

### Example: end-to-end via curl

```bash
TOK=$(cat artifacts/spike/token)
H="Authorization: Bearer $TOK"
B=http://127.0.0.1:8747

# register a user (first user = owner) and mint a user token
curl -s -X POST $B/api/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"owner","password":"strong-pass-1","display_name":"Owner"}'

# stage an event and inspect candidates
curl -s -X POST $B/api/events -H "$H" -H 'Content-Type: application/json' \
  -d '{"source":"saved_file_comparison","action":"row.updated","resource":"clients",
       "record_key":"clients:C001"}'
curl -s "$B/api/candidates" -H "$H"

# plan → generate → sandbox-test → approve (the Create Automation UI shows the payloads)
```

## UI theme system

Three modes — **Light**, **Dark**, **System** (follows the OS and live-updates when the
OS theme changes) — switchable from the account menu (Appearance) and persisted across
sessions. All colors
come from CSS custom properties (design tokens) on `:root` / `[data-theme="dark"]`; the
choice is applied by an inline boot script before first paint, so there is no flash of the
wrong theme. Terminal/monitor surfaces are intentionally always-dark in both themes.
Focus-visible outlines, disabled states, and native form controls adapt per theme.

---

## Testing

| Suite | What it proves | Status |
|-------|----------------|--------|
| `pytest tests/` (132 tests + 29 subtests) | Full backend behavior on isolated throwaway DBs: lifecycle, RBAC, sandbox, triggers, registry, privacy, retention, hardening armor | **Passing** |
| `scripts/qa_probe.py` (57 checks) | The live stack end-to-end: worker + Node-RED + all feature surfaces | **Passing** |
| `scripts/scenario_battery.py` (31 checks) | Behavioral battery against the *running* server: happy path, idempotent rerun, failure path (HTTP 400 + `failed` run + failing node recorded), cancel semantics, invalid inputs, 6-way concurrent exactly-once, webhook auth/fire, schedule tick + once-per-day, RBAC edges, audit `verify=1`; self-cleaning | **Passing** |
| `scripts/measure_budgets.py` | Idle CPU, resident memory, capture-poll latency vs budgets in `docs/budgets.json` | **Within budget** |
| `npm run build` (frontend) | Production bundle builds clean | **Passing** |

## Security model

- **Transport/binding** — loopback-only listeners; CORS restricted to the two local UI
  origins (`localhost:5173`, `localhost:4173`), no credentials, no wildcards.
- **Auth** — bearer tokens: persisted service token (0600 file, gitignored) and
  per-user API tokens (hashed at rest, create/revoke via API). Passwords: PBKDF2-HMAC,
  200 000 iterations, per-user salt; comparisons via `hmac.compare_digest`. Login
  locks for 15 minutes after repeated failures.
- **Authorization** — role model (observer/operator/approver/owner) enforced on every
  mutating route, including all legacy workflow/run routes and the trigger tick; every
  read route that returns org data requires a token; admin org actions are owner-only.
- **Sandbox** — generated code is statically validated (module allowlist, banned
  constructs, 20 KB cap) *and* executed in a fresh subprocess whose guard blocks sockets
  and strips `open`/`exec`/`eval`/`compile` from the generated code's builtins; POSIX
  rlimits + wall-clock timeout; results content-bound by SHA-256.
- **Webhooks** — secret header checked (constant-time compare) before any rate-limiter
  state is recorded; limiter map capped with idle eviction; 1 MB request-body cap on
  every route.
- **Honest failures** — a run whose nodes fail from caller-caused data violations
  (missing column, unknown template, missing row) ends `failed` in the DB and returns
  HTTP 400 with `run_id` in the error detail — never a misleading 500, never a zombie.
- **Integrity** — every meaningful action appends to a SHA-256 hash-chained audit log
  with chain verification; SIEM stream + compliance bundle for export.
- **Secrets hygiene** — the tracked flow template (`desktop/spike-flow.json`) contains
  only `__WORKER_TOKEN__` placeholders; live credentials are injected at deploy time and
  persisted exclusively to the gitignored Node-RED user dir. No secrets are committed.

## Data handling

SQLite in WAL mode with foreign keys ON, single file at `artifacts/spike/spike.db`;
hot filter columns are indexed at startup (idempotent `CREATE INDEX IF NOT EXISTS`).
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
| Port already in use (`8747`/`18790`/`5173`) | A previous instance is alive: `netstat -ano \| findstr :8747` then `taskkill //F //PID <pid>`. |
| `no such column: workflows.deleted_at` | One-time migration for pre-existing dev DBs: `sqlite3 artifacts/spike/spike.db "ALTER TABLE workflows ADD COLUMN deleted_at DATETIME"`. Fresh databases are created correctly by `create_all`. |
| Trigger didn't fire | Triggers must be enabled, the workflow non-deleted, and the loop running (only `scripts/run_worker.py` starts it). Schedule triggers need a due `time_of_day`. Force one pass: `POST /api/triggers/tick` (requires operator role or service token). |
| AI generation errors | Without `AUTOSTACK_GEMINI_API_KEY`, provider `gemini` fails closed by design. Use the default `mock` provider for offline work. |
| Sandbox job `failed` with `NoneType object is not callable` | The generated code tried a blocked builtin (`socket`/`open`/`exec`…). This is the guard working; fix the code, or check `static_check` violations on the artifact. |
| Run returns HTTP 400 with `run_id` but "failed" status | A caller-caused data violation (missing column, unknown template, missing row). Check the run's node records via `GET /api/runs/{id}/nodes` for the exact node error. |
| Tests "pollute" the dev DB | They don't — `tests/spike/conftest.py` isolates every test in a throwaway DB. Verify: workflow count is unchanged after `pytest`. |
| `qa_probe.py` creates a few demo workflows | Expected: the probe stages demo evidence and cleans up its triggers; run `scripts/cleanup_dev_junk.py --apply` to tidy the dev DB afterwards. |

---

## Status

Capability status — deliberately explicit:

- **Implemented & verified** (evidence above): worker API + RBAC, workflow engine with
  exactly-once journal, sandboxed generation/test/approval lifecycle, schedule/file/
  webhook triggers, Node-RED embedded runtime, hash-chained audit + SIEM export,
  privacy ledger/retention/export, registry publish/import/withdraw, teams/roles/
  invitations, runners pairing, dark/light/system theming, 127-test suite, live
  probe + battery, performance budgets.
- **Experimental / spike-scoped**: Electron desktop shell (functional, UI polish
  pending), Gemini provider (real API client, requires your own key), paired-runner
  mode (gated to team tier, loopback-simulated pairing).
- **Manual-only**: Gemini key provisioning, production deployment beyond the loopback
  spike, browser-not-available scenarios (everything is loopback-bound by design).
- **Not yet implemented**: outbound HTTP connector node, multi-machine deployment,
  keyring-backed secret storage (file-based 0600 token today).

**Known limitations**: loopback-only single-machine deployment; SQLite storage;
mock AI provider by default; `qa_probe.py` stages small demo evidence in the dev DB
(cleanable via `scripts/cleanup_dev_junk.py`).

Roadmap and history: [`docs/product-roadmap.md`](docs/product-roadmap.md) (planned work),
[`docs/test-report-and-fix-plan.md`](docs/test-report-and-fix-plan.md) (six QA rounds,
every bug documented), [`docs/spike-evidence.md`](docs/spike-evidence.md) (spike verdicts).

## Repository layout

```
backend/           FastAPI worker (app.py, roadmap_routes.py, engine/, security/, teams, models, db)
frontend/          React 19 + Vite UI (src/main.jsx shell, theme.js, page modules, tokens in styles.css)
desktop/           Node-RED embed (red-embed.js, red-embed-core.js) + Electron shell (main.js)
scripts/           run_worker.py, qa_probe.py (57), scenario_battery.py (31), cleanup_dev_junk.py, measure_budgets.py
tests/spike/       132 pytest tests + 29 subtests; isolated-DB conftest
docs/              contracts, phase-1 plan/status, spike evidence, platform matrix, roadmap, QA report, budgets
artifacts/spike/   runtime state: spike.db, token, red-userdir, logs (gitignored)
```
