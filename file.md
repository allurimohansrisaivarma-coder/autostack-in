# Codebase file guide

The project is grouped by responsibility so teammates can find their work quickly. This guide covers every project-owned area; installed libraries and generated output are grouped at the end.

**Current stage:** the application is a running local-first automation platform — a FastAPI worker (`backend/`, `:8747`, embedded Node-RED on `:18790`) with SQLite persistence, a React 19 + Vite frontend (`frontend/`, dev `:5173`), a capture layer (`backend/capture/`, `browser-extension/`), and a QA suite (`tests/`, `scripts/qa_probe.py`, `scripts/scenario_battery.py`, `scripts/authz_matrix.py`). The frontend talks to the live worker; demo data appears only when the worker is unreachable.

## Folder layout

```text
BLUE-copy/
├── frontend/             React 19 + Vite app (floating nav shell, landing, settings)
│   ├── src/              Screens, navigation, design system, API client
│   ├── src/assets/       Theme-aware logo assets (light/dark marks + lockups)
│   ├── public/           Theme-aware favicons
│   ├── index.html        Browser entry page (theme boot script, theme favicons)
│   └── package*.json     Frontend dependencies and commands
├── backend/              FastAPI worker: API, engine, persistence, security
│   ├── security/         Token guards (RBAC), hash-chained audit ledger, safe IO
│   ├── engine/           Workflow engine: generation, runner, journal, rollback
│   ├── detection/        Evidence-based pattern detection service
│   ├── capture/          Local capture watcher
│   └── nodebridge/       Flow compiler for the embedded Node-RED runtime
├── browser-extension/    Capture script, worker, and event popup
├── deploy/               Deployment assets
├── desktop/              Desktop shell assets
├── shared/
│   └── contracts/        Data formats shared between components
├── tests/
│   ├── spike/            Backend suite: identity, RBAC, lifecycle, registry, e2e
│   ├── unit/             Python correctness and rejection tests
│   ├── browser/          Browser capture and UI checks (Playwright)
│   ├── fixtures/         Sample records and office page
│   └── package*.json     Browser-test dependencies and commands
├── docs/                 Phase docs, contracts, platform matrix, test reports
├── artifacts/            Runtime state (worker token, logs); ignored by Git
├── scripts/              Worker launcher, QA probes, authz matrix, logo pipeline
├── README.md             Product overview, setup, architecture, roles, FAQ
├── plan.md               Development phases and safety gates
├── file.md               This file guide
├── requirements.txt      Pinned Python dependencies for the worker
├── package.json          Convenient root commands
└── .gitignore            Files Git should exclude
```

## Root: orientation and commands

| File | Purpose |
| --- | --- |
| [README.md](README.md) | Product idea, setup, architecture, design system, roles, verification commands, FAQ. Read first. |
| [plan.md](plan.md) | Phases, targets, security requirements S1–S11, and completion gates. |
| [file.md](file.md) | This map. Update alongside new, moved, or removed files. |
| [requirements.txt](requirements.txt) | Pinned Python libraries for the worker (FastAPI, SQLAlchemy, APScheduler, uvicorn, …). |
| [package.json](package.json) | Root shortcuts for frontend/test commands; no dependencies of its own. |
| [.gitignore](.gitignore) | Excludes `.venv/`, `node_modules/`, `dist/`, `artifacts/`, caches, `.env*`. |

Backend setup: `python -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt` (Windows Git Bash paths; use `.venv/bin` on Linux/macOS).

| Command | What it does |
| --- | --- |
| `.venv/Scripts/python.exe scripts/run_worker.py` | Starts the worker + in-process trigger loop (`:8747`, Node-RED on `:18790`). |
| `cd frontend && npm install && npm run dev` | Starts the Vite dev server (`:5173`). |
| `cd frontend && npm run build` | Production build into `frontend/dist/`. |
| `.venv/Scripts/python.exe -m pytest -q` | Full backend test suite (`tests/spike/`, `tests/unit/`). |
| `.venv/Scripts/python.exe scripts/qa_probe.py` | 57-check live API battery against a running worker. |
| `AUTOSTACK_TOKEN=$(cat artifacts/spike/token) .venv/Scripts/python.exe scripts/scenario_battery.py` | 31-check end-to-end workflow scenarios. |
| `AUTOSTACK_TOKEN=$(cat artifacts/spike/token) .venv/Scripts/python.exe scripts/authz_matrix.py` | 147-check authorization matrix (all roles, IDOR, escalation). |
| `npm run test:browser` | Playwright browser checks (requires Chromium + Python deps). |

## Frontend: what the user sees

