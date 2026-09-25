// CreateAutomation — REAL backend-gated stepper (Phase 10).
// plan → generate → sandbox test → activation → bind → (optional) publish.
// Every gate is a real worker call that fails closed; the UI never fakes progress.
import React, { useState, useEffect } from 'react';
import { api } from './api.js';
import { subscribeLive, capturePoll } from './live.js';
import { Icon, ICONS, Terminal, stamp } from './main-shared.jsx';

export function CreateAutomation({ setPage }) {
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

  const bind = () => gate(async () => {
    const b = await api.createWorkflowFromPlan(planId);
    setBound(b);
    return b;
  }, b => `workflow ${b.workflow_id} v${b.version} bound to plan + activated code`);

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

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Create Automation</div>
          <h2>Create New Automation</h2>
        </div>
        <span className={`badge ${connected ? 'green' : 'orange'}`}>{connected ? 'Worker: LIVE' : 'Worker offline — gates locked'}</span>
      </div>

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
            <p>Context only — the plan rules themselves are confirmed in step 3. Capture stays opt-in and schema-only.</p>
            <div className="form-grid">
              <label>Team / Department
                <select defaultValue="Finance"><option>Finance</option><option>Operations</option><option>Procurement</option><option>HR</option></select>
              </label>
              <label>Process Type
                <select defaultValue="Compliance and filing"><option>Compliance and filing</option><option>Approval workflows</option><option>Vendor onboarding</option><option>Report generation</option></select>
              </label>
              <label>Data Sensitivity
                <select defaultValue="Medium"><option>Low</option><option>Medium</option><option>High</option></select>
              </label>
              <label>Capture surfaces
                <select defaultValue="Tracking file (CSV)"><option>Tracking file (CSV)</option><option>Browser (synthetic contract)</option></select>
              </label>
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
              <button className="btn-primary" disabled={busy || !connected} onClick={savePlan}>
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
            <div className="publish-actions" style={{ flexWrap: 'wrap' }}>
              <button className="btn-outline" disabled={busy || !planId || !!artifact} onClick={generate}>1 · Generate</button>
              <button className="btn-outline" disabled={busy || !artifact || (job && job.status === 'passed')} onClick={runTest}>2 · Run sandbox test</button>
              <button className="btn-primary" disabled={busy || !job || job.status !== 'passed' || !!approval} onClick={approve}>3 · Approve activation</button>
              {approval && <button className="btn-dark" onClick={() => setStep(5)}>Continue to bind <Icon d={ICONS.arrow} size={14} /></button>}
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
            <h3>Bind the workflow — then publish if you choose</h3>
            <p>Binding creates a versioned workflow whose hash covers graph + plan + activated code together. Publication is separate consent and shares the schema only.</p>
            <div className="publish-box">
              <div className="publish-stat"><span>Plan</span><b>{planId ? `${planId.slice(0, 8)}…` : '—'}</b></div>
              <div className="publish-stat"><span>Activated code</span><b>{artifact ? `${artifact.code_sha256.slice(0, 10)}…` : '—'}</b></div>
              <div className="publish-stat"><span>Workflow</span><b>{bound ? `${bound.workflow_id} v${bound.version}` : 'not bound'}</b></div>
            </div>
            <div className="publish-actions" style={{ flexWrap: 'wrap' }}>
              <button className="btn-primary" disabled={busy || !approval || !!bound} onClick={bind}>
                <Icon d={ICONS.check} size={16} /> {bound ? 'Workflow bound' : 'Create workflow'}
              </button>
              <button className="btn-outline" disabled={!bound || busy || published} onClick={publish}>
                {published ? 'Published' : 'Publish to Registry'}
              </button>
              {bound && <button className="btn-dark" onClick={() => setPage('workflows')}>Go to Workflows <Icon d={ICONS.arrow} size={14} /></button>}
            </div>
          </div>
        )}

        {err && <p className="helper-error">Gate refused: {err}</p>}

        <div className="step-actions">
          <button className="btn-outline" onClick={() => setStep(prev => Math.max(1, prev - 1))} disabled={step === 1}>Back</button>
          {step < 5 && <button className="btn-primary" onClick={() => setStep(prev => Math.min(5, prev + 1))}>Next <Icon d={ICONS.arrow} size={16} /></button>}
        </div>
      </div>
    </div>
  );
}
