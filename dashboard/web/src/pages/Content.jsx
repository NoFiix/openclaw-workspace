import React, { useCallback } from 'react';
import { api } from '../api/client';
import { useApiData, timeAgo } from '../hooks';
import { LoadingState, ErrorState, SectionTitle, Card, MetricCard, Badge, LastUpdated } from '../components/UI';

const fetchFn = () => api.content();

export default function Content() {
  const fetch = useCallback(fetchFn, []);
  const { data, error, loading, refresh, lastUpdated } = useApiData(fetch, 30000);

  if (loading) return <LoadingState text="Loading content pipeline..." />;
  if (error)   return <ErrorState message={error} onRetry={refresh} />;

  const drafts    = data?.drafts ?? {};
  const published = data?.published ?? {};
  const scraper   = data?.scraper ?? {};
  const articles  = data?.recent_articles ?? [];
  const queue     = data?.draft_queue ?? [];
  const twitter   = data?.twitter ?? {};

  return (
    <div>
      <SectionTitle>Content Pipeline</SectionTitle>
      <div className="grid-4 mb-24">
        <MetricCard label="Drafts Available" value={drafts.available ?? '—'} color="amber" sub={`${drafts.total ?? 0} total (IDs #1–#100)`} />
        <MetricCard label="Published Today" value={published.today ?? '—'} color="green" sub={`${published.this_week ?? 0} this week`} />
        <MetricCard label="Sources Scraped" value={scraper.sources_total ?? '—'} sub={`Last run: ${timeAgo(scraper.last_run)}`} />
        <MetricCard label="Twitter Posts" value={twitter.today ?? '—'} color="blue" sub={`${twitter.total ?? 0} total`} />
      </div>

      <div className="grid-3-2 mb-24">
        {/* Draft queue */}
        <Card title="Draft Queue">
          <table className="data-table">
            <thead>
              <tr>
                <th>#</th><th>Status</th><th>Preview</th><th>Source</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {queue.slice(0, 15).map((d) => (
                <tr key={d.id}>
                  <td className="mono text-amber">{d.id}</td>
                  <td>
                    <Badge color={
                      d.status === 'available' ? 'green' :
                      d.status === 'published' ? 'blue' :
                      d.status === 'rejected'  ? 'red' : 'grey'
                    }>{d.status}</Badge>
                  </td>
                  <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-ui)', fontSize: 12 }}>
                    {d.preview ?? '—'}
                  </td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{d.source ?? '—'}</td>
                  <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(d.created_at)}</td>
                </tr>
              ))}
              {!queue.length && (
                <tr><td colSpan={5} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No drafts in queue</td></tr>
              )}
            </tbody>
          </table>
        </Card>

        {/* Scraper + pipeline status */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Card title="Scraper Status">
            <table className="data-table">
              <thead>
                <tr><th>Source</th><th>Articles</th><th>Last</th><th>Status</th></tr>
              </thead>
              <tbody>
                {(scraper.sources ?? []).map((s) => (
                  <tr key={s.name}>
                    <td className="mono" style={{ fontSize: 11 }}>{s.name}</td>
                    <td className="mono">{s.articles_24h ?? '—'}</td>
                    <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(s.last_fetch)}</td>
                    <td>
                      <Badge color={s.status === 'ok' ? 'green' : 'red'}>{s.status ?? 'unknown'}</Badge>
                    </td>
                  </tr>
                ))}
                {!(scraper.sources?.length) && (
                  <tr><td colSpan={4} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No scraper data</td></tr>
                )}
              </tbody>
            </table>
          </Card>

          <Card title="Pipeline Components">
            {[
              { name: 'scraper.js',         label: 'RSS Scraper',         status: scraper.status },
              { name: 'hourly_scraper.js',  label: 'Hourly Scraper',      status: scraper.hourly_status },
              { name: 'poller.js',          label: 'Content Poller',      status: data?.poller_status },
              { name: 'drafts.js',          label: 'Draft Module',        status: 'ok' },
            ].map((comp) => (
              <div key={comp.name} className="flex-between" style={{ padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                <div>
                  <div className="mono" style={{ fontSize: 11 }}>{comp.label}</div>
                  <div className="text-muted mono" style={{ fontSize: 9 }}>{comp.name}</div>
                </div>
                <Badge color={comp.status === 'ok' ? 'green' : comp.status === 'warn' ? 'amber' : comp.status ? 'red' : 'grey'}>
                  {comp.status ?? 'unknown'}
                </Badge>
              </div>
            ))}
          </Card>
        </div>
      </div>

      {/* Recent articles */}
      <SectionTitle>Recent Articles (Scraped)</SectionTitle>
      <Card>
        <table className="data-table">
          <thead>
            <tr>
              <th>Title</th><th>Source</th><th>Score</th><th>Status</th><th>Scraped</th>
            </tr>
          </thead>
          <tbody>
            {articles.slice(0, 20).map((a, i) => (
              <tr key={i}>
                <td style={{ maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 12 }}>
                  {a.url ? (
                    <a href={a.url} target="_blank" rel="noreferrer" style={{ color: 'var(--text-primary)', textDecoration: 'none' }}>
                      {a.title ?? '—'}
                    </a>
                  ) : (a.title ?? '—')}
                </td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{a.source}</td>
                <td>
                  {a.score != null ? (
                    <span className={`mono ${a.score >= 7 ? 'text-amber' : a.score >= 5 ? 'text-primary' : 'text-muted'}`} style={{ fontSize: 11 }}>
                      {a.score.toFixed(1)}
                    </span>
                  ) : '—'}
                </td>
                <td>
                  <Badge color={a.used ? 'blue' : a.discarded ? 'grey' : 'green'}>
                    {a.used ? 'used' : a.discarded ? 'skip' : 'pending'}
                  </Badge>
                </td>
                <td className="text-muted mono" style={{ fontSize: 10 }}>{timeAgo(a.scraped_at)}</td>
              </tr>
            ))}
            {!articles.length && (
              <tr><td colSpan={5} style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>No articles scraped yet</td></tr>
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
