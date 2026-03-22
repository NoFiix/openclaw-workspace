/**
 * POLY_TRADING_PUBLISHER — Messages
 * Toutes les fonctions de formatage des messages Telegram.
 * Chaque fonction retourne une string Markdown V1.
 */

import {
  formatMoney, formatPct, formatTs, formatParisDate,
  shortId, trendEmoji, formatDuration,
} from './formatters.js';

// ── Helpers internes ─────────────────────────────────────────────────────────

function sep() { return '─────────────────────'; }

function stratLine(stratName) {
  return `📌 Stratégie : \`${stratName}\``;
}

function tradeLine(trade) {
  const side  = trade.side === 'YES' ? '🟢 YES' : '🔴 NO';
  const mkt   = shortId(trade.market_id || trade.condition_id || '?');
  const price = trade.price_usd != null ? `${(trade.price_usd * 100).toFixed(1)}¢` : '?¢';
  const size  = trade.size_eur  != null ? formatMoney(trade.size_eur) : '?€';
  return `${side}  \`${mkt}\`\n💵 Prix: ${price} · Taille: ${size}`;
}

function pnlLine(pnl, pct) {
  const em = trendEmoji(pnl);
  return `${em} P&L : ${formatMoney(pnl, true)}  (${formatPct(pct, true)})`;
}

// ── LIVE alerts (priority 1) ─────────────────────────────────────────────────

/**
 * Trade LIVE ouvert.
 */
export function msgLiveTradeOpened(trade) {
  return [
    `🔴 *LIVE — Ordre ouvert*`,
    stratLine(trade.strategy_name || trade.strategy || '?'),
    tradeLine(trade),
    `⏰ ${formatTs(trade.opened_at || trade.timestamp || Date.now())}`,
  ].join('\n');
}

/**
 * Trade LIVE clôturé (résolu).
 * @param {Object} trade
 * @param {number|null} trade.pnl_eur
 * @param {number|null} trade.pnl_pct
 * @param {string|null} trade.outcome  'YES'|'NO'|null
 */
export function msgLiveTradeClosed(trade) {
  const won   = trade.outcome === trade.side;
  const icon  = trade.pnl_eur == null ? '🔵' : won ? '✅' : '🚨';
  const lines = [
    `${icon} *LIVE — Trade résolu*`,
    stratLine(trade.strategy_name || trade.strategy || '?'),
    tradeLine(trade),
  ];
  if (trade.pnl_eur != null) {
    lines.push(pnlLine(trade.pnl_eur, trade.pnl_pct));
  } else {
    lines.push('💰 P&L : en cours de calcul');
  }
  if (trade.duration_ms) lines.push(`⏱️ Durée : ${formatDuration(trade.duration_ms)}`);
  lines.push(`⏰ ${formatTs(trade.closed_at || trade.timestamp || Date.now())}`);
  return lines.join('\n');
}

/**
 * Kill Switch déclenché sur une stratégie LIVE.
 */
export function msgLiveKillSwitch(stratName, reason, drawdown) {
  return [
    `🚨 *LIVE — Kill Switch stratégie*`,
    stratLine(stratName),
    `📉 Drawdown : ${formatPct(drawdown, true)}`,
    `❗ Raison : ${reason || 'seuil dépassé'}`,
    sep(),
    `_Stratégie suspendue automatiquement._`,
  ].join('\n');
}

/**
 * Kill Switch GLOBAL déclenché (toutes stratégies arrêtées).
 */
export function msgGlobalKillSwitch(status, totalLoss) {
  return [
    `🚨🚨 *POLY — KILL SWITCH GLOBAL*`,
    `📊 Statut : \`${status}\``,
    `💸 Pertes cumulées : ${formatMoney(totalLoss, true)}`,
    sep(),
    `_Toutes les stratégies sont stoppées._`,
    `_Intervention humaine requise._`,
  ].join('\n');
}

/**
 * Promotion PAPER → LIVE approuvée.
 */
export function msgPromotion(stratName, metrics) {
  const m = metrics || {};
  return [
    `🚀 *PROMOTION — Paper → Live*`,
    stratLine(stratName),
    `✅ Win Rate : ${formatPct(m.win_rate)}`,
    `✅ Sharpe   : ${m.sharpe != null ? m.sharpe.toFixed(2) : '—'}`,
    `✅ DD max   : ${formatPct(m.max_drawdown)}`,
    `✅ Trades   : ${m.trade_count ?? '—'}`,
    sep(),
    `_Capital live alloué : 1 000€_`,
  ].join('\n');
}

/**
 * Stratégie LIVE mise en pause.
 */
export function msgLiveStrategyPaused(stratName, reason) {
  return [
    `⏸️ *LIVE — Stratégie en pause*`,
    stratLine(stratName),
    `❗ Raison : ${reason || 'manuelle'}`,
  ].join('\n');
}

/**
 * Stratégie LIVE reprise.
 */
export function msgLiveStrategyResumed(stratName) {
  return [
    `▶️ *LIVE — Stratégie reprise*`,
    stratLine(stratName),
  ].join('\n');
}

