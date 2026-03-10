import React, { useState, useEffect } from 'react';
import { api } from './api/client';
import { PulseDot } from './components/UI';

import Overview      from './pages/Overview';
import SystemMap     from './pages/SystemMap';
import Costs         from './pages/Costs';
import Trading       from './pages/Trading';
import Content       from './pages/Content';
import Infrastructure from './pages/Infrastructure';
import Docs          from './pages/Docs';

// ── Icons (inline SVG to avoid dependency) ──────────────────────────
const Icons = {
  Overview:    () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="1" width="6" height="6" rx="0.5"/><rect x="9" y="1" width="6" height="6" rx="0.5"/><rect x="1" y="9" width="6" height="6" rx="0.5"/><rect x="9" y="9" width="6" height="6" rx="0.5"/></svg>,
  Map:         () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="6"/><circle cx="8" cy="8" r="2"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="8" y1="10" x2="8" y2="14"/><line x1="2" y1="8" x2="6" y2="8"/><line x1="10" y1="8" x2="14" y2="8"/></svg>,
  Costs:       () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 1v14M5 4h4.5a2 2 0 010 4H5m0 0h5a2 2 0 010 4H5"/></svg>,
  Trading:     () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><polyline points="1,11 5,7 8,9 12,4 15,6"/><polyline points="11,4 15,4 15,8"/></svg>,
  Content:     () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="2" y="2" width="12" height="12" rx="1"/><line x1="5" y1="6" x2="11" y2="6"/><line x1="5" y1="9" x2="9" y2="9"/></svg>,
  Infra:       () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="1" y="3" width="14" height="4" rx="0.5"/><rect x="1" y="9" width="14" height="4" rx="0.5"/><circle cx="12" cy="5" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="11" r="1" fill="currentColor" stroke="none"/></svg>,
  Docs:        () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M4 2h8a1 1 0 011 1v10a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z"/><line x1="5.5" y1="6" x2="10.5" y2="6"/><line x1="5.5" y1="9" x2="8.5" y2="9"/></svg>,
  Settings:    () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><circle cx="8" cy="8" r="2.5"/><path d="M8 1v2m0 10v2M1 8h2m10 0h2m-2.5-4.5-1.5 1.5M4 4l1.5 1.5M4 12l1.5-1.5M12 12l-1.5-1.5"/></svg>,
  Refresh:     () => <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M13.5 2.5A7 7 0 102 8"/><polyline points="2,4 2,8 6,8"/></svg>,
};

// ── Navigation config ────────────────────────────────────────────────
const NAV = [
  { id: 'overview',  label: 'Vue Globale',    Icon: Icons.Overview,  Page: Overview },
  { id: 'map',       label: 'System Map',     Icon: Icons.Map,       Page: SystemMap },
  { id: 'costs',     label: 'Coûts LLM',      Icon: Icons.Costs,     Page: Costs },
  { id: 'trading',   label: 'Trading',        Icon: Icons.Trading,   Page: Trading },
  { id: 'content',   label: 'Content',        Icon: Icons.Content,   Page: Content },
  { id: 'infra',     label: 'Infrastructure', Icon: Icons.Infra,     Page: Infrastructure },
  { id: 'docs',      label: 'API Docs',       Icon: Icons.Docs,      Page: Docs },
];

// ── API Key Modal ────────────────────────────────────────────────────
function ApiKeyModal({ onSave }) {
  const [key, setKey] = useState('');
  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <div className="modal-title">⬡ OpenClaw Dashboard</div>
        <div className="modal-sub">
          Enter your API key to access the dashboard.<br />
          Set <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)' }}>DASHBOARD_API_KEY</code> in your <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>.env</code> file.
        </div>
        <input
          className="modal-input"
          type="password"
          placeholder="API key..."
          value={key}
          onChange={(e) => setKey(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && key && onSave(key)}
          autoFocus
        />
        <button className="modal-btn" onClick={() => key && onSave(key)}>
          CONNECT
        </button>
      </div>
    </div>
  );
}

// ── Settings Modal ───────────────────────────────────────────────────
function SettingsModal({ onClose }) {
  const [key, setKey] = useState(api.getApiKey());
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">Settings</div>
        <div className="modal-sub">Update your API key</div>
        <input
          className="modal-input"
          type="password"
          placeholder="New API key..."
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        <button className="modal-btn" onClick={() => { api.setApiKey(key); onClose(); }}>
          SAVE
        </button>
      </div>
    </div>
  );
}

// ── PAGE TITLES ──────────────────────────────────────────────────────
const PAGE_TITLES = {
  overview: 'VUE GLOBALE',
  map:      'SYSTEM MAP',
  costs:    'COÛTS LLM',
  trading:  'TRADING',
  content:  'CONTENT PIPELINE',
  infra:    'INFRASTRUCTURE',
  docs:     'API DOCS',
};

// ── Main App ─────────────────────────────────────────────────────────
export default function App() {
  const [page,         setPage]    = useState('overview');
  const [showSettings, setSettings] = useState(false);
  const [apiKeySet,    setApiKeySet] = useState(!!api.getApiKey());
  const [refreshKey,   setRefreshKey] = useState(0);

  const { Page } = NAV.find((n) => n.id === page) ?? NAV[0];

  if (!apiKeySet) {
    return (
      <ApiKeyModal onSave={(k) => { api.setApiKey(k); setApiKeySet(true); }} />
    );
  }

  return (
    <div className="app-shell">
      {showSettings && <SettingsModal onClose={() => setSettings(false)} />}

      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-logo">
          <div className="sidebar-logo-mark">OC</div>
          <div>
            <div className="sidebar-logo-text">OpenClaw</div>
            <div className="sidebar-logo-sub">CryptoRizon</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section-label">Navigation</div>
          {NAV.map(({ id, label, Icon }) => (
            <div
              key={id}
              className={`nav-item ${page === id ? 'active' : ''}`}
              onClick={() => setPage(id)}
            >
              <span className="nav-item-icon"><Icon /></span>
              {label}
            </div>
          ))}

          <div className="nav-section-label" style={{ marginTop: 8 }}>System</div>
          <div className="nav-item" onClick={() => setSettings(true)}>
            <span className="nav-item-icon"><Icons.Settings /></span>
            Settings
          </div>
        </nav>

        {/* Sidebar footer */}
        <div style={{
          padding: '12px 20px',
          borderTop: '1px solid var(--border)',
          fontFamily: 'var(--font-mono)',
          fontSize: 9,
          color: 'var(--text-muted)',
          lineHeight: 1.8,
        }}>
          <div>TESTNET MODE</div>
          <div style={{ color: 'var(--green)', marginTop: 2 }}>
            <span className="pulse-dot" style={{ display: 'inline-block', marginRight: 4 }} />
            POLLER ACTIVE
          </div>
        </div>
      </aside>

      {/* Main */}
      <div className="main-area">
        <header className="topbar">
          <span className="topbar-title">{PAGE_TITLES[page] ?? page.toUpperCase()}</span>
          <span className="topbar-spacer" />

          <div className="topbar-status-pill">
            <PulseDot />
            <span>TESTNET</span>
          </div>

          <button
            className="topbar-refresh-btn"
            onClick={() => setRefreshKey((k) => k + 1)}
            title="Force refresh"
          >
            <Icons.Refresh />
          </button>
        </header>

        <main className="page-content" key={`${page}-${refreshKey}`}>
          <Page />
        </main>
      </div>
    </div>
  );
}
