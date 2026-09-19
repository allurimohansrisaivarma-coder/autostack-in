# AutoStack IN

**Team AutoMaters · SIH 2026 · SIH26193 / Student Innovation · Smart Automation**

A background desktop assistant that discovers repetitive office work, generates automation code, tests it in isolation, and lets the user approve and run it. A **workflow** is a repeatable sequence, such as updating a client register and preparing a follow-up message.

**The existing React code is a visual/interaction demo of the intended product.** Its example events and results are not the implementation specification. Everything below is planned unless explicitly marked existing. Security means enforced controls and tested limits; software cannot be guaranteed foolproof.

New to the codebase? Use [file.md](file.md) for a guide to each project file and [the Phase 1 confirmation checklist](docs/phase-1.md#your-phase-1-confirmation-checklist) to verify the current proofs.

## 1. Product commitments

| Requirement from our presentation and discussions | Delivery plan |
| --- | --- |
| Background operation without an open window | Opt-in startup at sign-in, independent worker, tray controls, optional React dashboard. Closing the window does not quit the worker. |
| Cross-platform | Windows, macOS, and Linux clients; publish a tested feature/OS matrix. Individual integrations may have narrower support. |
| Consent-based observation and pattern discovery | Defined collectors, local event matching, visible evidence, pause/revocation/deletion controls. |
| Code generation, savings estimates, notifications | Cloud-assisted generation, evidence-based savings, persistent dashboard items, and permitted desktop alerts. |
| Testing before use | Separate approval to test, enforced sandbox checks, then separate approval to activate the tested version. |
| Complete office workflows | Confirm data mappings/rules, then coordinate supported steps across apps, pausing for required human decisions. |
| National automation registry | Later, share reviewed templates without office records or credentials; receiving offices adapt and retest. |
| Free development | Open-source tools, existing hardware, synthetic data, and limited free model quota; no automatic paid fallback. |

The presentation's market figures and external case studies explain the opportunity; they are not project results. National-scale operation and universal app coverage are not prototype claims.

## 2. What exists today

| Existing screen | Demonstrated interaction |
| --- | --- |
| Dashboard | Navigation, sample activity, summary cards, illustrative chart. |
| Discovery | Select sample patterns and inspect steps/estimates. |
| Registry | Search examples; rank against a fixed example team profile. |
| Workflows | Browse example workflows and status/details. |
| Create Automation | Five-step interaction, simulated capture, candidate selection, timed sandbox playback. |
| Trust Log | Sample audit records. |

The React demo has no real observation, AI call, backend, persistent database, sandbox, security enforcement, notification service, or live registry yet. Clipboard messages, spreadsheet differences, confidence scores, tests, signatures, and savings shown there are illustrative. Monitoring stops when its screen is left; “Publish” changes UI state only. Reuse the appearance, replace simulated behavior, and add private activation before optional sharing.

**Phase 1 has started separately:** the [feasibility kit](docs/phase-1.md) includes a working browser connector for one local synthetic page, saved CSV/XLSX comparison, validated event contracts, automated tests, and reference screenshots of the existing design. Its code is organized into `backend/`, `browser-extension/`, `shared/`, and `tests/`. These proofs are not connected to the dashboard and do not yet implement background observation or execution. See [evidence and remaining checks](docs/phase-1-status.md); Docker/paired-runner tests are deferred, so Phase 1 is not complete.

## 3. User journey and approval states

1. **Enable observation:** select supported sites/files and permissions. Tray controls expose status, Pause, Open dashboard, and Quit.
2. **Receive a suggestion:** background discovery saves a dashboard item with evidence, proposed steps, missing information, and provisional savings. Desktop alerts are optional; dismissal never means approval.
3. **Confirm the plan:** review field mappings, update rules, output targets, and cloud-bound context. Generate a versioned draft from this specification.
4. **Approve testing:** review the code/description and test data, then authorize an isolated sandbox run.
5. **Review results:** inspect checks, output differences, limitations, code, and permissions. Failed, missing, or timed-out required checks block activation.
6. **Approve activation:** approve the exact tested code, dependencies, connectors, and permissions.
7. **Run now:** select an input and explicitly start the approved workflow. Reuse tested code; show progress, cancellation, outcomes, and recovery options.

**States:** Detected → Plan confirmed → Draft → Awaiting test approval → Testing → Passed/Blocked → Awaiting activation → Ready → Running → Completed/Failed/Cancelled. The backend enforces transitions. Changes to code, mappings, targets, permissions, dependencies, connectors, or execution policy invalidate approval and require retesting.

Input records/files and run dates are declared parameters within the approved resource scope. New data within that scope does not require regeneration; different output resources, mappings, or broader access do require retesting and approval. A file path supplied by a user or model never grants access by itself.

Observation, content reading, cloud/runner transfer, testing, activation, on-demand runs, and publication are distinct permissions. Scheduling is a later opt-in feature. Pausing observation stops collection; cancelling a run is separate. Revoking execution access stops dependent operations.

## 4. Observation: what we can actually see

First workflow: **sample client webpage → selected CSV/XLSX tracking file → in-app follow-up draft**. Use invented clients and real observed actions; never unlock candidates using timers.

A **connector** is code written for a supported app or format. Define its coverage before claiming a workflow is supported.

| Source | Implementation and evidence | Boundary |
| --- | --- | --- |
| Supported browser page | Allowlisted Chrome/Edge extension records known actions: opening a client, submitting a supported form, initiating an export. | Clicks alone do not prove success; require a supported success signal. No automatic visibility into every site, frame, or desktop app. |
| Selected CSV/XLSX | A watcher notices a save; a parser compares stable saved versions using the confirmed client-ID column. Report changed fields and added/removed rows. | Requires permission to read contents. Shows saved differences, not unsaved edits, clipboard use, or exact gestures. |
| Our draft editor | Record actual draft saves linked to the client ID. | Initial drafts stay in-app; no account access or sending. |
| Later Excel/email connectors | Excel add-in events where supported; Gmail/Graph reports for explicitly authorized operations. | Separate implementation, account/platform permissions, and tests. |

Wait for stable file content; coalesce duplicate notifications and retry locks/incomplete writes within a bounded interval. Failed parses are gaps. Row reordering is not a data update; missing/duplicate IDs make matching ambiguous. Never infer an unobserved mental action such as “read and understood a document.” Platform limits: [Chrome content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts), [Excel events](https://learn.microsoft.com/en-us/office/dev/add-ins/excel/excel-add-ins-events).

**Event contract:** unique ID, capture order/time and processing time, connector/version, action, permitted resource alias, locally protected client-matching token, changed field names, success/ambiguity flag. Raw values are not event-log defaults; permitted content can be read locally for comparison using protected, short-lived snapshots. Password capture, system-wide clipboard/keystroke logging, and screenshots are outside the initial scope.

Collectors show available/paused/disconnected/error. Missing evidence is never invented. Exclude AutoStack's own actions so the detector cannot learn from its own automated runs.

## 5. Pattern detection: the first algorithm

A local detector counts recurring **ordered action sequences**. The cloud model explains candidates and proposes automation; it does not invent observation evidence.

1. **Group task instances automatically.** Opening a supported client record starts an instance; saving its linked draft requests completion. Allow an initial five-second grace period for pending file parsing; order saved-file changes by captured save time, not parser finish time. Count only successful stable comparisons; unresolved timing stays ambiguous. Link by confirmed client ID and initially handle one client at a time. After ten inactive minutes, mark unfinished instances incomplete. Flag interleaved work. Guided demonstrations are optional; normal background discovery needs no recording button.
2. **Normalize actions.** Remove duplicate events and incidental navigation. Replace particular IDs with roles, retaining meaningful action order, changed fields, and file structure. Count each completed instance once. The first expected sequence is `record_opened → spreadsheet_row_updated → draft_saved`.
3. **Group matching sequences.** Group identical normalized sequences with compatible resource roles/columns. Suggest after **three completed, unambiguous instances involving at least two sample clients**, with actual saved changes. Refreshes, duplicate event delivery, and incomplete work do not count.
4. **Explain evidence.** Show “Observed 3 times,” dates, matching steps, incomplete attempts, and gaps. These are initial configurable engineering thresholds, not probability estimates. No “91% confidence.” Unordered Jaccard similarity alone cannot establish a workflow. Approximate sequence matching comes later with evaluated rules.
5. **Respect calendar evidence.** Accelerated demos prove repetition, not daily/weekly recurrence. Show observed dates separately from user-confirmed frequency. Learned schedules require real calendar history and validation.

**Acceptance:** human-performed sample work produces the expected suggestion only after the threshold. Reject reordered steps, unrelated IDs, duplicate events, missing steps, ambiguous work, and self-generated runs. Evaluate on separate examples not used for tuning; report false suggestions and missed patterns with sample counts. Passing these cases validates this supported workflow, not every office process.

## 6. From repeated actions to correct code

Observation does not reveal every business rule. Confirm the matching ID, source-to-column mappings, allowed fields, append/update behavior, duplicate handling, draft template, and output locations. Show synthetic before/after examples; unresolved rules block generation.

**Initial example rule:** use `ClientID`, `Name`, `Email`, `FollowUpDate`, and `Status`. Prepare drafts for records due on/before the selected run date with a user-approved status. Update matching tracking rows to `Draft prepared`, never `Sent`. Missing/duplicate IDs or invalid required fields stop the batch with an explanation; no guessed recipients or silent overwrites. Users confirm these rules before use.

The model proposes a structured plan, Python code, operations, and tests. The backend validates format/policy; the team supplies independent expected-output tests. Store the confirmed specification, code, dependency versions, permissions, and results as a versioned artifact. Structured output enforces format, not correctness. [Gemini structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)

Generated code transforms supplied inputs and proposes structured edits/drafts. Handwritten, trusted connectors hold credentials and apply approved changes. Later account/browser steps use named, allowlisted operations, not arbitrary URLs or shell access. Portal authorization, CAPTCHA/MFA, payments, and statutory submissions require supported integrations and appropriate human involvement.

**Savings:** estimate a range using `runs/month × (manual active effort − remaining review effort) − maintenance effort`. Exclude long idle gaps; ask users to confirm uncertain timing/frequency. Display sample counts/assumptions and later compare with measured run/review effort. Demo cycles are not proven monthly savings.

## 7. Execution without Docker on every computer

A **runner** executes generated code inside isolation. Build one Runner API with two deployment modes. Tests and real runs use the same versioned code, runtime, dependencies, and security policy.

| Mode | Execution location | Requirement |
| --- | --- | --- |
| Local | Hardened Docker container on the user's computer. | Compatible permitted installation, available engine, passing security preflight. |
| Paired office/team runner | Hardened container on a trusted existing computer over an approved network. | Endpoint needs no Docker/virtualization. Pair identities, authenticate/encrypt connections, and obtain consent for selected data leaving the device. |
| No available approved runner | Discovery, notifications, and review remain usable. | Testing/execution disabled with an actionable explanation. No direct-Python fallback. |

Shared mode removes Docker from endpoints, not the entire system. It needs a reachable, maintained host and permitted transfer. Use an existing team computer and synthetic data for free development. An organization forbidding installation or transfer needs an approved deployment arrangement; there is no universal bypass.

Expose only our per-user authenticated job API, **never Docker controls**. Separate job storage, apply quotas, and forbid client-selected mounts/images/security flags. Pin runner identity; verify report signatures and job/code/input/runtime/policy identifiers. Endpoint clients must not receive Docker administration credentials. [Docker access guidance](https://docs.docker.com/engine/security/protect-access/)

For real runs, send only consented necessary input copies. Return structured proposed edits/drafts, not arbitrary executable artifacts. The local agent validates schema, target fields, output sizes, and unchanged original input before applying approved operations. Reject macros/unsupported workbook types and unexpected executable spreadsheet formulas. Credentials remain outside generated code.

Delete runner payloads after acknowledged completion; expire abandoned jobs within 24 hours. Runner administrators can potentially access transferred data: LAN hosting is still another machine. On disconnect, reconcile job status before retrying; never blindly repeat effects. New runner identities require pairing/revalidation.

Without internet, local capture/detection/review continue; new cloud generation waits. Approved deterministic workflows can run without model calls if their runner/connectors are available. No runner means no generated-code execution. Free-quota exhaustion pauses generation without switching to paid service.

## 8. Security gates and failure handling

Enforce controls in the backend/runner. A UI badge, signature, scanner, or user approval alone is not proof of safety.

| Gate | Required behavior |
| --- | --- |
| Consent and storage | Separate observation/content/model-transfer/runner-transfer/execution scopes. Default retention: 30 days for observations, 90 for reports/history, configurable with deletion controls. Encrypt sensitive local records; keep keys in OS credential storage. |
| Static checks | Validate approved operations/imports, secrets, code structure, and dependency vulnerabilities. Pin reviewed dependencies; no generated shell commands, dynamic code loading, or package installation. Treat pages, records, and model output as untrusted. |
| Isolation | Non-admin process, read-only base, dropped privileges, OS security profile, CPU/memory/process/time/output limits, minimal mounts, no host/control sockets. Generated code has no network or account credentials; trusted connectors mediate permitted operations. Check actual enforcement; Docker defaults alone are insufficient. |
| Test suite | Expected outputs; malformed records; missing columns; duplicate IDs; repeated runs; interruptions; schema changes; malicious instructions; forbidden file/network access; resource exhaustion; secret leakage; recovery. Use synthetic data/mocks, with separately approved test accounts for later connectors. |
| Approval binding | All required checks pass for the exact artifact/runtime/connector policy. Record approval; invalidate it after relevant changes. Check permission again at every run and before each effect. |
| Safe writes | Stage/validate results, compare original input versions, back up files, and apply bounded changes. Deduplicate business effects: for drafts, use client ID + follow-up purpose/date + destination, recording the resulting draft ID. Keep code/input hashes for evidence, not as the only duplicate key. Reconcile effects after retries, edited inputs, or upgraded workflows; intentional repeats need explicit new occurrences. Stop on locks, concurrent changes, or unexpected schemas. |
| Partial failure | Durable operation journal, reconciliation before retries, verified unfinished-step recovery. Restore supported local changes where possible. Cancellation stops new actions; it cannot guarantee undoing completed sends/submissions. |
| Audit | Redacted observations, plans, tests, approvals, runs, failures, and recovery. Hash-linked records expose edits; trusted checkpoints are needed to detect wholesale rewriting. Local logs cannot defeat a fully compromised administrator. |

Keep Electron's UI isolated with a narrow communication interface; its renderer sandbox is not the generated-code runner. Protect paired connections with authenticated HTTPS. Before external sending, add recipient/content confirmation, explicit send permission, duplicate protection, and connector-specific recovery tests. The mandatory S1–S11 requirements and phase-specific abuse tests in [plan.md](plan.md#mandatory-safety-requirements-and-proof) define the detailed security acceptance criteria, including restricted file parsing, independent test controllers, runner revocation, secondary-copy cleanup, and safe filesystem access.

The SIH demo uses synthetic records. Sensitive production deployment needs a validated threat model and deployment review. Failed/unavailable isolation always blocks execution, including after a previously passing test.

## 9. Software, APIs, and zero-fee development

An **API** is an agreed way for programs to communicate. These are planned components unless marked existing.

| Software/service | Role / cost boundary |
| --- | --- |
| React, Vite, Node.js/npm | Existing UI and build/development tools; free. |
| Electron | Cross-platform window, tray, notifications, startup, local communication; free. |
| Python + FastAPI | Worker, local detector, permission/state enforcement, local/shared Runner APIs; free. |
| SQLite + OS credential store | Local workflow/history storage and protected keys; free. Implement encryption explicitly; SQLite alone does not provide it. |
| Browser extension + native messaging | Capture permitted supported browser actions and relay to the local agent; free development. |
| File watcher, CSV tools, openpyxl | Observe saves; compare/process permitted spreadsheet data; free, no Excel subscription required. |
| Gemini API + Google AI Studio | Developer key and cloud generation from approved minimal schemas/synthetic examples. Choose a free-tier model after checking availability and task quality. |
| Docker Engine/Desktop | Isolated jobs on a local/paired runner; Desktop free for eligible educational/personal use. |
| pytest, Bandit, pip-audit | Behavior tests, risky-code checks, dependency vulnerability checks; free, supplement isolation. |
| Playwright | Supported browser operations and integration tests; free, not a desktop recorder. |
| Git + GitHub | Version control, reviews, basic team collaboration; free options. |
| Later: Excel add-in, Gmail API, Microsoft Graph, Google Sheets API | Richer capture and authorized account workflows; check individual licenses, permissions, quotas, and platforms. |
| Later: PostgreSQL / optional Supabase + registry API | Accounts, templates, permissions, versions. Team-hosted PostgreSQL keeps development free; hosted scale is separate. |

Our APIs cover events, candidates, confirmed plans, generation jobs, test approvals/results, activation, runs, and audit history. Authenticate desktop-to-agent communication; keep it local. Keys stay outside React, prompts, generated code, and Git. Keep the model provider replaceable.

**Zero software/service fees is the development target**, conditional on existing hardware/internet and free quota. No paid model, domain, hosted database, or cloud sandbox is mandatory. Cache generated artifacts, cap retries, pause on quota exhaustion, and never automatically enable billing. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)

Free Gemini terms allow content use for product improvement. Send no real client values, secrets, or private documents; minimize schemas and replace confidential labels before transfer. Generating from synthetic examples does not require uploading the real records later processed by the runner. [Gemini terms](https://ai.google.dev/gemini-api/terms)

Docker educational eligibility does not guarantee free government/enterprise deployment. Paid models, distribution/signing, hosting, optional account products, and extra hardware may cost money later. Free development is not free production forever. [Docker licensing](https://docs.docker.com/subscription-billing/desktop-license/)

## 10. Development phases and acceptance gates

Each phase produces evidence, not just a screen. Assign owners across UI/desktop, capture/detection, backend/AI, and runner/security. Agree event/API contracts before parallel work.

| Phase | Deliverable | Exit condition |
| --- | --- | --- |
| **1. Feasibility and contracts** | Events/specifications, synthetic fixtures, risks, supported-source list, resource limits, local/shared runner trials. | Real browser capture and saved-file comparison work; a paired endpoint without Docker executes a harmless team-written fixture. Generated code remains blocked until later security gates pass. Record blockers before broader promises. |
| **2. Background foundation** | Shell, worker, SQLite, consent, protected storage, tray, startup, authenticated communication. | UI closure leaves worker running; restart preserves state; pause/revocation/deletion work. |
| **3. Real capture** | Browser adapter, stable-file parser, draft events, ID linking, deduplication, coverage status. | Human sample work produces attributable events; ambiguous/locked/unrelated files are handled correctly. |
| **4. Explainable detection** | Ordered-sequence counting, task boundaries, thresholds, evidence, notifications, provisional savings. | Section 5 positive/negative cases pass on real and replayed events; no invented confidence. |
| **5. Confirmed generation** | Mapping/rule review, sanitized cloud requests, versioned code, quota/provider handling. | Code matches the confirmed sample specification; invalid output/missing rules/quota errors never trigger execution. |
| **6. Verified runner** | Hardened local/paired modes, independent tests, version-bound signed reports, separate test/activation approvals. | Unsafe cases fail closed; stale/forged reports cannot activate code; no-Docker endpoint completes consented testing. |
| **7. End-to-end use** | Run now, validated outputs, safe writes, deduplication, audit, cancellation/recovery. | New sample records complete the client workflow; reruns/crashes/disconnections do not silently repeat effects; test paired execution as well as local. |
| **8. Cross-platform and connectors** | Windows/macOS/Linux matrix, permissions, notifications, resource use, installers, selected connector expansion. | Core flow passes on each supported OS using local or paired execution; each connector has independent permission/failure tests. |
| **9. Shared registry** | Authenticated publishing, sanitization/review, versions, search, adaptation, recipient testing. | Two installations reuse a template with different mappings without sharing records or inheriting approval. |

Test security and portability throughout. Begin registry implementation after the core flow is reliable through phase 8. Fuzzy matching, schedules, and broader app coverage follow measured results.

## 11. Registry and Indian-office roadmap

**Registry contract:** separate owner permission to publish; review code/schema/dependencies/examples for private information. Share versioned logic, parameter definitions, synthetic examples, compatible connectors, and test evidence—never credentials, real records, organization-specific paths, or inherited permissions. Add ownership, moderation, withdrawal, and version updates. Recipients map their columns/approval rules, supply synthetic local tests, retest, and approve. “Verified” means passed a stated suite/environment, not universal certification.

Ordinary withdrawal stops new imports; a known security revocation also blocks installed affected versions, including offline. Registry outages cannot clear a known block. Imported workflows may continue only within the agreed finite status-freshness policy; show the last status check and require repair/retesting for revoked versions.

| Office use case | Workflow as supported connectors are added |
| --- | --- |
| Client follow-up — first implementation | Read sample records → update tracking row → prepare in-app draft. |
| Invoice / purchase-order checks | Compare approved exports → flag mismatches → prepare finance review sheet. |
| Receivables | Identify overdue entries → update tracker → draft reminders. |
| Vendor onboarding | Check document completeness → update register → draft missing-document requests. |
| GST/PAN and procurement — presentation example | Use an authorized verification source when available → compare vendor details → gather approval evidence → prepare payment request. Format checks are not official verification; no assumed portal access or automatic payment. |
| GST/TDS preparation | Reconcile supplied records → flag mismatches → prepare accountant review pack. |
| HR joining / attendance | Consolidate permitted exports → identify missing documents/attendance exceptions → prepare checklists/reports. |
| Procurement / inventory | Compare quotations or stock thresholds → prepare approval/reorder request. |
| Expenses | Match receipts to claims → flag duplicates → prepare reimbursement review list. |
| Government / college administration | Update correspondence/application registers → identify pending items → prepare status reports. |
| Management reporting | Consolidate department sheets → summarize → prepare distribution drafts. |

Different office formats and local-language messages use reviewed mappings/templates. Financial approvals, statutory submissions, and external sends remain explicit human decisions until separately scoped and validated. Measure actual time/error reductions; do not claim percentages from external case studies.

## 12. Run the existing frontend

Install **Node.js 22.12+ within the 22.x line, or a newer supported long-term support (LTS) release**, with npm. From this repository:

```sh
npm ci --ignore-scripts --prefix frontend
npm run dev
```

Open Vite's printed URL. The development server binds to this computer only by default. Root commands forward to the frontend package, so you can stay in the repository root. No AI key, Docker, or backend is needed for this visual demo. To install both frontend and browser-test dependencies, use `npm run setup` instead of the first command above.

```sh
npm run build
npm run preview
```

| Existing file | Purpose |
| --- | --- |
| `frontend/src/main.jsx` | Screens, example data, simulated interactions. |
| `frontend/src/styles.css` | Styling. |
| `frontend/index.html` | Web entry point. |
| `frontend/package.json` / `frontend/package-lock.json` | Frontend dependencies and reproducible installation. |
| `package.json` | Root shortcuts for setup, dev, build, preview, and tests. It has no dependencies of its own. |

Folders are organized by responsibility: `frontend/` for React, `backend/` for Python logic, `browser-extension/` for capture, `shared/contracts/` for data formats, `tests/` for checks/sample data, `docs/` for detailed guides, and ignored `artifacts/` for generated evidence. See [file.md](file.md) for every file's role.

Use the [Phase 1 setup](docs/phase-1.md) for the synthetic extension/file proofs and tests. Add backend, runner pairing, key, and deployment instructions when implemented. Keep supported OS/connectors, limits, evaluation results, and implemented/planned status current. Never commit credentials or real client records.

*Design reviewed: 19 September 2026. AutoStack IN is the frontend product label; AutoMaters is the presentation's team name. Context: the team's six-slide SIH_Submitted_ppt.pdf and agreed project decisions.*
