import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import { subscribeLive, startLive } from './live.js';

import { Icon, ICONS, StatusBadge, Terminal, stamp } from './main-shared.jsx';

// ─── tiny icon set (inline SVG so no dependency issues) ───────────────────────
// ─── data ─────────────────────────────────────────────────────────────────────
const liveOps = [
  { name:'Vendor Onboarding', sub:'Automated document verification', status:'Success', time:'Just now', icon:'check', dept:'Procurement' },
  { name:'GST Verification', sub:'Batch processing 500 records', status:'In Progress', time:'45% complete', icon:'refresh', dept:'Finance' },
  { name:'Payroll Data Extraction', sub:'HR Department', status:'Success', time:'2 mins ago', icon:'check', dept:'HR' },
  { name:'API Gateway Sync', sub:'Timeout on external endpoint', status:'Failed', time:'15 mins ago', icon:'x', dept:'IT Ops' },
  { name:'Customer KYC Followup', sub:'Missing docs flagged, reminders sent', status:'Success', time:'1 hr ago', icon:'check', dept:'Operations' },
];

const registryItems = [
  {
    id: 1, title:'GST Vendor Verification', sector:'MSME Finance', usedBy:218, rating:'4.9',
    tags:['Finance','Compliance','Vendor'],
    desc:'Validates GSTIN against government portal, flags mismatches, generates approval note and updates ERP.',
    steps:['Extract GSTIN from vendor docs','Validate on GST portal API','Flag mismatches automatically','Generate approval note','Log to ERP and audit trail'],
    saves:'96 hrs/month', orgs:'218 offices across 8 states'
  },
  {
    id: 2, title:'Invoice Approval Routing', sector:'Manufacturing', usedBy:164, rating:'4.8',
    tags:['Finance','Approvals','ERP'],
    desc:'Reads invoice metadata, matches against PO, routes to correct approver based on amount bracket, logs payment status.',
    steps:['Read invoice metadata','Match PO value and vendor','Route to approver tier','Send approval notification','Log payment status in system'],
    saves:'84 hrs/month', orgs:'164 manufacturing units'
  },
  {
    id: 3, title:'HR Joining Document Pack', sector:'Services / IT', usedBy:132, rating:'4.7',
    tags:['HR','Onboarding','Compliance'],
    desc:'Collects offer letter, ID proofs, PF/ESIC fields, creates employee profile, sends welcome kit and task list.',
    steps:['Collect joining documents','Check for missing proofs','Create employee profile','File PF/ESIC fields','Send joining kit and calendar invite'],
    saves:'74 hrs/month', orgs:'132 service companies'
  },
  {
    id: 4, title:'Monthly TDS Filing Pack', sector:'Finance / CA Offices', usedBy:98, rating:'4.6',
    tags:['Tax','Compliance','Filing'],
    desc:'Collects challans, reconciles deductions across departments, prepares TDS summary, routes for CA approval.',
    steps:['Collect challan details','Reconcile deductions department-wise','Prepare TDS summary sheet','Route to CA for approval','File and archive'],
    saves:'120 hrs/month', orgs:'98 finance offices'
  },
  {
    id: 5, title:'Customer KYC Followup', sector:'BFSI / Operations', usedBy:87, rating:'4.5',
    tags:['KYC','Customer','Compliance'],
    desc:'Detects missing documents, triggers reminder emails, updates CRM ticket status, maintains audit trail.',
    steps:['Detect missing documents in CRM','Send reminder email from template','Update ticket status','Escalate after 72hrs if unresolved','Log to audit trail'],
    saves:'58 hrs/month', orgs:'87 BFSI branches'
  },
  {
    id: 6, title:'Procurement Approval Chain', sector:'Government / PSU', usedBy:74, rating:'4.5',
    tags:['Procurement','Approvals','Government'],
    desc:'Routes purchase requests through approval hierarchy, checks budget availability, generates purchase order draft.',
    steps:['Read purchase request','Check budget availability','Route through approval hierarchy','Generate PO draft','Send for final sign-off'],
    saves:'110 hrs/month', orgs:'74 government departments'
  },
];

const operatorProfile = {
  user: 'Admin User',
  team: 'Finance',
  secondaryTeams: ['Operations'],
  preferredTags: ['Finance', 'Compliance', 'Tax', 'Approvals', 'ERP'],
  tools: ['Finance portal', 'ERP', 'Email', 'Document folder'],
};

