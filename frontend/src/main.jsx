import React, { useState, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { motion, AnimatePresence } from 'motion/react';
import './styles.css';
import './styles-premium.css';
import { subscribeLive, startLive } from './live.js';

import { Icon, ICONS, StatusBadge, Terminal, stamp } from './main-shared.jsx';
import { ThemeLogo } from './brand.jsx';
import { PageTransition, SpringPopover } from './premium.jsx';
import { ThemeSwitcher } from './premium.jsx';
import { Landing, AuthScreen } from './landing.jsx';

// ─── tiny icon set (inline SVG so no dependency issues) ───────────────────────
// ─── data ─────────────────────────────────────────────────────────────────────
// ─── screens ──────────────────────────────────────────────────────────────────
// Dashboard/Workflows/Registry/TrustLog are live modules (Phase 10).
import { Dashboard, Workflows, Registry, TrustLog } from './screens-live.jsx';
import { NotificationCenter, DataPrivacy, Connectors } from './roadmap-complete.jsx';
import { api, setToken } from './api.js';
import { Login, Profile, Teams, Runners, Scheduling } from './roadmap-pages.jsx';
import { Settings } from './settings.jsx';

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
  const shown = realCandidates;
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
          {shown.filter(c => !dismissedIds.includes(c.id)).length === 0 && (
            <div className="card empty-state" style={{ padding: 24 }}>
              <p>No qualifying patterns yet — candidates appear only from real repeated work (≥3 instances across ≥2 clients).</p>
            </div>
          )}
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
import { spring } from './motion.js';
// ─── shell ────────────────────────────────────────────────────────────────────
// Sidebar IA (Phases 4–5): three flat groups — Main / Operate / Trust. Personal
// and management screens (Profile, Teams, Settings, theme) moved out of the
// nav into the bottom account control + its popover, and into the dedicated
// Settings experience. Teams stays reachable (account menu / Settings →
// Organization & members); nothing is orphaned.
const pages = [
  { id:'dashboard',     label:'Dashboard',      icon: ICONS.grid,    group:'Main' },
  { id:'discovery',     label:'Discovery',      icon: ICONS.zap,     group:'Main' },
  { id:'create',        label:'Create',         icon: ICONS.plus,    group:'Main' },
  { id:'workflows',     label:'Workflows',      icon: ICONS.flow,    group:'Main' },
  { id:'notifications', label:'Notifications',  icon: ICONS.bell,    group:'Main' },

  { id:'scheduling',  label:'Scheduling',       icon: ICONS.clock,   group:'Operate' },
  { id:'runners',     label:'Runners',          icon: ICONS.cpu,     group:'Operate' },
  { id:'connectors',  label:'Connectors',       icon: ICONS.package, group:'Operate' },

  { id:'registry',    label:'Registry',         icon: ICONS.db,      group:'Trust' },
  { id:'trustlog',    label:'Trust Log',        icon: ICONS.shield,  group:'Trust' },
  { id:'privacy',     label:'Data & Privacy',   icon: ICONS.shield,  group:'Trust' },
];

// Unknown hashes must never dead-end: the router falls back to a real page
// with a working path back into the app.
function NotFound({ setPage }) {
  return (
    <div className="screen">
      <header className="screen-head">
        <div>
          <h1>Page not found</h1>
          <p className="muted">That link doesn't match any page in this workspace.</p>
        </div>
      </header>
      <div><button className="btn" onClick={() => setPage('dashboard')}>Go to Dashboard</button></div>
    </div>
  );
}

function App() {
  // Hash router: the URL is the source of truth, so deep links (#/page) survive
  // reloads and every navigation writes a shareable hash. Unknown hashes render
  // NotFound (never a blank screen).
  const pageForHash = () => {
    const h = (window.location.hash || '').replace(/^#/, '');
    if (!h) return 'dashboard';
    // Settings owns its sub-path (#/settings/<section>); the app router only
    // needs to know the context is "settings".
    if (h.startsWith('settings')) return 'settings';
    return h;
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
  const [authMode, setAuthMode] = useState(null); // null → landing; 'login'|'signup' → auth hero
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
    // Cinematic landing is the entry surface; the auth card appears as a
    // hero-split screen (AuthScreen) so context is never lost.
    if (!authMode) {
      return <Landing
        workerUp={workerUp}
        onSignUp={() => setAuthMode('signup')}
        onSignIn={() => setAuthMode('login')}
      />;
    }
    return (
      <AuthScreen>
        <Login
          setPage={setPage}
          initialMode={authMode}
          onBack={() => setAuthMode(null)}
          setIdentity={(me) => { setIdentity(me); setAuthState('ok'); }}
        />
      </AuthScreen>
    );
  }
  // BUGFIX (Phase 2 audit): Dashboard/Discovery/Workflows/Create render real
  // navigation buttons that call setPage — they must receive it, or every one
  // of those buttons throws "setPage is not a function" on click.
  const screenMap = {
    settings: <Settings identity={identity} onExit={() => setPage('dashboard')} setPage={setPage} />,
    profile: <Profile identity={identity} />,
    teams: <Teams identity={identity} />,
    runners: <Runners identity={identity} />,
    scheduling: <Scheduling identity={identity} />,
    notifications: <NotificationCenter />,
    privacy: <DataPrivacy />,
    connectors: <Connectors />,
    dashboard: <Dashboard setPage={setPage} />,
    discovery: <Discovery setPage={setPage} />,
    registry: <Registry identity={identity} />,
    workflows: <Workflows setPage={setPage} />,
    create: <CreateAutomation setPage={setPage} />,
    trustlog: <TrustLog />,
  };
  const Screen = screenMap[page] || <NotFound setPage={setPage} />;

  const doSignOut = async () => {
    setToken('');
    setIdentity(null);
    setAuthState('anon');
    setPage('dashboard');
  };
  const isOwner = !!(identity && identity.role === 'owner');

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand" aria-label="AutoStack IN">
          <ThemeLogo lockup={false} h={34} />
        </div>

        <nav className="nav">
          {['Main', 'Operate', 'Trust'].map(group => (
            <div key={group} className="nav-group">
              <div className="nav-group-label">{group}</div>
              {pages.filter(p => p.group === group).map(p => (
                <button
                  key={p.id}
                  className={`nav-item ${page === p.id ? 'active' : ''}`}
                  title={p.label === 'Create' ? 'Create automation' : undefined}
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
          <div className="consent-badge" title={workerUp ? 'Worker on :8747 — live data' : 'Worker unreachable — demo data shown'}>
            <Icon d={ICONS.lock} size={14} />
            <span>{workerUp ? 'Worker: LIVE' : 'Worker: demo mode'}</span>
          </div>
          {/* Phase 6: one interactive account control opens the account popover
              (Account / Members / Settings / Appearance / Sign out). Keyboard,
              outside-click and Escape close live in SpringPopover. */}
          {identity && identity.user ? (
            <SpringPopover
              className="account-pop"
              align="left"
              label={
                <span className="sidebar-user account-btn">
                  <span className="avatar">{identity.user.username.slice(0, 2).toUpperCase()}</span>
                  <span className="sidebar-user-meta">
                    <span className="user-name">{identity.user.display_name || identity.user.username}</span>
                    <span className="user-role">{identity ? `${identity.capabilities.tier} · ${identity.role}` : ''}</span>
                  </span>
                  <Icon d={ICONS.chevron} size={14} />
                </span>
              }
            >
              {({ close }) => (
                <div className="account-menu">
                  <div className="account-menu-head">
                    <span className="user-name">{identity.user.display_name || identity.user.username}</span>
                    <span className="user-role">@{identity.user.username} · {identity.role} · {identity.capabilities.tier} tier</span>
                  </div>
                  <button className="account-item" onClick={() => { close(); setPage('profile'); }}>
                    <Icon d={ICONS.user} size={16} /> Account &amp; tokens
                  </button>
                  {isOwner && (
                    <button className="account-item" onClick={() => { close(); setPage('teams'); }}>
                      <Icon d={ICONS.users} size={16} /> Members &amp; organization
                    </button>
                  )}
                  <button className="account-item" onClick={() => { close(); setPage('settings'); }}>
                    <Icon d={ICONS.cog} size={16} /> Settings
                  </button>
                  <div className="account-menu-sep" />
                  <div className="account-theme">
                    <span>Appearance</span>
                    <ThemeSwitcher compact />
                  </div>
                  <div className="account-menu-sep" />
                  <button className="account-item danger" onClick={() => { close(); doSignOut(); }}>
                    <Icon d={ICONS.logout} size={16} /> Sign out
                  </button>
                </div>
              )}
            </SpringPopover>
          ) : (
            <div className="sidebar-user">
              <div className="avatar">SV</div>
              <div className="sidebar-user-meta">
                <div className="user-name">Service token</div>
                <div className="user-role">legacy mode</div>
              </div>
            </div>
          )}
        </div>
      </aside>

      <main className="main">
        <PageTransition pageKey={page}>
          {Screen}
        </PageTransition>
      </main>
    </div>
  );
}

createRoot(document.getElementById('root')).render(<App />);
