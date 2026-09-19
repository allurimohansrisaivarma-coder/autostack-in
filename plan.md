# AutoStack IN — Development Plan

**This file is the roadmap. Phase 1 implementation has begun; see the [Phase 1 guide](docs/phase-1.md) and [file map](file.md).**

Use [README.md](README.md) for product rules, architecture, and security requirements. This file turns those decisions into phased work. Phases 1–9 match the README; phase 10 is final integration and release acceptance. Phase 1 is **in progress**; phases 2–10 are **not started**. The existing React application remains the visual demo, not evidence that the backend phases are complete.

## End-product target

Deliver a background application for Windows, macOS, and Linux that discovers supported repetitive work, notifies the user, generates code, tests it after approval, and allows the approved workflow to run on demand. Add template sharing only after the local workflow is reliable.

**The finished dashboard must retain the current React frontend's visual identity:** pale-blue sidebar, blue active navigation/buttons, light workspace, white cards, tables, badges, detail panels, terminal-style output, and guided creation flow. Keep the six main destinations: Dashboard, Discovery, Registry, Workflows, Create Automation, and Trust Log.

Reuse the existing design rather than redesigning the product. Labels and controls must change where needed for truthful behavior: evidence instead of invented confidence, real tests instead of timed playback, and private activation before optional publication. Add settings, notifications, permission review, and recovery using the same design language.

**First complete workflow:** sample client webpage → update a selected CSV/XLSX tracking file → prepare an in-app follow-up draft. Use synthetic clients throughout development.

## Working rules and dependencies

- Keep development free of software/service fees using existing hardware, local tools, eligible Docker use, and available Gemini free quota. Never enable paid fallback automatically. Service limits and data rules are in the README.
- Capture and pattern detection stay local. Only approved, minimized schemas and synthetic examples go to the model. A paired runner is another computer and requires explicit transfer permission.
- Earlier feasibility experiments use harmless, team-written fixtures. In phase 6, first validate runner isolation and the trusted test controller; then allow approved generated-code sandbox tests. Only a passing workflow suite plus separate activation approval permits restricted real runs. Sandbox readiness and workflow approval are different gates.
- A phase finishes when its completion checks pass and evidence is recorded. A screenshot or successful animation is insufficient.
- Agree data formats between components early. Assign a named teammate to each work area before starting; do not invent deadlines until availability and phase 1 results are known.
- Preserve the current source as a versioned visual reference. Keep sample data in an explicitly labeled demo mode, separate from real activity and results.

| Work area | Main responsibility |
| --- | --- |
| UI / desktop | Existing React design, desktop shell, tray, notifications, permissions, accessible interaction. |
| Capture / detection | Browser/file events, client matching, task boundaries, pattern evidence, savings measurement. |
| Backend / AI | Persistent state, API contracts, confirmed plans, cloud generation, approvals, workflow versions. |
| Runner / security / QA | Isolation, local/paired runners, independent tests, safe changes, recovery, cross-platform verification. |

**Dependency path:** prove feasibility → background foundation → real capture → detection → confirmed generation → verified testing → approved execution → platform/connector validation → registry → final release check.

After phase 1, teams may prepare UI components, synthetic fixtures, and the runner in parallel against agreed contracts. Integration still follows the gates above. Registry implementation waits for phase 8 completion.

## Mandatory safety requirements and proof

These requirements address the security review. They are future implementation work, not safeguards already present. Each responsible phase must record both a successful allowed case and a rejected abuse case; any unresolved failure blocks that capability. An unavailable optional connector need not block unrelated, tested features.

