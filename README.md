# AutoStack IN

> **Smart India Hackathon 2026 Submission**  
> Local-first business automation platform for Indian SMEs — describe an office workflow in plain English, get AI-drafted automation, test it safely in a sandbox, approve it, and let it run on a schedule, file-change, or webhook — with a tamper-evident audit trail and role-based access control throughout.

---
DEMO VIDEO LINK - (https://drive.google.com/file/d/11lU6d4mTxDCkl8erF6AZy_DYP-136ZwN/view?usp=drivesdk)
## Problem Statement

**Repetitive office work kills productivity in Indian SMEs.**

Client follow-ups, PO matching, invoice reconciliation, and filing reminders are tracked in spreadsheets and executed by hand. Cloud automation tools (Zapier, Make, n8n cloud) cannot reach local files, do not fit Indian compliance workflows, and charge per-action — making them unaffordable and irrelevant for small businesses.

## Our Solution

**AutoStack IN** is a local-first automation platform that:

- **Watches your files** — detects patterns in CSV/Excel data (new clients, changed invoices, overdue follow-ups)
- **Drafts automations with AI** — turns repeated events into structured plans using Gemini or our offline mock provider
- **Proves safety in a sandbox** — every generated automation runs in a hardened subprocess before activation
- **Requires human approval** — no automation ever goes live without explicit sign-off
- **Runs reliably** — exactly-once execution, idempotent steps, cancel/rollback, and a SHA-256 hash-chained audit log
- **Fits Indian SME compliance** — role-based access (observer/operator/approver/owner), privacy ledger, SIEM export, data retention windows

---

## Live Demo

| Component | URL | Status |
|-----------|-----|--------|
| Frontend (Vite + React 19) | [autostack-in.vercel.app](https://autostack-in.vercel.app) | Production (Vercel) |
| Backend API (FastAPI on Railway) | [autostack-backend-production.up.railway.app](https://autostack-backend-production.up.railway.app) | Production (Railway) |
| Local Worker (Self-hosted) | `http://127.0.0.1:8747` | Dev / Local-first |

> The production deployment connects the Vercel frontend to the Railway backend with dynamic CORS and token persistence. For local development, the frontend auto-detects the local worker at `http://127.0.0.1:8747`.

---

## Architecture

```
Browser (React 19 + Vite, :5173 / Vercel)
   |  fetch + live poll, bearer token
   v
Worker (FastAPI, :8747) --> SQLite (workflows, runs, events, audit hash-chain)
   |  Capture -> Plan -> Generate -> Sandbox Test -> Approve -> Run
   v
Node-RED (embedded, :18790)
   |  compiled flow calls back per step
   v
Worker step endpoints (read-due / update-row / draft-create / notify)
```

### The Automation Lifecycle

1. **Capture** — file watchers or manual staging turn CSV drops into Events
2. **Plan** — AI (Gemini or mock) turns the event into a structured plan
3. **Generate** — plan compiles to a Python module validated against an allowlist before execution
4. **Test** — artifact runs in a hardened sandbox: fresh subprocess, blocked sockets, stripped builtins, POSIX rlimits, wall-clock kill
5. **Approve** — explicit human approval referencing both artifact and its passing test job
6. **Run** — approved workflows execute through a graph executor with per-node steps, idempotency, cancel/rollback, and hash-chained audit entries

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 8, Vanilla CSS (design tokens), Motion |
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2, SQLite (WAL mode) |
| Automation runtime | Node-RED (embedded), APScheduler |
| AI | Google Gemini API (optional) / deterministic mock (offline) |
| Security | PBKDF2-HMAC passwords, bearer tokens, sandboxed subprocess, SHA-256 audit chain |
| Desktop shell | Electron (optional) |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1. Clone and set up

```bash
git clone https://github.com/YOUR_USERNAME/autostack-in.git
cd autostack-in

# Python environment
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # Linux/macOS

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env — only needed if you want Gemini AI. Mock AI works offline with no config.
```

### 3. Run the stack

```bash
# Terminal 1 — Start the backend worker
.venv\Scripts\python scripts\run_worker.py          # Windows
# python scripts/run_worker.py                       # Linux/macOS

# Terminal 2 — Start the frontend
cd frontend && npm run dev
```

Open **http://localhost:5173** > Register the first user (becomes org owner) > go to **Discovery > Create Automation**

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AUTOSTACK_TOKEN` | auto-generated | Service bearer token. Auto-created on first run; env var overrides. |
| `AUTOSTACK_AI_PROVIDER` | `mock` | `mock` (offline, deterministic) or `gemini` |
| `AUTOSTACK_GEMINI_API_KEY` | unset | Required only for `gemini` provider. Get from Google AI Studio. |

Copy `.env.example` to `.env` and fill in your values. Never commit `.env`.

---

## Application Features

### Roles and Access Control

Four org roles gate every route server-side:

- **Observer** — read-only access
- **Operator** — run workflows, stage events, drive callbacks
- **Approver** — sandbox-test and activate automations
- **Owner** — publish to registry, admin: tier, members, triggers, delete workflows

First registered user becomes **owner**; subsequent users join as **operator**.

### Pages

- **Dashboard** — live run/event/heartbeat status
- **Workflows** — list, runs, parameter schemas, manage
- **Discovery** — detected automation candidates from real observed patterns
- **Create** — plan > generate > sandbox test > approve stepper
- **Scheduling** — per-workflow triggers (schedule, file watch, webhook)
- **Trust Log** — hash-chained audit with chain verification and SIEM export
- **Registry** — versioned template publish/import with consent gating and secret scanning
- **Data and Privacy** — processing ledger, retention windows, subject data export

### Trigger Types

| Type | Description |
|------|-------------|
| Manual | `POST /api/runs` — run now from UI or API |
| Schedule | Daily at HH:MM UTC, optional days-of-week |
| File watch | Fires when a watched CSV/file event matches the alias + action |
| Webhook | `POST /api/webhook/{trigger_id}` with `X-AutoStack-Secret` header |

---

## Security Model

- **Auth** — PBKDF2-HMAC passwords (200k iterations, per-user salt), bearer tokens hashed at rest, login lockout after repeated failures
- **Authorization** — role model enforced server-side on every route including legacy and trigger endpoints
- **Sandbox** — static validation (module allowlist, banned constructs, 20 KB cap) + subprocess isolation (blocked sockets, stripped builtins, POSIX rlimits, wall-clock timeout)
- **Webhooks** — constant-time secret comparison, rate-limited (60s window), 1 MB body cap
- **Audit** — SHA-256 hash-chained audit log; `GET /api/audit?verify=1` verifies the chain; SIEM stream + compliance bundle export
- **Secrets hygiene** — no credentials committed; tokens are gitignored 0600 files; flow templates use placeholder tokens

---

## Testing

```bash
# Full pytest suite (isolated throwaway DBs, never touches dev DB)
.venv\Scripts\python -m pytest tests/ -q             # 132 tests + 29 subtests

# Live-stack probes (worker must be running)
.venv\Scripts\python scripts/qa_probe.py             # 57 checks
.venv\Scripts\python scripts/scenario_battery.py     # 31 checks
.venv\Scripts\python scripts/authz_matrix.py         # 147 auth checks

# Frontend build check
cd frontend && npm run build
```

| Suite | Coverage | Status |
|-------|----------|--------|
| pytest (132 tests + 29 subtests) | Lifecycle, RBAC, sandbox, triggers, registry, privacy, retention | Passing |
| qa_probe.py (57 checks) | Full live-stack end-to-end | Passing |
| scenario_battery.py (31 checks) | Concurrency, failure paths, webhook, schedule, RBAC edges | Passing |
| authz_matrix.py (147 checks) | Every protected endpoint, IDOR, escalation, token lifecycle | Passing |
| Frontend build | Production Vite bundle | Passing |

---

## Repository Layout

```
autostack-in/
├── backend/               FastAPI worker
│   ├── app.py             Main API (all routes)
│   ├── roadmap_routes.py  Extended routes (teams, registry, governance, privacy)
│   ├── models.py          SQLAlchemy models
│   ├── engine/            Workflow graph executor (runner, journal, rollback, AI, rows)
│   ├── security/          Auth, RBAC, sandbox hardening
│   └── db.py              SQLite session factory
├── frontend/              React 19 + Vite UI
│   ├── src/
│   │   ├── main.jsx       App shell + hash router
│   │   ├── nav.jsx        Floating navbar with dropdowns
│   │   ├── screens-live.jsx  All app pages
│   │   ├── landing.jsx    Public landing page
│   │   ├── create-automation.jsx  Stepper flow
│   │   ├── styles.css     Design tokens + base styles
│   │   └── styles-premium.css  Premium UI components
│   └── index.html
├── desktop/               Electron shell + Node-RED embed
├── scripts/               Dev/ops utilities
│   ├── run_worker.py      Start the backend worker
│   ├── qa_probe.py        57-check live probe
│   ├── scenario_battery.py  31-check behavioral battery
│   └── authz_matrix.py   147-check authorization matrix
├── tests/                 pytest suite (isolated DBs)
├── docs/                  Architecture, roadmap, QA reports
├── deploy/                Docker config
│   └── Dockerfile.worker
├── .env.example           Environment variable template
├── requirements.txt       Python dependencies
└── README.md
```

---

## Deployment

### Frontend to Vercel

The frontend is a static Vite build and deploys to Vercel in one click.

Vercel settings:
| Setting | Value |
|---------|-------|
| Framework Preset | Vite |
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

### Backend via Docker

```bash
docker build -f deploy/Dockerfile.worker -t autostack-worker .
docker run -p 8747:8747 \
  -e AUTOSTACK_TOKEN=your-token \
  -e AUTOSTACK_AI_PROVIDER=mock \
  -v autostack-data:/data \
  autostack-worker
```

---

## Commands Reference

| Command | Description |
|---------|-------------|
| `.venv\Scripts\python scripts\run_worker.py` | Start worker + trigger loop (:8747) |
| `cd frontend && npm run dev` | Vite dev server (:5173) |
| `cd frontend && npm run build` | Production frontend bundle |
| `.venv\Scripts\python -m pytest tests/ -q` | Full test suite |
| `.venv\Scripts\python scripts\qa_probe.py` | 57-check live probe |
| `.venv\Scripts\python scripts\scenario_battery.py` | 31-check behavioral battery |
| `.venv\Scripts\python scripts\authz_matrix.py` | 147-check authorization matrix |
| `.venv\Scripts\python scripts\cleanup_dev_junk.py [--apply]` | Soft-delete test-junk workflows |

---

## Roadmap

See [docs/product-roadmap.md](docs/product-roadmap.md) for the full roadmap.

Coming next:
- Outbound HTTP connector node
- Multi-machine deployment
- Keyring-backed secret storage
- More file format support (Excel, JSON feeds)

---

## Team

Built for **Smart India Hackathon 2026**.

---

## License

This project is submitted for SIH 2026. All rights reserved by the team.

---

## Additional Documentation

| Document | Description |
|----------|-------------|
| [docs/contracts.md](docs/contracts.md) | Event/plan/artifact contract specs |
| [docs/spike-evidence.md](docs/spike-evidence.md) | Spike verdicts with evidence |
| [docs/platform-matrix.md](docs/platform-matrix.md) | OS/runtime compatibility matrix |
| [docs/product-roadmap.md](docs/product-roadmap.md) | Full product roadmap |
| [docs/test-report-and-fix-plan.md](docs/test-report-and-fix-plan.md) | QA rounds 1-6: every bug, root cause, fix |
