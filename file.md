# Codebase file guide

The project is grouped by responsibility so teammates can find their work quickly. This guide covers every project-owned file; installed libraries and generated output are grouped at the end.

**Current stage:** `frontend/` is the React visual demo. `backend/` and `browser-extension/` contain the working Phase 1 proofs using invented data. No backend web server, background desktop agent, AI generation, execution runner, or live registry has been implemented yet.

## Folder layout

```text
SIH_26/
├── frontend/             React dashboard and its build tools
│   ├── src/              Screen code and styles
│   ├── index.html        Browser entry page
│   └── package*.json     Frontend dependencies and commands
├── backend/              Python comparison and event-validation logic
├── browser-extension/    Capture script, worker, and event popup
├── shared/
│   └── contracts/        Data formats shared between components
├── tests/
│   ├── unit/             Python correctness and rejection tests
│   ├── browser/          Browser capture and UI checks
│   ├── fixtures/         Invented records and sample office page
│   └── package*.json     Browser-test dependencies and commands
├── docs/                 Phase 1 setup, contracts, and progress evidence
├── artifacts/            Generated reports/screenshots; ignored by Git
├── README.md             Project overview
├── plan.md               Development phases and safety gates
├── file.md               This file guide
├── package.json          Convenient commands from the repository root
└── .gitignore            Files Git should exclude
```

## Root: orientation and commands

| File | Purpose |
| --- | --- |
| [README.md](README.md) | Product idea, current progress, software/services, security rules, office examples, and frontend setup. Read first. |
| [plan.md](plan.md) | Phases, targets, complications, security requirements S1–S11, and completion gates. Guides what to build next. |
| [file.md](file.md) | This map. Update alongside new, moved, or removed files. |
| [package.json](package.json) | Shortcuts that install or run the frontend/tests. Has no dependencies of its own; dependency lockfiles belong to `frontend/` and `tests/`. |
| [.gitignore](.gitignore) | Excludes installed dependencies, builds, artifacts, caches, virtual environments, and local environment-secret files. Does not encrypt files or prevent cloud-folder syncing. |

Run these commands from the repository root. Use `npm.cmd` in PowerShell if `npm` is blocked by script execution policy.

| Command | What it does |
| --- | --- |
| `npm run setup` | Installs frontend and browser-test JavaScript dependencies from their existing lockfiles, without install scripts. |
| `npm run dev` | Starts the React development server on this computer only. |
| `npm run build` | Builds the frontend into `frontend/dist/`. |
| `npm run preview` | Serves that built frontend locally. |
| `npm run test:unit` | Runs the Python unit tests; requires the Python dependencies first. |
| `npm run test:browser` | Runs browser capture/UI checks; requires Playwright's Chromium and the Python dependencies. |

Full Python/browser setup and manual confirmation are in [docs/phase-1.md](docs/phase-1.md). For frontend-only installation, use `npm ci --ignore-scripts --prefix frontend`. A bare `npm ci` at the root is not the setup command.

## Frontend: what the user sees

| File | Purpose |
| --- | --- |
| [frontend/index.html](frontend/index.html) | Browser entry page; provides the `root` element and loads `/src/main.jsx` relative to the frontend server. |
| [frontend/src/main.jsx](frontend/src/main.jsx) | All six React screens, navigation, cards/details, sample data, creation steps, and simulated monitoring/sandbox interactions. Demo confidence, savings, tests, and audit entries are illustrative. |
| [frontend/src/styles.css](frontend/src/styles.css) | Sidebar, spacing, colors, typography, cards, tables, buttons, badges, and terminal appearance. Imports external fonts; offline reference screenshots use fallback fonts. |
| [frontend/package.json](frontend/package.json) | Frontend `dev`, `build`, and `preview` commands plus pinned React/Vite-related dependencies. |
| [frontend/package-lock.json](frontend/package-lock.json) | npm's exact frontend dependency versions and integrity values. Keep with the manifest; let npm manage dependency updates. |

`.jsx` holds React interface code; `.css` controls appearance. Preserve the existing visual identity as real functionality is added.

## Backend: Python logic

