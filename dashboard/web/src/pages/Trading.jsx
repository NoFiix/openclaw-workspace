import React, { useCallback } from 'react';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  CartesianGrid, LineChart, Line, ReferenceLine
} from 'recharts';
import { api } from '../api/client';
import { useApiData, fmtUSD, fmtPct, timeAgo } from '../hooks';
import {
  LoadingState, ErrorState, SectionTitle, Card, MetricCard,
  Badge, KillSwitchBanner, LastUpdated, ProgressBar
} from '../components/UI';

const fetchFn = () => api.trading();

function TooltipPnL({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.value >= 0 ? 'var(--green)' : 'var(--red)' }}>
          PnL: {fmtUSD(p.value)}
        </div>
      ))}
    </div>
  );
}

function RegimeBadge({ regime }) {
  const map = {
    TREND_UP:   'green',  TREND_DOWN: 'red',
    RANGE:      'blue',   PANIC:      'red',
    EUPHORIA:   'amber',  VOLATILE:   'amber',
    UNKNOWN:    'grey',
  };
  return <Badge color={map[regime] ?? 'grey'}>{regime ?? 'UNKNOWN'}</Badge>;
}

function WhaleBiasBadge({ bias }) {
  const map = { ACCUMULATION: 'green', DISTRIBUTION: 'red', NEUTRAL: 'grey', MIXED: 'amber' };
  return <Badge color={map[bias] ?? 'grey'}>{bias ?? 'NEUTRAL'}</Badge>;
}

