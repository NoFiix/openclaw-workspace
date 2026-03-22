const BASE_URL = '/api';
function getApiKey() {
  return localStorage.getItem('openclaw_api_key') || '';
}
async function apiFetch(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': getApiKey(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}
export const api = {
  setApiKey: (key) => localStorage.setItem('openclaw_api_key', key),
  getApiKey,
  health:          () => apiFetch('/health'),
  costs:           () => apiFetch('/costs/summary'),
  trading:         () => apiFetch('/trading/live'),
  tradingTrades:   () => apiFetch('/trading/trades'),
  tradingPerf:     () => apiFetch('/trading/performance'),
  tradingHistory:  () => apiFetch('/trading/history'),
  tradingStrategies: () => apiFetch('/trading/strategies'),
  content: () => apiFetch('/content/summary'),
  storage: () => apiFetch('/storage/summary'),
  docs:    () => apiFetch('/docs'),
  // ── Polymarket (POLY_FACTORY) ─────────────────────────────────────────────
  polyLive:       () => apiFetch('/polymarket/live'),
  polyStrategies: () => apiFetch('/polymarket/strategies'),
  polyTrades:     (params = '') => apiFetch(`/polymarket/trades${params}`),
  polyHealth:     () => apiFetch('/polymarket/health'),
};