/**
 * Avertissement drawdown LIVE (avant kill switch).
 */
export function msgLiveDrawdownWarning(stratName, drawdown, threshold) {
  return [
    `💰 *LIVE — Alerte drawdown*`,
    stratLine(stratName),
    `📉 Drawdown actuel : ${formatPct(drawdown, true)}`,
    `⚠️ Seuil kill switch : ${formatPct(threshold, true)}`,
    `_Surveillance renforcée._`,
  ].join('\n');
}

// ── PAPER alerts (priority 2) ────────────────────────────────────────────────

/**
 * Trade PAPER ouvert (sélectif — seulement si première ouverture d'une stratégie).
 */
export function msgPaperTradeOpened(trade) {
  return [
    `📘 *PAPER — Ordre ouvert*`,
    stratLine(trade.strategy_name || trade.strategy || '?'),
    tradeLine(trade),
    `⏰ ${formatTs(trade.opened_at || trade.timestamp || Date.now())}`,
  ].join('\n');
}

/**
 * Trade PAPER clôturé avec résultat.
 */
export function msgPaperTradeClosed(trade) {
  const won  = trade.outcome === trade.side;
  const icon = trade.pnl_eur == null ? '📋' : won ? '📗' : '📕';
  const lines = [
    `${icon} *PAPER — Trade résolu*`,
    stratLine(trade.strategy_name || trade.strategy || '?'),
    tradeLine(trade),
  ];
  if (trade.pnl_eur != null) {
    lines.push(pnlLine(trade.pnl_eur, trade.pnl_pct));
  }
  if (trade.duration_ms) lines.push(`⏱️ Durée : ${formatDuration(trade.duration_ms)}`);
  return lines.join('\n');
}

/**
 * Stratégie PAPER proche de l'éligibilité live.
 */
export function msgPaperNearEligibility(stratName, metrics) {
  const m = metrics || {};
  const lines = [`📊 *PAPER — Proche validation live*`, stratLine(stratName)];
  if (m.trade_count  != null) lines.push(`📈 Trades   : ${m.trade_count}/50`);
  if (m.win_rate     != null) lines.push(`🎯 Win Rate : ${formatPct(m.win_rate)} (seuil: 52.6%)`);
  if (m.sharpe       != null) lines.push(`📐 Sharpe   : ${m.sharpe.toFixed(2)} (seuil: 2.5)`);
  if (m.max_drawdown != null) lines.push(`📉 DD max   : ${formatPct(m.max_drawdown)} (seuil: 5%)`);
  lines.push(`_Candidat potentiel pour promotion._`);
  return lines.join('\n');
}

/**
 * Validation PAPER échouée (stratégie ne progresse pas).
 */
export function msgPaperValidationFailed(stratName, reason) {
  return [
    `⚠️ *PAPER — Validation échouée*`,
    stratLine(stratName),
    `❌ Raison : ${reason || 'critères non atteints'}`,
    `_Stratégie maintenue en observation._`,
  ].join('\n');
}

/**
 * Kill Switch PAPER déclenché.
 */
export function msgPaperKillSwitch(stratName, drawdown) {
  return [
    `🚨 *PAPER — Kill Switch*`,
    stratLine(stratName),
    `📉 Drawdown : ${formatPct(drawdown, true)}`,
    `_Capital paper protégé. Simulation stoppée._`,
  ].join('\n');
}

// ── Reports (priority 3) ─────────────────────────────────────────────────────

/**
 * Rapport quotidien 20h00 Paris.
 * @param {Object} data
 * @param {Object[]} data.paper      - [{name, pnl_eur, pnl_pct, trade_count, win_rate, status}]
 * @param {Object[]} data.live       - [{name, pnl_eur, pnl_pct, trade_count, win_rate, status}]
 * @param {Object}   data.global     - {total_pnl, risk_status, capital_at_risk}
 * @param {string}   isoDate         - "YYYY-MM-DD"
 */