export default function Trading() {
  const fetch = useCallback(fetchFn, []);
  const { data, error, loading, refresh, lastUpdated } = useApiData(fetch, 15000);

  if (loading) return <LoadingState text="Loading trading data..." />;
  if (error)   return <ErrorState message={error} onRetry={refresh} />;

  const ks         = data?.kill_switch ?? {};
  const positions  = data?.positions ?? [];
  const perf       = data?.performance?.global ?? {};
  const byStrategy = data?.performance?.by_strategy ?? [];
  const byAsset    = data?.performance?.by_asset ?? [];
  const regime     = data?.regime ?? {};
  const whale      = data?.whale_signal ?? {};
  const daily      = data?.daily_pnl ?? {};
  const recentTrades = data?.recent_trades ?? [];
  const pnlHistory   = data?.daily_pnl_history ?? [];
  const stratActive  = data?.strategies ?? [];

  const winRatePct = perf.win_rate != null ? (perf.win_rate * 100).toFixed(1) : null;
  const drawdown   = perf.max_drawdown_pct ?? null;

  return (
    <div>
      <KillSwitchBanner state={ks} />

      {/* Global KPIs */}
      <SectionTitle>Performance Overview</SectionTitle>
      <div className="grid-4 mb-24">
        <MetricCard
          label="Total PnL"
          value={fmtUSD(perf.total_pnl_usd)}
          color={perf.total_pnl_usd >= 0 ? 'green' : 'red'}
          sub={`${perf.total_trades ?? 0} trades total`}
        />
        <MetricCard
          label="Win Rate"
          value={winRatePct ? `${winRatePct}%` : '—'}
          sub={`${perf.win_count ?? 0}W / ${perf.loss_count ?? 0}L`}
        />
        <MetricCard
          label="Profit Factor"
          value={perf.profit_factor?.toFixed(2) ?? '—'}
          color={perf.profit_factor >= 1.5 ? 'green' : perf.profit_factor >= 1 ? 'amber' : 'red'}
          sub="Gross win / Gross loss"
        />
        <MetricCard
          label="Max Drawdown"
          value={drawdown != null ? `${Math.abs(drawdown).toFixed(2)}%` : '—'}
          color={Math.abs(drawdown) > 3 ? 'red' : 'amber'}
          sub="from peak equity"
        />
      </div>

      <div className="grid-4 mb-24">
        <MetricCard label="Daily PnL" value={fmtUSD(daily.pnl_usd)} color={daily.pnl_usd >= 0 ? 'green' : 'red'} sub={fmtPct(daily.pnl_pct)} />
        <MetricCard label="Open Positions" value={positions.length} color="amber" sub="max 3 simultaneous" />
        <MetricCard label="Avg Win" value={fmtUSD(perf.avg_win_usd)} color="green" sub={`Avg Loss: ${fmtUSD(perf.avg_loss_usd)}`} />
        <MetricCard label="Sharpe Ratio" value={perf.sharpe?.toFixed(2) ?? '—'} sub="annualized" />
      </div>

      {/* Market Context */}
      <SectionTitle>Market Context</SectionTitle>
      <div className="grid-3 mb-24">
        <Card title="Market Regime">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Regime</span>
              <RegimeBadge regime={regime.regime} />
            </div>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Confidence</span>
              <span className="mono text-amber" style={{ fontSize: 12 }}>
                {regime.confidence != null ? `${(regime.confidence * 100).toFixed(0)}%` : '—'}
              </span>
            </div>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Updated</span>
              <span className="mono text-muted" style={{ fontSize: 10 }}>{timeAgo(regime.timestamp)}</span>
            </div>
            {regime.confidence != null && (
              <ProgressBar value={regime.confidence * 100} color="amber" />
            )}
          </div>
        </Card>

        <Card title="Whale Signal">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Bias</span>
              <WhaleBiasBadge bias={whale.bias} />
            </div>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Flow Score</span>
              <span className={`mono ${whale.score > 0.3 ? 'text-green' : whale.score < -0.3 ? 'text-red' : 'text-muted'}`} style={{ fontSize: 12 }}>
                {whale.score != null ? whale.score.toFixed(3) : '—'}
              </span>
            </div>
            <div className="flex-between">
              <span className="text-muted mono" style={{ fontSize: 11 }}>Strength</span>
              <span className="mono" style={{ fontSize: 11 }}>{whale.strength ?? '—'}</span>
            </div>
            {whale.score != null && (
              <ProgressBar value={(whale.score + 1) * 50} color={whale.score > 0.3 ? 'green' : whale.score < -0.3 ? 'red' : 'amber'} />
            )}
          </div>
        </Card>

        <Card title="Active Strategies">
          <table className="data-table">
            <thead>
              <tr><th>Strategy</th><th>Status</th><th>Score</th></tr>
            </thead>
            <tbody>
              {stratActive.map((s) => (
                <tr key={s.name}>
                  <td className="mono" style={{ fontSize: 11 }}>{s.name}</td>
                  <td>
                    <Badge color={s.status === 'active' ? 'green' : s.status === 'testing' ? 'amber' : 'red'}>
                      {s.status}
                    </Badge>
                  </td>
                  <td className={`mono ${s.score >= 0.6 ? 'text-green' : s.score >= 0.4 ? 'text-amber' : 'text-red'}`}>
                    {s.score?.toFixed(3) ?? '—'}
                  </td>
                </tr>
              ))}
              {!stratActive.length && (
                <tr><td colSpan={3} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No strategy data</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Open Positions */}
      <SectionTitle>Open Positions</SectionTitle>
      <Card className="mb-24">
        {positions.length === 0 ? (
          <div style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 12, padding: '16px 0' }}>
            No open positions
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th>
                <th>Current</th><th>TP</th><th>SL</th><th>PnL</th>
                <th>PnL %</th><th>Strategy</th><th>Regime</th><th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => (
                <tr key={i}>
                  <td className="mono text-amber">{p.symbol}</td>
                  <td><Badge color={p.side === 'BUY' ? 'green' : 'red'}>{p.side}</Badge></td>
                  <td className="mono">{p.quantity?.toFixed(4) ?? '—'}</td>
                  <td className="mono">${p.entry_price?.toFixed(2) ?? '—'}</td>
                  <td className="mono">${p.current_price?.toFixed(2) ?? '—'}</td>
                  <td className="mono text-green">${p.take_profit?.toFixed(2) ?? '—'}</td>
                  <td className="mono text-red">${p.stop_loss?.toFixed(2) ?? '—'}</td>
                  <td className={`mono ${p.unrealized_pnl >= 0 ? 'text-green' : 'text-red'}`}>{fmtUSD(p.unrealized_pnl)}</td>
                  <td className={`mono ${p.unrealized_pnl_pct >= 0 ? 'text-green' : 'text-red'}`}>{fmtPct(p.unrealized_pnl_pct)}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{p.strategy}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{p.regime}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(p.opened_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* Charts row */}
      <div className="grid-2 mb-24">
        {/* PnL history */}
        <Card title="Daily PnL History">
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pnlHistory} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} tickFormatter={v => v?.slice(5)} />
                <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
                <ReferenceLine y={0} stroke="var(--border-bright)" />
                <Tooltip content={<TooltipPnL />} />
                <Bar dataKey="pnl_usd" name="PnL" radius={1}
                  fill="var(--green)"
                  label={false}
                >
                  {pnlHistory.map((entry, index) => (
                    <rect key={index} fill={entry.pnl_usd >= 0 ? 'var(--green)' : 'var(--red)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Strategy performance */}
        <Card title="Strategy Performance">
          <table className="data-table">
            <thead>
              <tr><th>Strategy</th><th>Trades</th><th>Win%</th><th>PF</th><th>PnL</th><th>Score</th></tr>
            </thead>
            <tbody>
              {byStrategy.map((s) => (
                <tr key={s.name}>
                  <td className="mono" style={{ fontSize: 11 }}>{s.name}</td>
                  <td className="mono">{s.total_trades ?? '—'}</td>
                  <td className={`mono ${s.win_rate >= 0.5 ? 'text-green' : 'text-red'}`}>
                    {s.win_rate != null ? `${(s.win_rate * 100).toFixed(0)}%` : '—'}
                  </td>
                  <td className={`mono ${s.profit_factor >= 1 ? 'text-green' : 'text-red'}`}>
                    {s.profit_factor?.toFixed(2) ?? '—'}
                  </td>
                  <td className={`mono ${s.pnl_usd >= 0 ? 'text-green' : 'text-red'}`}>{fmtUSD(s.pnl_usd)}</td>
                  <td>
                    <div className="mono" style={{ fontSize: 11, color: s.score >= 0.6 ? 'var(--green)' : s.score >= 0.4 ? 'var(--amber)' : 'var(--red)' }}>
                      {s.score?.toFixed(3) ?? '—'}
                    </div>
                  </td>
                </tr>
              ))}
              {!byStrategy.length && (
                <tr><td colSpan={6} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No strategy data yet</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Recent trades */}
      <SectionTitle>Trade Ledger (Last 50)</SectionTitle>
      <Card>
        <table className="data-table">
          <thead>
            <tr>
              <th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th>
              <th>PnL</th><th>PnL%</th><th>Strategy</th>
              <th>Regime</th><th>Duration</th><th>Closed</th>
            </tr>
          </thead>
          <tbody>
            {recentTrades.slice(0, 50).map((t, i) => (
              <tr key={i}>
                <td className="mono text-amber">{t.symbol}</td>
                <td><Badge color={t.side === 'BUY' ? 'green' : 'red'}>{t.side}</Badge></td>
                <td className="mono">${t.entry_price?.toFixed(2) ?? '—'}</td>
                <td className="mono">${t.exit_price?.toFixed(2) ?? '—'}</td>
                <td className={`mono ${t.pnl_usd >= 0 ? 'text-green' : 'text-red'}`}>{fmtUSD(t.pnl_usd)}</td>
                <td className={`mono ${t.pnl_pct >= 0 ? 'text-green' : 'text-red'}`}>{fmtPct(t.pnl_pct)}</td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{t.strategy}</td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{t.regime}</td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{t.duration_min ? `${t.duration_min}m` : '—'}</td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(t.closed_at)}</td>
              </tr>
            ))}
            {!recentTrades.length && (
              <tr><td colSpan={10} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No trades yet</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <div className="mt-12" style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