| File | Purpose |
| --- | --- |
| [frontend/index.html](frontend/index.html) | Entry page; theme boot script (no flash of wrong theme) and theme-aware favicons. |
| [frontend/src/main.jsx](frontend/src/main.jsx) | Hash router, auth state, screen map, floating-nav shell, NotFound recovery. |
| [frontend/src/nav.jsx](frontend/src/nav.jsx) | Floating navigation: desktop dropdown groups, account menu, notifications panel, ⌘K command palette, mobile grouped sheet. |
| [frontend/src/screens-live.jsx](frontend/src/screens-live.jsx) | Dashboard (execution-health hero, honest metrics), Workflows, Registry, Trust Log — live worker data. |
| [frontend/src/settings.jsx](frontend/src/settings.jsx) | Dedicated two-pane Settings (`#/settings/<section>`), owner-gated Organization. |
| [frontend/src/landing.jsx](frontend/src/landing.jsx) | Marketing landing: scroll-expansion hero, container-scroll product window, bento, trust chapter. |
| [frontend/src/roadmap-pages.jsx](frontend/src/roadmap-pages.jsx) | Login, Profile, Teams, Runners, Scheduling (role-gated forms). |
| [frontend/src/roadmap-complete.jsx](frontend/src/roadmap-complete.jsx) | Notifications center, Data & Privacy, Connectors. |
| [frontend/src/create-automation.jsx](frontend/src/create-automation.jsx) | Guided create flow: plan → generate → sandbox test → approve → bind. |
| [frontend/src/api.js](frontend/src/api.js) | Typed worker API client (token in `localStorage`, Authorization header). |
| [frontend/src/live.js](frontend/src/live.js) | 4 s polling bridge; anonymous users never poll (no 401 loops). |
| [frontend/src/premium.jsx](frontend/src/premium.jsx) | Reusable primitives: GlassSurface, Reveal, ScrollText, ContainerScroll, PremiumCard, SpringPopover, ThemeSwitcher. |
| [frontend/src/motion.js](frontend/src/motion.js) | Motion levels (reduced/touch/full), springs, easings, durations. |
| [frontend/src/brand.jsx](frontend/src/brand.jsx) | Theme-aware logo (light/dark PNG swap). |
| [frontend/src/styles.css](frontend/src/styles.css) | Base tokens and component styles. |
| [frontend/src/styles-premium.css](frontend/src/styles-premium.css) | Premium materials, floating nav, dashboard hero, landing sections, effect gates. |

## Backend: the worker

| File | Purpose |
| --- | --- |
| [backend/app.py](backend/app.py) | FastAPI app: workflows, runs, events, artifacts, approvals, registry, CORS allowlist, bootstrap. |
| [backend/roadmap_routes.py](backend/roadmap_routes.py) | Identity, capabilities/tier, teams, runners, triggers, gates, governance, privacy, webhook triggers. |
| [backend/security/tokens.py](backend/security/tokens.py) | Service + user token auth, role guards (`require_writer/tester/publisher/admin`), permission ladder. |
| [backend/security/audit.py](backend/security/audit.py) | Hash-chained, append-only audit ledger with chain verification. |
| [backend/security/safeio.py](backend/security/safeio.py) | Constrained file IO helpers. |
| [backend/identity.py](backend/identity.py) | Local accounts: PBKDF2-SHA256 (200k iterations) password hashing, API tokens. |
| [backend/teams.py](backend/teams.py) | Roles (observer/operator/approver/owner) and permission minimums. |
| [backend/entitlements.py](backend/entitlements.py) | Tier capabilities (solo/team/enterprise/government/developer). |
| [backend/models.py](backend/models.py) | SQLAlchemy models: users, memberships, workflows, runs, audit, settings, … |
| [backend/db.py](backend/db.py) | SQLite engine (WAL, foreign keys, busy timeout). |
| [backend/engine/](backend/engine/) | Workflow engine: runner, effect journal (exactly-once), rollback, generation, AI adapter. |
| [backend/detection/](backend/detection/) | Evidence-based pattern detection (no invented confidence). |
| [backend/capture/](backend/capture/) | Local capture watcher (approved apps, redacted values). |
| [backend/nodebridge/](backend/nodebridge/) | Compiles workflows to Node-RED flows. |
| [backend/spike_config.py](backend/spike_config.py) | Configuration. |

## Verification & docs

| Path | Purpose |
| --- | --- |
| [tests/spike/](tests/spike/) | Backend suite: identity, RBAC, lifecycle, registry, hardening, end-to-end. |
| [tests/unit/](tests/unit/) | Python correctness tests (file diff, event validation). |
| [tests/browser/](tests/browser/) | Playwright capture/UI checks. |
| [scripts/qa_probe.py](scripts/qa_probe.py) | 57 live API checks. |
| [scripts/scenario_battery.py](scripts/scenario_battery.py) | 31 end-to-end workflow scenarios. |
| [scripts/authz_matrix.py](scripts/authz_matrix.py) | 147-check authorization matrix. |
| [scripts/process_logos.py](scripts/process_logos.py) | One-off logo asset pipeline (Pillow + numpy). |
| [docs/](docs/) | Phase docs, API contracts, platform matrix, test reports and fix plans. |
| [deploy/](deploy/) · [desktop/](desktop/) | Deployment and desktop-shell assets. |
| [browser-extension/](browser-extension/) | Capture extension (inbound events are validated server-side). |

**Current stage (repeated for skimmers):** worker, frontend, and QA batteries are all live and passing. `artifacts/` is Git-ignored and holds runtime secrets — never commit it.
