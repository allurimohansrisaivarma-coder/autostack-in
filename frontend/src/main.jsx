import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

// ─── tiny icon set (inline SVG so no dependency issues) ───────────────────────
const Icon = ({ d, size = 18, stroke = 'currentColor' }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={stroke} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
  </svg>
);

const ICONS = {
  grid:    "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  search:  "M11 3a8 8 0 1 0 0 16A8 8 0 0 0 11 3zM21 21l-4.35-4.35",
  db:      ["M12 2C6.48 2 2 4.02 2 6.5v11C2 19.98 6.48 22 12 22s10-2.02 10-4.5v-11C22 4.02 17.52 2 12 2z","M2 6.5C2 8.98 6.48 11 12 11s10-2.02 10-4.5","M2 12c0 2.48 4.48 4.5 10 4.5s10-2.02 10-4.5"],
  flow:    ["M5 6a1 1 0 1 0 2 0A1 1 0 0 0 5 6zM5 18a1 1 0 1 0 2 0A1 1 0 0 0 5 18zM17 12a1 1 0 1 0 2 0A1 1 0 0 0 17 12z","M7 6h4a4 4 0 0 1 4 4v0a4 4 0 0 0 4 4","M7 18h4a4 4 0 0 0 4-4v0a4 4 0 0 1 4-4"],
  shield:  ["M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z","M9 12l2 2 4-4"],
  bell:    ["M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9","M13.73 21a2 2 0 0 1-3.46 0"],
  check:   "M20 6L9 17l-5-5",
  x:       "M18 6L6 18M6 6l12 12",
  circle:  "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z",
  zap:     "M13 2L3 14h9l-1 8 10-12h-9l1-8z",
  arrow:   "M5 12h14M12 5l7 7-7 7",
  clock:   ["M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2z","M12 6v6l4 2"],
  chart:   ["M18 20V10","M12 20V4","M6 20v-6"],
  user:    ["M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2","M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
  lock:    ["M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2z","M7 11V7a5 5 0 0 1 10 0v4"],
  refresh: "M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15",
  eye:     ["M1 12S5 4 12 4s11 8 11 8-4 8-11 8S1 12 1 12z","M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"],
  plus:    "M12 5v14M5 12h14",
  chevron: "M9 18l6-6-6-6",
  package: ["M16.5 9.4l-9-5.18M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z","M3.27 6.96L12 12.01l8.73-5.05","M12 22.08V12"],
  list:    ["M8 6h13","M8 12h13","M8 18h13","M3 6h.01","M3 12h.01","M3 18h.01"],
  hash:    ["M4 9h16","M4 15h16","M10 3L8 21","M16 3l-2 18"],
};

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

// ─── helpers ──────────────────────────────────────────────────────────────────
const StatusBadge = ({ s }) => {
  const map = {
    'Success':       'badge green',
    'Verified':      'badge green',
    'In Progress':   'badge blue',
    'Drafting':      'badge blue',
    'Failed':        'badge red',
    'Needs Review':  'badge orange',
    'Blocked':       'badge red',
    'Pass':          'badge green',
    'Flagged':       'badge orange',
    'Rolled back':   'badge gray',
  };
  return <span className={map[s] || 'badge gray'}>{s}</span>;
};

function stamp() {
  return new Date().toLocaleTimeString('en-GB', { hour12: false });
}

function Terminal({ title, lines, running }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines]);

  return (
    <div className="term">
      <div className="term-bar">
        <div className="term-dots"><i /><i /><i /></div>
        <span className="term-title">{title}</span>
        {running
          ? <span className="term-live">● LIVE</span>
          : <span className="term-idle">idle</span>}
      </div>
      <div className="term-body" ref={ref}>
        {lines.length === 0 && (
          <div className="term-line dim">waiting for process…</div>
        )}
        {lines.map((line, i) => (
          <div key={i} className={`term-line ${line.kind || ''}`}>
            {line.ts && <span className="term-ts">{line.ts}</span>}
            <span>{line.text}</span>
          </div>
        ))}
        {running && <div className="term-line cursor"><span className="blink">█</span></div>}
      </div>
    </div>
  );
}

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
function Dashboard({ setPage }) {
  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <h2>Operations Dashboard</h2>
        </div>
        <button className="btn-icon"><Icon d={ICONS.bell} /></button>
      </div>

      <div className="metric-row">
        {[
          { label:'Active Automations', value:'124', sub:'+12% vs last week', color:'blue' },
          { label:'Hours Saved (Monthly)', value:'1,240 hrs', sub:'+8.5% vs last month', color:'orange' },
          { label:'Success Rate', value:'99.8%', sub:'Sandbox gated', color:'green', bar:true },
          { label:'Tasks in Registry', value:'450+', sub:'Across 12 departments', color:'purple' },
        ].map(m => (
          <div className="metric-card" key={m.label}>
            <div className="metric-label">{m.label}</div>
            <div className="metric-value">{m.value}</div>
            {m.bar && <div className="metric-bar"><div className="metric-bar-fill" /></div>}
            <div className={`metric-sub ${m.color}`}>{m.sub}</div>
          </div>
        ))}
      </div>

      <div className="two-col">
        <div className="card">
          <div className="card-header">
            <div className="card-title-row">
              <span className="dot green" /> <strong>Live Operations</strong>
            </div>
            <button className="link-btn" onClick={() => setPage('workflows')}>View All</button>
          </div>
          <table className="ops-table">
            <tbody>
              {liveOps.map(op => (
                <tr key={op.name}>
                  <td>
                    <div className={`op-icon ${op.status === 'Success' ? 'green' : op.status === 'In Progress' ? 'blue' : 'red'}`}>
                      <Icon d={ICONS[op.icon]} size={15} />
                    </div>
                  </td>
                  <td>
                    <div className="op-name">{op.name}</div>
                    <div className="op-sub">{op.sub}</div>
                  </td>
                  <td className="op-right">
                    <StatusBadge s={op.status} />
                    <div className="op-time">{op.time}</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="right-col">
          <div className="card discovery-hint">
            <div className="card-header">
              <strong>Discovery Engine</strong>
              <Icon d={ICONS.search} size={18} />
            </div>
            <p className="hint-sub">AI has detected a new repeated manual pattern.</p>
            <div className="hint-box">
              <div className="hint-name">Monthly TDS Filing</div>
              <div className="hint-detail">Detected in Finance Dept. Occurs ~40 times/month.</div>
              <div className="hint-save">↘ Est. 120 hrs saveable</div>
            </div>
            <button className="btn-primary" onClick={() => setPage('discovery')}>
              <Icon d={ICONS.zap} size={16} /> Draft Automation
            </button>
          </div>

          <div className="card">
            <div className="card-header"><strong>Quick Actions</strong></div>
            {[
              ['Approve New Script', 'workflows'],
              ['Create Custom Workflow', 'create'],
              ['View National Registry', 'registry'],
            ].map(([label, page]) => (
              <button className="quick-action" key={label} onClick={() => setPage(page)}>
                {label} <Icon d={ICONS.chevron} size={16} />
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <strong>Efficiency Chart (30 Days)</strong>
          <span className="badge blue">Time Saved</span>
        </div>
        <div className="bar-chart">
          {[62,75,58,88,70,95,83,91,77,88,74,96,82,90,78,85,92,68,80,95,72,88,76,91,84,97,79,93,88,100].map((h,i) => (
            <div key={i} className="bar-wrap">
              <div className="bar" style={{ height: `${h}%` }} />
            </div>
          ))}
        </div>
        <div className="chart-labels">
          <span>1 Aug</span><span>10 Aug</span><span>20 Aug</span><span>30 Aug</span>
        </div>
      </div>
    </div>
  );
}

function Discovery({ setPage }) {
  const [selected, setSelected] = useState(null);
  const [drafted, setDrafted] = useState([]);

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
          {discoveredCandidates.map(c => (
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
                <div className="conf-label">Detection confidence</div>
                <div className="conf-bar">
                  <div className="conf-fill" style={{ width: `${c.confidence}%`, background: c.confidence > 85 ? '#2563EB' : '#f59e0b' }} />
                </div>
                <div className="conf-pct">{c.confidence}%</div>
              </div>
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

function Registry() {
  const [search, setSearch] = useState('');
  const [active, setActive] = useState(null);

  const filtered = registryItems.filter(r =>
    r.title.toLowerCase().includes(search.toLowerCase()) ||
    r.sector.toLowerCase().includes(search.toLowerCase()) ||
    r.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))
  );

  const ranked = [...filtered]
    .map((item) => ({ ...item, suitability: getSuitability(item) }))
    .sort((a, b) => b.suitability.score - a.suitability.score);

  const recommended = ranked.slice(0, 3);

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Shared Registry</div>
          <h2>Automation Registry</h2>
        </div>
        <div className="search-box">
          <Icon d={ICONS.search} size={16} />
          <input
            placeholder="Search by workflow, sector, or tag..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="info-banner">
        <Icon d={ICONS.package} size={18} />
        <span>Teams with similar workflows can pull a verified automation template and adapt it — no rebuilding from scratch. Only workflow <b>schemas</b> are shared, never actual data.</span>
      </div>

      <div className="card profile-card">
        <div className="card-header">
          <strong>Suitable for You</strong>
          <span className="badge blue">{operatorProfile.team} Team Profile</span>
        </div>
        <p className="profile-sub">
          Recommendations are ranked using your team profile, tool usage, and workflow history.
        </p>
        <div className="tag-row">
          <span className="tag">Primary team: {operatorProfile.team}</span>
          <span className="tag">Tools: ERP + Email + Portal</span>
          <span className="tag">Priority: Compliance-heavy workflows</span>
        </div>
        <div className="recommended-row">
          {recommended.map((item) => (
            <button
              key={`rec-${item.id}`}
              className="recommended-pill"
              onClick={() => setActive(item)}
            >
              <span>{item.title}</span>
              <b>{item.suitability.score}% match</b>
            </button>
          ))}
        </div>
      </div>

      <div className="registry-grid">
        {ranked.map(item => (
          <div
            className={`card registry-item ${active?.id === item.id ? 'selected' : ''}`}
            key={item.id}
            onClick={() => setActive(active?.id === item.id ? null : item)}
          >
            <div className="reg-top">
              <div>
                <div className="op-name">{item.title}</div>
                <div className="op-sub">{item.sector}</div>
              </div>
              <div className="reg-rating">★ {item.rating}</div>
            </div>
            <div className="fit-row">
              <span className="fit-score">Suitable for you: {item.suitability.score}%</span>
              <span className="fit-reason">{item.suitability.reasons.slice(0, 2).join(' · ') || 'general workflow match'}</span>
            </div>
            <div className="tag-row" style={{ margin:'12px 0' }}>
              {item.tags.map(t => <span key={t} className="tag">{t}</span>)}
            </div>
            <p className="reg-desc">{item.desc}</p>
            <div className="reg-steps">
              {item.steps.map((s, i) => (
                <div className="reg-step" key={s}>
                  <span className="step-num">{i + 1}</span>
                  <span>{s}</span>
                </div>
              ))}
            </div>
            <div className="reg-footer">
              <div>
                <div className="reg-stat"><Icon d={ICONS.user} size={14} /> {item.usedBy} offices</div>
                <div className="reg-stat green-text"><Icon d={ICONS.clock} size={14} /> Saves {item.saves}</div>
              </div>
              <button
                className="btn-dark"
                onClick={e => { e.stopPropagation(); }}
              >
                Use Workflow
              </button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="card empty-state" style={{ gridColumn:'1/-1' }}>
            <Icon d={ICONS.search} size={28} />
            <p>No workflows found for "{search}"</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Workflows({ setPage }) {
  const [selected, setSelected] = useState(null);

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">My Workflows</div>
          <h2>All Workflows</h2>
        </div>
        <button className="btn-primary" onClick={() => setPage('create')}>
          <Icon d={ICONS.plus} size={16} /> Create New Automation
        </button>
      </div>

      <div className="two-col" style={{ alignItems:'flex-start' }}>
        <div className="card" style={{ padding:0, overflow:'hidden' }}>
          <table className="full-table">
            <thead>
              <tr>
                <th>Workflow</th>
                <th>Team</th>
                <th>Status</th>
                <th>Saves</th>
                <th>Sandbox</th>
                <th>Last Run</th>
              </tr>
            </thead>
            <tbody>
              {workflowsData.map(w => (
                <tr
                  key={w.id}
                  onClick={() => setSelected(w)}
                  className={selected?.id === w.id ? 'row-active' : ''}
                >
                  <td><div className="op-name">{w.name}</div></td>
                  <td><span className="tag">{w.team}</span></td>
                  <td><StatusBadge s={w.status} /></td>
                  <td className="green-text fw">{w.saves}</td>
                  <td>
                    {w.sandboxPass
                      ? <span className="badge green">Pass</span>
                      : <span className="badge red">Pending</span>}
                  </td>
                  <td className="op-sub">{w.lastRun}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {selected && (
          <div className="card" style={{ minWidth:280, position:'sticky', top:20 }}>
            <div className="card-header">
              <strong>{selected.name}</strong>
              <button className="btn-icon small" onClick={() => setSelected(null)}><Icon d={ICONS.x} size={16} /></button>
            </div>
            <div className="detail-section">
              <div className="stat-pair">
                <div className="stat-box">
                  <div className="stat-val">{selected.saves}</div>
                  <div className="stat-lbl">Monthly saving</div>
                </div>
                <div className="stat-box">
                  <div className="stat-val">{selected.scripts}</div>
                  <div className="stat-lbl">Script versions</div>
                </div>
              </div>
            </div>
            <div className="detail-section">
              <div className="detail-label">Approvals</div>
              <div style={{ display:'flex', flexDirection:'column', gap:8, marginTop:8 }}>
                <div className="approval-row">
                  <span>Sandbox test</span>
                  {selected.sandboxPass
                    ? <span className="badge green">Pass</span>
                    : <span className="badge red">Pending</span>}
                </div>
                <div className="approval-row">
                  <span>User approved</span>
                  {selected.approved
                    ? <span className="badge green">Yes</span>
                    : <span className="badge orange">Awaiting</span>}
                </div>
              </div>
            </div>
            <div className="detail-section">
              <div className="detail-label">Actions</div>
              <div style={{ display:'flex', flexDirection:'column', gap:8, marginTop:8 }}>
                {!selected.approved && (
                  <button className="btn-primary full-w"><Icon d={ICONS.check} size={16} /> Approve Script</button>
                )}
                <button className="btn-outline full-w"><Icon d={ICONS.eye} size={16} /> View Audit Log</button>
                <button className="btn-outline full-w"><Icon d={ICONS.refresh} size={16} /> Re-run Sandbox</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CreateAutomation({ setPage }) {
  const [step, setStep] = useState(1);
  const [monitoring, setMonitoring] = useState(false);
  const [monitorLines, setMonitorLines] = useState([]);
  const [eventCount, setEventCount] = useState(0);
  const [unlocked, setUnlocked] = useState([]);
  const [selectedOps, setSelectedOps] = useState([]);
  const [sandboxRun, setSandboxRun] = useState(false);
  const [sandboxReady, setSandboxReady] = useState(false);
  const [sandboxLines, setSandboxLines] = useState([]);
  const [testStatus, setTestStatus] = useState({});
  const [published, setPublished] = useState(false);
  const monitorTick = useRef(0);
  const sandboxTimer = useRef(null);

  useEffect(() => {
    if (!monitoring) return undefined;
    const id = setInterval(() => {
      const tick = monitorTick.current;
      monitorTick.current = tick + 1;
      const ev = MONITOR_POOL[tick % MONITOR_POOL.length];
      setMonitorLines((prev) => {
        const next = [...prev, { ...ev, ts: stamp() }];
        return next.slice(-80);
      });
      setEventCount((n) => n + 1);

      const unlockAt = [
        [8,  discoveredCandidates[0], 61],
        [16, discoveredCandidates[0], 78],
        [22, discoveredCandidates[2], 64],
        [30, discoveredCandidates[0], 91],
        [38, discoveredCandidates[1], 71],
        [46, discoveredCandidates[2], 78],
        [54, discoveredCandidates[1], 84],
      ];
      const hit = unlockAt.find(([at]) => at === tick + 1);
      if (hit) {
        const [, cand, conf] = hit;
        setUnlocked((prev) => {
          const exists = prev.find((p) => p.id === cand.id);
          const next = exists
            ? prev.map((p) => (p.id === cand.id ? { ...p, confidence: conf } : p))
            : [...prev, { ...cand, confidence: conf }];
          return next;
        });
        setMonitorLines((prev) => ([
          ...prev.slice(-79),
          {
            ts: stamp(),
            kind: 'ok',
            text: `detector     CANDIDATE  ${cand.name}  conf=${(conf / 100).toFixed(2)}  repeats=${6 + Math.floor(tick / 4)}`,
          },
        ]));
        setSelectedOps((prev) => (prev.includes(cand.name) ? prev : [...prev, cand.name]));
      }
    }, 900);
    return () => clearInterval(id);
  }, [monitoring]);

  useEffect(() => () => {
    if (sandboxTimer.current) clearTimeout(sandboxTimer.current);
  }, []);

  const toggleSelection = (name) => {
    setSelectedOps((prev) => (
      prev.includes(name) ? prev.filter((item) => item !== name) : [...prev, name]
    ));
  };

  const startMonitoring = () => {
    if (monitoring) return;
    setMonitoring(true);
    if (monitorLines.length === 0) {
      setMonitorLines([
        { ts: stamp(), kind: 'info', text: 'agent.bind     surfaces=[browser, xlsx, email]  consent=true  local_first=true' },
        { ts: stamp(), kind: 'dim',  text: 'watchdog.start pid=4412  poll=250ms  redact=schema_only' },
        { ts: stamp(), kind: 'info', text: 'session        sid=fin-q3-8841  operator=Admin User  team=Finance' },
        { ts: stamp(), kind: 'warn', text: 'note           capture stays ON while you work. pause when you want. it does not auto-stop.' },
      ]);
    }
  };

  const pauseMonitoring = () => setMonitoring(false);

  const runSandbox = () => {
    if (sandboxRun) return;
    if (sandboxTimer.current) clearTimeout(sandboxTimer.current);
    setSandboxRun(true);
    setSandboxReady(false);
    setSandboxLines([]);
    setTestStatus({});

    let i = 0;
    const play = () => {
      if (i >= SANDBOX_SCRIPT.length) {
        setSandboxRun(false);
        setSandboxReady(true);
        return;
      }
      const line = SANDBOX_SCRIPT[i];
      i += 1;
      setSandboxLines((prev) => [...prev, { ...line, ts: stamp() }]);
      if (line.test) {
        setTestStatus((prev) => ({
          ...prev,
          [line.test]: line.kind === 'ok' ? 'pass' : line.kind === 'fail' ? 'fail' : 'run',
        }));
      }
      sandboxTimer.current = setTimeout(play, line.delay);
    };
    play();
  };

  const visibleCandidates = unlocked.length ? unlocked : [];
  const stepTitles = [
    'Know Your Workflow',
    'Live Monitoring',
    'Detected Workflows',
    'Sandbox Terminal',
    'Publish & Reuse',
  ];

  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Create Automation</div>
          <h2>Create New Automation</h2>
        </div>
      </div>

      <div className="card create-flow-card">
        <div className="stepper-row">
          {stepTitles.map((title, index) => {
            const current = index + 1;
            const stateClass = current < step ? 'done' : current === step ? 'active' : 'todo';
            return (
              <button
                key={title}
                className={`step-item ${stateClass}`}
                onClick={() => setStep(current)}
              >
                <span>{current}</span>
                <p>{title}</p>
              </button>
            );
          })}
        </div>

        {step === 1 && (
          <div className="step-panel">
            <h3>Know your workflow context</h3>
            <p>Tell the agent which team and surfaces to watch. Capture stays opt-in and schema-only.</p>
            <div className="form-grid">
              <label>
                Team / Department
                <select defaultValue="Finance">
                  <option>Finance</option>
                  <option>Operations</option>
                  <option>Procurement</option>
                  <option>HR</option>
                </select>
              </label>
              <label>
                Process Type
                <select defaultValue="Compliance and filing">
                  <option>Compliance and filing</option>
                  <option>Approval workflows</option>
                  <option>Vendor onboarding</option>
                  <option>Report generation</option>
                </select>
              </label>
              <label>
                Data Sensitivity
                <select defaultValue="Medium">
                  <option>Low</option>
                  <option>Medium</option>
                  <option>High</option>
                </select>
              </label>
              <label>
                Capture surfaces
                <select defaultValue="Browser + Excel + Email">
                  <option>Browser + Excel + Email</option>
                  <option>Browser only</option>
                  <option>Excel + Email</option>
                </select>
              </label>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Live capture while you work</h3>
                <p>This does not finish in 10 seconds. The agent stays attached. Keep working — repeated sequences surface as candidates over time.</p>
              </div>
              <div className="monitor-actions">
                {!monitoring
                  ? <button className="btn-primary" onClick={startMonitoring}><Icon d={ICONS.eye} size={16} /> Start monitoring</button>
                  : <button className="btn-dark" onClick={pauseMonitoring}>Pause capture</button>}
              </div>
            </div>
            <div className="stat-pair" style={{ marginBottom: 14 }}>
              <div className="stat-box">
                <div className="stat-val">{eventCount}</div>
                <div className="stat-lbl">Structured events</div>
              </div>
              <div className="stat-box">
                <div className="stat-val">{unlocked.length}</div>
                <div className="stat-lbl">Candidates so far</div>
              </div>
            </div>
            <Terminal
              title="autostack-capture — session fin-q3-8841"
              lines={monitorLines}
              running={monitoring}
            />
            {unlocked.length > 0 && (
              <div className="live-cands">
                {unlocked.map((c) => (
                  <div className="live-cand" key={c.id}>
                    <div>
                      <div className="op-name">{c.name}</div>
                      <div className="op-sub">{c.dept} · confidence {c.confidence}%</div>
                    </div>
                    <span className="badge green">Detected</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Workflows that can be automated</h3>
                <p>
                  {monitoring
                    ? 'Capture is still running. New candidates can appear while you review this list.'
                    : unlocked.length
                      ? 'Select what to generate. You can go back and keep monitoring if the list is thin.'
                      : 'Nothing yet. Start monitoring and keep working — this list fills as patterns repeat.'}
                </p>
              </div>
              {monitoring && <span className="badge blue">Capture still live</span>}
            </div>

            {visibleCandidates.length === 0 ? (
              <div className="card empty-state" style={{ minHeight: 180 }}>
                <Icon d={ICONS.eye} size={28} />
                <p>Start live monitoring in the previous step. Candidates show up as you repeat real work — they are not preloaded.</p>
                <button className="btn-primary" onClick={() => setStep(2)}>Go to monitoring</button>
              </div>
            ) : (
              <div className="opportunities-list">
                {visibleCandidates.map((item) => {
                  const checked = selectedOps.includes(item.name);
                  return (
                    <label key={item.id} className={`opportunity ${checked ? 'checked' : ''}`}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelection(item.name)}
                      />
                      <div>
                        <div className="op-name">{item.name}</div>
                        <div className="op-sub">{item.dept} · {item.saving}</div>
                      </div>
                      <span className="badge blue">{item.confidence}% confidence</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="step-panel">
            <div className="step-head-row">
              <div>
                <h3>Sandbox verification</h3>
                <p>Watch the isolated runner. Tests execute one by one. A failed gate blocks delivery — including a deliberate header-drift injection.</p>
              </div>
              <button className="btn-primary" onClick={runSandbox} disabled={sandboxRun}>
                <Icon d={ICONS.refresh} size={16} /> {sandboxRun ? 'Running suite…' : sandboxReady ? 'Re-run suite' : 'Run sandbox'}
              </button>
            </div>
            <div className="sandbox-layout">
              <Terminal
                title="autostack-sandbox — docker://runner:1.4.2"
                lines={sandboxLines}
                running={sandboxRun}
              />
              <div className="test-rail">
                <div className="detail-label">Suite 12 tests</div>
                {SANDBOX_TESTS.map((t, idx) => {
                  const st = testStatus[t.id] || 'wait';
                  return (
                    <div key={t.id} className={`rail-row ${st}`}>
                      <span className="rail-idx">{String(idx + 1).padStart(2, '0')}</span>
                      <span className="rail-name">{t.label}</span>
                      <span className="rail-st">
                        {st === 'pass' ? 'PASS' : st === 'fail' ? 'FAIL' : st === 'run' ? 'RUN' : '—'}
                      </span>
                    </div>
                  );
                })}
                {sandboxReady && <div className="rail-done">Gate open. Artifact signed.</div>}
              </div>
            </div>
          </div>
        )}

        {step === 5 && (
          <div className="step-panel">
            <h3>Publish and share reusable automation</h3>
            <p>Only a verified artifact can be published. The registry gets the schema, not source data.</p>
            <div className="publish-box">
              <div className="publish-stat">
                <span>Selected workflows</span>
                <b>{selectedOps.length}</b>
              </div>
              <div className="publish-stat">
                <span>Sandbox gate</span>
                <b className={sandboxReady ? 'green-text' : ''}>{sandboxReady ? 'Open' : 'Closed'}</b>
              </div>
              <div className="publish-stat">
                <span>Events captured</span>
                <b>{eventCount}</b>
              </div>
            </div>
            <div className="publish-actions">
              <button
                className={`btn-primary ${published ? 'success' : ''}`}
                disabled={!sandboxReady || selectedOps.length === 0}
                onClick={() => setPublished(true)}
              >
                <Icon d={ICONS.check} size={16} /> {published ? 'Published to Registry' : 'Publish Automation'}
              </button>
              <button className="btn-outline" onClick={() => setPage('registry')}>
                <Icon d={ICONS.db} size={16} /> View Registry
              </button>
            </div>
            {!sandboxReady && <p className="helper-error">Run the sandbox suite in the previous step. Delivery stays blocked until the gate opens.</p>}
            {sandboxReady && selectedOps.length === 0 && <p className="helper-error">Select at least one detected workflow first.</p>}
          </div>
        )}

        <div className="step-actions">
          <button
            className="btn-outline"
            onClick={() => setStep((prev) => Math.max(1, prev - 1))}
            disabled={step === 1}
          >
            Back
          </button>
          {step < 5 && (
            <button
              className="btn-primary"
              onClick={() => setStep((prev) => Math.min(5, prev + 1))}
            >
              Next <Icon d={ICONS.arrow} size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function TrustLog() {
  return (
    <div className="screen">
      <div className="screen-header">
        <div>
          <div className="breadcrumb">Trust &amp; Audit</div>
          <h2>Trust Log</h2>
        </div>
        <div className="tag-row">
          <span className="tag">Hash-chained</span>
          <span className="tag">Append-only</span>
          <span className="tag">SHA-256</span>
        </div>
      </div>

      <div className="info-banner">
        <Icon d={ICONS.lock} size={18} />
        <span>Every action is logged in a hash-chained append-only table. Each entry links to the previous hash so tampering is detectable. Scripts blocked by sandbox are never delivered.</span>
      </div>

      <div className="card" style={{ padding:0, overflow:'hidden' }}>
        <table className="full-table">
          <thead>
            <tr>
              <th>Txn ID</th>
              <th>Action</th>
              <th>Workflow</th>
              <th>By</th>
              <th>Time</th>
              <th>Hash (preview)</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {trustLog.map(t => (
              <tr key={t.id}>
                <td><span className="mono">{t.id}</span></td>
                <td>{t.action}</td>
                <td className="op-name">{t.workflow}</td>
                <td><span className="tag">{t.user}</span></td>
                <td className="op-sub">{t.time}</td>
                <td><span className="mono dim">{t.hash}</span></td>
                <td><StatusBadge s={t.result} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="two-col" style={{ marginTop:20 }}>
        <div className="card">
          <div className="card-header"><strong>How the chain works</strong></div>
          <div className="timeline-list">
            {[
              'Every contribution, pull, approval, test result and rollback is recorded.',
              'Each record hashes its own content plus the previous record\'s hash.',
              'The chain is visible — any modification breaks the hash sequence immediately.',
              'Blocked sandbox tests mean a faulty script is never delivered to the user.',
              'One-click rollback is available for any approved script.',
            ].map((s, i) => (
              <div key={i} className="tl-row">
                <div className="tl-num">{i + 1}</div>
                <div className="tl-text">{s}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-header"><strong>India market context</strong></div>
          <div className="stat-list">
            {[
              ['USD 217.67M → 900.35M', 'India RPA market 2025–2034 (IMARC Group)'],
              ['51M hrs/week', 'Potential time savings for Indian workers by 2026 (Pearson)'],
              ['24% of tasks', 'Can be fully automated in key Indian industries (EY India 2025)'],
              ['6.3 crore MSMEs', 'Only ~25% using any AI/ML tools (Vi Business 2026)'],
            ].map(([val, lbl]) => (
              <div key={val} className="stat-row">
                <div className="stat-v">{val}</div>
                <div className="stat-l">{lbl}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── shell ────────────────────────────────────────────────────────────────────
const pages = [
  { id:'dashboard', label:'Dashboard',  icon: ICONS.grid },
  { id:'discovery', label:'Discovery',  icon: ICONS.zap },
  { id:'registry',  label:'Registry',   icon: ICONS.db },
  { id:'workflows', label:'Workflows',  icon: ICONS.flow },
  { id:'create',    label:'Create Automation', icon: ICONS.plus },
  { id:'trustlog',  label:'Trust Log',  icon: ICONS.shield },
];

function App() {
  const [page, setPage] = useState('dashboard');
  const Screen = {
    dashboard: Dashboard,
    discovery: Discovery,
    registry: Registry,
    workflows: Workflows,
    create: CreateAutomation,
    trustlog: TrustLog
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
          {pages.map(p => (
            <button
              key={p.id}
              className={`nav-item ${page === p.id ? 'active' : ''}`}
              onClick={() => setPage(p.id)}
            >
              <Icon d={p.icon} size={18} />
              <span>{p.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="consent-badge">
            <Icon d={ICONS.lock} size={14} />
            <span>Consent mode on</span>
          </div>
          <div className="sidebar-user">
            <div className="avatar">AU</div>
            <div>
              <div className="user-name">Admin User</div>
              <div className="user-role">System Ops</div>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <Screen setPage={setPage} />
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