export function msgDailyReport(data, isoDate) {
  const { paper = [], live = [], global: g = {} } = data;
  const dateLabel = formatParisDate(isoDate);

  const lines = [
    `🗓️ *Rapport quotidien — ${dateLabel}*`,
    sep(),
  ];

  // ── LIVE section ──
  if (live.length > 0) {
    lines.push(`\n🟢 *LIVE*`);
    for (const s of live) {
      const pnl = s.pnl_eur != null
        ? `${formatMoney(s.pnl_eur, true)} (${formatPct(s.pnl_pct, true)})`
        : 'en cours';
      const wr = s.win_rate != null ? ` · WR ${formatPct(s.win_rate)}` : '';
      lines.push(`• \`${s.name}\`: ${pnl} · ${s.trade_count ?? 0} trades${wr}`);
    }
  } else {
    lines.push(`\n🟢 *LIVE* : aucune stratégie active`);
  }

  // ── PAPER section ──
  if (paper.length > 0) {
    lines.push(`\n📘 *PAPER*`);
    for (const s of paper) {
      const pnl = s.pnl_eur != null
        ? `${formatMoney(s.pnl_eur, true)} (${formatPct(s.pnl_pct, true)})`
        : 'en cours';
      const wr = s.win_rate != null ? ` · WR ${formatPct(s.win_rate)}` : '';
      const flag = s.near_eligible ? ' ⭐' : '';
      lines.push(`• \`${s.name}\`: ${pnl} · ${s.trade_count ?? 0} trades${wr}${flag}`);
    }
    lines.push(`_⭐ = proche éligibilité live_`);
  } else {
    lines.push(`\n📘 *PAPER* : aucun trade aujourd'hui`);
  }

  // ── Global risk ──
  lines.push(`\n${sep()}`);
  const riskIcon = g.risk_status === 'NORMAL' ? '✅' : '🚨';
  lines.push(`${riskIcon} Risque global : \`${g.risk_status ?? 'NORMAL'}\``);
  if (g.total_pnl != null) lines.push(`💰 P&L global : ${formatMoney(g.total_pnl, true)}`);
  if (g.capital_at_risk != null) lines.push(`⚠️ Capital à risque : ${formatMoney(g.capital_at_risk)}`);

  return lines.join('\n');
}

/**
 * Rapport hebdomadaire — dimanche 20h00 Paris.
 * @param {Object} data
 * @param {Object[]} data.paper      - [{name, pnl_eur, pnl_pct, trade_count, win_rate, sharpe, max_drawdown, near_eligible}]
 * @param {Object[]} data.live       - [{name, pnl_eur, pnl_pct, trade_count, win_rate, sharpe, max_drawdown}]
 * @param {Object}   data.global     - {weekly_pnl, total_pnl, risk_status}
 * @param {Object[]} data.candidates - [{name, score}]  (prêts pour promotion)
 * @param {string}   weekLabel       - ex: "S10 2026"
 */
export function msgWeeklyReport(data, weekLabel) {
  const { paper = [], live = [], global: g = {}, candidates = [] } = data;

  const lines = [
    `📆 *Rapport hebdomadaire — ${weekLabel}*`,
    sep(),
  ];

  // ── LIVE ──
  if (live.length > 0) {
    lines.push(`\n🟢 *LIVE — Performance semaine*`);
    for (const s of live) {
      const pnl    = s.pnl_eur     != null ? formatMoney(s.pnl_eur, true)    : '—';
      const pct    = s.pnl_pct     != null ? formatPct(s.pnl_pct, true)      : '—';
      const wr     = s.win_rate    != null ? formatPct(s.win_rate)            : '—';
      const sharpe = s.sharpe      != null ? s.sharpe.toFixed(2)              : '—';
      const dd     = s.max_drawdown != null ? formatPct(s.max_drawdown)       : '—';
      lines.push(
        `• \`${s.name}\`\n` +
        `  P&L: ${pnl} (${pct}) · WR: ${wr} · Sharpe: ${sharpe} · DD: ${dd} · ${s.trade_count ?? 0}T`
      );
    }
  } else {
    lines.push(`\n🟢 *LIVE* : aucune stratégie active`);
  }

  // ── PAPER ──
  if (paper.length > 0) {
    lines.push(`\n📘 *PAPER — Bilan semaine*`);
    for (const s of paper) {
      const pnl    = s.pnl_eur      != null ? formatMoney(s.pnl_eur, true)  : 'en cours';
      const wr     = s.win_rate     != null ? formatPct(s.win_rate)          : '—';
      const sharpe = s.sharpe       != null ? s.sharpe.toFixed(2)            : '—';
      const dd     = s.max_drawdown != null ? formatPct(s.max_drawdown)      : '—';
      const flag   = s.near_eligible ? ' ⭐' : '';
      lines.push(
        `• \`${s.name}\`${flag}\n` +
        `  P&L: ${pnl} · WR: ${wr} · Sharpe: ${sharpe} · DD: ${dd} · ${s.trade_count ?? 0}T`
      );
    }
  } else {
    lines.push(`\n📘 *PAPER* : pas de données cette semaine`);
  }

  // ── Candidats promotion ──
  if (candidates.length > 0) {
    lines.push(`\n🚀 *Candidats promotion*`);
    for (const c of candidates) {
      const score = c.score != null ? ` (score: ${c.score.toFixed(0)}/100)` : '';
      lines.push(`• \`${c.name}\`${score}`);
    }
    lines.push(`_Passage par POLY_STRATEGY_PROMOTION_GATE requis._`);
  }

  // ── Global ──
  lines.push(`\n${sep()}`);
  const riskIcon = g.risk_status === 'NORMAL' ? '✅' : '🚨';
  lines.push(`${riskIcon} Risque global : \`${g.risk_status ?? 'NORMAL'}\``);
  if (g.weekly_pnl != null) lines.push(`${trendEmoji(g.weekly_pnl)} P&L semaine : ${formatMoney(g.weekly_pnl, true)}`);
  if (g.total_pnl  != null) lines.push(`💰 P&L cumulé : ${formatMoney(g.total_pnl, true)}`);

  return lines.join('\n');
}
