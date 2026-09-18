# AutoStack IN

**Team AutoMaters | Smart India Hackathon 2026 | Smart Automation**

A desktop assistant that notices repetitive office work, generates automation code, tests it safely, and lets the user decide when to run it. A **workflow** is a repeatable sequence of tasks.

**Current status: interactive frontend prototype.** Background observation, AI generation, security checks, and real execution are planned, not implemented.

## 1. The experience we are building

Target **Windows, macOS, and Linux**. With permission, start at sign-in and keep running when the dashboard closes. A tray menu provides **Open dashboard, Pause observation, and Quit**.

1. **Choose what to observe.** The user permits specific sites and folders and can pause or revoke access.
2. **Discover repetition.** Find daily, weekly, or monthly patterns across sessions, with evidence users can correct or dismiss.
3. **Notify the user.** Save a dashboard notification and show a desktop alert when permitted, including steps, estimated savings, and requested access.
4. **Prepare the automation.** A cloud AI model proposes a plan and generates code using operations our app allows.
5. **Approve a sandbox test.** A sandbox is an isolated test environment. With permission, run the code on test data and check behavior and security.
6. **Review and activate.** Show the explanation, code, output preview, permissions, and test report. Require separate approval after all checks pass.
7. **Run when needed.** Select an input under **My Workflows → Run now**. Reuse the approved code without regenerating it.

Automatic discovery does **not** mean automatic execution. Scheduling is a later opt-in feature. Sharing a template will also be separate from activating it privately.

## 2. Our first complete workflow

**Sample client records → validate details → update a local spreadsheet → prepare follow-up drafts.**

Use invented clients and demonstrate the entire discovery-to-execution flow above. Initially, drafts appear inside our app; no email account or actual sending is needed.

Observe selected browser sites and a chosen folder first. Folder changes cannot explain every action inside Excel; detailed desktop-app observation needs later integrations.

Savings must come from measured work, not invented dashboard numbers:

> Estimated monthly saving = number of runs × (manual effort per run − remaining review effort per run) − maintenance effort.

Show the observation count, assumptions, and a range; separate estimates from savings measured after real runs.

## 3. What already works

| Area | Current frontend capability |
| --- | --- |
| Dashboard | Summary cards, sample operations, an illustrative chart, and navigation. |
| Discovery | Select sample patterns, inspect steps and estimates, and enter the creation screen. |
| Registry | Search sample templates and rank them using a fixed team profile. |
| Workflows | Browse sample workflows and view their status/details. |
| Create Automation | Five-step interface, start/pause simulated monitoring, select candidates, and replay simulated sandbox results. |
| Trust Log | Display sample audit records. |

Events, scores, savings, tests, hashes, and signatures are **demo data**. Some buttons are placeholders. “Publish” only changes the screen; monitoring stops when its screen is left. Nothing is saved permanently.

There is **no backend, database, AI connection, real execution/security system, desktop notification, or live registry**. Replace the current “Publish” step with private review/activation for the initial release.

## 4. Software, services, and their roles

An **API** lets programs communicate. Everything below is local except the cloud model and optional code collaboration.

