import { useCallback } from 'react';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, Card, Badge, LastUpdated } from '../components/UI';

const ProgBar = ({ val, max=100, color="amber" }) => (
  <div style={{ height:4, background:'var(--bg-elevated)', borderRadius:2, overflow:'hidden', marginTop:6 }}>
    <div style={{ height:'100%', borderRadius:2, width:`${Math.min(100,Math.max(0,(val/max)*100))}%`, background:`var(--${color})`, transition:'width .3s ease' }} />
  </div>
);

export default function Infrastructure() {
  const fetchHealth  = useCallback(() => api.health(), []);
  const fetchStorage = useCallback(() => api.storage(), []);
  const { data: health,  loading: lH, lastUpdated } = useApiData(fetchHealth,  30000);
  const { data: storage, loading: lS } = useApiData(fetchStorage, 60000);

  if ((lH || lS) && !health && !storage) return <LoadingState text="Chargement infrastructure..." />;

  const disk  = storage?.disk  ?? {};
  const sizes = storage?.sizes ?? {};

  return (
    <div>
      <SectionTitle>Ressources Système</SectionTitle>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:24 }}>
        <MetricCard label="Disque Libre"    value={disk.free_mb ? `${(disk.free_mb/1024).toFixed(0)} GB` : health?.disk?.free ?? '—'} color="green" sub={`Utilisé: ${disk.pct_used??health?.disk?.pct??'—'}%`} />
        <MetricCard label="Score Système"   value={health?.score!=null?`${health.score}/100`:'—'} color={health?.score>=80?'green':health?.score>=50?'amber':'red'} sub={`${health?.open_incidents??0} incident(s)`} />
        <MetricCard label="Watchdog"        value={health?.last_watchdog_run ? timeAgo(health.last_watchdog_run*1000) : '—'} sub="dernier rapport" />
        <MetricCard label="Alertes"         value={`${health?.crits??0} crit / ${health?.warns??0} warn`} color={health?.crits>0?'red':health?.warns>0?'amber':'green'} sub="SYSTEM_WATCHDOG" />
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:24 }}>
        <Card title="Pollers">
          {[['Trading', health?.pollers?.trading], ['Content', health?.pollers?.content]].map(([l, p]) => (
            <div key={l} style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'10px 0', borderBottom:'1px solid var(--border)' }}>
              <span style={{ fontFamily:'var(--font-mono)', fontSize:11, color:'var(--text-primary)' }}>{l} Poller</span>
              <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                <span style={{ fontFamily:'var(--font-mono)', fontSize:9, color:'var(--text-secondary)' }}>PID {p?.pid??'—'}</span>
                <Badge color={p?.active?'green':'red'}>{p?.active?'ACTIF':'INACTIF'}</Badge>
              </div>
            </div>
          ))}
        </Card>

        <Card title="Disque — Utilisation par dossier (MB)">
          {Object.entries(sizes).map(([k, v]) => (
            <div key={k} style={{ marginBottom:10 }}>
              <div style={{ display:'flex', justifyContent:'space-between', fontFamily:'var(--font-mono)', fontSize:10 }}>
                <span style={{ color:'var(--text-secondary)' }}>{k}</span>
                <span style={{ color:'var(--text-primary)' }}>{v} MB</span>
              </div>
              <ProgBar val={v} max={Math.max(...Object.values(sizes))} color="amber" />
            </div>
          ))}
        </Card>
      </div>

      <div style={{ display:'flex', justifyContent:'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
