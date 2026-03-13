/**
 * POLY_TRADING_PUBLISHER — Handler
 * Publie sur Telegram les alertes Polymarket et les rapports périodiques.
 *
 * Sources de données (lecture directe — aucun ctx.bus POLY) :
 *   POLY_BASE/trading/paper_trades_log.jsonl
 *   POLY_BASE/trading/live_trades_log.jsonl
 *   POLY_BASE/accounts/ACC_POLY_*.json
 *   POLY_BASE/risk/kill_switch_status.json
 *   POLY_BASE/risk/global_risk_state.json
 *   POLY_BASE/evaluation/strategy_scores.json
 *   POLY_BASE/orchestrator/system_state.json
 *
 * State agent (ctx.state, persisté dans OpenClaw stateDir) :
 *   known_paper_ids  : Set<string> — trade IDs déjà connus (anti-flood)
 *   known_live_ids   : Set<string>
 *   sent_keys        : { [key]: timestamp } — déduplication
 *   prev_ks_levels   : { [strategy]: level } — suivi des changements kill switch
 *   prev_global      : string — dernier statut global risk
 */

import fs   from 'fs';
import path from 'path';

const POLY_BASE = process.env.POLY_BASE_PATH
  || '/home/openclawadmin/openclaw/workspace/POLY_FACTORY/state';

// ── Telegram ────────────────────────────────────────────────────────────────