const discoveredCandidates = [
  {
    id:1, name:'Monthly TDS Filing Pack', dept:'Finance Dept.', freq:'~40 times/month',
    surfaces:['Finance portal','Email','Document folder'],
    avgTime:'22 min per run', saving:'Est. 120 hrs/month saveable',
    confidence:91, status:'Ready to draft',
    steps:['Download challan from portal','Open Excel and paste values','Send approval email to CA','Archive in shared folder'],
  },
  {
    id:2, name:'Weekly MIS Report', dept:'Operations', freq:'~4 times/month',
    surfaces:['ERP','Excel','Email'],
    avgTime:'3.5 hrs per run', saving:'Est. 56 hrs/month saveable',
    confidence:84, status:'Ready to draft',
    steps:['Pull data from ERP','Consolidate in Excel','Format report tables','Email to management'],
  },
  {
    id:3, name:'Vendor Document Collection', dept:'Procurement', freq:'~18 times/month',
    surfaces:['Email','Shared drive','ERP'],
    avgTime:'45 min per run', saving:'Est. 40 hrs/month saveable',
    confidence:78, status:'Needs review',
    steps:['Email vendor for documents','Download attachments','Rename and file to folder','Update vendor status in ERP'],
  },
];

const workflowsData = [
  { id:1, name:'GST Vendor Verification', status:'Verified', team:'Procurement', saves:'96 hrs/mo', scripts:3, lastRun:'2 hrs ago', sandboxPass:true, approved:true },
  { id:2, name:'Monthly TDS Filing Pack', status:'Drafting', team:'Finance', saves:'120 hrs/mo', scripts:1, lastRun:'Pending', sandboxPass:false, approved:false },
  { id:3, name:'Employee Joining Compliance', status:'Verified', team:'HR', saves:'74 hrs/mo', scripts:2, lastRun:'1 day ago', sandboxPass:true, approved:true },
  { id:4, name:'Customer KYC Followup', status:'Needs Review', team:'Operations', saves:'58 hrs/mo', scripts:1, lastRun:'3 hrs ago', sandboxPass:false, approved:false },
  { id:5, name:'Invoice Approval Routing', status:'Verified', team:'Finance', saves:'84 hrs/mo', scripts:2, lastRun:'30 mins ago', sandboxPass:true, approved:true },
  { id:6, name:'Procurement Approval Chain', status:'Verified', team:'Procurement', saves:'110 hrs/mo', scripts:4, lastRun:'5 hrs ago', sandboxPass:true, approved:true },
];

const trustLog = [
  { id:'TXN-0041', action:'Workflow published to registry', workflow:'GST Vendor Verification', user:'Admin', time:'Today 14:23', hash:'a9f3...d72c', result:'Pass' },
  { id:'TXN-0040', action:'Sandbox test — deliberate column mismatch caught', workflow:'Monthly TDS Filing Pack', user:'System', time:'Today 13:58', hash:'3b1e...f09a', result:'Blocked' },
  { id:'TXN-0039', action:'Script approved by user', workflow:'Invoice Approval Routing', user:'Priya S.', time:'Today 12:11', hash:'7c4a...b31f', result:'Pass' },
  { id:'TXN-0038', action:'Workflow pulled from registry', workflow:'HR Joining Document Pack', user:'Ratan M.', time:'Today 11:44', hash:'d6e2...219b', result:'Pass' },
  { id:'TXN-0037', action:'Sandbox test passed', workflow:'GST Vendor Verification', user:'System', time:'Today 10:30', hash:'1fa8...c47d', result:'Pass' },
  { id:'TXN-0036', action:'New pattern detected', workflow:'Customer KYC Followup', user:'Discovery Engine', time:'Yesterday 17:02', hash:'9b3c...e81a', result:'Flagged' },
  { id:'TXN-0035', action:'Script rollback triggered', workflow:'Payroll Data Extraction', user:'Ankit R.', time:'Yesterday 15:17', hash:'2d7f...a03c', result:'Rolled back' },
  { id:'TXN-0034', action:'Workflow contributed to registry', workflow:'Procurement Approval Chain', user:'Admin', time:'Yesterday 09:55', hash:'f4b1...7e2d', result:'Pass' },
];