| File | Purpose |
| --- | --- |
| [backend/__init__.py](backend/__init__.py) | Python package marker, enabling commands such as `python -m backend.file_diff`. Identifies the current code as synthetic-data proofs. |
| [backend/file_diff.py](backend/file_diff.py) | Reads two supported sample CSV/XLSX versions, matches rows by `ClientID`, and reports added/removed records and changed column names without returning cell values. Rejects unsupported workbook content and checks file/row/cell limits. It does not watch folders, write changes, or provide production parser isolation. |
| [backend/validate_events.py](backend/validate_events.py) | Loads shared schemas and validates exported events, including timestamps, allowed fields, a maximum batch size, and duplicate IDs within a batch. Can run as a command. Validation does not grant execution permission. |
| [backend/requirements.txt](backend/requirements.txt) | Pinned Python libraries: `openpyxl` for XLSX, `defusedxml` for XML safeguards, and `jsonschema` for structured-data checks. A complete indirect-dependency lock remains future work. |

The backend folder is the home for future application logic. Its existence does not mean FastAPI, persistence, or workflow execution is already running.

## Browser extension: sample-page observation

Capture is restricted to exactly `http://127.0.0.1:4174/office.html`, including the port/path. Use a dedicated test profile and invented data.

| File | Purpose |
| --- | --- |
| [browser-extension/manifest.json](browser-extension/manifest.json) | Extension name/version, storage permission, sample-page match, capture script, worker, and popup. Scripts additionally enforce the exact URL/port. |
| [browser-extension/capture.js](browser-extension/capture.js) | Observes browser-dispatched Open record / Save draft clicks with the sample page's success signal. Sends only action, sample ID, and time. Collects neither typed text nor clipboard contents. |
| [browser-extension/worker.js](browser-extension/worker.js) | Validates message source/shape and stores up to 100 minimized events in extension-local storage. This is an extension worker, not the future operating-system background agent. |
| [browser-extension/events.html](browser-extension/events.html) | Popup displaying events with Refresh and Delete fixture events controls. |
| [browser-extension/events.js](browser-extension/events.js) | Reads stored events as text and handles popup refresh/deletion. |

## Shared contracts: agreed data formats

A **contract** defines the shape and meaning of information exchanged between components; a **schema** provides machine-readable rules for that shape.

| File | Purpose |
| --- | --- |
| [shared/contracts/event.schema.json](shared/contracts/event.schema.json) | Allowed synthetic event fields, sources/actions, sample record keys, and changed field names. Rejects additional raw-value or approval fields. Used by backend validation and tests. |
| [shared/contracts/runner-report.schema.json](shared/contracts/runner-report.schema.json) | Proposed future report shape: job/owner/runner identity, hashes, checks, timestamps, and signature fields. A passed report cannot contain failed checks. Does not implement isolation, authenticate signatures, or approve workflows. |

See [docs/contracts.md](docs/contracts.md) for the intended behavior behind these formats.

## Tests: checks and invented examples

A **fixture** is a prepared input or expected result used for testing. All client records here are invented. `.cjs` is JavaScript run by Node.js; `.py` is Python.

| File | Purpose |
| --- | --- |
| [tests/package.json](tests/package.json) | Pins Playwright; its local `test` command runs the browser checks. |
| [tests/package-lock.json](tests/package-lock.json) | Exact browser-test npm dependencies, separate from frontend dependencies. |
| [tests/browser/capture-and-ui.cjs](tests/browser/capture-and-ui.cjs) | Starts temporary sample/Vite servers, loads the extension in a fresh Chromium profile, verifies accepted/rejected observations, exports/validates events, and screenshots the React screens. Writes evidence, closes its servers/browser, and deletes the temporary profile. |
| [tests/unit/__init__.py](tests/unit/__init__.py) | Empty Python package marker for the unit-test directory. |
| [tests/unit/test_file_diff.py](tests/unit/test_file_diff.py) | Twelve tests for comparison results, reordering/add/remove, invalid IDs/rows, formulas, bounds, XLSX equivalence, unsafe XML, and malformed/unsupported workbooks. Creates temporary XLSX/invalid inputs when running. |
| [tests/unit/test_contracts.py](tests/unit/test_contracts.py) | Eight tests for schemas/events, raw-value exclusion, timestamps, duplicate IDs, batch limits, changed-field requirements, and report shape. Does not test a real sandbox or signer. |
| [tests/fixtures/clients-before.csv](tests/fixtures/clients-before.csv) | Three invented clients before changes; comparison input. |
| [tests/fixtures/clients-after.csv](tests/fixtures/clients-after.csv) | Prepared saved version with C001/C003 set to `Draft prepared` and rows reordered; C002 unchanged. Not output from an implemented automation. |
| [tests/fixtures/expected-diff.json](tests/fixtures/expected-diff.json) | Independent expected comparison result: two `Status` changes, no added/removed records. |
| [tests/fixtures/office.html](tests/fixtures/office.html) | Sample office page with client selection, record display, draft editor, unobserved test input, and deletion. Own small stylesheet; does not replace React. |
| [tests/fixtures/office.js](tests/fixtures/office.js) | Opens sample records, saves drafts to the test browser's local storage, reports success/failure, and deletes drafts. Sends no email. |

