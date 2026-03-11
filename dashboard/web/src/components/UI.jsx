import React, { useState } from 'react';

export function LoadingState({ text = 'Loading...' }) {
  return (
    <div className="loading-state">
      <div className="spinner" />
      <span>{text}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div className="loading-state" style={{ flexDirection: 'column', gap: 12 }}>
      <span style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
        ✗ {message}
      </span>
      {onRetry && (
        <button className="topbar-refresh-btn" onClick={onRetry}>Retry</button>
      )}
    </div>
  );
}

export function SectionTitle({ children }) {
  return <div className="section-title">{children}</div>;
}

export function InfoTooltip({ text }) {
  const [show, setShow] = useState(false);
  return (
    <div
      style={{ position: 'absolute', top: 8, right: 8, zIndex: 10 }}
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <div style={{
        width: 15, height: 15, borderRadius: '50%',
        border: '1px solid var(--border-bright)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)',
        cursor: 'default', userSelect: 'none',
      }}>i</div>
      {show && (
        <div style={{
          position: 'absolute', top: 20, right: 0, width: 220,
          background: 'var(--bg-elevated)', border: '1px solid var(--border-bright)',
          borderRadius: 'var(--radius)', padding: '10px 12px',
          fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-secondary)',
          lineHeight: 1.6, zIndex: 100, boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
        }}>{text}</div>
      )}
    </div>
  );
}

export function MetricCard({ label, value, sub, sub2, color = '', unit = '', tooltip }) {
  return (
    <div className={`metric-card ${color}`} style={{ position: 'relative' }}>
      {tooltip && <InfoTooltip text={tooltip} />}
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${color}`}>
        {value != null ? value : '—'}
        {unit && <span style={{ fontSize: 14, marginLeft: 4, color: 'var(--text-secondary)' }}>{unit}</span>}
      </div>
      {sub  && <div className="metric-sub">{sub}</div>}
      {sub2 && <div className="metric-sub">{sub2}</div>}
    </div>
  );
}

export function Badge({ children, color = 'grey' }) {
  return <span className={`badge ${color}`}>{children}</span>;
}

export function PulseDot({ color = '' }) {
  return <span className={`pulse-dot ${color}`} />;
}

export function Card({ title, children, action, style }) {
  return (
    <div className="card" style={style}>
      {(title || action) && (
        <div className="card-header">
          {title && <div className="card-title">{title}</div>}
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function KillSwitchBanner({ state }) {
  const tripped = state?.tripped === true;
  return (
    <div className={`killswitch-bar ${tripped ? 'tripped' : 'active'}`}>
      <PulseDot color={tripped ? 'red' : 'green'} />
      <span style={{
        fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 12,
        color: tripped ? 'var(--red)' : 'var(--green)',
        letterSpacing: '0.08em', textTransform: 'uppercase',
      }}>
        KILL SWITCH: {tripped ? 'TRIPPED — TRADING HALTED' : 'ACTIVE — TRADING ENABLED'}
      </span>
      {state?.daily_pnl_pct != null && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', marginLeft: 'auto' }}>
          Daily PnL: <span style={{ color: state.daily_pnl_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {state.daily_pnl_pct >= 0 ? '+' : ''}{state.daily_pnl_pct?.toFixed(2)}%
          </span>
          {' '}/ Threshold: {state.threshold_pct ?? -3}%
        </span>
      )}
    </div>
  );
}

export function LastUpdated({ ts }) {
  if (!ts) return null;
  return (
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
      Updated {ts.toLocaleTimeString('fr-FR')}
    </span>
  );
}

export function ProgressBar({ value, max = 100, color = 'amber' }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="progress-bar">
      <div className={`progress-fill ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}
