/**
 * POLY_TRADING_PUBLISHER — Formatters
 * Helpers partagés pour formater les données numériques et temporelles.
 * Aucune logique métier ici — fonctions pures uniquement.
 */

/**
 * Formate un montant en euros avec signe optionnel.
 * @param {number|null} val
 * @param {boolean} showSign — affiche + pour positif
 * @returns {string}
 */
export function formatMoney(val, showSign = false) {
  if (val == null || isNaN(val)) return '—';
  const abs  = Math.abs(val);
  const sign = showSign
    ? (val > 0 ? '+' : val < 0 ? '-' : '')
    : (val < 0 ? '-' : '');
  if (abs >= 1000) return `${sign}${(abs / 1000).toFixed(2)}k€`;
  return `${sign}${abs.toFixed(2)}€`;
}

/**
 * Formate un pourcentage avec signe.
 * @param {number|null} val
 * @param {boolean} showSign
 * @returns {string}
 */
export function formatPct(val, showSign = true) {
  if (val == null || isNaN(val)) return '—';
  const sign = showSign ? (val >= 0 ? '+' : '') : '';
  return `${sign}${val.toFixed(2)}%`;
}

/**
 * Formate une durée en millisecondes → "2h30min" ou "45min".
 * @param {number|null} ms
 * @returns {string}
 */
export function formatDuration(ms) {
  if (!ms || ms <= 0) return '—';
  const min = Math.round(ms / 60000);
  if (min < 60) return `${min}min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h}h${m}min` : `${h}h`;
}

/**
 * Formate un timestamp ISO → date/heure Paris lisible.
 * @param {string|number|null} ts
 * @returns {string}
 */
export function formatTs(ts) {
  if (!ts) return '—';
  try {
    const d = typeof ts === 'number' ? new Date(ts) : new Date(ts);
    if (isNaN(d.getTime())) return String(ts).slice(0, 16);
    return d.toLocaleString('fr-FR', {
      timeZone: 'Europe/Paris',
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return String(ts).slice(0, 16); }
}

/**
 * Formate une date ISO "YYYY-MM-DD" → "13 mars 2026".
 * @param {string} isoDate
 * @returns {string}
 */
export function formatParisDate(isoDate) {
  if (!isoDate) return '—';
  const MONTHS = [
    'janvier','février','mars','avril','mai','juin',
    'juillet','août','septembre','octobre','novembre','décembre',
  ];
  const [y, m, d] = isoDate.split('-');
  return `${parseInt(d, 10)} ${MONTHS[parseInt(m, 10) - 1]} ${y}`;
}

/**
 * Tronque un market_id long pour l'affichage.
 * @param {string|null} id
 * @returns {string}
 */
export function shortId(id) {
  if (!id) return '—';
  return id.length > 20 ? `${id.slice(0, 12)}…${id.slice(-6)}` : id;
}

/**
 * Retourne l'emoji de tendance selon le signe d'une valeur.
 * @param {number} val
 * @returns {string}
 */
export function trendEmoji(val) {
  if (val == null) return '➖';
  return val > 0 ? '📈' : val < 0 ? '📉' : '➖';
}