const MONITOR_POOL = [
  { kind: 'cmd',  text: 'evt  browser.nav       https://services.gst.gov.in/services/searchtp' },
  { kind: 'dim',  text: '     dom.click         #gstin-input  value_len=15  redacted=true' },
  { kind: 'cmd',  text: 'evt  browser.submit    form#gst-lookup  fields=3  xhr=1' },
  { kind: 'info', text: '     http  GET /api/searchtp  200  312ms  bytes=4.1k' },
  { kind: 'cmd',  text: 'evt  file.save         vendor_master.xlsx  sheet=Q3  +12 rows' },
  { kind: 'dim',  text: '     openpyxl.diff     col[GSTIN] unchanged  col[STATUS] 12 writes' },
  { kind: 'cmd',  text: 'evt  email.send        to=ca@***  subj="TDS pack"  attach=1' },
  { kind: 'info', text: '     gmail.api         messages.send  id=18f2c…  latency=640ms' },
  { kind: 'cmd',  text: 'evt  browser.download  challan_jul.csv  18.4kb  sha=b31c…' },
  { kind: 'cmd',  text: 'evt  file.open         challan_jul.csv → excel  pid=8821' },
  { kind: 'dim',  text: '     clipboard         copy  range=A1:F84  (schema only, values hashed)' },
  { kind: 'cmd',  text: 'evt  file.save         tds_summary.xlsx  sheet=Jul  +1 tab' },
  { kind: 'cmd',  text: 'evt  email.draft       to=ca@***  subj="TDS pack — Jul"  wait_send=true' },
  { kind: 'info', text: 'pattern.seq           hash=7f3a91  prefix=download→xlsx→email  n=3' },
  { kind: 'cmd',  text: 'evt  browser.nav       https://eportal.incometax.gov.in/iec/foservices' },
  { kind: 'dim',  text: '     form.fill         #assessmentYear=2025-26  #formType=24Q' },
  { kind: 'cmd',  text: 'evt  file.save         24Q_annexure.xlsx  cells=412  dirty=true' },
  { kind: 'info', text: 'pattern.cluster       C-12  size=9  jaccard=0.81  window=47m' },
  { kind: 'cmd',  text: 'evt  browser.nav       erp.internal/po/approve  ticket=PO-4419' },
  { kind: 'dim',  text: '     table.row         vendor=***  amount_band=50k-2L  approver=L2' },
  { kind: 'cmd',  text: 'evt  email.send        to=cfo@***  subj="PO-4419 pending"' },
  { kind: 'info', text: 'pattern.cluster       C-19  size=6  jaccard=0.74  window=2h' },
  { kind: 'cmd',  text: 'evt  file.save         kyc_gap_list.csv  +7 rows  missing=PAN,addr' },
  { kind: 'cmd',  text: 'evt  email.send        template=kyc_nudge_v2  n=7  queued=true' },
  { kind: 'dim',  text: '     crm.patch         ticket.KYC-1104  status=FOLLOWUP' },
  { kind: 'info', text: 'detector.score        C-12  conf=0.73  repeats=11  est_min=22' },
];

