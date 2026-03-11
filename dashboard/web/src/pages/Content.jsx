import { useCallback } from 'react';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, MetricCard, Card, Badge, LastUpdated } from '../components/UI';

const CONTENT_AGENTS = [
  { name: 'hourly_scraper', type: 'SCRIPT', llm: 'Haiku',  schedule: '1h (7h–23h)',   every_seconds: 3600 },
  { name: 'scraper',        type: 'SCRIPT', llm: 'Haiku',  schedule: 'Manuel',         every_seconds: null },
  { name: 'drafts.js',      type: 'MODULE', llm: null,      schedule: 'Continu',        every_seconds: null },
  { name: 'poller.js',      type: 'POLLER', llm: null,      schedule: 'Continu',        every_seconds: null },
  { name: 'copywriter',     type: 'AGENT',  llm: 'Sonnet', schedule: 'À la demande',   every_seconds: null },
  { name: 'twitter.js',     type: 'SCRIPT', llm: null,      schedule: 'Sur validation', every_seconds: null },
];

const TYPE_COLOR = {
  SCRIPT: 'var(--blue)',
  POLLER: 'var(--amber)',
  MODULE: 'var(--purple)',
  AGENT:  'var(--green)',
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

export default function Content() {
  const fetchFn = useCallback(() => api.content(), []);
  const { data, loading, error, refresh, lastUpdated } = useApiData(fetchFn, 60000);

  if (loading && !data) return <LoadingState text="Chargement content..." />;
  if (error   && !data) return <ErrorState message={error} onRetry={refresh} />;

  const drafts  = data?.drafts   ?? {};
  const scrapers = data?.scrapers ?? {};
  const agents   = data?.agents   ?? {};

  const hourlyOk = scrapers.hourly_last_run && Date.now() - scrapers.hourly_last_run < 7_200_000;
  const dailyOk  = scrapers.daily_last_run  && Date.now() - scrapers.daily_last_run  < 86_400_000;

  return (
    <div>
      {/* ── MÉTRIQUES ── */}
      <SectionTitle>Content Pipeline</SectionTitle>
      <div className="g4 mb24">
        <MetricCard
          label="Drafts Disponibles"
          value={drafts.pending ?? '—'}
          color="amber"
          sub={`${drafts.total ?? 0} total · ${drafts.approved ?? 0} approuvés`}
        />
        <MetricCard
          label="Publiés Aujourd'hui"
          value={data?.today ?? '—'}
          color="green"
          sub={data?.month != null ? `${data.month} ce mois` : 'données agrégées indisponibles'}
        />
        <MetricCard
          label="Sources Scraper"
          value={6}
          sub={`Dernier horaire : ${timeAgo(scrapers.hourly_last_run)}`}
        />
        <MetricCard
          label="Drafts Rejetés"
          value={drafts.rejected ?? '—'}
          color={drafts.rejected > 0 ? 'red' : 'green'}
          sub="drafts non validés"
        />
      </div>

      {/* ── SCRAPERS + AGENTS RUNTIME ── */}
      <div className="g2 mb24">
        <Card title="État des Scrapers">
          {[
            ['Scraper Horaire', scrapers.hourly_last_run, hourlyOk],
            ['Scraper Daily',   scrapers.daily_last_run,  dailyOk],
          ].map(([label, ts, ok]) => (
            <div key={label} className="fbet" style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-primary)' }}>{label}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>
                  {ts ? timeAgo(ts) : '—'}
                </span>
                <Badge color={ok ? 'green' : 'amber'}>{ok ? 'ok' : 'stale'}</Badge>
              </div>
            </div>
          ))}

          <div style={{ marginTop: 16 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 8, fontWeight: 600, letterSpacing: '.15em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 10 }}>
              Drafts — Répartition
            </div>
            {[
              ['En attente', drafts.pending  ?? 0, 'amber'],
              ['Approuvés',  drafts.approved ?? 0, 'green'],
              ['Rejetés',    drafts.rejected ?? 0, 'red'],
            ].map(([label, val, color]) => (
              <div key={label} style={{ marginBottom: 8 }}>
                <div className="fbet" style={{ marginBottom: 4 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-secondary)' }}>{label}</span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600, color: `var(--${color})` }}>{val}</span>
                </div>
                <div style={{ height: 3, background: 'var(--bg-elevated)', borderRadius: 2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 2, width: `${drafts.total ? (val / drafts.total) * 100 : 0}%`, background: `var(--${color})`, transition: 'width .3s ease' }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Agents Content — État Runtime">
          {Object.keys(agents).length === 0 ? (
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-secondary)', padding: '12px 0' }}>
              Aucun agent actif (états non chargés)
            </div>
          ) : (
            <table className="page-table">
              <thead><tr>
                <TH>Agent</TH><TH>Dernier run</TH><TH>Runs</TH><TH>Statut</TH>
              </tr></thead>
              <tbody>
                {Object.entries(agents).map(([name, v]) => {
                  const lastRun = v.last_run_ts ?? null;
                  const stale   = !lastRun || Date.now() - lastRun > 3_600_000;
                  return (
                    <tr key={name}>
                      <TD style={{ fontSize: 10 }}>{name}</TD>
                      <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{lastRun ? timeAgo(lastRun) : '—'}</TD>
                      <TD>{v.runs ?? 0}</TD>
                      <TD><Badge color={stale ? 'grey' : 'green'}>{stale ? 'inactif' : 'actif'}</Badge></TD>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      {/* ── AGENTS & SCRIPTS ── */}
      <SectionTitle>Agents & Scripts Content</SectionTitle>
      <Card>
        <table className="page-table">
          <thead><tr>
            <TH>Agent / Script</TH><TH>Type</TH><TH>Statut</TH><TH>Dernier run</TH><TH>Schedule</TH><TH>LLM</TH>
          </tr></thead>
          <tbody>
            {CONTENT_AGENTS.map(agent => {
              const runtime    = agents[agent.name] ?? null;
              const lastRunTs  = runtime?.last_run_ts ?? null;
              const staleness  = lastRunTs && agent.every_seconds ? (Date.now() - lastRunTs) / 1000 : null;
              const agStatus   = !staleness
                ? 'unknown'
                : staleness < agent.every_seconds * 2 ? 'ok'
                : staleness < agent.every_seconds * 5 ? 'warn'
                : 'error';

              return (
                <tr key={agent.name}>
                  <TD style={{ fontSize: 10 }}>{agent.name}</TD>
                  <TD>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: 8, fontWeight: 600,
                      padding: '1px 5px', borderRadius: 2,
                      background: `${TYPE_COLOR[agent.type]}18`,
                      color: TYPE_COLOR[agent.type],
                    }}>{agent.type}</span>
                  </TD>
                  <TD>
                    <Badge color={agStatus === 'ok' ? 'green' : agStatus === 'warn' ? 'amber' : agStatus === 'error' ? 'red' : 'grey'}>
                      {agStatus === 'unknown' ? '?' : agStatus}
                    </Badge>
                  </TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>
                    {lastRunTs ? timeAgo(lastRunTs) : '—'}
                  </TD>
                  <TD style={{ color: 'var(--text-secondary)', fontSize: 9 }}>{agent.schedule}</TD>
                  <TD style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color: agent.llm ? 'var(--amber)' : 'var(--text-muted)' }}>
                    {agent.llm ?? '—'}
                  </TD>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