async function sendTelegram(token, chatId, text) {
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: 'Markdown' }),
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Telegram HTTP ${res.status}: ${body}`);
    }
    return true;
  } catch (e) {
    console.error('[POLY_TRADING_PUBLISHER] Telegram error:', e.message);
    return false;
  }
}

// ── File helpers ─────────────────────────────────────────────────────────────

function readJSON(relPath, def = null) {
  try {
    return JSON.parse(fs.readFileSync(path.join(POLY_BASE, relPath), 'utf-8'));
  } catch {
    return def;
  }
}

function readJSONL(relPath) {
  try {
    const txt = fs.readFileSync(path.join(POLY_BASE, relPath), 'utf-8');
    return txt.trim().split('\n').filter(Boolean).map(l => JSON.parse(l));
  } catch {
    return [];
  }
}

/** Retourne heure Paris (0–23). */
function parisHour() {
  const s = new Date().toLocaleString('sv', { timeZone: 'Europe/Paris' });
  // s = "2026-03-13 20:05:03"
  return parseInt(s.split(' ')[1].split(':')[0], 10);
}

/** Retourne jour semaine Paris (0=dim, 6=sam). */
function parisDayOfWeek() {
  return new Date(new Date().toLocaleString('en-US', { timeZone: 'Europe/Paris' })).getDay();
}

/** Retourne "YYYY-MM-DD" Paris. */
function parisDate() {
  return new Date().toLocaleString('sv', { timeZone: 'Europe/Paris' }).slice(0, 10);
}

/** Label semaine "S10 2026". */
function weekLabel() {
  const now  = new Date();
  const start = new Date(now.getFullYear(), 0, 1);
  const week  = Math.ceil((((now - start) / 86400000) + start.getDay() + 1) / 7);
  return `S${week} ${now.getFullYear()}`;
}

// ── Account helpers ──────────────────────────────────────────────────────────

function loadAllAccounts() {
  const dir = path.join(POLY_BASE, 'accounts');
  try {
    const files = fs.readdirSync(dir).filter(f => f.endsWith('.json') && f !== 'archive');
    return files.map(f => {
      try { return JSON.parse(fs.readFileSync(path.join(dir, f), 'utf-8')); } catch { return null; }
    }).filter(Boolean);
  } catch {
    return [];
  }
}

function accountSummary(acc) {
  const cap  = acc.capital  || {};
  const dd   = acc.drawdown || {};
  const init = cap.initial || 1000;
  const curr = cap.current  ?? init;
  const pnl  = curr - init;
  const pct  = init > 0 ? (pnl / init) * 100 : 0;
  return {
    name:          acc.strategy || acc.account_id || '?',
    account_id:    acc.account_id,
    status:        acc.status || 'unknown',
    pnl_eur:       pnl,
    pnl_pct:       pct,
    max_drawdown:  dd.max_drawdown_pct,
    trade_count:   acc.performance?.total_trades ?? null,
    win_rate:      acc.performance?.win_rate     ?? null,
    sharpe:        acc.performance?.sharpe       ?? null,
    near_eligible: false,  // set below
  };
}

// Seuils d'éligibilité live (POLY_FACTORY_IMPLEMENTATION_PLAN section 9)
const ELIGIBLE_WIN_RATE   = 52.6;
const ELIGIBLE_SHARPE     = 2.5;
const ELIGIBLE_DD         = 5.0;
const ELIGIBLE_TRADES     = 50;
const NEAR_ELIGIBLE_RATIO = 0.8;  // 80% du seuil = "proche"

function markNearEligible(s) {
  const tc = s.trade_count ?? 0;
  if (tc < ELIGIBLE_TRADES * NEAR_ELIGIBLE_RATIO) return s;
  const wr = s.win_rate     != null && s.win_rate     >= ELIGIBLE_WIN_RATE   * NEAR_ELIGIBLE_RATIO;
  const sh = s.sharpe       != null && s.sharpe       >= ELIGIBLE_SHARPE     * NEAR_ELIGIBLE_RATIO;
  const dd = s.max_drawdown != null && Math.abs(s.max_drawdown) <= ELIGIBLE_DD / NEAR_ELIGIBLE_RATIO;
  s.near_eligible = wr && sh && dd;
  return s;
}

// ── Kill switch helpers ──────────────────────────────────────────────────────

const BLOCKED_LEVELS = new Set(['PAUSE_DAILY', 'PAUSE_SESSION', 'STOP_STRATEGY']);

function ksDrawdownPct(entry) {
  return entry?.drawdown_pct ?? null;
}

// ── Main handler ─────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const token  = process.env.POLY_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.POLY_TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    ctx.log('❌ POLY_TELEGRAM_BOT_TOKEN ou POLY_TELEGRAM_CHAT_ID manquant');
    return;
  }

  // ── Importer les messages ──────────────────────────────────────────────
  const {
    msgLiveTradeOpened, msgLiveTradeClosed,
    msgLiveKillSwitch, msgGlobalKillSwitch,
    msgPromotion,
    msgLiveStrategyPaused, msgLiveStrategyResumed,
    msgLiveDrawdownWarning,
    msgPaperTradeOpened, msgPaperTradeClosed,
    msgPaperNearEligibility, msgPaperValidationFailed, msgPaperKillSwitch,
    msgDailyReport, msgWeeklyReport,
  } = await import('./messages.js');

  // ── État persistant ────────────────────────────────────────────────────
  const state = ctx.state;
  const sentKeys    = state.sent_keys      || {};
  const prevKsLevels = state.prev_ks_levels || {};
  const prevGlobal  = state.prev_global    || 'NORMAL';

  // known IDs persistés dans l'état agent (Set sérialisé en Array)
  let knownPaperIds = new Set(state.known_paper_ids || []);
  let knownLiveIds  = new Set(state.known_live_ids  || []);
  const isFirstRun  = !state._initialized;

  let published = 0;

  async function send(key, msgFn, cooldownMs = 0) {
    if (key && sentKeys[key]) {
      if (cooldownMs > 0 && Date.now() - sentKeys[key] < cooldownMs) return false;
    }
    const text = typeof msgFn === 'function' ? msgFn() : msgFn;
    if (!text) return false;
    const ok = await sendTelegram(token, chatId, text);
    if (ok) {
      if (key) sentKeys[key] = Date.now();
      published++;
    }
    return ok;
  }

  // ── 1. LIVE trades ───────────────────────────────────────────────────────
  const liveTrades = readJSONL('trading/live_trades_log.jsonl');

  if (isFirstRun) {
    // Bootstrap: enregistrer tous les trades existants sans envoyer
    liveTrades.forEach(t => knownLiveIds.add(t.trade_id));
    ctx.log(`[bootstrap] ${liveTrades.length} live trades connus (pas d'alerte)`);
  } else {
    for (const trade of liveTrades) {
      if (knownLiveIds.has(trade.trade_id)) continue;
      knownLiveIds.add(trade.trade_id);

      if (trade.status === 'open' || !trade.status) {
        await send(`live_open_${trade.trade_id}`, () => msgLiveTradeOpened(trade));
        ctx.log(`📤 LIVE OPEN ${trade.strategy} ${trade.market_id}`);
      } else if (trade.status === 'closed' || trade.outcome) {
        await send(`live_close_${trade.trade_id}`, () => msgLiveTradeClosed(trade));
        ctx.log(`📤 LIVE CLOSE ${trade.strategy} pnl=${trade.pnl_eur}`);
      }
    }
  }

  // ── 2. PAPER trades ──────────────────────────────────────────────────────
  const paperTrades = readJSONL('trading/paper_trades_log.jsonl');

  if (isFirstRun) {
    paperTrades.forEach(t => knownPaperIds.add(t.trade_id));
    ctx.log(`[bootstrap] ${paperTrades.length} paper trades connus (pas d'alerte)`);
  } else {
    // Compte de trades ouverts par stratégie ce jour — n'envoyer le "first open"
    // que lors de la toute première ouverture (moins de bruit)
    const openedToday = {};
    for (const trade of paperTrades) {
      if (knownPaperIds.has(trade.trade_id)) {
        if (trade.strategy) openedToday[trade.strategy] = (openedToday[trade.strategy] || 0) + 1;
        continue;
      }
      knownPaperIds.add(trade.trade_id);

      const prevCount = openedToday[trade.strategy] || 0;
      openedToday[trade.strategy] = prevCount + 1;

      if (!trade.outcome) {
        // Nouveau trade ouvert — envoyer seulement le 1er de la journée par stratégie
        if (prevCount === 0) {
          const dayKey = `paper_open_${trade.strategy}_${parisDate()}`;
          if (!sentKeys[dayKey]) {
            await send(dayKey, () => msgPaperTradeOpened(trade));
            ctx.log(`📘 PAPER OPEN ${trade.strategy}`);
          }
        }
      } else {
        // Trade résolu
        await send(`paper_close_${trade.trade_id}`, () => msgPaperTradeClosed(trade));
        ctx.log(`📗 PAPER CLOSE ${trade.strategy} pnl=${trade.pnl_eur}`);
      }
    }
  }

  // ── 3. Kill switch par stratégie ─────────────────────────────────────────
  const ksStatus = readJSON('risk/kill_switch_status.json', {});
  for (const [strategy, entry] of Object.entries(ksStatus)) {
    const level    = entry.level || 'OK';
    const prevLevel = prevKsLevels[strategy] || 'OK';

    if (level === prevLevel) continue;  // pas de changement

    prevKsLevels[strategy] = level;

    if (level === 'STOP_STRATEGY') {
      const dd = ksDrawdownPct(entry);
      await send(`ks_stop_${strategy}_${entry.triggered_at}`,
        () => msgLiveKillSwitch(strategy, entry.reason || 'drawdown_total', dd));
      ctx.log(`🚨 KS STOP ${strategy}`);

    } else if (BLOCKED_LEVELS.has(level) && !BLOCKED_LEVELS.has(prevLevel)) {
      // Passage en pause
      await send(`ks_pause_${strategy}_${entry.triggered_at}`,
        () => msgLiveStrategyPaused(strategy, entry.reason));
      ctx.log(`⏸️ KS PAUSE ${strategy}`);

    } else if (level === 'OK' && BLOCKED_LEVELS.has(prevLevel)) {
      // Reprise
      await send(`ks_resume_${strategy}_${Date.now()}`,
        () => msgLiveStrategyResumed(strategy));
      ctx.log(`▶️ KS RESUME ${strategy}`);

    } else if (level === 'WARNING') {
      const dd        = ksDrawdownPct(entry);
      const threshold = entry.threshold_pct ?? -5;
      // Cooldown 4h pour les warnings
      await send(`ks_warn_${strategy}`, () => msgLiveDrawdownWarning(strategy, dd, threshold), 4 * 3600 * 1000);
      ctx.log(`💰 KS WARNING ${strategy}`);

    } else if (level === 'PAUSE_DAILY') {
      // Kill switch spécifique paper/live
      const dd = ksDrawdownPct(entry);
      const accs = loadAllAccounts();
      const acc  = accs.find(a => a.strategy === strategy);
      const isPaper = acc?.status?.includes('paper') || acc?.status === 'paper_testing';
      if (isPaper) {
        await send(`ks_paper_${strategy}_${entry.triggered_at}`,
          () => msgPaperKillSwitch(strategy, dd));
      } else {
        await send(`ks_pause_${strategy}_${entry.triggered_at}`,
          () => msgLiveKillSwitch(strategy, entry.reason || 'daily_drawdown', dd));
      }
      ctx.log(`🚨 KS PAUSE_DAILY ${strategy}`);
    }
  }

  // ── 4. Kill switch global ────────────────────────────────────────────────
  const globalRisk = readJSON('risk/global_risk_state.json', { status: 'NORMAL' });
  const globalStatus = globalRisk.status || 'NORMAL';

  if (globalStatus !== prevGlobal) {
    state.prev_global = globalStatus;

    if (globalStatus === 'ARRET_TOTAL') {
      const totalLoss = globalRisk.total_loss_eur ?? 0;
      await send(`global_ks_${globalStatus}`,
        () => msgGlobalKillSwitch(globalStatus, -Math.abs(totalLoss)));
      ctx.log(`🚨🚨 GLOBAL KS ARRET_TOTAL`);

    } else if (['CRITIQUE', 'ALERTE'].includes(globalStatus) &&
               ['NORMAL', 'ALERTE'].includes(prevGlobal)) {
      const totalLoss = globalRisk.total_loss_eur ?? 0;
      // Cooldown 6h pour les alertes non-critiques
      await send(`global_ks_${globalStatus}_${parisDate()}`,
        () => msgGlobalKillSwitch(globalStatus, -Math.abs(totalLoss)), 6 * 3600 * 1000);
      ctx.log(`⚠️ GLOBAL RISK ${globalStatus}`);
    }
  }

  // ── 5. Near eligibility — paper strategies ───────────────────────────────
  const scores = readJSON('evaluation/strategy_scores.json', {});
  const accounts = loadAllAccounts();

  for (const acc of accounts) {
    if (!acc.status?.includes('paper')) continue;
    const summary = markNearEligible(accountSummary(acc));
    if (!summary.near_eligible) continue;

    const score = scores[summary.name]?.score_total ?? null;
    const key   = `near_eligible_${summary.name}_${parisDate()}`;
    if (sentKeys[key]) continue;

    // Enrichir avec les scores d'évaluation
    const axes = scores[summary.name]?.axes || {};
    const metrics = {
      trade_count:  summary.trade_count,
      win_rate:     summary.win_rate,
      sharpe:       summary.sharpe,
      max_drawdown: summary.max_drawdown,
      score,
    };
    await send(key, () => msgPaperNearEligibility(summary.name, metrics));
    ctx.log(`📊 NEAR ELIGIBLE ${summary.name}`);
  }

  // ── 6. Promotions (statut → live) ────────────────────────────────────────
  for (const acc of accounts) {
    if (acc.status !== 'live') continue;
    const histEntry = (acc.status_history || []).findLast(h => h.status === 'live');
    if (!histEntry) continue;
    const promotedAt = histEntry.timestamp;
    const key = `promoted_${acc.account_id}_${promotedAt}`;
    if (sentKeys[key]) continue;

    const axes = scores[acc.strategy]?.axes || {};
    const metrics = {
      win_rate:     axes.win_rate?.value      ?? null,
      sharpe:       axes.sharpe?.value        ?? null,
      max_drawdown: axes.max_drawdown?.value  ?? null,
      trade_count:  axes.trade_count?.value   ?? null,
    };
    await send(key, () => msgPromotion(acc.strategy || acc.account_id, metrics));
    ctx.log(`🚀 PROMOTED ${acc.strategy}`);
  }

  // ── 7. Rapport quotidien — 20h Paris ────────────────────────────────────
  const hour       = parisHour();
  const today      = parisDate();
  const dailyKey   = `daily_report_${today}`;

  if (hour >= 20 && hour < 21 && !sentKeys[dailyKey]) {
    const paperAccs = accounts.filter(a => a.status?.includes('paper')).map(a => markNearEligible(accountSummary(a)));
    const liveAccs  = accounts.filter(a => a.status === 'live').map(a => accountSummary(a));

    const totalPnl = [...paperAccs, ...liveAccs].reduce((s, a) => s + (a.pnl_eur || 0), 0);
    const lossAccs = accounts.filter(a => (a.capital?.current ?? 1000) < (a.capital?.initial ?? 1000));
    const capAtRisk = lossAccs.reduce((s, a) => {
      const c = a.capital || {};
      return s + Math.abs((c.current ?? c.initial ?? 1000) - (c.initial ?? 1000));
    }, 0);

    const reportData = {
      paper: paperAccs,
      live:  liveAccs,
      global: {
        total_pnl:     totalPnl,
        risk_status:   globalStatus,
        capital_at_risk: capAtRisk > 0 ? capAtRisk : null,
      },
    };

    await send(dailyKey, () => msgDailyReport(reportData, today));
    ctx.log(`🗓️ Rapport quotidien envoyé (${today})`);
  }

  // ── 8. Rapport hebdomadaire — dimanche 20h Paris ─────────────────────────
  const dow      = parisDayOfWeek();
  const weekKey  = `weekly_report_${today}`;

  if (dow === 0 && hour >= 20 && hour < 21 && !sentKeys[weekKey]) {
    const paperAccs = accounts.filter(a => a.status?.includes('paper')).map(a => markNearEligible(accountSummary(a)));
    const liveAccs  = accounts.filter(a => a.status === 'live').map(a => accountSummary(a));

    // Candidats à la promotion (score ≥ 60)
    const candidates = [];
    for (const [stratName, entry] of Object.entries(scores)) {
      if ((entry.score_total ?? 0) >= 60) {
        candidates.push({ name: stratName, score: entry.score_total });
      }
    }

    const totalPnl = [...paperAccs, ...liveAccs].reduce((s, a) => s + (a.pnl_eur || 0), 0);

    const reportData = {
      paper:      paperAccs,
      live:       liveAccs,
      candidates,
      global: {
        weekly_pnl: null,  // non calculable sans snapshot hebdo
        total_pnl:  totalPnl,
        risk_status: globalStatus,
      },
    };

    await send(weekKey, () => msgWeeklyReport(reportData, weekLabel()));
    ctx.log(`📆 Rapport hebdomadaire envoyé`);
  }

  // ── Sauvegarde état ──────────────────────────────────────────────────────
  state.sent_keys       = sentKeys;
  state.prev_ks_levels  = prevKsLevels;
  state.prev_global     = globalStatus;
  state.known_paper_ids = [...knownPaperIds];
  state.known_live_ids  = [...knownLiveIds];
  state._initialized    = true;

  ctx.log(`✅ ${published} messages publiés`);
}
