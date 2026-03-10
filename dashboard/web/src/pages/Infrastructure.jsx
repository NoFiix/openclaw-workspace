import React, { useCallback } from 'react';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, Card, MetricCard, Badge, LastUpdated, ProgressBar } from '../components/UI';

const fetchAll = async () => {
  const [health, storage] = await Promise.all([api.health(), api.storage()]);
  return { health, storage };
};

function EnvVarRow({ name, present }) {
  return (
    <div className="flex-between" style={{ padding: '5px 0', borderBottom: '1px solid var(--border)' }}>
      <span className="mono" style={{ fontSize: 11 }}>{name}</span>
      <Badge color={present ? 'green' : 'red'}>{present ? 'set' : 'missing'}</Badge>
    </div>
  );
}

const ENV_VARS = [
  'ANTHROPIC_API_KEY', 'OPENAI_API_KEY',
  'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID',
  'TRADER_TELEGRAM_BOT_TOKEN', 'TRADER_TELEGRAM_CHAT_ID',
  'BUILDER_TELEGRAM_BOT_TOKEN', 'BUILDER_TELEGRAM_CHAT_ID',
  'TWITTER_API_KEY', 'TWITTER_API_SECRET',
  'TWITTER_ACCESS_TOKEN', 'TWITTER_ACCESS_TOKEN_SECRET',
  'BINANCE_TESTNET_API_KEY', 'BINANCE_TESTNET_SECRET_KEY',
  'TRADING_MODE',
];