| Software/service | Role | Status and development cost |
| --- | --- | --- |
| React + Vite + Node.js/npm | Build and run the dashboard and its development tools. | Already used; free. |
| Electron | Package the dashboard as a desktop app with tray controls, startup, and notifications. | Planned; [free and open source](https://www.electronjs.org/docs/latest/why-electron). |
| Python + FastAPI | Background worker and our API for workflows, approvals, and runs. | Planned; free. |
| SQLite | Store observations, workflow versions, approvals, and history. | Planned; free. |
| Browser extension APIs + native messaging | Observe permitted browser actions and communicate with the local agent. Start with Chrome/Edge. | Planned; local development is free. |
| Gemini API + Google AI Studio | Get an API key; interpret workflow summaries and generate code. | Planned; limited free tier. |
| Python CSV tools + openpyxl | Read/write selected CSV and Excel files without requiring an Excel subscription. | Planned; free. |
| Playwright | Automate supported browser steps and test demo pages when needed. | Planned; free. |
| Docker Engine/Desktop | Run the isolated test runner locally. | Planned; Desktop is free for eligible educational/personal use. |
| pytest + Bandit + pip-audit | Test behavior, flag risky code, and check software dependencies for known vulnerabilities. | Planned; free. |
| Operating-system credential store | Keep API keys/tokens out of the interface, generated scripts, and repository. | Planned; built into the OS, with a supported adapter. |
| Git + GitHub | Share code, review changes, and track work. | Git is used; GitHub Free is sufficient for basic collaboration. |

The model proposes a plan, code, and permissions; our backend validates them. AI cannot approve itself. Select the Gemini model after checking free availability and sample-task quality; keep the provider replaceable.

**Later options:** Gmail API/Microsoft Graph for email drafts, Google Sheets API for online sheets, and PostgreSQL/Supabase plus our registry API for sharing. Check permissions and costs first. GST, Aadhaar, banking, and government-portal API access is not assumed.

## 5. Free development and data boundaries

**Target: zero software/service fees**, using existing computers/internet, local tools, synthetic records, and Gemini's free tier. No paid hosting, domain, cloud sandbox, or Office subscription is required.

- Free model availability and quotas vary. Cache generated workflows, limit retries, and pause when quota is exhausted. **Never automatically enable billing or a paid fallback.** [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- Google's unpaid terms allow content use for product improvement. Send only synthetic examples and permitted, minimized descriptions; never real client records, credentials, or private documents. [Gemini terms](https://ai.google.dev/gemini-api/terms)
- Docker Desktop is free for eligible educational use; future government/enterprise customers need a licensing check. Suitable hardware and virtualization are required. [Docker licensing](https://docs.docker.com/subscription-billing/desktop-license/)
- Paid models such as OpenAI, hosting, public distribution/signing, or test hardware may cost money later. They are outside the free prototype requirement.

## 6. Security rules we must implement

**A passed test permits review; user approval permits only the actions tested.** Enforce these rules in the backend and runner.

| Protection | What it means in practice |
| --- | --- |
| Consent and privacy | Only allowed sites/folders; never capture passwords. Screenshots and broad keystroke logging are off by default. Provide pause, revocation, retention limits, deletion, and protected storage. |
| Treat content as data | Instructions hidden in a client record, webpage, or generated response must not override app rules or permissions. |
| Restrict generated code | Allow approved operations and fixed dependency versions. Check for secrets/unsafe code; reject arbitrary shell commands and automatic software installation. |
| Isolate every test | Disposable test data, non-admin execution, read-only base, resource/time limits, and blocked network. No live credentials, Docker control socket, or broad host-folder access. |
| Test failures too | Test missing columns, bad records, duplicates, repeat runs, interruptions, recovery, unauthorized access, and malicious instructions. The team defines expected outputs independently of AI. |
| Enforce approval | Bind approval to tested code, dependencies, and permissions. Changes require retesting/reapproval. Missing, failed, or interrupted checks block activation. |
| Constrain actual runs | Keep generated code isolated; trusted app operations handle approved file/account access. Back up files, prevent duplicates, support cancellation, and stop on unexpected input changes. |
| Keep evidence | Log redacted events, versions, tests, approvals, and outcomes. Show changes and recovery options. Sent messages cannot reliably be undone. |

Authenticate local API/desktop connections. Block execution if isolation is unavailable. Scans and passing tests reduce risk; they do not guarantee complete safety.

## 7. Development phases

Complete the usable workflow before building the registry. Each phase has a visible completion condition; security is part of every phase.

| Phase | Build | Finished when |
| --- | --- | --- |
| **1. Foundation** | Label demo data; define states, permissions, sample records, expected outputs, and risks. | Team agrees the flow and blocked actions. |
| **2. Background app** | Desktop shell, worker, storage, consent, tray controls, optional startup. | Worker survives dashboard closure; settings/history survive restart. |
| **3. Discovery** | Real supported capture, pattern detection, savings estimates, notifications. | Repeated sample work produces a suggestion users can inspect or dismiss. |
| **4. AI generation** | Free Gemini connection, minimized prompts, constrained code, versions. | Reviewable code is produced; invalid output/quota failures trigger no execution. |
| **5. Sandbox gates** | Isolation, functional/security tests, independent expected outputs, reports. | Valid cases pass; unsafe/broken cases cannot activate. |
| **6. Approved execution** | Review, activation, Run now, restricted writes, history, cancellation/recovery. | Full client demo works; reruns avoid duplicates and unauthorized actions are blocked. |
| **7. Cross-platform validation** | Package/test all three OS targets, including permissions, notifications, resource use, and restart. | Full demo passes on each supported OS; gaps are documented. |
| **8. Shared registry** | Optional sanitized templates, search, versions, import, retesting. | Another installation adapts/retests a template without sharing private records. |

**Team work areas:** desktop/UI, capture/detection, backend/AI, and sandbox/security/testing. Assign owners and agree data formats together; review changes and update feature status here. Test portability throughout development. Begin the registry only after phases 1–7 pass.

## 8. More workflow ideas for Indian offices

Future ideas, not implemented features. Keep approvals, legal submissions, payments, and external communication under human control.

| Office/task | Possible workflow |
| --- | --- |
| Client follow-up — first demo | Read records → update contact/status sheet → prepare follow-up drafts. |
| MSME invoice tracking | Read approved invoice files → update receivables → flag overdue items → draft reminders. |
| Vendor onboarding | Check a supplied document checklist → flag missing items → update vendor register → prepare a request draft. |
| GST/TDS preparation | Organize supplied purchase/sales records → identify missing fields or mismatches → prepare a review pack for the accountant; no automatic filing. |
| HR attendance and leave | Combine approved attendance exports → flag inconsistencies → prepare a monthly review sheet. |
| Employee joining | Check joining-document completeness → update checklist → prepare welcome and missing-document drafts. |
| Procurement | Collect quotation details → build a comparison sheet → prepare an approval request; no automatic purchase. |
| Stock and dispatch | Combine stock/delivery exports → identify low stock or pending deliveries → prepare a replenishment/follow-up list. |
| Expense reimbursement | Sort submitted receipts → match employee claims → flag duplicates or missing evidence → prepare a review sheet. |
| Government/college administration | Update an inward/outward correspondence or application register → identify pending files → prepare a status report. |
| Management reporting | Combine weekly department spreadsheets → generate a summary → prepare a report draft. |

## 9. Run the frontend today

Only the web prototype is runnable. Install **Node.js 22.12+ within the 22.x line, or a newer supported long-term support (LTS) release**, with npm.

From the repository folder:

```sh
npm ci
npm run dev -- --host 127.0.0.1
```

Open the URL printed by Vite. The host option keeps access local to your machine. No API key is needed.

```sh
npm run build
npm run preview -- --host 127.0.0.1
```

| Existing file | Purpose |
| --- | --- |
| `src/main.jsx` | Screens, demo data, and simulated interactions. |
| `src/styles.css` | Visual styling. |
| `index.html` | Page entry point. |
| `package.json` / `package-lock.json` | Commands and reproducible dependency installation. |

Add backend, extension, API-key, and sandbox setup here when implemented. Never commit credentials or private records. Keep **implemented**, **simulated**, and **planned** status accurate.

*Plan and service references reviewed: 19 September 2026. Product label currently follows the frontend (AutoStack IN); AutoMaters is the team name used in the presentation.*
