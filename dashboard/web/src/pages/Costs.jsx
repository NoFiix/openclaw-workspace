import { useCallback } from 'react';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { api } from '../api/client';
import { useApiData, fmtUSD, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, Card, LastUpdated } from '../components/UI';

const MODEL_COLORS = {
  'claude-haiku-4-5-20251001': '#10b981',
  'claude-sonnet-4-20250514':  '#f59e0b',
  'claude-opus-4-20250514':    '#ef4444',
  'gpt-4o':                    '#3b82f6',
  'gpt-4o-mini':               '#8b5cf6',
};
const modelColor = (m) => {
  if (!m) return 'var(--text-secondary)';
  const k = m.toLowerCase();
  for (const [key, v] of Object.entries(MODEL_COLORS)) if (k.includes(key)) return v;
  return 'var(--text-secondary)';
};
const shortModel = (m) => {
  if (!m) return '—';
  if (m.includes('haiku'))  return 'Haiku';
  if (m.includes('sonnet')) return 'Sonnet';
  if (m.includes('opus'))   return 'Opus';
  if (m.includes('gpt-4o-mini')) return 'GPT-4o-mini';
  if (m.includes('gpt-4o')) return 'GPT-4o';
  return m;
};

const TT = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background:'var(--bg-elevated)', border:'1px solid var(--border)', padding:'8px 12px', fontFamily:'var(--font-mono)', fontSize:10 }}>
      <div style={{ color:'var(--text-secondary)', marginBottom:4 }}>{label}</div>
      {payload.map(p => <div key={p.dataKey} style={{ color: p.color||'var(--amber)' }}>{p.name}: {fmtUSD(p.value)}</div>)}
    </div>
  );
};

export default function Costs() {
  const fetchFn = useCallback(() => api.costs(), []);
  const { data, error, loading, refresh, lastUpdated } = useApiData(fetchFn, 60000);

  if (loading && !data) return <LoadingState text="Chargement des coûts LLM..." />;
  if (error && !data)   return <ErrorState message={error} onRetry={refresh} />;

  // Convertir by_agent objet → tableau
  const byAgentArr = data?.by_agent
    ? Object.entries(data.by_agent).map(([agent, v]) => ({ agent, ...v }))
    : [];

  // Agréger par modèle pour le pie chart
  const byModel = Object.values(
    byAgentArr.reduce((acc, a) => {
      const m = shortModel(a.model);
      if (!acc[m]) acc[m] = { model: m, cost_usd: 0 };
      acc[m].cost_usd += a.today || 0;
      return acc;
    }, {})
  );

  const totalToday = data?.today ?? 0;
  const totalMonth = data?.month ?? 0;

  return (
    <div>
      <SectionTitle>Coûts Tokens LLM</SectionTitle>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:24 }}>
        <MetricCard label="Aujourd'hui"   value={fmtUSD(totalToday)}  color="amber" sub="Tous modèles" />
        <MetricCard label="Ce mois"       value={fmtUSD(totalMonth)}  color="blue"  sub="cumulé" />
        <MetricCard label="Agents actifs" value={byAgentArr.length}   sub="avec LLM" />
        <MetricCard label="Top agent"     value={byAgentArr.sort((a,b)=>(b.today||0)-(a.today||0))[0]?.agent?.split('_')[0] ?? '—'} sub="coût le plus élevé" />
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'2fr 1fr', gap:12, marginBottom:24 }}>
        <Card title="Coût par Agent (aujourd'hui)">
          {byAgentArr.length === 0 ? (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-secondary)', padding:'20px 0' }}>Aucune donnée</div>
          ) : (
            <div style={{ height:220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byAgentArr} layout="vertical" margin={{ top:0, right:16, left:0, bottom:0 }}>
                  <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-secondary)' }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toFixed(3)}`} />
                  <YAxis type="category" dataKey="agent" tick={{ fontFamily:'var(--font-mono)', fontSize:9, fill:'var(--text-secondary)' }} axisLine={false} tickLine={false} width={150} />
                  <Tooltip content={<TT />} />
                  <Bar dataKey="today" name="Coût" fill="var(--amber)" radius={1} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
        <Card title="Par Modèle">
          {byModel.length === 0 ? (
            <div style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-secondary)', padding:'20px 0' }}>Aucune donnée</div>
          ) : (
            <div style={{ height:220 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={byModel} dataKey="cost_usd" nameKey="model" cx="50%" cy="50%" outerRadius={80}
                    label={({ model, percent }) => `${model} ${(percent*100).toFixed(0)}%`} labelLine={false}>
                    {byModel.map(e => <Cell key={e.model} fill={modelColor(e.model)} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background:'var(--bg-elevated)', border:'1px solid var(--border)', fontFamily:'var(--font-mono)', fontSize:10 }} formatter={v => fmtUSD(v)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      <SectionTitle>Détail par Agent</SectionTitle>
      <div style={{ background:'var(--bg-surface)', border:'1px solid var(--border)', borderRadius:'var(--radius)', padding:16, marginBottom:24 }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontFamily:'var(--font-mono)', fontSize:11 }}>
          <thead>
            <tr>
              {['Agent','Modèle','Coût Auj.','Coût Mois','Total'].map(h => (
                <th key={h} style={{ textAlign:'left', padding:'5px 8px', fontSize:8, fontWeight:600, letterSpacing:'.12em', textTransform:'uppercase', color:'var(--text-secondary)', borderBottom:'1px solid var(--border)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {byAgentArr.length === 0 ? (
              <tr><td colSpan={5} style={{ padding:'16px 8px', color:'var(--text-secondary)', textAlign:'center' }}>Aucune donnée disponible</td></tr>
            ) : byAgentArr.map(a => (
              <tr key={a.agent} style={{ borderBottom:'1px solid var(--border)' }}>
                <td style={{ padding:'7px 8px', color:'var(--amber)' }}>{a.agent}</td>
                <td style={{ padding:'7px 8px' }}>
                  <span style={{ fontFamily:'var(--font-mono)', fontSize:9, fontWeight:600, padding:'2px 6px', borderRadius:'var(--radius)', background:`${modelColor(a.model)}20`, color:modelColor(a.model) }}>
                    {shortModel(a.model)}
                  </span>
                </td>
                <td style={{ padding:'7px 8px', color: (a.today||0) > 0 ? 'var(--amber)' : 'var(--text-secondary)' }}>{fmtUSD(a.today||0)}</td>
                <td style={{ padding:'7px 8px' }}>{fmtUSD(a.month||0)}</td>
                <td style={{ padding:'7px 8px', color:'var(--text-secondary)' }}>{fmtUSD(a.total||0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display:'flex', justifyContent:'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