export default function Infrastructure() {
  const fetch = useCallback(fetchAll, []);
  const { data, error, loading, refresh, lastUpdated } = useApiData(fetch, 60000);

  if (loading) return <LoadingState text="Loading infrastructure data..." />;
  if (error)   return <ErrorState message={error} onRetry={refresh} />;

  const { health, storage } = data;
  const docker   = health?.docker ?? {};
  const system   = health?.system ?? {};
  const crons    = health?.crons ?? [];
  const envVars  = health?.env_vars ?? {};
  const disks    = storage?.disks ?? [];
  const files    = storage?.key_files ?? [];

  const diskMain = disks[0] ?? {};

  return (
    <div>
      {/* System KPIs */}
      <SectionTitle>System Resources</SectionTitle>
      <div className="grid-4 mb-24">
        <MetricCard
          label="Disk Used"
          value={diskMain.used_gb != null ? `${diskMain.used_gb.toFixed(1)} GB` : '—'}
          sub={diskMain.total_gb ? `of ${diskMain.total_gb.toFixed(0)} GB — ${diskMain.use_pct?.toFixed(0)}%` : ''}
          color={diskMain.use_pct > 85 ? 'red' : diskMain.use_pct > 70 ? 'amber' : 'green'}
        />
        <MetricCard
          label="Memory"
          value={system.mem_used_gb != null ? `${system.mem_used_gb.toFixed(1)} GB` : '—'}
          sub={system.mem_total_gb ? `of ${system.mem_total_gb.toFixed(0)} GB` : ''}
          color={system.mem_pct > 85 ? 'red' : system.mem_pct > 70 ? 'amber' : 'green'}
        />
        <MetricCard
          label="CPU Load"
          value={system.cpu_load_1m != null ? `${system.cpu_load_1m.toFixed(2)}` : '—'}
          sub="1-min avg load"
          color={system.cpu_load_1m > 2 ? 'red' : system.cpu_load_1m > 1 ? 'amber' : 'green'}
        />
        <MetricCard
          label="Container"
          value={docker.status ?? '—'}
          color={docker.status === 'running' ? 'green' : 'red'}
          sub={docker.image ?? 'openclaw'}
        />
      </div>

      <div className="grid-2 mb-24">
        {/* Docker info */}
        <Card title="Docker Container">
          {[
            { label: 'Container',   value: docker.name ?? 'openclaw-openclaw-gateway-1' },
            { label: 'Image',       value: docker.image ?? 'ghcr.io/openclaw/openclaw:2026.3.2' },
            { label: 'Status',      value: docker.status, badge: true, color: docker.status === 'running' ? 'green' : 'red' },
            { label: 'Port',        value: docker.port ?? '18789' },
            { label: 'Uptime',      value: docker.uptime ?? '—' },
            { label: 'Restarts',    value: docker.restart_count ?? '0' },
            { label: 'Node.js',     value: 'v22' },
            { label: 'Trading Mode',value: health?.trading_mode ?? '—', badge: true, color: health?.trading_mode === 'testnet' ? 'amber' : 'red' },
          ].map((row) => (
            <div key={row.label} className="flex-between" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
              <span className="text-muted mono" style={{ fontSize: 11 }}>{row.label}</span>
              {row.badge
                ? <Badge color={row.color}>{row.value}</Badge>
                : <span className="mono" style={{ fontSize: 11 }}>{row.value}</span>
              }
            </div>
          ))}
        </Card>

        {/* Disk usage */}
        <Card title="Storage">
          <div className="mb-16">
            {disks.map((d) => (
              <div key={d.mount} style={{ marginBottom: 12 }}>
                <div className="flex-between mb-8">
                  <span className="mono" style={{ fontSize: 11 }}>{d.mount}</span>
                  <span className="text-muted mono" style={{ fontSize: 10 }}>
                    {d.used_gb?.toFixed(1)}GB / {d.total_gb?.toFixed(0)}GB ({d.use_pct?.toFixed(0)}%)
                  </span>
                </div>
                <ProgressBar value={d.use_pct ?? 0} color={d.use_pct > 85 ? 'red' : d.use_pct > 70 ? 'amber' : 'green'} />
              </div>
            ))}
          </div>

          <div className="card-title mb-8">Bus Topic Sizes</div>
          <table className="data-table">
            <thead><tr><th>File</th><th>Size</th><th>Modified</th></tr></thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.path}>
                  <td className="mono" style={{ fontSize: 10 }}>{f.name ?? f.path}</td>
                  <td className="mono" style={{ fontSize: 11 }}>{f.size_mb != null ? `${f.size_mb.toFixed(2)} MB` : f.size ?? '—'}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(f.modified_at)}</td>
                </tr>
              ))}
              {!files.length && <tr><td colSpan={3} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No file data</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>

      {/* Env vars + Crons */}
      <div className="grid-2 mb-24">
        <Card title="Environment Variables">
          {ENV_VARS.map((v) => (
            <EnvVarRow key={v} name={v} present={envVars[v] ?? false} />
          ))}
          {!Object.keys(envVars).length && (
            <div style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11, padding: '12px 0' }}>
              Env var status not exposed by API
            </div>
          )}
        </Card>

        <Card title="Cron Jobs">
          <table className="data-table">
            <thead>
              <tr><th>Job</th><th>Schedule</th><th>Last Run</th><th>Status</th></tr>
            </thead>
            <tbody>
              {crons.map((c, i) => (
                <tr key={i}>
                  <td className="mono" style={{ fontSize: 11 }}>{c.name}</td>
                  <td className="mono text-muted" style={{ fontSize: 10 }}>{c.schedule}</td>
                  <td className="mono text-muted" style={{ fontSize: 10 }}>{timeAgo(c.last_run)}</td>
                  <td><Badge color={c.status === 'ok' ? 'green' : 'red'}>{c.status ?? 'unknown'}</Badge></td>
                </tr>
              ))}
              {!crons.length && (
                <>
                  <tr>
                    <td className="mono" style={{ fontSize: 10 }}>bus_cleanup_trading</td>
                    <td className="mono text-muted" style={{ fontSize: 10 }}>30 3 * * *</td>
                    <td className="mono text-muted" style={{ fontSize: 10 }}>—</td>
                    <td><Badge color="grey">unknown</Badge></td>
                  </tr>
                </>
              )}
            </tbody>
          </table>

          <div style={{ marginTop: 16 }}>
            <div className="card-title mb-8">GitHub Repo</div>
            <div className="flex-between" style={{ padding: '6px 0' }}>
              <span className="mono" style={{ fontSize: 11 }}>Remote</span>
              <a href="https://github.com/NoFiix/openclaw-workspace" target="_blank" rel="noreferrer"
                style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--amber)', textDecoration: 'none' }}>
                NoFiix/openclaw-workspace
              </a>
            </div>
            {health?.git_commit && (
              <div className="flex-between" style={{ padding: '6px 0' }}>
                <span className="mono text-muted" style={{ fontSize: 11 }}>Last commit</span>
                <span className="mono" style={{ fontSize: 11 }}>{health.git_commit.slice(0, 8)}</span>
              </div>
            )}
          </div>
        </Card>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <LastUpdated ts={lastUpdated} />
      </div>
    </div>
  );
}
