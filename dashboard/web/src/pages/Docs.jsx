import React, { useCallback } from 'react';
import { api } from '../api/client';
import { useApiData } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, Card, Badge } from '../components/UI';

const fetchFn = () => api.docs();

const METHOD_COLORS = { GET: 'green', POST: 'blue', PUT: 'amber', DELETE: 'red' };

export default function Docs() {
  const fetch = useCallback(fetchFn, []);
  const { data, error, loading, refresh } = useApiData(fetch, 0); // no refresh

  // Fallback static docs if API not ready
  const staticRoutes = [
    { method: 'GET', path: '/api/health',  desc: 'System health: agents, Docker, system metrics, bus topics' },
    { method: 'GET', path: '/api/costs',   desc: 'LLM costs: by agent, by model, history, summary' },
    { method: 'GET', path: '/api/trading', desc: 'Trading: positions, kill switch, performance, regime, whale, trades' },
    { method: 'GET', path: '/api/content', desc: 'Content: drafts, published, scraper sources, articles queue' },
    { method: 'GET', path: '/api/storage', desc: 'Storage: disk usage, bus files, key state files' },
    { method: 'GET', path: '/api/docs',    desc: 'This documentation' },
  ];

  const routes = data?.routes ?? staticRoutes;

  return (
    <div>
      <SectionTitle>API Reference</SectionTitle>

      <div className="mb-24">
        <div className="alert info" style={{ marginBottom: 16 }}>
          All endpoints require <span className="mono" style={{ fontWeight: 700 }}>x-api-key</span> header.
          Set your key via the settings icon in the sidebar.
        </div>
        <div className="alert warn">
          Base URL: <span className="mono">http://localhost/api</span> (Nginx proxy → Express on port configured in ecosystem.config.cjs)
        </div>
      </div>

      <Card title="Endpoints">
        <table className="data-table">
          <thead>
            <tr><th>Method</th><th>Path</th><th>Description</th></tr>
          </thead>
          <tbody>
            {routes.map((r, i) => (
              <tr key={i}>
                <td><Badge color={METHOD_COLORS[r.method] ?? 'grey'}>{r.method}</Badge></td>
                <td className="mono" style={{ fontSize: 11 }}>{r.path}</td>
                <td style={{ fontSize: 12 }}>{r.desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-12 mb-24">
        <SectionTitle>Response Shape Reference</SectionTitle>
        {[
          {
            route: 'GET /api/health',
            shape: `{
  uptime_pct: number,
  trading_mode: "testnet" | "live",
  git_commit: string,
  docker: { name, image, status, port, uptime, restart_count },
  system: { mem_used_gb, mem_total_gb, mem_pct, cpu_load_1m },
  agents: [{ name, status, last_run, every_seconds, llm }],
  bus_topics: [{ topic, last_event, events_24h, ttl, size_mb }],
  crons: [{ name, schedule, last_run, status }],
  env_vars: { VAR_NAME: bool },
  alerts: [{ type, msg }]
}`
          },
          {
            route: 'GET /api/trading',
            shape: `{
  kill_switch: { tripped, daily_pnl_pct, threshold_pct },
  positions: [{ symbol, side, quantity, entry_price, current_price, take_profit, stop_loss, unrealized_pnl, unrealized_pnl_pct, strategy, regime, opened_at }],
  recent_trades: [{ symbol, side, entry_price, exit_price, pnl_usd, pnl_pct, strategy, regime, duration_min, closed_at }],
  daily_pnl: { pnl_usd, pnl_pct },
  daily_pnl_history: [{ date, pnl_usd }],
  regime: { regime, confidence, timestamp },
  whale_signal: { bias, score, strength },
  strategies: [{ name, status, score }],
  performance: {
    global: { total_pnl_usd, total_trades, win_rate, win_count, loss_count, profit_factor, avg_win_usd, avg_loss_usd, max_drawdown_pct, sharpe },
    by_strategy: [{ name, total_trades, win_rate, profit_factor, pnl_usd, score }],
    by_asset: [{ symbol, total_trades, win_rate, pnl_usd }]
  }
}`
          },
          {
            route: 'GET /api/costs',
            shape: `{
  summary: { today_total_usd, month_total_usd, avg_daily_7d_usd, projected_monthly_usd, total_tokens_today },
  by_agent: [{ agent, model, calls_today, tokens_in, tokens_out, cost_usd, cost_month_usd, projected_monthly_usd }],
  by_model: [{ model, cost_usd }],
  history_7d: [{ date, total_usd, haiku_usd, sonnet_usd }]
}`
          },
          {
            route: 'GET /api/content',
            shape: `{
  drafts: { total, available },
  published: { today, this_week },
  twitter: { today, total },
  poller_status: string,
  scraper: { status, hourly_status, last_run, sources_total, sources: [{ name, articles_24h, last_fetch, status }] },
  draft_queue: [{ id, status, preview, source, created_at }],
  recent_articles: [{ title, url, source, score, used, discarded, scraped_at }]
}`
          },
          {
            route: 'GET /api/storage',
            shape: `{
  disks: [{ mount, used_gb, total_gb, use_pct }],
  key_files: [{ name, path, size_mb, modified_at }]
}`
          },
        ].map((item) => (
          <Card key={item.route} title={item.route}>
            <pre style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-secondary)',
              background: 'var(--bg-base)',
              padding: 12,
              borderRadius: 'var(--radius)',
              border: '1px solid var(--border)',
              overflow: 'auto',
              lineHeight: 1.6,
              marginTop: 4,
            }}>
              {item.shape}
            </pre>
          </Card>
        ))}
      </div>
    </div>
  );
}
