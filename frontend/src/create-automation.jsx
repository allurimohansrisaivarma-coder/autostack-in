// CreateAutomation — REAL backend-gated stepper (Phase 10).
// plan → generate → sandbox test → activation → bind → (optional) publish.
// Every gate is a real worker call that fails closed; the UI never fakes progress.
import React, { useState, useEffect } from 'react';
import { api } from './api.js';
import { subscribeLive, capturePoll } from './live.js';
import { Icon, ICONS, Terminal, stamp } from './main-shared.jsx';

export function CreateAutomation({ setPage }) {
  // Entry mode: 'step' = existing guided flow; 'ai' = autopilot (goal → plan →
  // sandbox → approve-at-create). Both preserve the 5-step visual flow.
  const [mode, setMode] = useState(null); // null = chooser not answered
  const [step, setStep] = useState(1);
  const [live, setLive] = useState(null);
  useEffect(() => subscribeLive(setLive), []);

  // Step 2: real capture polling against the worker (honest failures included).
  const [monitoring, setMonitoring] = useState(false);
  const [monitorLines, setMonitorLines] = useState([]);
  const [eventCount, setEventCount] = useState(0);

  // Step 3: confirmed plan (the only source of eligibility truth).
  const [candidateId, setCandidateId] = useState(null);
  const [statusVal, setStatusVal] = useState('Follow-up due');
  const [dateVal, setDateVal] = useState('2026-09-20');
  const [actionSel, setActionSel] = useState('create_draft');
  const [notifySel, setNotifySel] = useState(true);
  const [planId, setPlanId] = useState(null);
  const [planMissing, setPlanMissing] = useState([]);

  // Step 4: generation → isolated test → activation approval.
  const [artifact, setArtifact] = useState(null);
  const [job, setJob] = useState(null);
  const [approval, setApproval] = useState(null);

  // Step 5: binding to a versioned workflow (+ optional publish).
  const [bound, setBound] = useState(null);
  const [published, setPublished] = useState(false);

  // Step 1 context (org type → size → department → process type), from the
  // worker's catalog — never a hardcoded UI list. "Other" is free text.
  // Expanded subsections: connectors, tool categories, trigger preference,
  // sensitivity note, target outcome (all stored with the workflow context).
  const [catalog, setCatalog] = useState(null);
  const [ctxOrgType, setCtxOrgType] = useState('corporate');
  const [ctxSize, setCtxSize] = useState('medium');
  const [ctxDept, setCtxDept] = useState('finance');
  const [ctxProcess, setCtxProcess] = useState('accounts_payable');
  const [ctxOther, setCtxOther] = useState('');
  const [ctxConnectors, setCtxConnectors] = useState([]);
  const [ctxTools, setCtxTools] = useState([]);
  const [ctxTrigger, setCtxTrigger] = useState('manual');
  const [ctxSensitivity, setCtxSensitivity] = useState('');
  const [ctxOutcome, setCtxOutcome] = useState('');
  const [connectors, setConnectors] = useState(null);
  const [nodes, setNodes] = useState(null);
  useEffect(() => { api.orgCatalog().then(setCatalog).catch(() => setCatalog(null)); }, []);
  useEffect(() => { api.connectors().then(setConnectors).catch(() => setConnectors(null)); }, []);
  // Node catalog: the worker's own validated node set — drives the capability
  // chips in step 4 so the UI can never advertise a node the executor refuses.
  useEffect(() => { api.nodeCatalog().then(setNodes).catch(() => setNodes(null)); }, []);

  // Reset downstream selections whenever an upstream context choice changes.
  useEffect(() => {
    if (!catalog) return;
    if (!catalog.sizes_for_type[ctxOrgType]?.includes(ctxSize)) setCtxSize(catalog.sizes_for_type[ctxOrgType]?.[0] || 'small');
  }, [ctxOrgType]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!catalog) return;
    if (!catalog.departments[ctxOrgType]?.includes(ctxDept)) setCtxDept(catalog.departments[ctxOrgType]?.[0] || '');
  }, [ctxOrgType]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!catalog) return;
    const allowed = catalog.process_types[ctxDept] || catalog.default_process_types;
    if (!allowed.includes(ctxProcess)) setCtxProcess(allowed[0] || '');
  }, [ctxDept, ctxOrgType]); // eslint-disable-line react-hooks/exhaustive-deps

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const connected = !!(live && live.connected);
  const realCands = ((live && live.candidates) || []).filter(c => c.status === 'suggested');

  const pushLine = (kind, text) =>
    setMonitorLines(prev => [...prev, { ts: stamp(), kind, text }].slice(-80));

  useEffect(() => {
    if (!monitoring) return undefined;
    const id = setInterval(async () => {
      try {
        const res = await capturePoll();
        if (res) {
          setEventCount(n => n + (res.accepted || 0));
          pushLine(res.accepted ? 'ok' : 'dim',
            `capture.poll    accepted=${res.accepted} dup=${res.duplicates_skipped} gaps=${(res.gaps || []).length}`);
        }
      } catch (e) {
        pushLine('warn', `capture.poll failed: ${e.message} — worker offline; nothing invented`);
      }
    }, 2500);
    return () => clearInterval(id);
  }, [monitoring]);

  const buildPlan = () => ({
    client_id_field: 'ClientID',
    field_mappings: { Name: 'Name', FollowUpDate: 'FollowUpDate' },
    eligibility: { status: statusVal, status_field: 'Status',
                   date_field: 'FollowUpDate', date_value: dateVal },
    action: actionSel,
    destinations: notifySel ? ['in_app', 'desktop_notification'] : ['in_app'],
  });

  const gate = async (fn, okMsg) => {
    setBusy(true); setErr(null);
    try {
      const out = await fn();
      if (okMsg) pushLine('ok', typeof okMsg === 'function' ? okMsg(out) : okMsg);
      return out;
    } catch (e) {
      setErr(e.message);
      pushLine('fail', `gate refused: ${e.message}`);
      return null;
    } finally {
      setBusy(false);
    }
  };

  const savePlan = () => gate(async () => {
    const res = await api.createPlan(buildPlan(),
      candidateId && candidateId.startsWith('real-') ? candidateId.slice(5) : null);
    if (!res.generatable) {
      setPlanMissing(res.missing_rules || []);
      throw new Error(`plan incomplete: ${(res.missing_rules || []).join(', ')}`);
    }
    setPlanMissing([]);
    setPlanId(res.plan_id);
    setStep(4);
    return res;
  }, r => `plan accepted  sha=${(r.plan_sha256 || '').slice(0, 12)}`);

  const generate = () => gate(async () => {
    const art = await api.generate(planId);
    if (art.violations && art.violations.length) {
      throw new Error(`static validation: ${art.violations.join('; ')}`);
    }
    setArtifact(art);
    return art;
  }, a => `artifact generated  sha=${(a.code_sha256 || '').slice(0, 12)}`);

  const runTest = () => gate(async () => {
    const j = await api.createTestJob(artifact.artifact_id, true);
    setJob(j);
    if (j.status !== 'passed') {
      throw new Error(`isolated test ${j.status} — activation stays blocked`);
    }
    return j;
  }, 'isolated test passed (subprocess sandbox, plan-derived expected outputs)');

  const approve = () => gate(async () => {
    const a = await api.approveActivation(artifact.artifact_id, job && job.job_id);
    setApproval(a);
    return a;
  }, 'human activation approval recorded');

  const buildContext = () => ({
    org_type: ctxOrgType,
    size: ctxSize,
    department: ctxDept,
    process_type: ctxOther.trim() ? ctxOther.trim().toLowerCase().replace(/\s+/g, '_') : ctxProcess,
    connectors: ctxConnectors,
    tools: ctxTools,
    trigger: ctxTrigger,
    sensitivity_note: ctxSensitivity.trim(),
    outcome: ctxOutcome.trim(),
  });

  const bind = () => gate(async () => {
    const b = await api.createWorkflowFromPlan(planId, buildContext());
    setBound(b);
    return b;
  }, b => `workflow ${b.workflow_id} v${b.version} bound to plan + activated code`);

  // Operators (and below) cannot create live workflows: their work is proposed
  // as a change request for an owner/admin to review and merge (PR-style).
  const submitChangeRequest = () => gate(async () => {
    const ctx = buildContext();
    const res = await api.openChangeRequest({
      kind: 'workflow_create',
      title: ctxOther.trim() ? ctxOther.trim() : `Client follow-up (${ctx.department})`,
      summary: ctx.outcome || 'submitted from the Create Automation flow',
      target_workflow_id: null,
      payload: { plan_id: planId, artifact_id: artifact && artifact.artifact_id,
                 job_id: job && job.job_id, ...ctx },
    });
    setBound({ change_request: res.id, status: res.status });
    return res;
  }, r => `change request ${r.id} opened — an owner/admin will review it`);

  // ── AI autopilot (full workflow) ──────────────────────────────────────────
  const [aiGoal, setAiGoal] = useState('');
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState(null);
  const [aiResult, setAiResult] = useState(null);
  const [aiApproved, setAiApproved] = useState(null);
  const [aiBound, setAiBound] = useState(null);
  const [aiCR, setAiCR] = useState(null);
  const [toolsBrowser, setToolsBrowser] = useState(null);
  const [toolsSearch, setToolsSearch] = useState('');

  const runAutopilot = () => gateAI(async () => {
    const res = await api.aiAutopilot({
      goal: aiGoal.trim() || 'draft client follow-ups for overdue accounts',
      org_type: ctxOrgType, size: ctxSize, department: ctxDept,
      process_type: ctxOther.trim() ? ctxOther.trim().toLowerCase().replace(/\s+/g, '_') : ctxProcess,
      connectors: ctxConnectors, tools: ctxTools, trigger: ctxTrigger,
      sensitivity_note: ctxSensitivity.trim(), outcome: ctxOutcome.trim(),
      status_val: statusVal, date_val: dateVal, action: actionSel, notify: notifySel,
    });
    setAiResult(res);
    return res;
  }, r => `autopilot finished — sandbox ${r.sandbox.result_class}${r.sandbox.repaired ? ' (after repair)' : ''}`);

  const gateAI = async (fn, okMsg) => {
    setAiBusy(true); setAiErr(null);
    try {
      const out = await fn();
      if (okMsg) pushLine('ok', typeof okMsg === 'function' ? okMsg(out) : okMsg);
      return out;
    } catch (e) {
      setAiErr(e.message);
      pushLine('fail', `autopilot refused: ${e.message}`);
      return null;
    } finally {
      setAiBusy(false);
    }
  };

  // Approve-at-create on the autopilot result: same activation endpoint as
  // the Verify step, then bind in-session. Owner/admin only (backend enforced).
  const approveAutopilotNow = () => gateAI(async () => {
    if (!aiResult || aiResult.sandbox.result_class !== 'passed') throw new Error('sandbox must be passed before approval');
    const a = await api.approveActivation(aiResult.artifact_id, aiResult.job_id);
    setAiApproved(a);
    const b = await api.createWorkflowFromPlan(aiResult.plan_id, aiResult.context);
    setAiBound(b);
    return b;
  }, b => `activated + bound: workflow ${b.workflow_id} v${b.version}`);

  // Operator path for the autopilot result: a change request carrying the
  // sandbox-passed evidence (nothing is activated or bound by the operator).
  const autopilotToCR = () => gateAI(async () => {
    const res = await api.openChangeRequest({
      kind: 'workflow_create',
      title: `Autopilot: ${aiGoal.trim().slice(0, 80) || 'client follow-ups'}`,
      summary: aiResult ? aiResult.note : 'autopilot result',
      target_workflow_id: null,
      payload: aiResult ? { plan_id: aiResult.plan_id, artifact_id: aiResult.artifact_id,
                            job_id: aiResult.job_id, ...aiResult.context } : {},
    });
    setAiCR(res);
    return res;
  }, r => `change request ${r.id} opened with the autopilot evidence`);

  const loadTools = async (search) => {
    try { setToolsBrowser(await api.tools({ search: search ?? toolsSearch, limit: 60 })); }
    catch (e) { setAiErr(e.message); }
  };

  const publish = () => gate(async () => {
    if (!bound) throw new Error('bind the workflow first');
    await api.registryPublish({
      slug: `client-followup-${planId.slice(0, 6)}`,
      title: `Client follow-up (${actionSel === 'update_status' ? 'status update' : 'drafts'})`,
      graph: bound.graph,
      compatible_connectors: ['sample-tracking-file'],
      publication_consent: true,
    });
    setPublished(true);
  }, 'published to registry (schema only, no records)');

  // Role awareness: plan/generate/bind are operator+; sandbox test + activation
  // approval are approver+ (backend enforces; the UI mirrors honestly). The
  // bind button checks server state (activation), not local session state, so
  // an operator can bind after an approver activates — the real team flow.
  const role = (live && live.me && live.me.role) || null;
  // Redesigned RBAC: owner/admin co-equal; operator proposes via change
  // requests; approver tests/activates. The backend re-checks every gate.
  const rank = { observer: 0, operator: 1, approver: 2, admin: 3, owner: 4 }[role] ?? null;
  const canPlan = rank === null || rank >= 1;
  const canApprove = rank === null || rank >= 2;
  const canBind = rank === null || rank >= 3;   // owner/admin create live workflows
  const canPublish = rank === null || rank >= 3;
  const isReviewer = rank !== null && rank >= 3;

  // Human-readable labels for the context summary chips.
  const ctxLabel = (kind, v) => (catalog && catalog.labels?.[kind]?.[v]) || String(v || '—').replace(/_/g, ' ');

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Create Automation</div>
          <h2>Create New Automation</h2>
        </div>
        <span className={`badge ${connected ? 'green' : 'orange'}`}>{connected ? 'Worker: LIVE' : 'Worker offline — gates locked'}</span>
      </div>

      {mode === null && (
        <div className="card create-flow-card">
          <h3>How do you want to build this?</h3>
          <p className="muted">Both paths end at the same gates: sandbox first, human approval before anything goes live.</p>
          <div className="publish-actions" style={{ flexWrap: 'wrap' }}>
            <button className="btn-primary" onClick={() => { setMode('ai'); setStep(1); }}>
              <Icon d={ICONS.zap} size={16} /> Build with AI (full workflow)
            </button>
            <button className="btn-outline" onClick={() => { setMode('step'); }}>
              Build step by step
            </button>
          </div>
          <p className="muted small">{role ? `Your role: ${role}.` : 'Checking your role…'} {role && !['owner', 'admin'].includes(role) && 'Your result will be submitted as a change request for an owner/admin to review.'}</p>
        </div>
      )}

      {mode === 'ai' && (
        <div className="card create-flow-card">
          <div className="step-head-row">
            <div>
              <h3>AI autopilot — full workflow</h3>
              <p>Describe the goal. The worker retrieves allowlisted tools from the registry (top-k, never the whole catalog), proposes the plan, generates, and runs the sandbox. <b>Nothing activates</b> until you approve below.</p>
            </div>
            <button className="btn-outline" onClick={() => { setMode('step'); }}>Switch to step-by-step</button>
          </div>
          <div className="form-grid">
            <label>Goal (natural language)
              <input placeholder="e.g. draft follow-up reminders for clients with overdue reviews and update the tracker"
                     value={aiGoal} onChange={e => setAiGoal(e.target.value)} />
            </label>
          </div>
          <div className="ctx-summary" style={{ marginTop: 10 }}>
            <div className="detail-label">Context hints (from step 1 — adjust there)</div>
            <div className="tag-row">
              <span className="tag">{ctxLabel('org_type', ctxOrgType)}</span>
              <span className="tag">{ctxLabel('department', ctxDept)}</span>
              {ctxConnectors.length > 0 && <span className="tag">connectors: {ctxConnectors.join(', ')}</span>}
              {ctxTrigger && <span className="tag">trigger: {ctxTrigger}</span>}
            </div>
          </div>
          <div className="publish-actions">
            <button className="btn-primary" disabled={aiBusy || !connected} onClick={runAutopilot}>
              <Icon d={ICONS.zap} size={16} /> {aiBusy ? 'Building…' : 'Build my workflow'}
            </button>
            <button className="btn-outline" disabled={aiBusy} onClick={() => loadTools()}>Browse tool registry</button>
          </div>
          {toolsBrowser && (
            <div className="detail-section" style={{ marginTop: 12 }}>
              <div className="detail-label">Tool registry ({toolsBrowser.total} tools — search, filters, pagination)</div>
              <div className="field"><input placeholder="search tools…" value={toolsSearch}
                     onChange={e => { setToolsSearch(e.target.value); loadTools(e.target.value); }} /></div>
              <div className="node-catalog">
                {toolsBrowser.tools.map(t => (
                  <span key={t.id} className="node-chip" title={`${t.category} · risk: ${t.risk} · ${JSON.stringify(t.sandbox_policy)}`}>
                    <span className="node-type mono">{t.id}</span>
                    <span className="muted small"> {t.status}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {aiErr && <p className="helper-error">{aiErr}</p>}
          {aiResult && (
            <div className="detail-section" style={{ marginTop: 12 }}>
              <div className="detail-label">Autopilot result</div>
              <div className="tag-row">
                <span className="tag">plan {aiResult.plan_id.slice(0, 8)}…</span>
                <span className="tag">sandbox: {aiResult.sandbox.result_class}{aiResult.sandbox.repaired ? ' (repaired)' : ''}</span>
                {aiResult.retrieved_tools.slice(0, 4).map(t => <span key={t} className="tag mono">{t.replace('native:', '')}</span>)}
              </div>
              <p className="muted small">{aiResult.note}</p>
              {aiResult.sandbox.result_class === 'passed' && isReviewer && (
                <div className="publish-actions">
                  <button className="btn-primary" disabled={aiBusy || !!aiBound} onClick={approveAutopilotNow}>
                    <Icon d={ICONS.check} size={16} /> Approve activation now
                  </button>
                  {!aiBound && <span className="muted small">activates this artifact under the confirmed plan, then binds — in one consent</span>}
                </div>
              )}
              {aiResult.sandbox.result_class === 'passed' && !isReviewer && (
                <div className="publish-actions">
                  <button className="btn-outline" disabled={aiBusy || !!aiCR} onClick={autopilotToCR}>Submit as change request</button>
                  <span className="muted small">owner/admin review required — you cannot activate directly</span>
                </div>
              )}
              {aiResult.sandbox.result_class === 'failed_infra' && (
                <p className="muted small">Infra failure — use “Build my workflow” to retry; the code is not blamed.</p>
              )}
              {aiResult.sandbox.result_class === 'failed_assertion' && (
                <p className="muted small">One repair loop was attempted; the result above is final — adjust the plan and retry.</p>
              )}
              {aiBound && (
                <div className="publish-actions">
                  <span className="badge green">Bound: {aiBound.workflow_id} v{aiBound.version}</span>
                  <button className="btn-dark" onClick={() => setPage('workflows')}>Go to Workflows</button>
                </div>
              )}
              {aiCR && <span className="badge orange">Change request {aiCR.id.slice(0, 8)}… opened</span>}
            </div>
          )}
        </div>
      )}

      {mode !== 'ai' && (
      <div className="card create-flow-card">
        <div className="stepper-row">
          {['Context', 'Capture', 'Plan', 'Verify', 'Bind & Publish'].map((title, index) => {
            const current = index + 1;
            const stateClass = current < step ? 'done' : current === step ? 'active' : 'todo';
            return (
              <button key={title} className={`step-item ${stateClass}`} onClick={() => setStep(current)}>
                <span>{current}</span>
                <p>{title}</p>
              </button>
            );
          })}
        </div>

        {step === 1 && (
          <div className="step-panel">
            <h3>Know your workflow context</h3>
            <p>Context only — the plan rules themselves are confirmed in step 3. The organization type drives the departments and process types offered; this classification is stored on the workflow.</p>
            {catalog ? (
              <div className="form-grid">
                <label>Organization type
                  <select value={ctxOrgType} onChange={e => setCtxOrgType(e.target.value)}>
                    {catalog.org_types.map(t => (
                      <option key={t} value={t}>{catalog.labels.org_type[t] || t}</option>
                    ))}
                  </select>
                </label>
                <label>Size
                  <select value={ctxSize} onChange={e => setCtxSize(e.target.value)} disabled={catalog.sizes_for_type[ctxOrgType]?.length === 1}>
                    {(catalog.sizes_for_type[ctxOrgType] || []).map(s => (
                      <option key={s} value={s}>{catalog.labels.size[s] || s}</option>
                    ))}
                  </select>
                </label>
                <label>Team / Department
                  <select value={ctxDept} onChange={e => setCtxDept(e.target.value)}>
                    {(catalog.departments[ctxOrgType] || []).map(d => (
                      <option key={d} value={d}>{catalog.labels.department[d] || d}</option>
                    ))}
                  </select>
                </label>
                <label>Process type
                  <select value={ctxProcess} onChange={e => setCtxProcess(e.target.value)} disabled={!!ctxOther.trim()}>
                    {(catalog.process_types[ctxDept] || catalog.default_process_types).map(p => (
                      <option key={p} value={p}>{catalog.labels.process_type[p] || p}</option>
                    ))}
                  </select>
                </label>
                <label>Other process type (optional — overrides the list)
                  <input placeholder="e.g. booth allocation for a fair" value={ctxOther}
                         onChange={e => setCtxOther(e.target.value)} />
                </label>
              </div>
            ) : (
              <p className="muted">Loading the organization catalog from the worker… (context selectors appear once it loads)</p>
            )}

            {/* ── Expanded context subsections (worker-sourced, honest) ── */}
            {catalog && (
              <div className="detail-section" style={{ marginTop: 14 }}>
                <div className="detail-label">Connectors to use (scopes the tools offered later)</div>
                {!connectors ? (
                  <p className="muted">Loading the connectors inventory from the worker…</p>
                ) : (
                  <div className="tag-row">
                    {connectors.connectors.filter(c => c.status === 'supported' || c.status === 'limited').map(c => {
                      const on = ctxConnectors.includes(c.id);
                      return (
                        <button key={c.id} className={`tag ${on ? 'sel' : ''}`} title={`${c.status}: ${c.can_see || c.detail || ''}`}
                                style={{ cursor: 'pointer', borderColor: on ? '#2563EB' : undefined }}
                                onClick={() => setCtxConnectors(on ? ctxConnectors.filter(x => x !== c.id) : [...ctxConnectors, c.id])}>
                          {c.name} · {c.status}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
            {catalog && catalog.tool_categories && (
              <div className="detail-section" style={{ marginTop: 14 }}>
                <div className="detail-label">Tool / node categories needed</div>
                <div className="tag-row">
                  {catalog.tool_categories.map(t => {
                    const on = ctxTools.includes(t.id);
                    return (
                      <button key={t.id} className={`tag ${on ? 'sel' : ''}`} title={t.label}
                              style={{ cursor: 'pointer', borderColor: on ? '#2563EB' : undefined }}
                              onClick={() => setCtxTools(on ? ctxTools.filter(x => x !== t.id) : [...ctxTools, t.id])}>
                        {t.id}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            <div className="form-grid" style={{ marginTop: 14 }}>
              <label>Trigger preference
                <select value={ctxTrigger} onChange={e => setCtxTrigger(e.target.value)}>
                  {(catalog?.trigger_options || []).map(t => (
                    <option key={t.id} value={t.id} disabled={t.status !== 'supported'}>
                      {t.label}{t.status !== 'supported' ? ' (unavailable)' : ''}
                    </option>
                  ))}
                </select>
              </label>
              <label>Data sensitivity / compliance note (optional)
                <input placeholder="e.g. contains client PII — internal only" value={ctxSensitivity}
                       onChange={e => setCtxSensitivity(e.target.value)} maxLength={200} />
              </label>
              <label>Target outcome (what success looks like)
                <input placeholder="e.g. zero missed follow-ups; drafts ready same day" value={ctxOutcome}
                       onChange={e => setCtxOutcome(e.target.value)} maxLength={200} />
              </label>
            </div>
            <div className="ctx-summary" style={{ marginTop: 16 }}>
              <div className="detail-label">Context summary (stored on the workflow)</div>
              <div className="tag-row">
                <span className="tag">{ctxLabel('org_type', ctxOrgType)}</span>
                <span className="tag">{ctxLabel('size', ctxSize)}</span>
                <span className="tag">{ctxLabel('department', ctxDept)}</span>
                <span className="tag">{ctxOther.trim() ? ctxOther.trim() : ctxLabel('process_type', ctxProcess)}</span>
                {ctxConnectors.length > 0 && <span className="tag">connectors: {ctxConnectors.join(', ')}</span>}
                {ctxTools.length > 0 && <span className="tag">tools: {ctxTools.join(', ')}</span>}
                {ctxTrigger && <span className="tag">trigger: {ctxTrigger}</span>}
                {ctxSensitivity.trim() && <span className="tag">sensitivity: {ctxSensitivity.trim()}</span>}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Live capture while you work</h3>
                <p>{connected
                  ? 'Polling the real watched folder. Saved + settled file changes produce contract-validated events; gaps are shown honestly.'
                  : 'The worker is offline, so capture is not running. Start the stack to observe real files — nothing is simulated here.'}</p>
              </div>
              <div className="monitor-actions">
                {!monitoring
                  ? <button className="btn-primary" onClick={() => { setMonitoring(true); if (!connected) pushLine('warn', 'worker offline — polls will fail honestly'); }}><Icon d={ICONS.eye} size={16} /> Start monitoring</button>
                  : <button className="btn-dark" onClick={() => setMonitoring(false)}>Pause capture</button>}
              </div>
            </div>
            <div className="stat-pair" style={{ marginBottom: 14 }}>
              <div className="stat-box"><div className="stat-val">{eventCount}</div><div className="stat-lbl">Events accepted</div></div>
              <div className="stat-box"><div className="stat-val">{realCands.length}</div><div className="stat-lbl">Real candidates</div></div>
            </div>
            <Terminal title="autostack-capture — /api/capture/poll (real)" lines={monitorLines} running={monitoring} />
          </div>
        )}

        {step === 3 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Confirm the plan</h3>
                <p>The plan is the only source of truth for generation and testing. Missing or contradictory rules block generation — no defaults are invented.</p>
              </div>
            </div>
            <div className="form-grid">
              <label>Eligibility status
                <select value={statusVal} onChange={e => setStatusVal(e.target.value)}>
                  <option>Follow-up due</option><option>New</option>
                </select>
              </label>
              <label>Due on or before
                <input type="date" value={dateVal} onChange={e => setDateVal(e.target.value)} />
              </label>
              <label>Action
                <select value={actionSel} onChange={e => setActionSel(e.target.value)}>
                  <option value="create_draft">Prepare in-app drafts</option>
                  <option value="update_status">Update tracking status</option>
                </select>
              </label>
              <label>Notify
                <select value={notifySel ? 'yes' : 'no'} onChange={e => setNotifySel(e.target.value === 'yes')}>
                  <option value="yes">Desktop + in-app</option>
                  <option value="no">In-app only</option>
                </select>
              </label>
            </div>
            <div className="detail-section">
              <div className="detail-label">Linked candidate (evidence-based, optional)</div>
              {realCands.length === 0
                ? <p className="op-sub">No live evidence-based candidates yet — the plan stands on its own confirmed rules.</p>
                : <div className="tag-row">
                    {realCands.map(c => (
                      <button key={c.id} className="tag" style={{ cursor: 'pointer',
                        borderColor: candidateId === `real-${c.id}` ? '#2563EB' : undefined }}
                        onClick={() => setCandidateId(candidateId === `real-${c.id}` ? null : `real-${c.id}`)}>
                        {((c.pattern && c.pattern.sequence) || []).join(' → ')} · {c.occurrences}×
                      </button>
                    ))}
                  </div>}
            </div>
            <div className="publish-actions">
              <button className="btn-primary" disabled={busy || !connected || !canPlan}
                      title={canPlan ? '' : 'creating workflows requires the operator role'} onClick={savePlan}>
                <Icon d={ICONS.check} size={16} /> {busy ? 'Saving…' : 'Confirm plan'}
              </button>
            </div>
            {planMissing.length > 0 && <p className="helper-error">Missing rules: {planMissing.join(', ')}</p>}
          </div>
        )}

        {step === 4 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Generate, test in isolation, approve</h3>
                <p>Generated code passes static security validation, then runs in a subprocess sandbox against expected outputs derived from YOUR plan. A failed test blocks activation. Your approval is recorded separately.</p>
              </div>
            </div>
            {!canApprove && (
              <div className="info-banner">
                <Icon d={ICONS.lock} size={16} />
                <span>Sandbox testing and activation approval need the <b>approver</b> role — an operator generates code and an approver takes over from step 4. Your role: <b>{role || 'unknown'}</b>.</span>
              </div>
            )}
            <div className="test-rail">
              {[
                ['Plan confirmed', !!planId, 'sha-bound'],
                ['Generated + static validation', !!artifact, artifact ? artifact.code_sha256.slice(0, 12) : 'awaiting generate'],
                ['Isolated sandbox test', !!(job && job.status === 'passed'), job ? `job ${job.status}` : 'consent-gated'],
                ['Human activation approval', !!approval, approval ? 'recorded' : 'required'],
              ].map(([label, ok, sub], i) => (
                <div key={label} className={`rail-row ${ok ? 'pass' : busy ? 'run' : 'wait'}`}>
                  <span className="rail-idx">{String(i + 1).padStart(2, '0')}</span>
                  <span className="rail-name">{label}<br /><span className="op-sub">{sub}</span></span>
                  <span className="rail-st">{ok ? 'PASS' : busy ? 'RUN' : '—'}</span>
                </div>
              ))}
            </div>
            {nodes && nodes.nodes && (
              <div className="detail-section">
                <div className="detail-label">Worker node catalog ({nodes.nodes.length} types — validated at bind time)</div>
                {/* Grouped by the catalog's own group field — n8n-style capability
                    surface driven by the SAME source the validator enforces. */}
                {(() => {
                  const groups = [];
                  for (const n of nodes.nodes) {
                    const g = n.group || 'Other';
                    if (!groups.includes(g)) groups.push(g);
                  }
                  return groups.map(g => (
                    <div key={g} style={{ marginBottom: 10 }}>
                      <div className="node-group" style={{ marginBottom: 6 }}>{g}</div>
                      <div className="node-catalog">
                        {nodes.nodes.filter(n => (n.group || 'Other') === g).map(n => (
                          <span key={n.type} className="node-chip" title={n.permission ? `permission: ${n.permission}` : 'no special permission'}>
                            <span className="node-type mono">{n.type}</span>
                            {n.permission && <span className="node-perm" aria-label={`requires ${n.permission}`}>🔒</span>}
                          </span>
                        ))}
                      </div>
                    </div>
                  ));
                })()}
              </div>
            )}
            <div className="publish-actions" style={{ flexWrap: 'wrap' }}>
              <button className="btn-outline" disabled={busy || !planId || !!artifact || !canPlan} onClick={generate}>1 · Generate</button>
              <button className="btn-outline" disabled={busy || !artifact || (job && job.status === 'passed') || !canApprove}
                      title={canApprove ? '' : 'requires the approver role'} onClick={runTest}>2 · Run sandbox test</button>
              <button className="btn-primary" disabled={busy || !job || job.status !== 'passed' || !!approval || !canApprove}
                      title={canApprove ? '' : 'requires the approver role'} onClick={approve}>3 · Approve activation</button>
              {approval && <button className="btn-dark" onClick={() => setStep(5)}>Continue to bind <Icon d={ICONS.arrow} size={14} /></button>}
              {!approval && artifact && canPlan && (
                <button className="btn-dark" title="an approver can also take over from here"
                        onClick={() => setStep(5)}>Continue to bind <Icon d={ICONS.arrow} size={14} /></button>
              )}
            </div>
            {job && job.report && job.report.checks && (
              <div className="detail-section">
                <div className="detail-label">Isolated test report (content-bound by sha256)</div>
                {job.report.checks.map(c => (
                  <div key={c.name} className="approval-row">
                    <span className="mono">{c.name}</span>
                    <span className={`badge ${c.ok ? 'green' : 'red'}`}>{c.ok ? 'Pass' : 'Fail'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 5 && (
          <div className="step-panel">
            <h3>{canBind ? 'Bind the workflow — then publish if you choose' : 'Submit your automation for review'}</h3>
            <p>{canBind
              ? 'Binding creates a versioned workflow whose hash covers graph + plan + activated code together. Publication is separate consent and shares the schema only.'
              : 'Your role submits a CHANGE REQUEST (like a GitHub PR): an owner or admin reviews it, and after merge the normal sandbox and activation gates still apply. Nothing goes live without approval.'}
              {!approval && canBind && ' Binding needs an ACTIVATED artifact — an approver must complete the sandbox test and activation approval first.'}</p>
            <div className="publish-box">
              <div className="publish-stat"><span>Plan</span><b>{planId ? `${planId.slice(0, 8)}…` : '—'}</b></div>
              <div className="publish-stat"><span>Activated code</span><b>{artifact ? `${artifact.code_sha256.slice(0, 10)}…` : '—'}</b></div>
              <div className="publish-stat"><span>{canBind ? 'Workflow' : 'Change request'}</span><b>{bound ? (bound.workflow_id ? `${bound.workflow_id} v${bound.version}` : `CR ${bound.change_request} · ${bound.status}`) : 'not submitted'}</b></div>
            </div>
            <div className="publish-actions" style={{ flexWrap: 'wrap' }}>
              {canBind ? (
                <button className="btn-primary" disabled={busy || !!bound || !catalog || !canPlan}
                        onClick={bind}>
                  <Icon d={ICONS.check} size={16} /> {bound ? 'Workflow bound' : 'Create workflow'}
                </button>
              ) : (
                <button className="btn-primary" disabled={busy || !!bound || !catalog || !canPlan}
                        onClick={submitChangeRequest}>
                  <Icon d={ICONS.check} size={16} /> {bound ? 'Change request opened' : 'Submit change request'}
                </button>
              )}
              <button className="btn-outline" disabled={!bound || busy || published || !canBind || bound.change_request}
                      title={canBind ? '' : 'publishing requires the owner or admin role'} onClick={publish}>
                {published ? 'Published' : 'Publish to Registry'}
              </button>
              {bound && bound.workflow_id && <button className="btn-dark" onClick={() => setPage('workflows')}>Go to Workflows <Icon d={ICONS.arrow} size={14} /></button>}
            </div>
          </div>
        )}

        {err && <p className="helper-error">Gate refused: {err}</p>}

        <div className="step-actions">
          <button className="btn-outline" onClick={() => setStep(prev => Math.max(1, prev - 1))} disabled={step === 1}>Back</button>
          {step < 5 && <button className="btn-primary" onClick={() => setStep(prev => Math.min(5, prev + 1))}>Next <Icon d={ICONS.arrow} size={16} /></button>}
        </div>
      </div>
      )}
    </div>
  );
}
