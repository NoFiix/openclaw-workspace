import React, { useCallback } from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid
} from 'recharts';
import { api } from '../api/client';
import { useApiData, fmtUSD, fmtPct, timeAgo } from '../hooks';
import {
  LoadingState, ErrorState, SectionTitle, MetricCard,
  Badge, Card, KillSwitchBanner, LastUpdated, PulseDot
} from '../components/UI';

const fetchAll = async () => {
  const [health, trading, costs, content] = await Promise.all([
    api.health(),
    api.trading(),
    api.costs(),
    api.content(),
  ]);
  return { health, trading, costs, content };
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      padding: '8px 12px',
      fontFamily: 'var(--font-mono)',
      fontSize: 11,
    }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {fmtUSD(p.value)}
        </div>
      ))}
    </div>
  );
}

export default function Overview() {
  const fetch = useCallback(fetchAll, []);
  const { data, error, loading, refresh, lastUpdated } = useApiData(fetch, 30000);

  if (loading) return <LoadingState text="Loading system status..." />;
  if (error)   return <ErrorState message={error} onRetry={refresh} />;

  const { health, trading, costs, content } = data;

  // Trading metrics
  const ks         = trading?.kill_switch ?? {};
  const positions  = trading?.positions ?? [];
  const perf       = trading?.performance?.global ?? {};
  const daily      = trading?.daily_pnl ?? {};
  const dailyChart = trading?.daily_pnl_history ?? [];

  // Costs metrics
  const totalMonthCost = costs?.summary?.month_total_usd ?? null;
  const todayCost      = costs?.summary?.today_total_usd ?? null;

  // Content metrics
  const draftsTotal  = content?.drafts?.total ?? null;
  const postsToday   = content?.published?.today ?? null;

  // Health
  const uptime    = health?.uptime_pct ?? null;
  const agentsUp  = health?.agents_active ?? null;
  const agentsAll = health?.agents_total ?? null;

  const alerts = [
    ...(ks.tripped ? [{ type: 'error', msg: 'KILL SWITCH TRIPPED — trading halted' }] : []),
    ...(health?.alerts ?? []),
  ];

  return (
    <div>
      {/* Kill switch banner */}
      <KillSwitchBanner state={ks} />

      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="mb-16">
          {alerts.map((a, i) => (
            <div key={i} className={`alert ${a.type}`}>{a.msg}</div>
          ))}
        </div>
      )}

      {/* KPI row */}
      <SectionTitle>System Overview</SectionTitle>
      <div className="grid-4 mb-24">
        <MetricCard
          label="Daily PnL"
          value={daily?.pnl_usd != null ? fmtUSD(daily.pnl_usd) : '—'}
          color={daily?.pnl_usd >= 0 ? 'green' : 'red'}
          sub={`${fmtPct(daily?.pnl_pct)} today`}
        />
        <MetricCard
          label="Open Positions"
          value={positions.length}
          color="amber"
          sub={`Max 3 — ${3 - positions.length} slot${3 - positions.length !== 1 ? 's' : ''} free`}
        />
        <MetricCard
          label="LLM Cost Today"
          value={todayCost != null ? fmtUSD(todayCost) : '—'}
          color="blue"
          sub={totalMonthCost != null ? `~${fmtUSD(totalMonthCost)} this month` : ''}
        />
        <MetricCard
          label="Total Trades"
          value={perf?.total_trades ?? '—'}
          sub={`Win rate: ${perf?.win_rate != null ? (perf.win_rate * 100).toFixed(1) + '%' : '—'}`}
        />
      </div>

      {/* Secondary row */}
      <div className="grid-4 mb-24">
        <MetricCard
          label="Agents Active"
          value={agentsAll != null ? `${agentsUp ?? '?'}/${agentsAll}` : '—'}
          color="green"
          sub="Poller running"
        />
        <MetricCard
          label="Drafts Pipeline"
          value={draftsTotal ?? '—'}
          sub={`${postsToday ?? 0} published today`}
        />
        <MetricCard
          label="Global PnL"
          value={perf?.total_pnl_usd != null ? fmtUSD(perf.total_pnl_usd) : '—'}
          color={perf?.total_pnl_usd >= 0 ? 'green' : 'red'}
          sub={`${perf?.total_trades ?? 0} total trades`}
        />
        <MetricCard
          label="Uptime"
          value={uptime != null ? `${uptime.toFixed(1)}%` : '—'}
          color="green"
          sub="Docker container"
        />
      </div>

      {/* Charts + positions */}
      <div className="grid-2-3 mb-24">
        {/* Daily PnL chart */}
        <Card title="Daily PnL — 30 days">
          {dailyChart.length > 0 ? (
            <div className="chart-container" style={{ height: 200 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={dailyChart} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }}
                    axisLine={false} tickLine={false}
                    tickFormatter={(v) => v?.slice(5)}
                  />
                  <YAxis
                    tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }}
                    axisLine={false} tickLine={false}
                    tickFormatter={(v) => `$${v}`}
                  />
                  <Tooltip content={<CustomTooltip />} />
                  <Line
                    type="monotone" dataKey="pnl_usd" name="PnL"
                    stroke="var(--amber)" strokeWidth={2} dot={false}
                    activeDot={{ r: 3, fill: 'var(--amber)' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="loading-state" style={{ height: 200 }}>
              <span style={{ fontSize: 11 }}>No history data yet</span>
            </div>
          )}
        </Card>

        {/* Open Positions */}
        <Card title="Open Positions">
          {positions.length === 0 ? (
            <div style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 12, padding: '20px 0' }}>
              No open positions
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Entry</th>
                  <th>Current</th>
                  <th>PnL</th>
                  <th>Strategy</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((p, i) => (
                  <tr key={i}>
                    <td><span className="text-amber mono">{p.symbol}</span></td>
                    <td>
                      <Badge color={p.side === 'BUY' ? 'green' : 'red'}>{p.side}</Badge>
                    </td>
                    <td className="mono">${p.entry_price?.toFixed(2) ?? '—'}</td>
                    <td className="mono">${p.current_price?.toFixed(2) ?? '—'}</td>
                    <td className={`mono ${p.unrealized_pnl >= 0 ? 'text-green' : 'text-red'}`}>
                      {fmtUSD(p.unrealized_pnl)}
                    </td>
                    <td className="text-muted mono" style={{ fontSize: 10 }}>{p.strategy ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {/* Bottom row: Agent health + recent trades */}
      <div className="grid-2 mb-16">
        <Card title="Agent Health">
          <table className="data-table">
            <thead>
              <tr><th>Agent</th><th>Status</th><th>Last Run</th><th>Schedule</th></tr>
            </thead>
            <tbody>
              {(health?.agents ?? []).slice(0, 8).map((a) => (
                <tr key={a.name}>
                  <td className="mono" style={{ fontSize: 10 }}>{a.name}</td>
                  <td>
                    <Badge color={a.status === 'ok' ? 'green' : a.status === 'warn' ? 'amber' : 'red'}>
                      {a.status}
                    </Badge>
                  </td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(a.last_run)}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{a.every_seconds}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Recent Trades">
          <table className="data-table">
            <thead>
              <tr><th>Symbol</th><th>Side</th><th>PnL</th><th>Strategy</th><th>Time</th></tr>
            </thead>
            <tbody>
              {(trading?.recent_trades ?? []).slice(0, 8).map((t, i) => (
                <tr key={i}>
                  <td className="mono text-amber">{t.symbol}</td>
                  <td><Badge color={t.side === 'BUY' ? 'green' : 'red'}>{t.side}</Badge></td>
                  <td className={`mono ${t.pnl_usd >= 0 ? 'text-green' : 'text-red'}`}>
                    {fmtUSD(t.pnl_usd)}
                  </td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{t.strategy}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(t.closed_at)}</td>
                </tr>
              ))}
              {!(trading?.recent_trades?.length) && (
                <tr><td colSpan={5} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No trades yet</td></tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
