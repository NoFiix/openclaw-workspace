import { useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { api } from '../api/client';
import { useApiData, fmtUSD, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, Card, Badge, LastUpdated } from '../components/UI';

const TT = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', padding: '8px 12px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: (p.value ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
          PnL: {fmtUSD(p.value)}
        </div>
      ))}
    </div>
  );
};

const TH = ({ children }) => (
  <th style={{ textAlign: 'left', padding: '5px 8px', fontSize: 8, fontWeight: 600, letterSpacing: '.12em', textTransform: 'uppercase', color: 'var(--text-secondary)', borderBottom: '1px solid var(--border)', whiteSpace: 'nowrap' }}>
    {children}
  </th>
);
const TD = ({ children, style }) => (
  <td style={{ padding: '7px 8px', fontFamily: 'var(--font-mono)', fontSize: 11, verticalAlign: 'middle', ...style }}>
    {children}
  </td>
);

export default function Overview() {
  const fetchHealth  = useCallback(() => api.health(),         []);
  const fetchTrading = useCallback(() => api.trading(),        []);
  const fetchPerf    = useCallback(() => api.tradingPerf(),    []);
  const fetchCosts   = useCallback(() => api.costs(),          []);
  const fetchContent = useCallback(() => api.content(),        []);
  const fetchHistory = useCallback(() => api.tradingHistory(), []);
  const fetchTrades  = useCallback(() => api.tradingTrades(),  []);

  const { data: health,  loading: lH, lastUpdated } = useApiData(fetchHealth,   30000);
  const { data: live,    loading: lT }              = useApiData(fetchTrading,  30000);
  const { data: perf,                }              = useApiData(fetchPerf,     60000);
  const { data: costs,               }              = useApiData(fetchCosts,    60000);
  const { data: content,             }              = useApiData(fetchContent,  60000);
  const { data: history,             }              = useApiData(fetchHistory, 120000);
  const { data: tradeData,           }              = useApiData(fetchTrades,   60000);

  if (lH && lT && !health && !live) return <LoadingState text="Chargement..." />;

  const g          = perf?.global ?? {};
  const agents     = live?.agents ?? {};
  const agentList  = Object.entries(agents).map(([name, v]) => ({ name, ...v }));
  const ksArmed    = live?.kill_switch_armed ?? false;
  const positions  = live?.positions ?? [];
  const pnlHistory = history?.history ?? [];
  const recentTrades = [...(tradeData?.trades ?? [])].reverse().slice(0, 5);

  const winRate      = g.win_rate ?? null;         // already percentage (0–100)
  const profitFactor = g.profit_factor ?? null;
  const totalPnl     = g.pnl_usd ?? null;
  const maxDrawdown  = g.max_drawdown_pct ?? null;
  const openSlots    = 3 - (live?.open_positions ?? 0);
  const projectedMonth = costs?.today != null ? (costs.today * 30).toFixed(4) : null;

  return (
    <div>
      {/* Kill Switch Banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px',
        borderRadius: 'var(--radius)', border: '1px solid', marginBottom: 16,
        background: ksArmed ? 'var(--red-glow)' : 'var(--green-glow)',
        borderColor: ksArmed ? 'var(--red)' : 'var(--green)',
      }}>
        <span style={{
          width: 6, height: 6, borderRadius: '50%', display: 'inline-block', flexShrink: 0,
          background: ksArmed ? 'var(--red)' : 'var(--green)',
          boxShadow: ksArmed ? '0 0 6px var(--red)' : '0 0 6px var(--green)',
        }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, letterSpacing: '.08em', textTransform: 'uppercase', color: ksArmed ? 'var(--red)' : 'var(--green)' }}>
          KILL SWITCH: {ksArmed ? 'TRIPPED — TRADING HALTÉ' : 'ACTIF — TRADING ACTIVÉ'}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
          Régime: <span style={{ color: 'var(--amber)' }}>{live?.regime ?? '—'}</span>
          {' · '}PnL jour:{' '}
          <span style={{ color: (live?.pnl_today ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {fmtUSD(live?.pnl_today ?? 0)}
          </span>
        </span>
      </div>

      {/* Rangée 1 — 4 métriques */}
      <SectionTitle>Vue Globale</SectionTitle>
      <div className="g4 mb12">
        <MetricCard
          label="Coût LLM Aujourd'hui"
          value={costs?.today != null ? `$${costs.today.toFixed(4)}` : '—'}
          color="blue"
          sub={projectedMonth ? `~$${projectedMonth} projeté ce mois` : 'calcul en cours…'}
          tooltip="Coût total en tokens consommés par tous les agents LLM aujourd'hui. La projection mensuelle est calculée sur la moyenne des 7 derniers jours."
        />
        <MetricCard
          label="Positions Ouvertes"
          value={live?.open_positions ?? '—'}
          color="amber"
          sub={`${openSlots >= 0 ? openSlots : 0} slot${openSlots !== 1 ? 's' : ''} libre${openSlots !== 1 ? 's' : ''} (max 3)`}
        />
        <MetricCard
          label="Total Trades"
          value={g.trades_count ?? '—'}
          color={(winRate ?? 0) >= 55 ? 'green' : 'amber'}
          sub={winRate != null ? `Win rate : ${winRate.toFixed(1)}%` : 'Win rate : —'}
          tooltip="Pourcentage de trades gagnants sur le total. À analyser avec le Profit Factor — un win rate de 40% peut être rentable si les gains sont bien supérieurs aux pertes."
        />
        <MetricCard
          label="Articles Publiés"
          value={content?.drafts?.approved ?? '—'}
          color="green"
          sub={`${content?.drafts?.pending ?? 0} en attente`}
          sub2={`${content?.drafts?.rejected ?? 0} refusés`}
        />
      </div>

      {/* Rangée 2 — 4 métriques */}
      <div className="g4 mb24">
        <MetricCard
          label="Agents Actifs"
          value={agentList.length || '—'}
          sub={`${health?.open_incidents ?? 0} incident(s)`}
          color={health?.score >= 80 ? 'green' : health?.score >= 50 ? 'amber' : 'red'}
        />
        <MetricCard
          label="Profit Factor"
          value={profitFactor != null ? profitFactor.toFixed(2) : '—'}
          color={profitFactor != null && profitFactor >= 1 ? 'green' : profitFactor != null ? 'red' : ''}
          sub="gains bruts / pertes brutes"
          tooltip="Ratio gains bruts / pertes brutes. PF > 1 = rentable. PF = 1.5 signifie que pour chaque dollar perdu, on en gagne 1.50."
        />
        <MetricCard
          label="PnL Global"
          value={totalPnl != null ? fmtUSD(totalPnl) : '—'}
          color={(totalPnl ?? 0) >= 0 ? 'green' : 'red'}
          sub={g.capital_usd ? `Capital: $${g.capital_usd.toFixed(0)}` : 'paper trading'}
          tooltip="Somme de tous les profits et pertes réalisés. N'inclut pas les positions encore ouvertes (PnL non réalisé)."
        />
        <MetricCard
          label="Max Drawdown"
          value={maxDrawdown != null ? `${maxDrawdown.toFixed(2)}%` : '—'}
          color={maxDrawdown != null && maxDrawdown > 2 ? 'red' : maxDrawdown != null && maxDrawdown > 1 ? 'amber' : 'green'}
          sub="kill switch à -3% journalier"
          tooltip="Perte maximale depuis un pic de capital. Le kill switch coupe automatiquement le trading à -3% de drawdown journalier."
        />
      </div>

      {/* Grid 2/3 : Daily PnL chart + Positions ouvertes */}
      <div className="g23 mb24">
        <Card title="Daily PnL — 7 jours">
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={pnlHistory.slice(-7)} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}`} />
                <ReferenceLine y={0} stroke="var(--border-bright)" />
                <Tooltip content={<TT />} />
                <Bar dataKey="pnl" name="PnL" radius={1}>
                  {pnlHistory.slice(-7).map((e, i) => (
                    <Cell key={i} fill={(e.pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Positions Ouvertes">
          {!positions.length ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '16px 0', textAlign: 'center' }}>
              Aucune position ouverte
            </div>
          ) : (
            <table className="page-table">
              <thead><tr>
                {['Symbol', 'Side', 'Entry', 'Actuel', 'PnL', 'Stratégie'].map(h => <TH key={h}>{h}</TH>)}
              </tr></thead>
              <tbody>{positions.map((p, i) => (
                <tr key={i}>
                  <TD style={{ color: 'var(--amber)' }}>{p.symbol ?? p.asset}</TD>
                  <TD><Badge color={p.side === 'BUY' ? 'green' : 'red'}>{p.side ?? '—'}</Badge></TD>
                  <TD>${p.entry_fill?.toFixed(0) ?? p.entry_price?.toFixed(0) ?? '—'}</TD>
                  <TD>${p.current_price?.toFixed(0) ?? '—'}</TD>
                  <TD style={{ color: (p.unrealized_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {fmtUSD(p.unrealized_pnl ?? 0)}
                  </TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{p.strategy ?? '—'}</TD>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Card>
      </div>

      {/* Grid 1/2 : Agent Health + Trades Récents */}
      <div className="g2 mb16">
        <Card title="Agent Health">
          <table className="page-table">
            <thead><tr>
              {['Agent', 'Statut', 'Dernier run', 'Runs', 'Erreurs'].map(h => <TH key={h}>{h}</TH>)}
            </tr></thead>
            <tbody>{agentList.slice(0, 8).map(a => {
              const lastRun = (a.last_run_ts ?? 0) * 1000;
              const stale   = Date.now() - lastRun > 600000;
              return (
                <tr key={a.name}>
                  <TD style={{ fontSize: 10 }}>{a.name}</TD>
                  <TD><Badge color={stale ? 'amber' : 'green'}>{stale ? 'stale' : 'ok'}</Badge></TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{timeAgo(lastRun)}</TD>
                  <TD>{a.runs ?? 0}</TD>
                  <TD style={{ color: (a.errors ?? 0) > 0 ? 'var(--red)' : 'var(--text-secondary)' }}>{a.errors ?? 0}</TD>
                </tr>
              );
            })}</tbody>
          </table>
        </Card>

        <Card title="Trades Récents">
          {!recentTrades.length ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '16px 0', textAlign: 'center' }}>
              Aucun trade récent
            </div>
          ) : (
            <table className="page-table">
              <thead><tr>
                {['Symbol', 'Side', 'PnL', 'Stratégie', 'Fermé'].map(h => <TH key={h}>{h}</TH>)}
              </tr></thead>
              <tbody>{recentTrades.map((t, i) => (
                <tr key={i}>
                  <TD style={{ color: 'var(--amber)' }}>{t.symbol}</TD>
                  <TD><Badge color={t.side === 'BUY' ? 'green' : 'red'}>{t.side ?? '—'}</Badge></TD>
                  <TD style={{ color: (t.pnl_usd ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                    {fmtUSD(t.pnl_usd)}
                  </TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{t.strategy ?? '—'}</TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{timeAgo(t.closed_at)}</TD>
                </tr>
              ))}</tbody>
            </table>
          )}
        </Card>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