const SANDBOX_SCRIPT = [
  { delay: 280, kind: 'cmd',  text: '$ autostack sandbox run --job tds-filing-v3 --isolate docker --seed 8841' },
  { delay: 420, kind: 'info', text: 'runtime   image=autostack/runner:1.4.2  sha256:9c1e8a…  cpu=2  mem=512m' },
  { delay: 260, kind: 'dim',  text: 'mount     /fixtures/tds_jul.csv → /work/in  ro' },
  { delay: 220, kind: 'dim',  text: 'mount     /generated/workflow.py → /work/job  rw' },
  { delay: 300, kind: 'info', text: 'policy    no_network=true  no_host_fs=true  timeout=90s  pii_redact=strict' },
  { delay: 180, kind: 'dim',  text: '' },
  { delay: 380, kind: 'cmd',  test: 'ast_compile', text: '[ 1/12] pytest  test_ast_compile.py::test_module_parses' },
  { delay: 520, kind: 'ok',   test: 'ast_compile', text: '         PASS  42 stmts  0 syntax errors  184ms' },
  { delay: 340, kind: 'cmd',  test: 'secret_scan', text: '[ 2/12] bandit + trufflehog  test_secret_scan.py' },
  { delay: 480, kind: 'dim',  text: '         scanned 1,204 tokens  entropy_threshold=4.5' },
  { delay: 360, kind: 'ok',   test: 'secret_scan', text: '         PASS  0 secrets  0 high-severity  211ms' },
  { delay: 320, kind: 'cmd',  test: 'schema_bind', text: '[ 3/12] test_schema_bind.py::test_columns_resolve' },
  { delay: 440, kind: 'dim',  text: '         expected [GSTIN, PAN, AMOUNT, PERIOD]  found 4/4' },
  { delay: 300, kind: 'ok',   test: 'schema_bind', text: '         PASS  bindings stable  96ms' },
  { delay: 360, kind: 'cmd',  test: 'golden_path', text: '[ 4/12] test_replay_golden.py::test_end_to_end_jul' },
  { delay: 700, kind: 'dim',  text: '         replay  84 rows  3 hops  browser→xlsx→email' },
  { delay: 420, kind: 'ok',   test: 'golden_path', text: '         PASS  output hash=e91c… matches fixture  1.12s' },
  { delay: 300, kind: 'cmd',  test: 'header_drift', text: '[ 5/12] test_header_drift.py::test_rename_gstin_column' },
  { delay: 520, kind: 'warn', text: '         INJECT  col "GSTIN" → "GST_NO"  (deliberate mutation)' },
  { delay: 480, kind: 'fail', text: '         FAIL  KeyError: GSTIN  at transform.py:88' },
  { delay: 360, kind: 'info', text: '         gate    delivery BLOCKED  reason=sandbox_mismatch' },
  { delay: 420, kind: 'ok',   test: 'header_drift', text: '         PASS  drift guard caught mutation  rollback=ok  640ms' },
  { delay: 300, kind: 'cmd',  test: 'gstin_check', text: '[ 6/12] test_gstin_checksum.py::test_mod97' },
  { delay: 440, kind: 'ok',   test: 'gstin_check', text: '         PASS  500 ids  0 false-accept  77ms' },
  { delay: 280, kind: 'cmd',  test: 'idempotent', text: '[ 7/12] test_idempotency.py::test_rerun_same_input' },
  { delay: 560, kind: 'ok',   test: 'idempotent', text: '         PASS  2nd run 0 extra emails  0 extra writes  403ms' },
  { delay: 280, kind: 'cmd',  test: 'pii_redact', text: '[ 8/12] test_pii_redaction.py::test_no_raw_values_in_logs' },
  { delay: 500, kind: 'ok',   test: 'pii_redact', text: '         PASS  0 PAN/GSTIN leaks in stdout+audit  158ms' },
  { delay: 280, kind: 'cmd',  test: 'timeouts', text: '[ 9/12] test_timeout_bounds.py::test_step_sla' },
  { delay: 420, kind: 'ok',   test: 'timeouts', text: '         PASS  each hop < 8s  overall 11.4s / 90s  88ms' },
  { delay: 280, kind: 'cmd',  test: 'hash_chain', text: '[10/12] test_audit_hash_chain.py::test_append_only' },
  { delay: 460, kind: 'ok',   test: 'hash_chain', text: '         PASS  prev_hash linked  sha256 ok  71ms' },
  { delay: 280, kind: 'cmd',  test: 'rollback', text: '[11/12] test_rollback_hook.py::test_one_click_revert' },
  { delay: 520, kind: 'ok',   test: 'rollback', text: '         PASS  snapshot restored  files=2  294ms' },
  { delay: 280, kind: 'cmd',  test: 'perm_scope', text: '[12/12] test_permission_scope.py::test_surfaces_only' },
  { delay: 480, kind: 'ok',   test: 'perm_scope', text: '         PASS  no desktop-wide hooks  allowlist=browser,xlsx,email' },
  { delay: 360, kind: 'dim',  text: '' },
  { delay: 240, kind: 'info', text: '────────  12 passed  1 injected-fail caught  0 delivered-on-fail  ────────' },
  { delay: 200, kind: 'ok',   text: 'sandbox   GATE OPEN  artifact=tds-filing-v3.job  sig=ed25519:4ab2…' },
];