| ID / phase | Concern and required solution | Required proof |
| --- | --- | --- |
| **S1 · 6** | **Code must not grade itself.** Keep the trusted controller, expected results, and report-signing keys outside the generated-code environment. Judge bounded, structured outputs and independent enforcement evidence; guest logs are untrusted text. | Printing “PASS,” editing test files, returning forged results, or replaying another job's report cannot activate a workflow. |
| **S2 · 2, 10** | **Protect the desktop UI.** Enable Electron context isolation and renderer sandboxing, disable UI Node access, and restrict scripts, navigation, new windows, and external links. Expose only narrowly defined, sender-validated messages. Render model output, logs, and registry descriptions as untrusted text. | Malicious HTML/links in every content surface cannot execute privileged actions or obtain local secrets. |
| **S3 · 2, 6** | **Local does not mean trusted.** Bind the local API to loopback or a protected local channel; authenticate callers, validate origins/senders and request shapes, and authorize each operation/resource. Use unpredictable credentials outside webpage access; do not depend on browser CORS alone. | Unrelated webpages, missing credentials, incorrect origins, another OS user, and another runner user cannot read jobs or approve/run workflows. |
| **S4 · 3** | **Parsing happens before generated-code tests.** Allow only supported formats; bound compressed/uncompressed size, rows, cells, memory, and parsing time. Use a restricted parser process and prohibit external references, macros, network access, and formula execution. If the required restrictions cannot be enforced, disable that file connector. | Malformed and oversized workbooks, archive expansion attacks, macros, and external references are rejected without freezing the agent or accessing external resources. |
| **S5 · 7** | **Protect the actual destination.** Resolve permitted resources safely, reject path traversal and link/junction escapes, and validate target identity/version when opening and committing. Use platform-appropriate locks and safe replacement; a string prefix comparison is not permission enforcement. | Traversal, symlinks/junctions, and swapping a file between checking and writing cannot redirect an update. Concurrent changes cause a visible stop instead of overwrite. |
| **S6 · 6** | **Pair and revoke runner trust.** Confirm the first runner identity through a separate trusted pairing step; verify certificates and pin identity. Define credential rotation, expiry, unpairing, lost-device revocation, job ownership, and deny-by-default authorization. Never expose Docker administration access. | Impersonated runners, revoked/expired credentials, old pairings, cross-user job IDs, and mismatched reports fail. Revocation stops new operations and rejects pending results before application. |
| **S7 · 2–4, 6–7** | **Privacy includes secondary copies.** Apply retention, encryption, access controls, and deletion to snapshots, temp files, queued transfers, backups, logs, and crash reports. Cancel unsent transfers after revocation. Default desktop alerts contain no client details. Document backup/cloud-sync limits instead of claiming guaranteed physical erasure. | After deletion or crash recovery, expired data is not restored or retransmitted. Secrets/client content do not appear in lock-screen alerts, logs, reports, or model payloads. |
| **S8 · 1, 8–10** | **Pinned versions still need updates.** Inventory dependencies, images, connectors, and templates; scan/review changes, verify artifact integrity against a trusted source, and maintain patch/revalidation procedures. Block known unsafe versions. Paid public code signing is not a prerequisite for local development. | A tampered artifact or known blocked version cannot install/run; an approved update invalidates affected test/approval evidence and requires revalidation. |
| **S9 · 5–7** | **Instructions inside data grant no authority.** Documents, page text, templates, and model output cannot change allowed actions, recipients, permissions, approval state, or execution policy. Validate plans and each operation independently of the model; prompt filtering is supplementary. | Embedded “ignore the rules” content cannot cause extra reads, transfers, sends, permission changes, or activation—even if the model repeats the instruction. |
| **S10 · 9** | **Withdrawal and security revocation differ.** Ordinary withdrawal stops new imports. Known security revocations also block installed affected versions, including offline, until repaired and retested. Cache trusted version-status information and show when it was last checked; define a finite freshness policy in phase 1. | Registry outage cannot clear a known block. A replayed older status cannot restore a revoked version; an expired freshness allowance blocks the affected imported workflow with an explanation. |
| **S11 · 6–7** | **Permissions and outcomes can change during a run.** Recheck authorization at each effect and before applying results. Use durable business-effect identities, atomic duplicate claims, and an operation journal. Cancellation/revocation prevents new effects; uncertain external outcomes require reconciliation, not blind retry. | Simultaneous runs, crashes, queued work after revocation, and repeated callbacks cannot duplicate effects or apply results under withdrawn permissions. |