## Docs: setup and evidence

| File | Purpose |
| --- | --- |
| [docs/phase-1.md](docs/phase-1.md) | Setup, automated commands, manual extension walkthrough, expected results, cleanup, and the Phase 1 confirmation checklist. |
| [docs/contracts.md](docs/contracts.md) | Event meanings, first business rule, planned workflow states, permissions, runner trust, resource limits, cleanup, and responsible roles. Separates implemented checks from planned enforcement. |
| [docs/phase-1-status.md](docs/phase-1-status.md) | Recorded results, versions, frontend fingerprints, limitations, and pending work. Add actual manual/platform/runner evidence here; never mark checks passed without performing them. |

## Generated and local files

These are tool-generated, not application source. Their presence varies between teammates' computers.

| Location / files | Purpose and handling |
| --- | --- |
| `frontend/node_modules/`, `tests/node_modules/` | Installed third-party JavaScript libraries. Ignored by Git. Change manifests and reinstall instead of editing library internals. |
| `frontend/dist/index.html`, `frontend/dist/assets/*` | Built frontend HTML/CSS/JavaScript. Asset names contain generated hashes. Ignored; change source and rebuild. |
| `.venv/` | Optional local Python environment. Ignored by Git. |
| `__pycache__/` and the `.pyc` files inside | Generated Python import caches, ignored by Git. |
| `artifacts/phase-1/browser-report.json` | Latest browser-check status, timestamp, versions, checks, source hashes, screenshot names, and limitations. A development report, not a signed execution approval. |
| `artifacts/phase-1/capture-events.json` | Four minimized synthetic events from a successful browser run. No client names, email addresses, or draft bodies. |
| `artifacts/phase-1/dashboard.png`, `discovery.png`, `registry.png`, `workflows.png`, `create.png`, `trust-log.png` | Six main-screen references; every listed PNG is in `artifacts/phase-1/`. |
| `artifacts/phase-1/discovery-detail.png`, `registry-detail.png`, `workflow-detail.png` | Three selected detail states, in the same artifacts folder. |
| `artifacts/phase-1/create-step-2.png` through `create-step-5.png` | Other creation steps; 13 screenshots total including those above. |
| `artifacts/phase-1/browser-profile-*` | Temporary test-browser profiles, normally removed during cleanup. Never use a personal browser profile here. |
| `.env`, `.env.*`, `*.local` | Git-excluded local configuration patterns. No API key is required for current proofs; this is not an implemented secret-management system. |
| `.git/` | Git's internal history/configuration. Use Git commands instead of editing these as source. |

All of `artifacts/` is ignored by Git. Teammates generate their own evidence with the documented commands. The presentation PDF remains an external reference, not a runtime file inside this repository.

## How the components connect today

- **Demo UI:** `frontend/index.html` → React screen code and styles.
- **Capture proof:** `tests/fixtures/office.html` / `office.js` → extension capture → extension worker → popup. The browser test exports observations for the Python validator.
- **File proof:** sample before/after files → `backend/file_diff.py` → changed-field summary checked against the expected fixture.
- **Verification:** Python and browser tests use `shared/contracts/`, write browser evidence to `artifacts/`, and have their results summarized in `docs/phase-1-status.md`.

These remain separate proofs. Later phases connect observation, detection, approvals, isolated runs, and the React interface according to `plan.md`.

*Updated: 20 September 2026. Files are organized by responsibility rather than development phase.*
