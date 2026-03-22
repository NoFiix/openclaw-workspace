import { useState, useCallback } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { api } from '../api/client';
import { useApiData, fmtUSD, fmtPct, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, Card, Badge, LastUpdated, InfoTooltip } from '../components/UI';

// ── Helpers locaux ────────────────────────────────────────────────────────────
const ProgBar = ({ val, max = 100, color = 'amber' }) => (
  <div style={{ height: 4, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden', marginTop: 8 }}>
    <div style={{ height: '100%', borderRadius: 2, width: `${Math.min(100, Math.max(0, (val / max) * 100))}%`, background: `var(--${color})`, transition: 'width .3s ease' }} />
  </div>
);

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

const RowInfo = ({ label, value, color }) => (
  <div className="fbet" style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>{label}</span>
    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color: color ? `var(--${color})` : 'var(--text-primary)' }}>{value}</span>
  </div>
);

// ── Composant principal ───────────────────────────────────────────────────────
export default function Trading() {
  const [mode,           setMode]           = useState('testnet');
  const [filterStrategy, setFilterStrategy] = useState('all');
  const [filterAsset,    setFilterAsset]    = useState('all');
  const [filterResult,   setFilterResult]   = useState('all');

  const fetchLive    = useCallback(() => api.trading(),            []);
  const fetchPerf    = useCallback(() => api.tradingPerf(),        []);
  const fetchTrades  = useCallback(() => api.tradingTrades(),      []);
  const fetchHistory = useCallback(() => api.tradingHistory(),     []);
  const fetchStrats  = useCallback(() => api.tradingStrategies(),  []);

  const { data: live,    loading: lLive,   error: eLive,   refresh: rLive, lastUpdated } = useApiData(fetchLive,    20000);
  const { data: perf,    loading: lPerf                                                 } = useApiData(fetchPerf,    60000);
  const { data: tData,   loading: lTrades                                               } = useApiData(fetchTrades,  60000);
  const { data: history                                                                  } = useApiData(fetchHistory, 120000);
  const { data: strats                                                                   } = useApiData(fetchStrats,  60000);

  if (lLive && !live) return <LoadingState text="Chargement trading..." />;
  if (eLive && !live) return <ErrorState message={eLive} onRetry={rLive} />;

  // ── Data mapping ──────────────────────────────────────────────────────────
  const ksArmed     = live?.kill_switch_armed ?? false;
  const positions   = live?.positions ?? [];
  const agentData   = live?.agents ?? {};
  const agentList   = Object.entries(agentData).map(([name, v]) => ({ name, ...v }));

  const g           = perf?.global ?? {};
  const strategies  = perf?.strategy ?? [];
  const assetPerfs  = perf?.asset ?? [];

  // Champs normalisés (real data: win_rate est déjà un %)
  const totalPnl     = g.pnl_usd ?? 0;
  const winRate      = g.win_rate ?? 0;        // 0–100
  const wins         = g.wins    ?? 0;
  const losses       = g.losses  ?? 0;
  const profitFactor = g.profit_factor ?? 0;
  const sharpe       = g.sharpe_ratio  ?? 0;
  const avgWin       = g.avg_win_usd   ?? 0;
  const avgLoss      = g.avg_loss_usd  ?? 0;
  const avgHoldMin   = g.avg_hold_min  ?? 0;
  const tradesCount  = g.trades_count  ?? 0;

  const CAPITAL_INITIAL = 10000;
  const capitalActuel   = CAPITAL_INITIAL + totalPnl;
  const variationPct    = ((capitalActuel - CAPITAL_INITIAL) / CAPITAL_INITIAL) * 100;

  const allTrades   = tData?.trades ?? [];
  const dailyHistory = history?.history ?? [];

  const availableStrategies = [...new Set(allTrades.map(t => t.strategy).filter(Boolean))];
  const availableAssets     = [...new Set(allTrades.map(t => t.symbol).filter(Boolean))];

  const filteredTrades = allTrades.filter(t => {
    if (filterStrategy !== 'all' && t.strategy !== filterStrategy) return false;
    if (filterAsset    !== 'all' && t.symbol   !== filterAsset)    return false;
    if (filterResult === 'win'  && (t.pnl_usd ?? 0) <  0) return false;
    if (filterResult === 'loss' && (t.pnl_usd ?? 0) >= 0) return false;
    return true;
  });

  const regimeColor = { TREND_UP: 'green', TREND_DOWN: 'red', RANGE: 'blue', PANIC: 'red', EUPHORIA: 'amber', VOLATILE: 'amber', UNKNOWN: 'grey' };

  return (
    <div>
      {/* ── FILTRES PRINCIPAUX ── */}
      <div style={{ marginBottom: 20 }}>
        {/* Mode testnet/mainnet */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center' }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '.15em', textTransform: 'uppercase', marginRight: 4 }}>Mode</span>
          {[
            { id: 'testnet', label: 'TESTNET', available: true },
            { id: 'mainnet', label: 'MAINNET', available: false },
          ].map(m => (
            <button key={m.id}
              onClick={() => m.available && setMode(m.id)}
              style={{
                padding: '6px 16px', border: '1px solid',
                borderColor: mode === m.id ? 'var(--amber)' : 'var(--border)',
                background: mode === m.id ? 'var(--amber-glow)' : 'var(--bg-elevated)',
                color: !m.available ? 'var(--text-muted)' : mode === m.id ? 'var(--amber)' : 'var(--text-secondary)',
                fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
                borderRadius: 'var(--radius)', cursor: m.available ? 'pointer' : 'not-allowed',
                letterSpacing: '.06em', display: 'flex', alignItems: 'center', gap: 6,
              }}>
              {m.label}
              {!m.available && <span style={{ fontSize: 8, background: 'var(--bg-hover)', padding: '1px 5px', borderRadius: 2 }}>BIENTÔT</span>}
            </button>
          ))}
        </div>

        {/* Filtres secondaires */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'center' }}>
          {/* Stratégie */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '.12em', textTransform: 'uppercase' }}>Stratégie</span>
            {['all', ...availableStrategies].map(s => (
              <button key={s} onClick={() => setFilterStrategy(s)}
                style={{
                  padding: '3px 10px', border: '1px solid',
                  borderColor: filterStrategy === s ? 'var(--blue)' : 'var(--border)',
                  background: filterStrategy === s ? 'var(--blue-dim)' : 'var(--bg-elevated)',
                  color: filterStrategy === s ? 'var(--blue)' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, borderRadius: 'var(--radius)', cursor: 'pointer',
                }}>
                {s === 'all' ? 'Toutes' : s}
              </button>
            ))}
          </div>

          {/* Actif */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '.12em', textTransform: 'uppercase' }}>Actif</span>
            {['all', ...availableAssets].map(a => (
              <button key={a} onClick={() => setFilterAsset(a)}
                style={{
                  padding: '3px 10px', border: '1px solid',
                  borderColor: filterAsset === a ? 'var(--purple)' : 'var(--border)',
                  background: filterAsset === a ? 'rgba(139,92,246,0.1)' : 'var(--bg-elevated)',
                  color: filterAsset === a ? 'var(--purple)' : 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, borderRadius: 'var(--radius)', cursor: 'pointer',
                }}>
                {a === 'all' ? 'Tous' : a}
              </button>
            ))}
          </div>

          {/* Résultat */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-muted)', letterSpacing: '.12em', textTransform: 'uppercase' }}>Résultat</span>
            {[{ id: 'all', label: 'Tous' }, { id: 'win', label: 'Gagnants' }, { id: 'loss', label: 'Perdants' }].map(r => (
              <button key={r.id} onClick={() => setFilterResult(r.id)}
                style={{
                  padding: '3px 10px', border: '1px solid',
                  borderColor: filterResult === r.id ? (r.id === 'win' ? 'var(--green)' : r.id === 'loss' ? 'var(--red)' : 'var(--border-bright)') : 'var(--border)',
                  background: filterResult === r.id ? (r.id === 'win' ? 'var(--green-glow)' : r.id === 'loss' ? 'var(--red-glow)' : 'var(--bg-hover)') : 'var(--bg-elevated)',
                  color: filterResult === r.id ? (r.id === 'win' ? 'var(--green)' : r.id === 'loss' ? 'var(--red)' : 'var(--text-primary)') : 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)', fontSize: 10, borderRadius: 'var(--radius)', cursor: 'pointer',
                }}>
                {r.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── KILL SWITCH BANNER ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px',
        borderRadius: 'var(--radius)', border: '1px solid', marginBottom: 20,
        background: ksArmed ? 'var(--red-glow)' : 'var(--green-glow)',
        borderColor: ksArmed ? 'var(--red)' : 'var(--green)',
      }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', display: 'inline-block', flexShrink: 0, background: ksArmed ? 'var(--red)' : 'var(--green)', boxShadow: ksArmed ? '0 0 6px var(--red)' : '0 0 6px var(--green)' }} />
        <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 11, color: ksArmed ? 'var(--red)' : 'var(--green)', textTransform: 'uppercase', letterSpacing: '.08em' }}>
          KILL SWITCH: {ksArmed ? 'TRIPPED — TRADING HALTÉ' : 'ACTIF — TRADING ACTIVÉ'}
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
          Régime: <span style={{ color: `var(--${regimeColor[live?.regime] ?? 'amber'})` }}>{live?.regime ?? '—'}</span>
          {' · '}Positions: <span style={{ color: 'var(--amber)' }}>{live?.open_positions ?? 0}</span>
          {' · '}PnL jour: <span style={{ color: (live?.pnl_today ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtUSD(live?.pnl_today ?? 0)}</span>
        </span>
      </div>

      {/* ── STRATEGY WALLETS ── */}
      {strats?.strategies?.length > 0 && (<>
        <SectionTitle>Stratégies Multi-Wallet</SectionTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12, marginBottom: 24 }}>
          {strats.strategies.map(s => {
            const pnlColor = (s.realized_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)';
            const statusColor = s.enabled ? 'var(--green)' : s.lifecycle_status === 'paper_ready' ? 'var(--amber)' : 'var(--text-secondary)';
            const wr = s.trade_count > 0 && s.win_count != null ? ((s.win_count / s.trade_count) * 100).toFixed(1) : null;
            return (
              <Card key={s.strategy_id} title={s.strategy_label || s.strategy_id}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <Badge color={s.enabled ? 'green' : s.lifecycle_status === 'paper_ready' ? 'amber' : 'grey'}>
                    {s.lifecycle_status ?? 'unknown'}
                  </Badge>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-secondary)' }}>
                    {s.execution_target ?? 'paper'}
                  </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Capital</span><br/><span style={{ fontSize: 13, fontWeight: 700 }}>{fmtUSD(s.initial_capital)}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Disponible</span><br/><span style={{ fontSize: 13, fontWeight: 700, color: (s.effective_cash ?? s.cash) < s.initial_capital * 0.1 ? 'var(--red)' : 'var(--text-primary)' }}>{fmtUSD(s.effective_cash ?? s.cash)}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Engagé</span><br/><span style={{ color: (s.committed ?? 0) > 0 ? 'var(--amber)' : 'var(--text-secondary)' }}>{fmtUSD(s.committed ?? 0)}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Positions</span><br/><span style={{ color: (s.open_positions_count ?? 0) > 0 ? 'var(--amber)' : 'var(--text-secondary)' }}>{s.open_positions_count ?? 0}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>PnL</span><br/><span style={{ color: pnlColor }}>{fmtUSD(s.realized_pnl)}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>ROI</span><br/><span style={{ color: pnlColor }}>{fmtPct(s.roi_pct)}</span></div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Trades</span><br/>{s.trade_count ?? 0}</div>
                  <div><span style={{ color: 'var(--text-secondary)' }}>Win Rate</span><br/>{wr != null ? `${wr}%` : 'N/A'}</div>
                </div>
                {(s.open_positions ?? []).length > 0 && (
                  <div style={{ marginTop: 8, padding: '6px 8px', background: 'var(--bg-elevated)', borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
                    {s.open_positions.map(p => (
                      <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '2px 0' }}>
                        <span style={{ color: 'var(--amber)' }}>{p.symbol} {p.side}</span>
                        <span style={{ color: 'var(--text-secondary)' }}>{fmtUSD(p.value_usd)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {s.status === 'suspended' && <div style={{ marginTop: 8, padding: '4px 8px', background: 'var(--red-glow)', borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--red)' }}>SUSPENDU — circuit breaker</div>}
              </Card>
            );
          })}
        </div>
        {strats.pending_candidates > 0 && (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--amber)', marginBottom: 16 }}>
            {strats.pending_candidates} candidate(s) en attente de validation
          </div>
        )}
      </>)}

      {/* ── CAPITAL & SIZING ── */}
      <SectionTitle>Capital & Sizing</SectionTitle>
      <div className="g3 mb24">
        <Card title="Capital Compte" style={{ position: 'relative' }}>
          <InfoTooltip text="Capital actuel sur le compte testnet incluant tous les PnL réalisés. Calculé depuis le capital initial de $10,000 USDT." />
          <RowInfo label="Capital initial"   value="$10,000.00" />
          <RowInfo label="Capital actuel"    value={`$${capitalActuel.toFixed(2)}`}   color={variationPct >= 0 ? 'green' : 'red'} />
          <RowInfo label="Variation totale"  value={`${variationPct >= 0 ? '+' : ''}${variationPct.toFixed(2)}%`} color={variationPct >= 0 ? 'green' : 'red'} />
          <ProgBar val={Math.min(100, Math.max(0, variationPct * 5))} color={variationPct >= 0 ? 'green' : 'red'} />
        </Card>

        <Card title="Sizing par Trade" style={{ position: 'relative' }}>
          <InfoTooltip text="Le risque par trade est fixé à 1% du capital ($100). La taille notionnelle varie selon la distance au stop loss : SL à 1% = $10k notionnel, SL à 2% = $5k notionnel, SL à 0.5% = $20k notionnel." />
          <RowInfo label="Risque par trade" value="$100.00 (1%)" color="amber" />
          <RowInfo label="Notionnel moyen"  value={g.avg_notional ? `$${g.avg_notional.toFixed(0)}` : '—'} />
          <RowInfo label="Levier implicite" value={g.avg_notional ? `${(g.avg_notional / capitalActuel).toFixed(2)}×` : '—'} />
        </Card>

        <Card title="Ratio Risque / Récompense" style={{ position: 'relative' }}>
          <InfoTooltip text="Compare le gain moyen au risque moyen. Un R:R de 2+ signifie que chaque trade gagnant rapporte 2× la mise risquée. Multiplie par le win rate pour obtenir l'espérance mathématique par trade." />
          <RowInfo label="Gain moyen"  value={avgWin  ? `+${fmtUSD(avgWin)}`  : '—'} color="green" />
          <RowInfo label="Perte moyenne" value={avgLoss ? fmtUSD(-Math.abs(avgLoss)) : '—'} color="red" />
          <RowInfo label="Ratio R:R"   value={(avgWin && avgLoss) ? `${(avgWin / Math.abs(avgLoss)).toFixed(2)}` : '—'} color="amber" />
        </Card>
      </div>

      {/* ── MÉTRIQUES PERFORMANCE ── */}
      <SectionTitle>Performance</SectionTitle>
      <div className="g4 mb12">
        <MetricCard
          label="Total PnL"
          value={fmtUSD(totalPnl)}
          color={totalPnl >= 0 ? 'green' : 'red'}
          sub={`${tradesCount} trades`}
          tooltip="Somme de tous les profits et pertes réalisés. N'inclut pas les positions encore ouvertes (PnL non réalisé)."
        />
        <MetricCard
          label="Win Rate"
          value={`${winRate.toFixed(1)}%`}
          sub={`${wins}W / ${losses}L`}
          tooltip="Pourcentage de trades gagnants sur le total. À analyser avec le Profit Factor — un win rate de 40% peut être rentable si les gains dépassent largement les pertes."
        />
        <MetricCard
          label="Profit Factor"
          value={profitFactor.toFixed(2)}
          color={profitFactor >= 1 ? 'green' : 'red'}
          sub="gains bruts / pertes brutes"
          tooltip="Ratio gains bruts / pertes brutes. PF > 1 = rentable. En dessous de 1 = stratégie perdante."
        />
        <MetricCard
          label="Sharpe Ratio"
          value={sharpe.toFixed(3)}
          sub="annualisé"
          tooltip="Mesure le rendement ajusté au risque. Sharpe > 1 = bon, > 2 = excellent. Il compare le gain obtenu par rapport à la volatilité du portefeuille."
        />
      </div>
      <div className="g4 mb24">
        <MetricCard
          label="Gain Moyen"
          value={fmtUSD(avgWin)}
          color="green"
          sub="par trade gagnant"
        />
        <MetricCard
          label="Perte Moyenne"
          value={avgLoss ? fmtUSD(-Math.abs(avgLoss)) : '—'}
          color={avgLoss ? 'red' : ''}
          sub="par trade perdant"
        />
        <MetricCard
          label="Durée Moyenne"
          value={avgHoldMin ? `${Math.floor(avgHoldMin / 60)}h${Math.round(avgHoldMin % 60)}m` : '—'}
          sub="de détention"
          tooltip="Durée moyenne de détention d'une position, de l'ouverture à la fermeture. Indicateur du style de trading (scalp = minutes, swing = heures)."
        />
        <MetricCard
          label="Trades Aujourd'hui"
          value={live?.trades_today ?? 0}
          sub={`${tradesCount} total`}
        />
      </div>

      {/* ── CONTEXTE MARCHÉ ── */}
      <SectionTitle>Contexte Marché</SectionTitle>
      <div className="g3 mb24">
        <Card title="Régime Marché">
          <RowInfo
            label="Régime"
            value={<Badge color={regimeColor[live?.regime] ?? 'grey'}>{live?.regime ?? '—'}</Badge>}
          />
          <RowInfo label="Mis à jour" value={<span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: 'var(--text-secondary)' }}>{timeAgo(live?.ts)}</span>} />
        </Card>

        <Card title="Stratégies Performance">
          <table className="page-table">
            <thead><tr>
              <TH>Stratégie</TH><TH>Trades</TH><TH>Win%</TH><TH>PnL</TH>
            </tr></thead>
            <tbody>
              {strategies.length === 0 ? (
                <tr><td colSpan={4} style={{ padding: '12px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10, textAlign: 'center' }}>Aucune donnée</td></tr>
              ) : strategies.map(s => (
                <tr key={s.strategy_id}>
                  <TD style={{ fontSize: 10 }}>{s.strategy_id}</TD>
                  <TD>{s.trades_count}</TD>
                  <TD style={{ color: (s.win_rate ?? 0) >= 50 ? 'var(--green)' : 'var(--red)' }}>{(s.win_rate ?? 0).toFixed(1)}%</TD>
                  <TD style={{ color: (s.pnl_usd ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtUSD(s.pnl_usd)}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Performance par Asset">
          <table className="page-table">
            <thead><tr>
              <TH>Asset</TH><TH>Trades</TH><TH>Win%</TH><TH>PnL</TH>
            </tr></thead>
            <tbody>
              {assetPerfs.length === 0 ? (
                <tr><td colSpan={4} style={{ padding: '12px 8px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 10, textAlign: 'center' }}>Aucune donnée</td></tr>
              ) : assetPerfs.map(a => (
                <tr key={a.asset}>
                  <TD style={{ color: 'var(--amber)', fontWeight: 600 }}>{a.asset}</TD>
                  <TD>{a.trades_count}</TD>
                  <TD style={{ color: (a.win_rate ?? 0) >= 50 ? 'var(--green)' : 'var(--red)' }}>{(a.win_rate ?? 0).toFixed(1)}%</TD>
                  <TD style={{ color: (a.pnl_usd ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>{fmtUSD(a.pnl_usd)}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* ── POSITIONS OUVERTES ── */}
      <SectionTitle>Positions Ouvertes ({positions.length})</SectionTitle>
      <Card style={{ marginBottom: 24 }}>
        <table className="page-table">
          <thead><tr>
            <TH>Symbol</TH><TH>Side</TH><TH>Qté</TH><TH>Entrée</TH><TH>TP</TH><TH>SL</TH><TH>PnL</TH><TH>PnL%</TH><TH>Stratégie</TH>
          </tr></thead>
          <tbody>
            {positions.length === 0 ? (
              <tr><td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>Aucune position ouverte</td></tr>
            ) : positions.map((p, i) => (
              <tr key={i}>
                <TD style={{ color: 'var(--amber)' }}>{p.symbol ?? p.asset}</TD>
                <TD><Badge color={p.side === 'BUY' ? 'green' : 'red'}>{p.side ?? '—'}</Badge></TD>
                <TD>{p.qty?.toFixed(4) ?? p.quantity?.toFixed(4) ?? '—'}</TD>
                <TD>${p.entry_fill?.toFixed(2) ?? p.entry_price?.toFixed(2) ?? '—'}</TD>
                <TD style={{ color: 'var(--green)' }}>{p.tp ? `$${p.tp.toFixed(0)}` : '—'}</TD>
                <TD style={{ color: 'var(--red)' }}>{p.stop ? `$${p.stop.toFixed(0)}` : '—'}</TD>
                <TD style={{ color: (p.unrealized_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                  {p.unrealized_pnl != null ? fmtUSD(p.unrealized_pnl) : '—'}
                </TD>
                <TD style={{ color: (p.unrealized_pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {p.unrealized_pnl_pct != null ? fmtPct(p.unrealized_pnl_pct) : '—'}
                </TD>
                <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{p.strategy ?? '—'}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* ── GRAPHIQUES ── */}
      <div className="g2 mb24">
        <Card title="Daily PnL — Historique">
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={dailyHistory} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontFamily: 'var(--font-mono)', fontSize: 9, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} tickFormatter={v => `${v}`} />
                <ReferenceLine y={0} stroke="var(--border-bright)" />
                <Tooltip content={<TT />} />
                <Bar dataKey="pnl" name="PnL" radius={1}>
                  {dailyHistory.map((e, i) => (
                    <Cell key={i} fill={(e.pnl ?? 0) >= 0 ? 'var(--green)' : 'var(--red)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Performance détaillée par Stratégie">
          <table className="page-table">
            <thead><tr>
              <TH>Stratégie</TH><TH>Trades</TH><TH>Win%</TH><TH>PF</TH><TH>PnL</TH><TH>Sharpe</TH>
            </tr></thead>
            <tbody>
              {strategies.length === 0 ? (
                <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '12px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>Aucune donnée</td></tr>
              ) : strategies.map(s => (
                <tr key={s.strategy_id}>
                  <TD style={{ fontSize: 10 }}>{s.strategy_id}</TD>
                  <TD>{s.trades_count}</TD>
                  <TD style={{ color: (s.win_rate ?? 0) >= 50 ? 'var(--green)' : 'var(--red)' }}>{(s.win_rate ?? 0).toFixed(0)}%</TD>
                  <TD style={{ color: (s.profit_factor ?? 0) >= 1 ? 'var(--green)' : 'var(--red)' }}>{(s.profit_factor ?? 0).toFixed(2)}</TD>
                  <TD style={{ color: (s.pnl_usd ?? 0) >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>{fmtUSD(s.pnl_usd)}</TD>
                  <TD>{s.sharpe_ratio?.toFixed(3) ?? '—'}</TD>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      {/* ── TRADES RÉCENTS (filtrés) ── */}
      <SectionTitle>
        Trades Fermés{filteredTrades.length !== allTrades.length && ` (${filteredTrades.length}/${allTrades.length})`}
      </SectionTitle>
      <Card style={{ marginBottom: 24 }}>
        {lTrades && !tData ? (
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '12px 0' }}>Chargement…</div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="page-table">
              <thead><tr>
                <TH>Symbol</TH><TH>Side</TH><TH>Entrée</TH><TH>Sortie</TH>
                <TH>PnL</TH><TH>PnL%</TH><TH>Stratégie</TH><TH>Régime</TH><TH>Durée</TH><TH>Fermé</TH>
              </tr></thead>
              <tbody>
                {[...filteredTrades].reverse().map((t, i) => {
                  const win = (t.pnl_usd ?? 0) >= 0;
                  const durationMin = t.hold_ms ? Math.round(t.hold_ms / 60000) : null;
                  return (
                    <tr key={i}>
                      <TD style={{ color: 'var(--amber)' }}>{t.symbol}</TD>
                      <TD><Badge color={t.side === 'BUY' ? 'green' : 'red'}>{t.side ?? '—'}</Badge></TD>
                      <TD>{t.entry_price ? `$${t.entry_price.toFixed(2)}` : '—'}</TD>
                      <TD>{t.exit_price  ? `$${t.exit_price.toFixed(2)}`  : '—'}</TD>
                      <TD style={{ color: win ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}>
                        {t.pnl_usd != null ? fmtUSD(t.pnl_usd) : '—'}
                      </TD>
                      <TD style={{ color: win ? 'var(--green)' : 'var(--red)' }}>
                        {t.pnl_pct != null ? fmtPct(t.pnl_pct) : '—'}
                      </TD>
                      <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{t.strategy ?? '—'}</TD>
                      <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{t.regime ?? '—'}</TD>
                      <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{durationMin != null ? `${durationMin}min` : '—'}</TD>
                      <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{timeAgo(t.closed_at)}</TD>
                    </tr>
                  );
                })}
                {filteredTrades.length === 0 && (
                  <tr><td colSpan={10} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '20px', fontFamily: 'var(--font-mono)', fontSize: 10 }}>Aucun trade avec ces filtres</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* ── AGENTS TRADING ── */}
      <SectionTitle>Agents Trading</SectionTitle>
      <Card style={{ marginBottom: 24 }}>
        <table className="page-table">
          <thead><tr>
            <TH>Agent</TH><TH>Statut</TH><TH>Dernier run</TH><TH>Runs</TH><TH>Erreurs</TH>
          </tr></thead>
          <tbody>{agentList.map(a => {
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

      {/* ── RÈGLES & CONTRAINTES ── */}
      <SectionTitle>Règles & Contraintes</SectionTitle>
      <Card>
        <table className="page-table">
          <thead><tr>
            <TH>Contrainte</TH><TH>Valeur</TH><TH>Description</TH>
          </tr></thead>
          <tbody>
            {[
              ['Risque par trade',          '1% ($100)',             'Perte maximale acceptée par position'],
              ['Positions simultanées max', '3',                     'Toutes paires confondues'],
              ['Doublons interdit',         'Oui',                   'Impossible d\'ouvrir 2 positions sur le même symbol'],
              ['Kill Switch daily',         '-3%',                   'Arrêt total si le drawdown journalier dépasse -3%'],
              ['Score stratégie min',       '0.60 (active)',         '0.40–0.59 = testing, < 0.40 = alerte'],
              ['Timeframes analysés',       '5m, 1h, 4h',           'Bougies utilisées pour l\'analyse technique'],
              ['Symbols tradés',            'BTC, ETH, BNB',        'BTCUSDT, ETHUSDT, BNBUSDT uniquement'],
              ['Environnement actif',       'Testnet',               'Ordres réels API Binance testnet, capital fictif'],
              ['Tuner : trades min',        '30',                    'TRADE_STRATEGY_TUNER attend 30 trades avant d\'optimiser'],
              ['Rollback auto',             'Activé',                'Si la modification dégrade les performances, retour arrière auto'],
            ].map(([contrainte, valeur, desc]) => (
              <tr key={contrainte}>
                <TD style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{contrainte}</TD>
                <TD style={{ color: 'var(--amber)', fontWeight: 600 }}>{valeur}</TD>
                <TD style={{ color: 'var(--text-secondary)' }}>{desc}</TD>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
