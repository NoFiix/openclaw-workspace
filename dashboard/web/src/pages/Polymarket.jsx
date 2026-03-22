import { useState, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, LineChart, Line, ReferenceLine,
} from 'recharts';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import {
  LoadingState, ErrorState, SectionTitle, MetricCard,
  Card, Badge, LastUpdated,
} from '../components/UI';

// ── Local helpers ─────────────────────────────────────────────────────────────
function fmtEUR(val) {
  if (val == null) return '—';
  const abs = Math.abs(val);
  const sign = val < 0 ? '-' : val > 0 ? '+' : '';
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(2)}k$`;
  return `${sign}${abs.toFixed(2)}$`;
}

function healthLabel(score) {
  if (score == null) return '—';
  if (score >= 80) return 'Healthy';
  if (score >= 60) return 'Dégradé';
  if (score >= 40) return 'Alerte';
  return 'Critique';
}

function healthColor(score) {
  if (score == null) return '';
  if (score >= 80) return 'green';
  if (score >= 60) return 'amber';
  return 'red';
}

function statusColor(s) {
  if (!s) return 'grey';
  const sl = s.toLowerCase();
  if (sl.includes('paper') || sl.includes('test')) return 'blue';
  if (sl === 'active' || sl === 'running') return 'green';
  if (sl === 'stopped' || sl === 'disabled') return 'red';
  if (sl === 'paused') return 'amber';
  return 'grey';
}

function statusLabel(s) {
  if (!s) return '—';
  const map = {
    paper_testing: 'TESTING',
    active:        'RUNNING',
    stopped:       'STOPPED',
    disabled:      'HALTED',
    paused:        'PAUSED',
  };
  return map[s.toLowerCase()] ?? s.toUpperCase();
}

function agentStatusColor(s) {
  if (!s) return 'grey';
  const sl = s.toLowerCase();
  if (sl === 'active') return 'green';
  if (sl === 'stale')  return 'amber';
  if (sl === 'disabled' || sl === 'offline' || sl === 'error') return 'red';
  return 'grey';
}

function signalFreshness(epochSec) {
  if (epochSec == null) return { label: 'OFFLINE', color: 'red' };
  const ageS = Math.floor(Date.now() / 1000) - epochSec;
  if (ageS < 300)  return { label: 'FRESH',  color: 'green' };
  if (ageS < 1800) return { label: 'AGING',  color: 'amber' };
  return { label: 'STALE', color: 'red' };
}

function riskBadgeColor(state) {
  if (!state || state === 'NORMAL') return 'green';
  if (state === 'ALERTE' || state === 'ELEVATED') return 'amber';
  if (state === 'CRITIQUE' || state === 'ARRET_TOTAL' || state === 'KILL_SWITCH') return 'red';
  return 'amber';
}

function ageLabel(epochSec) {
  if (epochSec == null) return '—';
  const s = Math.floor(Date.now() / 1000) - epochSec;
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  return `${Math.floor(s / 3600)}h`;
}

// ── Sub-components ────────────────────────────────────────────────────────────
const TH = ({ children, onClick, active, dir }) => (
  <th
    onClick={onClick}
    style={{
      textAlign: 'left', padding: '5px 8px', fontSize: 8, fontWeight: 600,
      letterSpacing: '.12em', textTransform: 'uppercase', whiteSpace: 'nowrap',
      color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
      borderBottom: '1px solid var(--border)',
      cursor: onClick ? 'pointer' : 'default', userSelect: 'none',
    }}
  >
    {children}{active ? (dir === -1 ? ' ▼' : ' ▲') : ''}
  </th>
);

const TD = ({ children, style }) => (
  <td style={{ padding: '7px 8px', fontFamily: 'var(--font-mono)', fontSize: 11, verticalAlign: 'middle', ...style }}>
    {children}
  </td>
);

const RowInfo = ({ label, value, color }) => (
  <div className="fbet" style={{ padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>{label}</span>
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: color ? `var(--${color})` : 'var(--text-primary)' }}>
      {value}
    </span>
  </div>
);

// ── Kill switch / status banner ───────────────────────────────────────────────
function StatusBanner({ live }) {
  const status  = live?.global_status ?? 'NORMAL';
  const isAlert = status !== 'NORMAL';
  const label   = status === 'ARRET_TOTAL' ? 'DÉCLENCHÉ — TRADING ARRÊTÉ'
    : status === 'CRITIQUE' ? 'CRITIQUE — SURVEILLANCE ACTIVE'
    : status === 'ALERTE'   ? 'ALERTE — TRADING SOUS SURVEILLANCE'
    : 'NORMAL — TRADING ACTIF';
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px',
      borderRadius: 'var(--radius)', border: '1px solid', marginBottom: 20,
      background: isAlert ? 'var(--red-glow)' : 'var(--green-glow)',
      borderColor: isAlert ? 'var(--red)' : 'var(--green)',
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%', display: 'inline-block', flexShrink: 0,
        background: isAlert ? 'var(--red)' : 'var(--green)',
        boxShadow: isAlert ? '0 0 6px var(--red)' : '0 0 6px var(--green)',
      }} />
      <span style={{
        fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11,
        color: isAlert ? 'var(--red)' : 'var(--green)',
        textTransform: 'uppercase', letterSpacing: '.08em',
      }}>
        POLY KILL SWITCH: {label}
      </span>
      <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)', display: 'flex', gap: 16 }}>
        <span>PnL jour: <span style={{ color: (live?.pnl_today ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{fmtEUR(live?.pnl_today ?? 0)}</span></span>
        <span>Positions: <span style={{ color: 'var(--amber)' }}>{live?.open_positions_count ?? 0}</span></span>
        <span>Stratégies: <span style={{ color: 'var(--blue)' }}>{live?.active_strategies_count ?? 0}</span></span>
      </span>
    </div>
  );
}

// ── Strategy card ─────────────────────────────────────────────────────────────
function StrategyCard({ s, onSelect, selected }) {
  const pnlPos = (s.pnl_eur ?? 0) >= 0;
  const isLive = s.mode === 'live';
  const ddHigh = (s.drawdown ?? 0) > 4;
  return (
    <div
      onClick={() => onSelect(s.name)}
      style={{
        background: 'var(--bg-card)',
        border: `1px solid ${selected ? (isLive ? 'var(--green)' : 'var(--blue)') : ddHigh ? 'rgba(239,68,68,.5)' : 'var(--border)'}`,
        borderRadius: 'var(--radius)', padding: '14px 16px', cursor: 'pointer',
        transition: 'border-color .15s',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10, minWidth: 0 }}>
        <span style={{
          fontFamily: 'var(--font-mono)', fontSize: 10, fontWeight: 700,
          color: 'var(--text-primary)', flex: 1,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {s.name.replace('POLY_', '')}
        </span>
        <Badge color={isLive ? 'green' : 'blue'}>{isLive ? 'LIVE' : 'PAPER'}</Badge>
        <Badge color={statusColor(s.status)}>{statusLabel(s.status)}</Badge>
      </div>

      {/* Main P&L + Capital */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color: pnlPos ? 'var(--green)' : 'var(--red)', lineHeight: 1 }}>
            {fmtEUR(s.pnl_eur ?? 0)}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>
            {s.pnl_percent != null
              ? `${s.pnl_percent >= 0 ? '+' : ''}${s.pnl_percent.toFixed(2)}%`
              : '—'}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--text-primary)', fontWeight: 600 }}>
            {s.capital != null ? `${s.capital.toFixed(0)}$` : '—'}
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginTop: 2 }}>capital</div>
        </div>
      </div>

      {/* Metric pills */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 5, marginBottom: 8 }}>
        {[
          { label: 'Pos',    value: `${s.positions_open ?? 0}/${s.positions_limit ?? 6}`, ok: (s.positions_open ?? 0) > 0 && (s.positions_open ?? 0) < 4, warn: (s.positions_open ?? 0) >= (s.positions_limit ?? 6), mild: (s.positions_open ?? 0) >= 4 },
          { label: 'ROI',    value: s.roi_pct != null ? `${s.roi_pct >= 0 ? '+' : ''}${s.roi_pct.toFixed(1)}%` : '—', ok: (s.roi_pct ?? 0) > 0, warn: (s.roi_pct ?? 0) < -10 },
          { label: 'Win%',   value: s.win_rate  != null ? `${s.win_rate.toFixed(0)}%`  : '—', ok: (s.win_rate  ?? 0) >= 52.6 },
          { label: 'DD',     value: s.drawdown  != null ? `${s.drawdown.toFixed(1)}%`  : '—', warn: (s.drawdown ?? 0) > 4, mild: (s.drawdown ?? 0) > 2 },
        ].map(({ label, value, ok, warn, mild }) => (
          <div key={label} style={{ background: 'var(--bg-elevated)', borderRadius: 3, padding: '4px 6px' }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.08em' }}>{label}</div>
            <div style={{
              fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
              color: warn ? 'var(--red)' : mild ? 'var(--amber)' : ok ? 'var(--green)' : 'var(--text-secondary)',
            }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
          {s.trades_total ?? 0} trades · {(s.capital_committed ?? 0) > 0 ? `${s.capital_committed.toFixed(0)}$ engagé` : '0$ engagé'}
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
          {timeAgo(s.last_activity)}
        </span>
      </div>
    </div>
  );
}

// ── Trade feed row ─────────────────────────────────────────────────────────────
function TradeFeedRow({ t }) {
  const time = t.timestamp
    ? new Date(t.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';
  const sideColor = t.direction === 'YES' ? 'var(--green)' : t.direction === 'NO' ? 'var(--red)' : 'var(--blue)';
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '62px minmax(0,1fr) 44px 52px 58px',
      gap: 8, padding: '6px 8px', borderBottom: '1px solid var(--border)',
      fontFamily: 'var(--font-mono)', fontSize: 10, alignItems: 'center',
    }}>
      <span style={{ color: 'var(--text-muted)', fontSize: 9 }}>{time}</span>
      <span style={{ color: 'var(--text-secondary)', fontSize: 9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        <span style={{ color: 'var(--blue)', fontWeight: 700 }}>{t.strategy ? t.strategy.replace('POLY_', '') : '—'}</span>
        {t.market_id && <span style={{ color: 'var(--text-muted)' }}> · {t.market_id.slice(0, 14)}</span>}
      </span>
      <span style={{ color: sideColor, fontWeight: 700 }}>{t.direction ?? '—'}</span>
      <span style={{ color: 'var(--text-primary)' }}>{t.fill_price != null ? t.fill_price.toFixed(3) : '—'}</span>
      <span style={{ color: 'var(--amber)' }}>{t.size_eur != null ? `${t.size_eur.toFixed(0)}$` : '—'}</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function Polymarket() {
  const [selectedStrategy, setSelectedStrategy] = useState(null);
  const [sortBy,  setSortBy]  = useState('pnl_eur');
  const [sortDir, setSortDir] = useState(-1);   // -1 = descending
  const [leaderMetric, setLeaderMetric] = useState('pnl_percent');

  const fetchLive       = useCallback(() => api.polyLive(),       []);
  const fetchStrategies = useCallback(() => api.polyStrategies(), []);
  const fetchTrades     = useCallback(() => api.polyTrades(),     []);
  const fetchHealth     = useCallback(() => api.polyHealth(),     []);

  const { data: live,       loading: lLive, error: eLive, refresh: rLive, lastUpdated } = useApiData(fetchLive,       30000);
  const { data: strategies                                                              } = useApiData(fetchStrategies, 60000);
  const { data: tradesData                                                              } = useApiData(fetchTrades,     60000);
  const { data: health                                                                  } = useApiData(fetchHealth,     30000);

  if (lLive && !live) return <LoadingState text="Chargement Polymarket..." />;
  if (eLive && !live) return <ErrorState message={eLive} onRetry={rLive} />;

  // ── Data ─────────────────────────────────────────────────────────────────
  // Strategies: prefer /strategies (richer) else fall back to /live active_strategies
  const stratList    = strategies?.strategies ?? live?.active_strategies ?? [];
  const recentTrades = live?.recent_trades ?? [];
  const allTrades    = tradesData?.trades   ?? [];
  const agents       = health?.agents_status  ?? [];
  const signals      = health?.signal_freshness ?? {};

  const openPositions = live?.open_positions ?? [];

  const healthScore    = live?.system_health_score ?? null;
  const totalPnl       = live?.total_pnl_paper       ?? 0;
  const totalCap       = live?.total_capital_deployed ?? 0;
  const totalCommitted = live?.total_capital_committed ?? 0;
  const totalAvailable = live?.total_capital_available ?? totalCap;
  const engagedPct     = totalCap > 0 ? (totalCommitted / totalCap * 100) : 0;
  const pnlPct         = totalCap > 0 ? (totalPnl / totalCap) * 100 : 0;
  const pnlToday       = live?.pnl_today              ?? 0;
  const unrealizedPnl  = live?.unrealized_pnl         ?? null;
  const openPos        = live?.open_positions_count   ?? 0;
  const activeStrat    = live?.active_strategies_count ?? 0;

  const globalMaxDD  = stratList.length > 0
    ? Math.max(0, ...stratList.map(s => s.drawdown ?? 0))
    : live?.max_drawdown_global ?? 0;
  const globalSharpe = live?.sharpe_global ?? null;

  const paperCount = stratList.filter(s => s.mode !== 'live').length;
  const liveCount  = stratList.filter(s => s.mode === 'live').length;

  const sysStatus = live?.global_status === 'ARRET_TOTAL' ? 'HALTED'
    : live?.global_status === 'CRITIQUE' ? 'DEGRADED'
    : live?.global_status === 'ALERTE'   ? 'DEGRADED'
    : 'RUNNING';

  // Sorted comparison table
  function toggleSort(col) {
    if (sortBy === col) setSortDir(d => -d);
    else { setSortBy(col); setSortDir(-1); }
  }
  const sortedStrats = [...stratList].sort((a, b) => {
    const va = a[sortBy];
    const vb = b[sortBy];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortDir * (typeof va === 'string' ? va.localeCompare(vb) : va - vb);
  });

  // Leaderboard
  const leaderData = [...stratList]
    .map(s => ({ name: s.name.replace('POLY_', ''), val: s[leaderMetric] ?? 0 }))
    .sort((a, b) => b.val - a.val);

  // Equity curve from resolved trades
  const resolvedTrades = allTrades.filter(t => t.pnl_eur != null);
  const equityData = (() => {
    let cum = 0;
    return resolvedTrades.map(t => {
      cum += t.pnl_eur;
      return { ts: t.timestamp?.slice(0, 10) ?? '—', pnl: parseFloat(cum.toFixed(2)) };
    });
  })();

  // Drawdown bar data
  const drawdownData = stratList.map(s => ({
    name: s.name.replace('POLY_', ''),
    dd: -(s.drawdown ?? 0),
  }));

  // Promotion gate derived
  const promotionRows = stratList.map(s => {
    const eligible = (s.win_rate ?? 0) >= 52.6 && (s.sharpe ?? 0) >= 2.5
      && (s.drawdown ?? 0) < 5 && (s.trades_total ?? 0) >= 50;
    const near = !eligible && ((s.win_rate ?? 0) >= 48 || (s.sharpe ?? 0) >= 2.0);
    const promoStatus = s.promotion_status === 'pending' ? 'PENDING'
      : eligible ? 'ELIGIBLE'
      : near     ? 'NEAR'
      : 'NOT_ELIGIBLE';
    return { ...s, promoStatus };
  });
  const promoColor = { PENDING: 'amber', ELIGIBLE: 'green', NEAR: 'blue', NOT_ELIGIBLE: 'grey' };

  return (
    <div>
      {/* ── 6.1 HEADER ── */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 20 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '.06em', textTransform: 'uppercase' }}>
            Polymarket
          </div>
          <div style={{ fontFamily: 'var(--font-ui)', fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
            Automated Prediction Market Trading
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <Badge color={sysStatus === 'RUNNING' ? 'green' : sysStatus === 'HALTED' ? 'red' : 'amber'}>
            {sysStatus}
          </Badge>
          <Badge color={riskBadgeColor(live?.global_status)}>
            {`RISK: ${live?.global_status ?? 'NORMAL'}`}
          </Badge>
          <Badge color="blue">PAPER {paperCount} / LIVE {liveCount}</Badge>
        </div>
      </div>

      <StatusBanner live={live} />

      {/* ── 6.2 KPI STRIP ── */}
      <SectionTitle>Vue d'Ensemble</SectionTitle>
      <div className="g3 mb12">
        <MetricCard
          label="System Health"
          value={healthScore != null ? `${healthScore} / 100` : '—'}
          color={healthColor(healthScore)}
          sub={healthLabel(healthScore)}
          tooltip="Score synthétique basé sur le statut global, dead letters et agents désactivés. 80–100 = vert, 60–79 = dégradé, < 40 = critique."
        />
        <MetricCard
          label="Capital"
          value={`${totalCap.toFixed(0)}$`}
          color="blue"
          sub={`Dispo: ${totalAvailable.toFixed(0)}$ · Engagé: ${totalCommitted.toFixed(0)}$ (${engagedPct.toFixed(1)}%)`}
          tooltip="Capital total déployé sur toutes les stratégies. Disponible = somme des capital.available par stratégie."
        />
        <MetricCard
          label="Total P&L (Paper)"
          value={fmtEUR(totalPnl)}
          color={(totalPnl ?? 0) >= 0 ? 'green' : 'red'}
          sub={`${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}% · Jour: ${fmtEUR(pnlToday)} · Unreal: ${unrealizedPnl != null ? fmtEUR(unrealizedPnl) : 'N/A'}`}
          tooltip="P&L réalisé cumulé. Unrealized PnL non disponible (calcul hors scope)."
        />
      </div>
      <div className="g3 mb24">
        <MetricCard
          label="Max Drawdown"
          value={`${globalMaxDD.toFixed(2)}%`}
          color={globalMaxDD > 5 ? 'red' : globalMaxDD > 2 ? 'amber' : 'green'}
          sub="seuil kill switch stratégie: -5% / -30%"
          tooltip="Pire drawdown observé parmi toutes les stratégies actives."
        />
        <MetricCard
          label="Positions Ouvertes"
          value={`${openPos}`}
          color={openPos >= 5 ? 'amber' : openPos > 0 ? 'blue' : 'green'}
          sub={`${totalCommitted.toFixed(0)}$ engagé · max 6/stratégie`}
          tooltip="Capital actuellement alloué dans des positions ouvertes. Ces positions se résolvent à la clôture du marché — pas de TP/SL."
        />
        <MetricCard
          label="Stratégies Actives"
          value={`${activeStrat} / ${stratList.length || 9}`}
          color="blue"
          sub={`${paperCount} paper · ${liveCount} live`}
        />
      </div>

      {/* ── 6.3 PERFORMANCE CHARTS ── */}
      <SectionTitle>Performance</SectionTitle>
      <div className="g2 mb24">
        <Card title="Equity Curve">
          <div style={{ height: 170, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {equityData.length < 2 ? (
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                  En cours de collecte
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', marginTop: 4 }}>
                  Disponible après résolution des marchés
                </div>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={equityData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="ts" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                  <ReferenceLine y={0} stroke="var(--border-bright)" />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 10 }}
                    formatter={v => [`${v}$`, 'P&L cumulé']}
                  />
                  <Line type="monotone" dataKey="pnl" stroke="var(--green)" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>

        <Card title="Drawdown par Stratégie">
          <div style={{ height: 170, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            {drawdownData.every(d => d.dd === 0) ? (
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>
                Aucun drawdown enregistré
              </span>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={drawdownData} margin={{ top: 4, right: 4, left: -20, bottom: 20 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontFamily: 'var(--font-mono)', fontSize: 7, fill: 'var(--text-secondary)', angle: -30, textAnchor: 'end' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                  <ReferenceLine y={0} stroke="var(--border-bright)" />
                  <Tooltip
                    contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 10 }}
                    formatter={v => [`${(-v).toFixed(2)}%`, 'Drawdown']}
                  />
                  <Bar dataKey="dd" radius={1}>
                    {stratList.map((s, i) => (
                      <Cell key={i} fill={
                        (s.drawdown ?? 0) > 4 ? 'var(--red)'
                          : (s.drawdown ?? 0) > 2 ? 'var(--amber)'
                          : 'var(--blue)'
                      } />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Card>
      </div>

      {/* ── 6.4 STRATEGY CARDS GRID ── */}
      <SectionTitle>Stratégies ({stratList.length})</SectionTitle>
      {stratList.length === 0 ? (
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', padding: '16px 0', marginBottom: 24 }}>
          Aucune stratégie chargée
        </div>
      ) : (
        <div className="g3 mb24">
          {stratList.map(s => (
            <StrategyCard
              key={s.name}
              s={s}
              onSelect={n => setSelectedStrategy(prev => prev === n ? null : n)}
              selected={selectedStrategy === s.name}
            />
          ))}
        </div>
      )}

      {/* ── 6.5 STRATEGY ANALYSIS ── */}
      <SectionTitle>Analyse Stratégies</SectionTitle>
      <div className="g2 mb24">
        {/* Leaderboard */}
        <Card
          title="Classement"
          action={
            <div style={{ display: 'flex', gap: 4 }}>
              {[
                { id: 'pnl_percent', label: 'P&L%' },
                { id: 'win_rate',    label: 'Win%' },
                { id: 'sharpe',      label: 'Sharpe' },
              ].map(m => (
                <button key={m.id} onClick={() => setLeaderMetric(m.id)} style={{
                  padding: '2px 8px', border: '1px solid',
                  borderColor: leaderMetric === m.id ? 'var(--blue)' : 'var(--border)',
                  background:  leaderMetric === m.id ? 'var(--blue-dim)' : 'transparent',
                  color:       leaderMetric === m.id ? 'var(--blue)' : 'var(--text-muted)',
                  fontFamily: 'var(--font-mono)', fontSize: 9,
                  borderRadius: 'var(--radius)', cursor: 'pointer',
                }}>{m.label}</button>
              ))}
            </div>
          }
        >
          <div style={{ height: 230 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={leaderData} layout="vertical" margin={{ top: 0, right: 8, left: 4, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={92} tick={{ fontFamily: 'var(--font-mono)', fontSize: 8, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                <ReferenceLine x={0} stroke="var(--border-bright)" />
                <Tooltip
                  contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', fontFamily: 'var(--font-mono)', fontSize: 10 }}
                  formatter={v => [v != null ? v.toFixed(2) : '—', leaderMetric]}
                />
                <Bar dataKey="val" radius={1}>
                  {leaderData.map((e, i) => (
                    <Cell key={i} fill={(e.val ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Comparison table */}
        <Card title="Tableau Comparatif">
          <div style={{ overflowX: 'auto' }}>
            <table className="page-table">
              <thead><tr>
                <TH>Stratégie</TH>
                <TH>Mode</TH>
                <TH onClick={() => toggleSort('capital')}     active={sortBy === 'capital'}     dir={sortDir}>Capital</TH>
                <TH onClick={() => toggleSort('capital_committed')} active={sortBy === 'capital_committed'} dir={sortDir}>Engagé</TH>
                <TH onClick={() => toggleSort('positions_open')}    active={sortBy === 'positions_open'}    dir={sortDir}>Pos</TH>
                <TH onClick={() => toggleSort('pnl_eur')}     active={sortBy === 'pnl_eur'}     dir={sortDir}>P&L $</TH>
                <TH onClick={() => toggleSort('pnl_percent')} active={sortBy === 'pnl_percent'} dir={sortDir}>P&L %</TH>
                <TH onClick={() => toggleSort('win_rate')}    active={sortBy === 'win_rate'}    dir={sortDir}>Win%</TH>
                <TH onClick={() => toggleSort('sharpe')}      active={sortBy === 'sharpe'}      dir={sortDir}>Sharpe</TH>
                <TH onClick={() => toggleSort('drawdown')}    active={sortBy === 'drawdown'}    dir={sortDir}>DD</TH>
                <TH>Trades</TH>
              </tr></thead>
              <tbody>
                {sortedStrats.length === 0 ? (
                  <tr><td colSpan={11} style={{ padding: '16px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10, textAlign: 'center' }}>Aucune donnée</td></tr>
                ) : sortedStrats.map(s => {
                  const isLive = s.mode === 'live';
                  const active = selectedStrategy === s.name;
                  return (
                    <tr key={s.name} style={{ cursor: 'pointer' }}
                      onClick={() => setSelectedStrategy(prev => prev === s.name ? null : s.name)}>
                      <TD style={{ fontSize: 9, color: active ? 'var(--blue)' : 'var(--text-primary)', fontWeight: active ? 700 : 400 }}>
                        {s.name.replace('POLY_', '')}
                      </TD>
                      <TD><Badge color={isLive ? 'green' : 'blue'}>{isLive ? 'LIVE' : 'PAPER'}</Badge></TD>
                      <TD>{s.capital != null ? `${s.capital.toFixed(0)}$` : '—'}</TD>
                      <TD style={{ color: (s.capital_committed ?? 0) > 0 ? 'var(--amber)' : 'var(--text-secondary)' }}>
                        {(s.capital_committed ?? 0) > 0 ? `${s.capital_committed.toFixed(0)}$` : '0$'}
                      </TD>
                      <TD style={{ color: (s.positions_open ?? 0) > 0 ? 'var(--blue)' : 'var(--text-secondary)' }}>
                        {`${s.positions_open ?? 0}/${s.positions_limit ?? 6}`}
                      </TD>
                      <TD style={{ color: (s.pnl_eur ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                        {fmtEUR(s.pnl_eur ?? 0)}
                      </TD>
                      <TD style={{ color: (s.pnl_percent ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                        {s.pnl_percent != null ? `${s.pnl_percent >= 0 ? '+' : ''}${s.pnl_percent.toFixed(2)}%` : '—'}
                      </TD>
                      <TD style={{ color: (s.win_rate ?? 0) >= 52.6 ? 'var(--green)' : 'var(--text-secondary)' }}>
                        {s.win_rate != null ? `${s.win_rate.toFixed(1)}%` : '—'}
                      </TD>
                      <TD style={{ color: (s.sharpe ?? 0) >= 2.5 ? 'var(--green)' : 'var(--text-secondary)' }}>
                        {s.sharpe != null ? s.sharpe.toFixed(2) : '—'}
                      </TD>
                      <TD style={{ color: (s.drawdown ?? 0) > 4 ? 'var(--red)' : (s.drawdown ?? 0) > 2 ? 'var(--amber)' : 'var(--text-secondary)' }}>
                        {s.drawdown != null ? `${s.drawdown.toFixed(1)}%` : '—'}
                      </TD>
                      <TD>{s.trades_total ?? 0}</TD>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      {/* ── 6.6 EXECUTION ── */}
      <SectionTitle>Exécution</SectionTitle>
      <div className="g2 mb24">
        {/* Live Trade Feed */}
        <Card title="Trades Récents">
          {recentTrades.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '20px 0', textAlign: 'center' }}>
              Aucun trade exécuté pour l'instant
            </div>
          ) : (
            <div>
              <div style={{ display: 'grid', gridTemplateColumns: '62px minmax(0,1fr) 44px 52px 58px', gap: 8, padding: '4px 8px', borderBottom: '1px solid var(--border)' }}>
                {['Heure', 'Stratégie / Marché', 'Side', 'Prix', 'Taille'].map(h => (
                  <span key={h} style={{ fontFamily: 'var(--font-mono)', fontSize: 8, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.1em' }}>{h}</span>
                ))}
              </div>
              {recentTrades.map((t, i) => <TradeFeedRow key={i} t={t} />)}
            </div>
          )}
        </Card>

        {/* Open Positions — source: portfolio_state.json */}
        <Card title={`Positions Ouvertes (${openPos})`}>
          {openPos === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '20px 0', textAlign: 'center' }}>
              Aucune position ouverte
            </div>
          ) : (
            <table className="page-table">
              <thead><tr>
                <TH>Stratégie</TH><TH>Marché</TH><TH>Catégorie</TH><TH>Direction</TH><TH>Taille</TH><TH>Ouvert</TH><TH>Lien</TH>
              </tr></thead>
              <tbody>
                {openPositions.map((p, i) => (
                  <tr key={i}>
                    <TD style={{ fontSize: 9 }}>{p.strategy ? p.strategy.replace('POLY_', '') : '—'}</TD>
                    <TD style={{ fontSize: 9, color: 'var(--text-muted)', maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.market_id ? `${p.market_id.slice(0, 10)}…${p.market_id.slice(-6)}` : '—'}
                    </TD>
                    <TD style={{ fontSize: 9 }}>{p.category && p.category !== 'unknown' ? p.category : '—'}</TD>
                    <TD style={{ fontSize: 9 }}>{p.direction ?? '—'}</TD>
                    <TD style={{ color: 'var(--amber)' }}>{p.size_eur != null ? `${p.size_eur.toFixed(0)}$` : '—'}</TD>
                    <TD style={{ color: 'var(--text-muted)', fontSize: 9 }}>{p.opened_at ? timeAgo(p.opened_at) : '—'}</TD>
                    <TD>{p.market_url ? <a href={p.market_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--blue)', fontSize: 9, textDecoration: 'none' }}>↗</a> : '—'}</TD>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {/* ── 6.7 RISK MANAGEMENT ── */}
      <SectionTitle>Risk Management</SectionTitle>
      <div className="g2 mb24">
        {/* Risk Overview */}
        <Card title="Risk Overview">
          <RowInfo
            label="Global Kill Switch"
            value={<Badge color={riskBadgeColor(live?.global_status)}>{live?.global_status ?? 'NORMAL'}</Badge>}
          />
          <RowInfo
            label="Max Drawdown global"
            value={`${globalMaxDD.toFixed(2)}%`}
            color={globalMaxDD > 5 ? 'red' : globalMaxDD > 2 ? 'amber' : 'green'}
          />
          <RowInfo
            label="Capital total déployé"
            value={`${(totalCap ?? 0).toFixed(0)}$`}
          />
          <RowInfo
            label="Positions ouvertes"
            value={`${openPos}`}
            color={openPos > 0 ? 'blue' : 'green'}
          />
          <RowInfo
            label="Dead letters (bus)"
            value={health?.dead_letter_count ?? 0}
            color={(health?.dead_letter_count ?? 0) > 0 ? 'amber' : ''}
          />
          <RowInfo
            label="Events bus (pending)"
            value={health?.bus_pending_real ?? 0}
          />
        </Card>

        {/* Promotion Gate */}
        <Card title="Promotion Gate">
          <div style={{ marginBottom: 8, fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>
            Critères: Win% ≥ 52.6 · Sharpe ≥ 2.5 · DD &lt; 5% · ≥ 50 trades · ≥ 14j paper
          </div>
          <table className="page-table">
            <thead><tr>
              <TH>Stratégie</TH><TH>Win%</TH><TH>Sharpe</TH><TH>DD%</TH><TH>Trades</TH><TH>Statut</TH>
            </tr></thead>
            <tbody>
              {promotionRows.length === 0 ? (
                <tr><td colSpan={6} style={{ padding: '12px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10, textAlign: 'center' }}>Aucune donnée</td></tr>
              ) : promotionRows.map(r => (
                <tr key={r.name}>
                  <TD style={{ fontSize: 9 }}>{r.name.replace('POLY_', '')}</TD>
                  <TD style={{ color: (r.win_rate ?? 0) >= 52.6 ? 'var(--green)' : 'var(--text-secondary)' }}>
                    {r.win_rate != null ? `${r.win_rate.toFixed(0)}%` : '—'}
                  </TD>
                  <TD style={{ color: (r.sharpe ?? 0) >= 2.5 ? 'var(--green)' : 'var(--text-secondary)' }}>
                    {r.sharpe != null ? r.sharpe.toFixed(2) : '—'}
                  </TD>
                  <TD style={{ color: (r.drawdown ?? 0) > 4 ? 'var(--red)' : 'var(--text-secondary)' }}>
                    {r.drawdown != null ? `${r.drawdown.toFixed(1)}%` : '—'}
                  </TD>
                  <TD style={{ color: (r.trades_total ?? 0) >= 50 ? 'var(--green)' : 'var(--text-secondary)' }}>
                    {r.trades_total ?? 0}
                    <span style={{ fontSize: 8, color: 'var(--text-muted)' }}> /50</span>
                  </TD>
                  <TD><Badge color={promoColor[r.promoStatus] ?? 'grey'}>{r.promoStatus}</Badge></TD>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* ── 6.8 SYSTEM HEALTH / INFRA ── */}
      <SectionTitle>Infrastructure</SectionTitle>
      <div className="g3 mb24">
        {/* Agent Health */}
        <Card title="Agent Health">
          {agents.length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '14px 0', textAlign: 'center' }}>
              Aucun heartbeat enregistré
            </div>
          ) : (
            <table className="page-table">
              <thead><tr>
                <TH>Agent</TH><TH>Statut</TH><TH>Restarts</TH><TH>Vu</TH>
              </tr></thead>
              <tbody>{agents.map(a => (
                <tr key={a.name}>
                  <TD style={{ fontSize: 9 }}>{a.name}</TD>
                  <TD><Badge color={agentStatusColor(a.status)}>{(a.status ?? 'unknown').toUpperCase()}</Badge></TD>
                  <TD style={{ color: (a.restart_count ?? 0) > 0 ? 'var(--amber)' : 'var(--text-secondary)' }}>
                    {a.restart_count ?? 0}
                  </TD>
                  <TD style={{ color: 'var(--text-muted)', fontSize: 9 }}>{timeAgo(a.last_seen)}</TD>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Card>

        {/* Event Bus */}
        <Card title="Event Bus">
          <RowInfo
            label="Events bus (pending)"
            value={health?.bus_pending_real ?? 0}
            color={(health?.bus_pending_real ?? 0) > 50 ? 'amber' : 'green'}
          />
          <RowInfo
            label="Dead letters"
            value={health?.dead_letter_count ?? 0}
            color={(health?.dead_letter_count ?? 0) > 0 ? 'red' : 'green'}
          />
          <RowInfo
            label="Dernier cycle nightly"
            value={health?.orchestrator_last_cycle ? timeAgo(health.orchestrator_last_cycle) : '—'}
          />
        </Card>

        {/* Signal Freshness */}
        <Card title="Signal Freshness">
          {[
            { label: 'Binance (BTC/ETH)', key: 'binance_last_update_s' },
            { label: 'NOAA Forecasts',    key: 'noaa_last_update_s'    },
            { label: 'Wallets',           key: 'wallets_last_update_s' },
            { label: 'Market Prices',     key: 'market_last_update_s'  },
          ].map(({ label, key }) => {
            const { label: fl, color: fc } = signalFreshness(signals[key]);
            const age = signals[key] != null ? ageLabel(signals[key]) : null;
            return (
              <div key={key} className="fbet" style={{ padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>{label}</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {age && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)' }}>{age}</span>}
                  <Badge color={fc}>{fl}</Badge>
                </span>
              </div>
            );
          })}
        </Card>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