Phase 1 assigns an owner, concrete limits/policies, fixtures, and expected results to each requirement. Phase 10 reviews the recorded evidence; it does not defer implementing these controls until release. Reference guidance: [Electron security](https://www.electronjs.org/docs/latest/tutorial/security), [Docker resource limits](https://docs.docker.com/engine/containers/resource_constraints/), [OWASP file handling](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html), [authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html), and [prompt injection](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).

## Phase 1 — Prove feasibility and define contracts

**Target:** resolve the difficult assumptions before building around them.

**Status: In progress.** See [recorded evidence](docs/phase-1-status.md) and [initial contracts/limits](docs/contracts.md). Implemented: synthetic browser capture, CSV/XLSX comparison, event validation, and visual-reference capture. Remaining: human acceptance, teammate assignment/review, other OS/model access, and isolated local/paired tests. **Docker/paired testing is deferred at the user's request; its gate has not passed.**

**Work and outputs**

- Inventory available Windows/macOS/Linux test machines, a Docker-capable host, browser permissions, and free model access. Identify an existing computer for paired execution.
- Record reference screenshots of every React screen and important interaction state. Agree which visual elements remain stable and which labels need correction.
- Define the event format, workflow states, permission scopes, input/output specification, runner job/report format, and error responses.
- Prepare a sample client page, invented records, tracking-sheet structure, expected drafts, and deliberately invalid examples as future development fixtures.
- Prove permitted browser capture, saved-file comparison, and one harmless isolated job from a second endpoint without Docker.
- Define resource/time/output limits, supported file formats, risks, and the release support matrix. Pin and review dependency versions before implementation expands.
- Assign S1–S11 owners and test evidence; define parser/job limits, cleanup responsibilities, runner trust/revocation procedures, and imported-template status freshness before dependent phases begin.

| Complication | Planned response |
| --- | --- |
| No suitable runner host, denied installation, or blocked network pairing | Establish a permitted team/office host first. If unavailable, record execution as blocked; do not substitute direct Python execution. |
| Spreadsheet changes cannot be linked to a browser record | Require a confirmed client-ID field; ambiguous records cannot count toward detection. |
| No access to one target OS | Track it as unverified and obtain a test machine before claiming support. |
| Free model quota unavailable | Continue local development with clearly labeled test responses; live generation acceptance waits for actual access. |

**Completion gate:** real capture and comparison evidence, successful local/paired fixture runs, agreed contracts, a visual reference set, and a documented list of supported and unsupported features.

## Phase 2 — Build the background foundation

**Target:** the app runs independently of the visible dashboard and remembers its state.

**Work and outputs**

- Package the React interface with Electron while preserving its appearance; introduce the Python/FastAPI worker and SQLite storage.
- Add opt-in startup, tray status, Open dashboard, Pause observation, and Quit. Define how quitting handles active local and paired jobs.
- Persist settings, permission grants, notifications, workflow versions, approvals, and job history. Add protected storage and OS credential handling.
- Authenticate desktop-to-agent communication. Keep the UI separate from system permissions and execution decisions.
- Add monitoring/runner connection status, loading, empty, unavailable, and error states using the existing components.

**Complications and responses:** window closure must not stop the worker; restarting must not duplicate workers or revive revoked permissions. If secure storage is unavailable, explain the limitation instead of saving secrets in plain text. On reconnect, recover server state rather than assuming the last UI state is current.

**Completion gate:** close/reopen the window, restart the app, pause/revoke collection, and delete retained data successfully. Confirm no duplicate worker or silent background collection after revocation.

**Security gate:** pass S2/S3 desktop and local-API abuse tests and S7 storage/deletion tests. No sensitive persistence when secure storage is unavailable.

## Phase 3 — Collect real, attributable observations

**Target:** every displayed observation comes from a supported source and has a known meaning.

**Work and outputs**

- Add an allowlisted browser connector for the sample client page, a selected-folder watcher plus CSV/XLSX parser, and an in-app draft editor.
- Record real success signals. Compare stable saved spreadsheet versions by client ID; distinguish added/removed rows, changed fields, and harmless reordering.
- Emit the agreed event fields, including capture/processing times, source, client token, and ambiguity status. Remove duplicate notifications and AutoStack-generated events.
- Show available/paused/disconnected/error for each collector. Replace monitoring-terminal demo lines with these real events.

| Complication | Planned response |
| --- | --- |
| Temporary files, locks, delayed writes, or parser errors | Bounded settling/retries; show a gap instead of inventing an event. |
| Draft saved before spreadsheet parsing finishes | Preserve save-capture time and allow the README's initial five-second settling grace period. Unresolved order remains ambiguous. |
| Missing/duplicate IDs or concurrent client work | Flag the instance; start with one client at a time. |
| Private values accidentally enter logs | Redact by default; keep permitted content comparisons local and snapshots short-lived. |

**Completion gate:** a person performs the workflow and the system records its real steps. Negative cases do not become successful observations. Demonstrate that the watcher never claims live Excel edits or clipboard capture.

**Security gate:** pass S4 input/parser isolation and S7 redaction/cleanup tests before enabling file observation.

## Phase 4 — Detect patterns and notify with evidence

**Target:** explain why a repeated workflow was suggested.

**Work and outputs**

- Implement the README's ordered-sequence detector: automatic task boundaries, normalization, compatible resource/column matching, and duplicate exclusion.
- Begin with three completed, unambiguous instances across at least two sample clients. Ten inactive minutes mark an unfinished instance incomplete.
- Show occurrence counts, dates, steps, missing evidence, and user corrections. Remove fabricated percentage confidence and Jaccard claims.
- Add persistent dashboard notifications and permitted desktop alerts. Opening a notification takes the user to that candidate; suppress repeated alerts for an unchanged candidate.
- Estimate active manual effort and record user-confirmed frequency; display ranges and assumptions separately from measured savings.

**Complications and responses:** unrelated clicks, reordered actions, missing steps, and the app's own runs must not qualify. Do not infer a daily schedule from accelerated demonstrations. If desktop notifications are disabled, preserve the dashboard item. Missing evidence produces an incomplete/ambiguous result, not confident automation.

**Completion gate:** real positive examples trigger at the threshold; defined negative examples do not. Evaluate separate examples not used to tune the detector and record false suggestions/missed patterns with sample counts. Capture remains active while users browse other screens.

**Security gate:** S7 desktop notifications remain generic; opening details requires the authorized local user context.

## Phase 5 — Confirm business rules and generate a draft

**Target:** generate code for an explicit user-approved specification, with no execution yet.

**Work and outputs**

- Add a plan review covering client ID, field mappings, eligibility dates/status, append/update rules, duplicate handling, allowed destinations, and draft content.
- Show synthetic before/after examples. Missing or contradictory rules block generation.
- Connect a validated free-tier Gemini model through a replaceable provider adapter. Review/minimize model-bound context and keep keys out of React, prompts, code, and Git.
- Store the plan, structured model output, Python code, dependencies, requested operations, and version identity together.
- Add plain-language and code previews within the current card/detail-panel design. Distinguish draft, generating, invalid, and awaiting-test-approval states.

**Complications and responses:** generated code may be incorrect, malformed, or request extra access. Validate it and reject unsupported behavior. Cap repair attempts and preserve version history. Quota/network failures pause generation; retries must not incur paid usage or execute partial output. New input data inside an approved scope is a parameter; broader access or changed mappings require a new review.

**Completion gate:** a real model response produces a reviewable artifact tied to confirmed rules. Invalid output, secrets, missing fields, or extra permissions cannot progress to execution. Tests still use independent expected results, not only tests invented by the model.

**Security gate:** pass S9 malicious-input/plan validation and S7 model-payload inspection. No model response can mint a permission or approval.

## Phase 6 — Verify local and paired execution safely

**Target:** code can be tested only after approval, with enforceable isolation and trustworthy results.

**Work and outputs**

- Build local and paired Runner API modes. Pair identities, authenticate HTTPS connections, enforce per-user job ownership, and explain exactly what data leaves the endpoint.
- Follow the order: trusted runner-readiness fixtures → candidate static checks and test consent → isolated generated-code tests → passing report → separate activation approval. Runner readiness alone never approves a candidate.
- Verify isolation settings and resource limits before accepting a job. No generated-code network access, credentials, host directories, Docker controls, or arbitrary dependency installation.
- Run static checks plus independent functional/security tests. Cover malformed records, forbidden access, malicious instructions, resource exhaustion, duplicate outputs, and failure recovery.
- Bind reports to job, code, input, runtime, policy, and connector versions. Protect report integrity and reject stale or mismatched evidence.
- Replace sandbox animation with actual logs/test statuses. A failed or missing check keeps activation blocked; a failed test itself must not be presented as a successful workflow.
- Require a separate review and activation approval after the test suite passes.

| Complication | Planned response |
| --- | --- |
| No Docker on the endpoint | Use the explicitly paired team/office runner. |
| No available runner or isolation enforcement fails | Leave observation/review usable; disable testing and execution. |
| Disconnect, forged report, wrong version, or unauthorized job access | Reconcile state or reject the report/request; never infer success. |
| Sensitive data on a shared runner | Synthetic prototype data, explicit transfer consent, protected jobs, disclosed operator access, and retention/cleanup rules. |

**Completion gate:** good cases pass; hostile/broken cases fail closed. A no-Docker endpoint completes a consented sandbox test. Skipping UI steps or sending direct API requests cannot bypass approvals. Previously approved versions become invalid after relevant changes.

**Security gate:** pass S1 report/controller separation, S3 job authorization, S6 runner trust/revocation, S7 job-data cleanup, and S9/S11 policy enforcement. Verify actual CPU/memory/process/time/output limits and deny-network controls; configuration text alone is not evidence.

## Phase 7 — Run the first complete workflow

**Target:** a user can safely use the approved automation on a new sample batch.

**Work and outputs**

- Add Run now with selected inputs/run date inside approved permissions. Execute the tested version in the same isolation policy.
- Receive structured proposed edits/drafts. A trusted local component checks permitted files/columns, input versions, output sizes, and unsafe spreadsheet content before applying changes.
- Stage results, back up affected files, keep an operation journal, and record actual outcomes in Dashboard, Workflows, and Trust Log.
- Prevent duplicate business effects using client + purpose/date + destination and stored result IDs; code/input hashes alone are insufficient.
- Support cancellation, permission revocation, restart reconciliation, and clearly scoped recovery. Keep initial drafts in-app; never label them Sent.

**Complications and responses:** a file may change while the job runs, or a crash may occur between creating a draft and updating its row. Stop on conflicting input, reconcile the journal, and complete only verified unfinished operations. Edited input or a new code version must not recreate an existing effect. Explain completed actions when cancellation cannot undo them.

**Completion gate:** observe → detect → notify → confirm → generate → approve test → pass → approve activation → Run now → inspect output/history works on new sample data, locally and through a paired runner. Reruns, crashes, revocation, and disconnected runners do not silently duplicate effects or broaden access.

**Security gate:** pass S5 filesystem-race/escape tests and S11 concurrent-run/revocation tests. Validate real outputs independently of the runner report; the report is not permission to write arbitrary data.

## Phase 8 — Validate platforms and grow supported workflows

**Target:** prove cross-platform behavior and demonstrate reusable logic beyond one client example.

**Work and outputs**

- Test installation, sign-in startup, tray, notifications, permissions, file handling, paired execution, and recovery on Windows/macOS/Linux.
- Measure idle CPU/memory, capture overhead, queue sizes, and job limits against budgets agreed in phase 1. Batch work and bound logs/queues so background use stays practical.
- Handle denied OS permissions and unavailable connectors visibly. Package required assets so the UI remains readable offline; check the current externally loaded fonts.
- Add a second scoped office workflow, such as invoice/purchase-order comparison, using approved exports and independent expected outputs.
- Add Excel/email/browser integrations only with their own capability, authorization, account-cost, and failure checks. Test drafts before considering sends.

**Complications and responses:** platform APIs, file paths, certificate trust, and app availability differ. Publish a feature matrix instead of assuming parity. An unavailable government API does not become a fake verification; keep that step unsupported or use an explicitly labeled sample source. Account-based or paid integrations cannot become mandatory for the free core demo.

**Completion gate:** the core journey works on each target OS using a supported local or paired runner. The second workflow passes its own tests. Resource measurements and known connector limits are documented. Registry work may now begin.

**Security gate:** verify platform-specific enforcement of S2–S8 and rehearse S8 update/rollback/revalidation using trusted development artifacts. Security settings that silently do nothing on a target OS do not pass.

## Phase 9 — Implement the shared registry

**Target:** another office can reuse a template without receiving private data or inheriting approval.

**Work and outputs**

- Add an authenticated registry API and template database; use a team-hosted development database to avoid mandatory hosting fees.
- Require separate publication consent and checks for records, credentials, private paths, and confidential examples hidden in code/schema.
- Store versioned logic, parameters, synthetic examples, compatible connectors, and environment-specific test evidence. Add ownership, review, withdrawal, and update handling.
- Connect the existing Registry search/cards/details and Use Workflow button to actual templates. Base recommendations on declared needs and compatibility; avoid unexplained match percentages.
- On import, require local mappings, permissions, synthetic tests, and activation approval. Template updates never silently replace an approved version.

**Complications and responses:** a template may be malicious, outdated, or incompatible with another office's columns. Treat imports as untrusted drafts and retest. Registry outages allow installed workflows only within the agreed status-freshness policy; they never clear a known security revocation. Ordinary withdrawal stops new imports without automatically invalidating safe installed copies. Do not populate invented ratings, office counts, or savings as live metrics.

**Completion gate:** two independent installations publish and adapt one template with different column mappings. Private records stay out of the registry; permissions/approval are not inherited; withdrawal, version updates, and rejected imports behave correctly.

**Security gate:** pass S8 template integrity/update checks and S10 withdrawal/revocation/offline cases; repeat S2/S3/S9 tests with registry content and users.

## Phase 10 — Final integration and visual acceptance

**Target:** deliver the current React design with real, coherent behavior across every screen.

| Existing screen | Final functional acceptance |
| --- | --- |
| Dashboard | Actual monitoring/runner status, persistent notifications, recent runs, and clearly labeled estimated/measured savings. Charts use recorded data and honest empty states. |
| Discovery | Real detected candidates, occurrence evidence, supported steps, ambiguity indicators, review/dismiss controls, and navigation to the correct plan. |
| Create Automation | Keep the guided stepper and terminal/test layout. Group the flow into context/permissions; observation/candidate selection; confirmed plan/generation; approved sandbox testing; review/activation. Publication is separate. Backend gates cannot be bypassed by clicking ahead. |
| Workflows | Persisted versions, accurate approval/test status, input selection, Run now, history, cancellation, permissions, and supported recovery. |
| Trust Log | Real redacted, linked records for tests, approvals, executions, failures, and recovery; selecting a workflow filters to its actual evidence. |
| Registry | Live searchable templates, compatibility details, working import/adapt/test flow, and honest usage information. |

**Visual checks:** compare with phase 1 reference screenshots at the same window sizes. Preserve sidebar structure, spacing, colors, typography, cards, tables, badges, and terminal styling. Additional controls must look native to that design. Check keyboard navigation, readable status text, window resizing, long workflow names, empty lists, and errors. A necessary truthful label change is acceptable; replacing the interface with a different design is not the target.

**Integration complications:** screens may disagree about state, show stale success, lose data after navigation, or accidentally mix fixtures with live events. Use one authoritative backend state, refresh/reconnect handling, consistent workflow/version IDs, and clear demo/live separation. Reopening the UI must reconstruct state without restarting observation or rerunning jobs.

**Final completion checklist**

- [ ] All six screens meet the mapping above and retain the existing visual identity.
- [ ] The complete first workflow succeeds through real observation, detection, generation, testing, approvals, execution, and audit.
- [ ] A second office workflow and registry reuse are demonstrated with independent expected results.
- [ ] Local and no-Docker paired execution pass, including unavailable-runner and disconnect cases.
- [ ] All three target OS clients have recorded results; unsupported optional integrations are clearly identified.
- [ ] Security failures, quota exhaustion, revoked permission, schema drift, concurrent edits, and restart/retry behavior are demonstrated.
- [ ] S1–S11 have owners and passing evidence on their declared platforms; unsupported or failing capabilities remain disabled.
- [ ] No normal screen represents simulated data as real success; no placeholder action suggests a capability it lacks.
- [ ] Free development has no mandatory paid service or silent billing path; real client data is absent from demo/cloud prompts.
- [ ] README setup, supported features, test evidence, recovery limits, and this plan's phase statuses are updated.

## Keeping the plan honest

Record an owner, status, evidence, known limitations, and next dependency for each phase as work begins. Use **Not started / In progress / Blocked / Passed**; a blocked gate stays blocked until evidence resolves it.

Keep national rollout, additional Indian-office examples, scheduling, approximate pattern matching, and sensitive production deployment as explicitly scoped follow-up work. Finishing this plan means a working, tested product for the declared supported workflows—not universal automation, unlimited free cloud capacity, or guaranteed security on every office computer.

*Prepared: 19 September 2026. Safety requirements and Phase 1 status revised: 20 September 2026. Only capabilities with recorded phase evidence count as implemented.*