const SANDBOX_TESTS = [
  { id: 'ast_compile', label: 'AST compile / syntax' },
  { id: 'secret_scan', label: 'Secret + malware scan' },
  { id: 'schema_bind', label: 'Schema binding' },
  { id: 'golden_path', label: 'Golden-path replay' },
  { id: 'header_drift', label: 'Header-drift injection' },
  { id: 'gstin_check', label: 'GSTIN checksum' },
  { id: 'idempotent', label: 'Idempotent re-run' },
  { id: 'pii_redact', label: 'PII redaction' },
  { id: 'timeouts', label: 'Timeout / SLA bounds' },
  { id: 'hash_chain', label: 'Audit hash-chain' },
  { id: 'rollback', label: 'Rollback hook' },
  { id: 'perm_scope', label: 'Permission scope' },
];

function getSuitability(item) {
  const title = `${item.title} ${item.sector}`.toLowerCase();
  let score = 50;

  const tagMatches = item.tags.filter((tag) => operatorProfile.preferredTags.includes(tag)).length;
  score += tagMatches * 10;

  if (title.includes(operatorProfile.team.toLowerCase())) score += 12;
  if (item.tags.includes('Compliance')) score += 8;
  if (item.tags.includes('ERP')) score += 6;

  score = Math.max(55, Math.min(score, 98));

  const reasons = [];
  if (tagMatches > 0) reasons.push(`${tagMatches} tag match${tagMatches > 1 ? 'es' : ''}`);
  if (item.tags.includes('Compliance')) reasons.push('compliance workflow');
  if (item.tags.includes('ERP')) reasons.push('ERP-aligned');
  if (title.includes('finance')) reasons.push('finance use-case');

  return { score, reasons };
}

// ─── screens ──────────────────────────────────────────────────────────────────
// Dashboard/Workflows/Registry/TrustLog are live modules (Phase 10).
import { Dashboard, Workflows, Registry, TrustLog } from './screens-live.jsx';
import { NotificationCenter, DataPrivacy, Connectors } from './roadmap-complete.jsx';
import { api } from './api.js';
import { Login, Home, Settings, Profile, Teams, Runners, Scheduling } from './roadmap-pages.jsx';

function Discovery({ setPage }) {
  const [selected, setSelected] = useState(null);
  const [drafted, setDrafted] = useState([]);
  const [live, setLive] = useState(null);
  useEffect(() => subscribeLive(setLive), []);

  // Real candidates replace demo cards only when the worker is connected. Real
  // candidates show exact occurrence counts (never a fabricated confidence %).
  const realCandidates = (live && live.connected && live.candidates || [])
    .filter(c => c.status === 'suggested')
    .map((c, i) => ({
      id: `real-${c.id}`,
      name: (c.pattern && c.pattern.sequence || []).join(' → ') || 'Detected pattern',
      dept: `resource: ${c.pattern && c.pattern.resource || 'unknown'}`,
      freq: `${c.occurrences} completed instances`,
      surfaces: [],
      avgTime: `clients: ${(c.evidence && c.evidence.distinct_clients) || 0}`,
      saving: `first seen ${String(c.evidence && c.evidence.first_seen || '').slice(0, 10)}`,
      confidence: null,
      status: 'Evidence-based candidate',
      steps: (c.evidence && c.evidence.steps) || [],
      real: true,
    }));
  const shown = [...realCandidates, ...discoveredCandidates];
  const [dismissedIds, setDismissedIds] = useState([]);
  const [dismissErr, setDismissErr] = useState(null);
  const dismissReal = async (realId) => {
    setDismissErr(null);
    try { await api.dismissCandidate(realId); setDismissedIds(d => [...d, realId]); }
    catch (e) { setDismissErr(e.message); }
  };

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Discovery Engine</div>
          <h2>Detected Patterns</h2>
        </div>
      </div>

      <div className="info-banner">
        <Icon d={ICONS.eye} size={18} />
        <span>Consent mode is <b>on</b>. The agent is observing approved apps only — browser, spreadsheet, and email. No file contents are captured.</span>
      </div>

      <div className="two-col" style={{ alignItems: 'flex-start' }}>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          {dismissErr && <div className="info-banner"><span>Dismiss refused: {dismissErr}</span></div>}
          {shown.filter(c => !dismissedIds.includes(c.id)).map(c => (
            <div
              key={c.id}
              className={`card candidate-card ${selected?.id === c.id ? 'selected' : ''}`}
              onClick={() => setSelected(c)}
            >
              <div className="card-header">
                <div>
                  <div className="op-name">{c.name}</div>
                  <div className="op-sub">{c.dept}</div>
                </div>
                <StatusBadge s={drafted.includes(c.id) ? 'Verified' : c.status} />
              </div>
              <div className="candidate-meta">
                <span><Icon d={ICONS.refresh} size={14} /> {c.freq}</span>
                <span><Icon d={ICONS.clock} size={14} /> {c.avgTime}</span>
                <span><Icon d={ICONS.chart} size={14} /> {c.saving}</span>
              </div>
              <div className="conf-bar-wrap">
                <div className="conf-label">{c.real ? 'Evidence (exact counts, no invented %)' : 'Detection confidence'}</div>
                <div className="conf-bar">
                  <div className="conf-fill" style={{ width: `${c.real ? 100 : c.confidence}%`, background: c.real ? '#16a34a' : (c.confidence > 85 ? '#2563EB' : '#f59e0b') }} />
                </div>
                <div className="conf-pct">{c.real ? `${c.freq}` : `${c.confidence}%`}</div>
              </div>
              {c.real && (
                <div style={{ marginTop: 8 }}>
                  <button className="btn-outline" onClick={(e) => { e.stopPropagation(); dismissReal(c.id.slice(5)); }}>
                    Dismiss (records review decision)
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        <div>
          {selected ? (
            <div className="card" style={{ position:'sticky', top:20 }}>
              <div className="card-header">
                <strong>{selected.name}</strong>
                <button className="btn-icon small" onClick={() => setSelected(null)}><Icon d={ICONS.x} size={16} /></button>
              </div>
              <div className="detail-section">
                <div className="detail-label">Detected surfaces</div>
                <div className="tag-row">
                  {selected.surfaces.map(s => <span key={s} className="tag">{s}</span>)}
                </div>
              </div>
              <div className="detail-section">
                <div className="detail-label">Repeated steps observed</div>
                <ol className="steps-list">
                  {selected.steps.map(s => <li key={s}>{s}</li>)}
                </ol>
              </div>
              <div className="stat-pair">
                <div className="stat-box">
                  <div className="stat-val">{selected.avgTime}</div>
                  <div className="stat-lbl">Avg manual run</div>
                </div>
                <div className="stat-box">
                  <div className="stat-val green-text">{selected.saving}</div>
                  <div className="stat-lbl">Estimated saving</div>
                </div>
              </div>
              <button
                className={`btn-primary full-w ${drafted.includes(selected.id) ? 'success' : ''}`}
                onClick={() => {
                  setDrafted(d => [...d, selected.id]);
                  setTimeout(() => setPage('create'), 800);
                }}
              >
                {drafted.includes(selected.id)
                  ? <><Icon d={ICONS.check} size={16} /> Sent to Create Flow</>
                  : <><Icon d={ICONS.zap} size={16} /> Draft Automation Plan</>}
              </button>
            </div>
          ) : (
            <div className="card empty-state">
              <Icon d={ICONS.search} size={32} />
              <p>Select a detected pattern on the left to see details and draft an automation plan.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// CreateAutomation now lives in its own module (real backend-gated stepper).
import { CreateAutomation } from './create-automation.jsx';
import { getTheme, setTheme } from './theme.js';

function ThemeSwitcher() {
  const [theme, setThemeState] = useState(getTheme());
  const options = [
    { id: 'light', label: 'Light' },
    { id: 'dark', label: 'Dark' },
    { id: 'system', label: 'System' },
  ];
  return (
    <div className="theme-switch" role="group" aria-label="Color theme">
      {options.map(o => (
        <button
          key={o.id}
          className={`theme-opt ${theme === o.id ? 'on' : ''}`}
          aria-pressed={theme === o.id}
          title={`${o.label} theme`}
          onClick={() => { setTheme(o.id); setThemeState(o.id); }}
        >{o.label}</button>
      ))}
    </div>
  );
}

// ─── shell ────────────────────────────────────────────────────────────────────
const pages = [    { id:'home',      label:'Home',       icon: ICONS.grid, group:'Account' },
    { id:'notifications', label:'Notifications', icon: ICONS.bell, group:'Work' },
    { id:'privacy',   label:'Data & Privacy', icon: ICONS.shield, group:'Trust' },
    { id:'connectors', label:'Connectors', icon: ICONS.package, group:'Operate' },
  { id:'dashboard', label:'Dashboard',  icon: ICONS.grid, group:'Work' },
  { id:'discovery', label:'Discovery',  icon: ICONS.zap,  group:'Work' },
  { id:'create',    label:'Create Automation', icon: ICONS.plus, group:'Work' },
  { id:'workflows', label:'Workflows',  icon: ICONS.flow, group:'Work' },
  { id:'registry',  label:'Registry',   icon: ICONS.db,   group:'Trust' },
  { id:'trustlog',  label:'Trust Log',  icon: ICONS.shield, group:'Trust' },
  { id:'scheduling',label:'Scheduling', icon: ICONS.clock, group:'Operate' },
  { id:'runners',   label:'Runners',    icon: ICONS.cpu,   group:'Operate' },
  { id:'teams',     label:'Teams',      icon: ICONS.users, group:'Account' },
  { id:'profile',   label:'Profile',    icon: ICONS.user,  group:'Account' },
  { id:'settings',  label:'Settings',   icon: ICONS.cog,   group:'Account' },
];

function App() {
  // Hash router: the URL is the source of truth, so deep links (#/page) survive
  // reloads and every navigation writes a shareable hash.
  const pageForHash = () => {
    const h = (window.location.hash || '').replace(/^#/, '');
    return h || 'dashboard';
  };
  const [page, setPageState] = useState(pageForHash);
  const setPage = (p) => {
    if (window.location.hash !== '#' + p) window.location.hash = p;
    else setPageState(p);
  };
  useEffect(() => {
    const onHash = () => setPageState(pageForHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  const [live, setLive] = useState(null);
  const [identity, setIdentity] = useState(null);
  const [authState, setAuthState] = useState('checking'); // checking|anon|ok
  useEffect(() => {
    const unsubscribe = subscribeLive(setLive);
    startLive(4000);
    api.authMe().then((me) => { setIdentity(me); setAuthState('ok'); })
      .catch(() => setAuthState('anon'));
    return unsubscribe;
  }, []);
  const workerUp = !!(live && live.connected);
  if (authState === 'checking') {
    return <div className="login-wrap"><div className="muted">Connecting to worker…</div></div>;
  }
  if (authState === 'anon') {
    return <Login setPage={setPage} setIdentity={(me) => { setIdentity(me); setAuthState('ok'); }} />;
  }
  const Screen = {
    home: <Home setPage={setPage} identity={identity} />,
    settings: <Settings identity={identity} />,
    profile: <Profile identity={identity} />,
    teams: <Teams />,
    runners: <Runners />,
    scheduling: <Scheduling />,
    notifications: <NotificationCenter />,
    privacy: <DataPrivacy />,
    connectors: <Connectors />,
    dashboard: <Dashboard />,
    discovery: <Discovery />,
    registry: <Registry />,
    workflows: <Workflows />,
    create: <CreateAutomation />,
    trustlog: <TrustLog />,
  }[page];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon"><Icon d={ICONS.hash} size={20} /></div>
          <div className="brand-text">
            <div className="brand-name">AutoStack IN</div>
          </div>
        </div>

        <nav className="nav">
          {['Work', 'Trust', 'Operate', 'Account'].map(group => (
            <div key={group} className="nav-group">
              <div className="nav-group-label">{group}</div>
              {pages.filter(p => p.group === group).map(p => (
                <button
                  key={p.id}
                  className={`nav-item ${page === p.id ? 'active' : ''}`}
                  onClick={() => setPage(p.id)}
                >
                  <Icon d={p.icon} size={18} />
                  <span>{p.label}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <ThemeSwitcher />
          <div className="consent-badge" title={workerUp ? 'Worker on :8747 — live data' : 'Worker unreachable — demo data shown'}>
            <Icon d={ICONS.lock} size={14} />
            <span>{workerUp ? 'Worker: LIVE' : 'Worker: demo mode'}</span>
          </div>
          <div className="sidebar-user">
            <div className="avatar">{identity && identity.user ? identity.user.username.slice(0, 2).toUpperCase() : 'SV'}</div>
            <div>
              <div className="user-name">{identity && identity.user ? identity.user.display_name || identity.user.username : 'Service token'}</div>
              <div className="user-role">{identity ? `${identity.capabilities.tier} · ${identity.role}` : 'legacy mode'}</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        {Screen}
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
