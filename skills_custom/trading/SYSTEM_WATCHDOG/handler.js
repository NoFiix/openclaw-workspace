/**
 * SYSTEM_WATCHDOG v4 - Handler
 *
 * Couvre 3 systemes :
 * 1. Trading agents    (22) - state/trading/memory/*.state.json + schedules
 * 2. Content scripts   (3)  - hourly_scraper, scraper, cleanup -> via timestamps logs
 * 3. Content Factory   (5)  - agents/AGENT/memory/state.json -> activite < 24h
 *
 * - Lit la config depuis config.json (pas de magic numbers)
 * - Lit les intervals depuis *.schedule.json existants
 * - Format incidents standardise
 * - WARN / CRIT / RESOLVED avec deduplication
 * - Rapport quotidien 08h UTC
 * - Zero appel LLM
 */

import fs   from "fs";
import path from "path";
import { execSync } from "child_process";

// ─── Config ───────────────────────────────────────────────────────────────────
const __dir      = path.dirname(new URL(import.meta.url).pathname);
const CONFIG     = JSON.parse(fs.readFileSync(path.join(__dir, "config.json"), "utf-8"));
const T          = CONFIG.thresholds;

const TELEGRAM_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT  = process.env.TELEGRAM_CHAT_ID;

// ─── Descriptions de tous les agents / scripts ───────────────────────────────
const AGENT_INFO = {
  // ── Trading agents ──────────────────────────────────────────────────────────
  BINANCE_PRICE_FEED:    { desc: "Prix BTC/ETH en temps reel depuis Binance", to: "PREDICTOR, MARKET_EYE, TRADE_GENERATOR" },
  MARKET_EYE:            { desc: "Analyse bougies 1m/1h/4h, detecte tendances et structures de marche", to: "PREDICTOR, TRADE_GENERATOR" },
  NEWS_FEED:             { desc: "Scrape 6 flux RSS crypto + Fear&Greed + SEC EDGAR", to: "NEWS_SCORING" },
  NEWS_SCORING:          { desc: "Score les news avec Haiku (impact trading positif/negatif)", to: "TRADE_GENERATOR" },
  PREDICTOR:             { desc: "Genere des signaux de prediction court terme", to: "TRADE_GENERATOR" },
  REGIME_DETECTOR:       { desc: "Detecte le regime de marche (TREND_UP/DOWN/SIDEWAYS)", to: "TRADE_GENERATOR, POLICY_ENGINE" },
  WHALE_FEED:            { desc: "Surveille transactions whale >500k$ sur Ethereum via Etherscan V2", to: "WHALE_ANALYZER" },
  WHALE_ANALYZER:        { desc: "Analyse comportement des whales et leur direction probable", to: "TRADE_GENERATOR" },
  TRADE_GENERATOR:       { desc: "Genere des propositions de trades en combinant tous les signaux", to: "RISK_MANAGER" },
  RISK_MANAGER:          { desc: "Calcule taille de position et valide le risque de chaque trade", to: "POLICY_ENGINE" },
  POLICY_ENGINE:         { desc: "Applique les regles de trading (drawdown max, exposition, filtres)", to: "TRADING_ORCHESTRATOR" },
  TRADING_ORCHESTRATOR:  { desc: "Chef d'orchestre : reçoit les ordres approuves et les envoie a l'executeur", to: "TESTNET_EXECUTOR" },
  TESTNET_EXECUTOR:      { desc: "Execute les ordres sur le testnet et enregistre dans le ledger", to: "TRADING_PUBLISHER" },
  PAPER_EXECUTOR:        { desc: "Simule l'execution des trades en paper trading (sans argent reel)", to: "TRADING_PUBLISHER" },
  TRADING_PUBLISHER:     { desc: "Publie les trades et bilans (journalier 21h, hebdo dimanche 22h) sur Telegram", to: "Telegram @CryptoRizonTrader" },
  KILL_SWITCH_GUARDIAN:  { desc: "Surveille le drawdown global et coupe tout si seuil depasse", to: "POLICY_ENGINE, TRADING_ORCHESTRATOR" },
  PERFORMANCE_ANALYST:   { desc: "Analyse les performances des strategies sur les trades passes", to: "STRATEGY_GATEKEEPER, TRADE_STRATEGY_TUNER" },
  STRATEGY_GATEKEEPER:   { desc: "Valide ou invalide les strategies selon leurs performances reelles", to: "TRADE_GENERATOR" },
  STRATEGY_RESEARCHER:   { desc: "Recherche et propose de nouvelles strategies de trading (1×/jour)", to: "STRATEGY_GATEKEEPER" },
  TRADE_STRATEGY_TUNER:  { desc: "Optimise les parametres des strategies existantes (1×/semaine)", to: "TRADE_GENERATOR" },
  GLOBAL_TOKEN_ANALYST:  { desc: "Analyse fondamentale des tokens (skip actuel - agent_id mismatch)", to: "TRADE_GENERATOR" },
  GLOBAL_TOKEN_TRACKER:  { desc: "Suit les metriques on-chain des tokens (skip actuel - agent_id mismatch)", to: "TRADE_GENERATOR" },

  // ── Content scripts ─────────────────────────────────────────────────────────
  hourly_scraper:        { desc: "Scrape 6 flux RSS crypto, traduit en français et cree des drafts Telegram", to: "Publisher bot (Telegram @CryptoRizonBuilder)", schedule: "toutes les heures de 7h a 23h" },
  daily_scraper:         { desc: "Scrape quotidien approfondi pour le briefing du soir", to: "Publisher bot", schedule: "1×/jour a 19h15" },

  // ── Content Factory agents ───────────────────────────────────────────────────
  copywriter:            { desc: "Redige les posts Twitter/Telegram dans le style Ogilvy/Halbert/Stan Leloup", to: "publisher" },
  publisher:             { desc: "Publie les posts approuves sur Twitter + canal Telegram @CryptoRizon", to: "Twitter, Telegram" },
  builder:               { desc: "Orchestre la selection et la validation des articles a publier", to: "copywriter, publisher" },
  performance_analyst:   { desc: "Analyse les performances des posts publies (engagement, portee)", to: "strategy_tuner" },
  news_scoring:          { desc: "Score la pertinence des articles scrapes pour la communaute CryptoRizon", to: "builder" },

  // ── Agents systeme ───────────────────────────────────────────────────────────
  SYSTEM_WATCHDOG:       { desc: "Surveille la sante de tout le systeme OpenClaw toutes les 15min et alerte sur @OppenCllawBot", to: "Telegram @OppenCllawBot" },
  LEARNER:               { desc: "Analyse les trades perdus/gagnes, detecte les patterns, propose des ameliorations actionnables", to: "STRATEGY_RESEARCHER, TRADE_STRATEGY_TUNER" },
};

// ─── Utilitaires ──────────────────────────────────────────────────────────────
function readJSON(p, fallback = {}) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return fallback; }
}

function escapeHtml(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function sendTelegram(msg) {
  if (!TELEGRAM_TOKEN || !TELEGRAM_CHAT) {
    console.log("[WATCHDOG] Telegram non configure");
    return false;
  }
  try {
    const res = await fetch(`https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: TELEGRAM_CHAT, text: msg, parse_mode: "HTML" }),
    });
    const d = await res.json();
    if (!d.ok) { console.error("[WATCHDOG] Telegram:", d.description); return false; }
    return true;
  } catch (e) {
    console.error("[WATCHDOG] Telegram error:", e.message);
    return false;
  }
}

function getMB(bytes)        { return (bytes / 1024 / 1024).toFixed(1); }
function nowSec()            { return Math.floor(Date.now() / 1000); }
function nowMs()             { return Date.now(); }
function parisTime()         { return new Date().toLocaleString("fr-FR", { timeZone: "Europe/Paris" }); }

function formatDuration(sec) {
  if (sec < 120)   return `${sec}s`;
  if (sec < 3600)  return `${Math.floor(sec / 60)}min`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h`;
  return `${Math.floor(sec / 86400)}j`;
}

function getDirSizeBytes(dirPath) {
  try {
    const out = execSync(`du -sb "${dirPath}" 2>/dev/null`, { timeout: 10000 }).toString();
    return parseInt(out.split("\t")[0]) || 0;
  } catch { return 0; }
}

function getFileSizeBytes(filePath) {
  try { return fs.statSync(filePath).size; } catch { return 0; }
}

function getFileMtimeSec(filePath) {
  try { return Math.floor(fs.statSync(filePath).mtimeMs / 1000); } catch { return 0; }
}

function getDiskFreePercent() {
  try {
    const out  = execSync(`df / --output=pcent 2>/dev/null | tail -1`, { timeout: 5000 }).toString();
    const used = parseInt(out.replace("%", "").trim());
    return isNaN(used) ? 100 : 100 - used;
  } catch { return 100; }
}

function isProcessRunning(pattern) {
  try {
    const out = execSync(`ps aux | grep "${pattern}" | grep -v grep | wc -l`, { timeout: 5000 }).toString();
    return parseInt(out.trim()) > 0;
  } catch { return false; }
}

function countRecentErrors(logPath, lines = 300) {
  try {
    const out = execSync(`tail -${lines} "${logPath}" 2>/dev/null | grep "exit code=1" | wc -l`, { timeout: 5000 }).toString();
    return parseInt(out.trim()) || 0;
  } catch { return 0; }
}

function loadAgentSchedules(schedulesDir) {
  const defaults = {
    BINANCE_PRICE_FEED:   10,   MARKET_EYE:           15,
    NEWS_FEED:            300,  NEWS_SCORING:          300,
    PREDICTOR:            60,   REGIME_DETECTOR:       60,
    RISK_MANAGER:         60,   POLICY_ENGINE:         30,
    TRADING_ORCHESTRATOR: 10,   TESTNET_EXECUTOR:      30,
    PAPER_EXECUTOR:       30,   TRADE_GENERATOR:       300,
    WHALE_FEED:           300,  WHALE_ANALYZER:        300,
    KILL_SWITCH_GUARDIAN: 60,   TRADING_PUBLISHER:     60,
    PERFORMANCE_ANALYST:  3600, STRATEGY_GATEKEEPER:   3600,
    STRATEGY_RESEARCHER:  86400,TRADE_STRATEGY_TUNER:  604800,
    GLOBAL_TOKEN_ANALYST: 3600, GLOBAL_TOKEN_TRACKER:  3600,
  };
  const result = {};
  for (const [agentId, fallback] of Object.entries(defaults)) {
    if ((CONFIG.skip_agents ?? []).includes(agentId)) continue;
    const sf   = path.join(schedulesDir, `${agentId}.schedule.json`);
    const sched = readJSON(sf, null);
    result[agentId] = sched?.every_seconds ?? fallback;
  }
  return result;
}

// ─── Gestion incidents ────────────────────────────────────────────────────────
function shouldAlert(inc, severity) {
  if (!inc || inc.count === 0) return true;
  if (severity === "CRIT" && inc.severity === "WARN") return true;
  const elapsed = nowMs() - inc.last_alert_at;
  if (inc.count === 1 && elapsed >= T.reminder_cooldown_ms)        return true;
  if (inc.count >= 2 && elapsed >= T.reminder_second_cooldown_ms)  return true;
  return false;
}

function openIncident(incidents, key, severity, message) {
  if (!incidents[key]) {
    incidents[key] = { status: "open", severity, opened_at: nowSec(), last_seen_at: nowSec(), last_alert_at: 0, count: 0, message };
  } else {
    incidents[key].last_seen_at = nowSec();
    incidents[key].severity     = severity;
    incidents[key].message      = message;
  }
}

function buildAlertMsg(severity, message, detail, isNew, openedAt) {
  const icon  = severity === "CRIT" ? "🚨" : "⚠️";
  const label = isNew
    ? "NOUVELLE ALERTE"
    : `RAPPEL - actif depuis ${formatDuration(nowSec() - openedAt)}`;
  return `${icon} <b>${severity} - ${label}</b>\n\n` +
    `<b>${escapeHtml(message)}</b>\n${escapeHtml(detail)}\n\n` +
    `🕐 ${parisTime()}`;
}

// ─── Handler principal ────────────────────────────────────────────────────────
export async function handler(ctx) {
  const now   = nowSec();
  const state = ctx.state;

  if (!state.incidents)              state.incidents = {};
  if (!state.last_daily_summary_key) state.last_daily_summary_key = "";
  if (!state.metrics)                state.metrics = { last_health_score: 100, last_warn_count: 0, last_crit_count: 0 };
  if (!state.stats)                  state.stats = { runs: 0, errors: 0, alerts_sent: 0, resolved_sent: 0, daily_summaries_sent: 0, last_run_ts: 0 };

  const STATE_DIR      = ctx.stateDir ?? "/home/node/.openclaw/workspace/state/trading";
  const WORKSPACE_DIR  = ctx.workspaceDir ?? "/home/node/.openclaw/workspace";
  const AGENTS_DIR     = path.join(WORKSPACE_DIR, "agents");
  const schedulesDir   = path.join(STATE_DIR, "schedules");
  const agentSchedules = loadAgentSchedules(schedulesDir);

  ctx.log("🔍 Demarrage verification systeme...");

  const currentIssues = {};
  function addIssue(key, severity, message, detail = "") {
    currentIssues[key] = { severity, message, detail };
  }
  function agentDetail(id, extra = "") {
    const info = AGENT_INFO[id];
    if (!info) return extra;
    return `Rôle: ${info.desc}\nCommunique avec: ${info.to}${extra ? "\n" + extra : ""}`;
  }

  // ── 1. Pollers & container ────────────────────────────────────────────────
  const tradingOk   = isProcessRunning("trading/poller.js");
  const contentOk   = isProcessRunning("skills_custom/poller.js");
  const containerOk = isProcessRunning("openclaw-gateway");

  if (!tradingOk)   addIssue("trading_poller_down", "CRIT", "trading/poller.js ne tourne PAS",      "Tous les 22 agents trading sont a l'arret");
  if (!contentOk)   addIssue("content_poller_down", "CRIT", "content poller.js ne tourne PAS",       "Le pipeline de publication CryptoRizon est arrete");
  if (!containerOk) addIssue("container_down",       "CRIT", "Container openclaw-gateway semble KO", "Tous les services sont potentiellement hors ligne");

  // ── 2. Trading agents stales ──────────────────────────────────────────────
  for (const [agentId, intervalSec] of Object.entries(agentSchedules)) {
    const sf         = path.join(STATE_DIR, "memory", `${agentId}.state.json`);
    const agentState = readJSON(sf, null);
    const lastRun    = agentState?.stats?.last_run_ts ?? 0;

    if (!agentState || lastRun === 0) {
      addIssue(`agent_never_${agentId}`, "WARN",
        `${agentId} - jamais observe`,
        agentDetail(agentId, "Aucun run enregistre depuis le demarrage"));
      continue;
    }

    const elapsed   = now - lastRun;
    const warnLimit = intervalSec * T.agent_stale_factor_warn;
    const critLimit = intervalSec * T.agent_stale_factor_crit;

    if (elapsed > critLimit) {
      addIssue(`agent_crit_${agentId}`, "CRIT",
        `${agentId} - retard critique`,
        agentDetail(agentId, `Dernier run: il y a ${formatDuration(elapsed)} (devrait tourner toutes les ${formatDuration(intervalSec)})`));
    } else if (elapsed > warnLimit) {
      addIssue(`agent_warn_${agentId}`, "WARN",
        `${agentId} - en retard`,
        agentDetail(agentId, `Dernier run: il y a ${formatDuration(elapsed)} (devrait tourner toutes les ${formatDuration(intervalSec)})`));
    }
  }

  // ── 3. Content scripts (via timestamp des logs) ───────────────────────────
  const contentLogDir = path.join(WORKSPACE_DIR, "state");
  const contentScripts = [
    {
      key:       "hourly_scraper",
      logPath:   path.join(contentLogDir, "hourly_scraper.log"),
      maxAgeH:   2,     // alerte si pas tourne depuis 2h (tourne toutes les heures de 7h a 23h)
      onlyHours: [7, 23], // pas d'alerte la nuit
    },
    {
      key:       "daily_scraper",
      logPath:   path.join(contentLogDir, "daily_scraper.log"),
      maxAgeH:   26,    // alerte si pas tourne depuis 26h
      onlyHours: null,
    },
  ];

  const currentHourUTC = new Date().getUTCHours();
  for (const cs of contentScripts) {
    const mtime   = getFileMtimeSec(cs.logPath);
    const info    = AGENT_INFO[cs.key];
    if (mtime === 0) {
      addIssue(`content_script_missing_${cs.key}`, "WARN",
        `${cs.key} - aucun log trouve`,
        info ? `Rôle: ${info.desc}\nSchedule: ${info.schedule}` : "");
      continue;
    }
    const elapsedH = (now - mtime) / 3600;
    const inActiveWindow = !cs.onlyHours || (currentHourUTC >= cs.onlyHours[0] && currentHourUTC <= cs.onlyHours[1]);
    if (inActiveWindow && elapsedH > cs.maxAgeH) {
      addIssue(`content_script_stale_${cs.key}`, "WARN",
        `${cs.key} - pas tourne depuis ${formatDuration(now - mtime)}`,
        info ? `Rôle: ${info.desc}\nSchedule: ${info.schedule}` : "");
    }
  }

  // ── 4. Content Factory agents (activite < 24h) ────────────────────────────
  const contentFactoryAgents = ["performance_analyst", "news_scoring", "copywriter", "publisher", "builder"];
  for (const agentId of contentFactoryAgents) {
    const sf         = path.join(AGENTS_DIR, agentId, "memory", "state.json");
    const agentState = readJSON(sf, null);
    if (!agentState) continue; // pas de state = pas encore utilise, skip silencieux
    const lastRun = agentState?.last_run_ts ?? agentState?.updated_at ?? 0;
    if (lastRun === 0) continue;
    const elapsedH = (now - lastRun) / 3600;
    if (elapsedH > 48) {
      addIssue(`cf_agent_stale_${agentId}`, "WARN",
        `Content Factory - ${agentId} inactif depuis ${formatDuration(now - lastRun)}`,
        agentDetail(agentId));
    }
  }

  // ── 5. Taille fichiers ────────────────────────────────────────────────────
  const pollerLogPath  = path.join(STATE_DIR, "poller.log");
  const busDir         = path.join(STATE_DIR, "bus");
  const pollerLogBytes = getFileSizeBytes(pollerLogPath);
  const busDirBytes    = getDirSizeBytes(busDir);
  const stateDirBytes  = getDirSizeBytes(STATE_DIR);

  if (pollerLogBytes / 1024 / 1024 > T.poller_log_mb)
    addIssue("poller_log_size", "WARN", `poller.log: ${getMB(pollerLogBytes)}MB`, `Seuil: ${T.poller_log_mb}MB - rotation recommandee`);
  if (busDirBytes / 1024 / 1024 > T.bus_dir_mb)
    addIssue("bus_size", "WARN", `Bus trading: ${getMB(busDirBytes)}MB`, `Seuil: ${T.bus_dir_mb}MB - cleanup urgent (cron 3h UTC)`);
  if (stateDirBytes / 1024 / 1024 > T.state_dir_mb)
    addIssue("state_size", "WARN", `State total: ${getMB(stateDirBytes)}MB`, `Seuil: ${T.state_dir_mb}MB`);

  // ── 6. Disque ─────────────────────────────────────────────────────────────
  const diskFree = getDiskFreePercent();
  if (diskFree < T.disk_free_pct_crit)
    addIssue("disk_critical", "CRIT", `Disque critique: ${diskFree}% libre`, `Seuil: ${T.disk_free_pct_crit}% - action immediate requise`);
  else if (diskFree < T.disk_free_pct_warn)
    addIssue("disk_warn", "WARN", `Disque faible: ${diskFree}% libre`, `Seuil: ${T.disk_free_pct_warn}%`);

  // ── 7. Erreurs repetees ───────────────────────────────────────────────────
  const recentErrors = countRecentErrors(pollerLogPath, 300);
  if (recentErrors > T.poller_error_threshold)
    addIssue("poller_errors", "WARN", `Erreurs repetees: ${recentErrors}× "exit code=1"`, "Voir les 300 dernieres lignes de poller.log");

  // ── 8. Kill switch ────────────────────────────────────────────────────────
  const ksFile = path.join(STATE_DIR, "exec", "kill_switch.json");
  const ks     = readJSON(ksFile, { state: "ARMED" });
  if (ks.state === "TRIPPED") {
    const dur     = ks.tripped_at ? formatDuration(now - Math.floor(ks.tripped_at / 1000)) : "duree inconnue";
    const hasNote = ks.reason && ks.reason.length > 3;
    addIssue("kill_switch_tripped", "CRIT",
      `Kill switch TRIPPED depuis ${dur}`,
      `Aucun trade executable${hasNote ? ` | raison: "${ks.reason}"` : " | aucune note - ajouter une note dans kill_switch.json"}`);
  } else if (ks.state === "ARMED" && ks.armed_at) {
    const elapsed = now - Math.floor(ks.armed_at / 1000);
    if (elapsed > T.kill_switch_armed_warn_hours * 3600 && !(ks.note?.length > 3)) {
      addIssue("ks_armed_no_note", "WARN",
        `Kill switch arme depuis ${formatDuration(elapsed)} sans annotation`,
        "Ajouter une note dans kill_switch.json si c'est intentionnel");
    }
  }

  // ── 9. Activite trades ────────────────────────────────────────────────────
  let tradeCount48h = 0;
  try {
    const { events: trades } = ctx.bus.readSince("trading.exec.trade.ledger", 0, 1000);
    const cutoff = nowMs() - T.no_trade_warn_hours * 3600 * 1000;
    tradeCount48h = trades.filter(e => (e.payload?.closed_at ?? 0) > cutoff).length;
  } catch {}

  // ── 10. Deduplication + envoi ─────────────────────────────────────────────
  const activeKeys   = new Set(Object.keys(currentIssues));
  const toSend       = [];
  const resolvedMsgs = [];

  // Resolutions
  for (const [key, inc] of Object.entries(state.incidents)) {
    if (!activeKeys.has(key)) {
      resolvedMsgs.push(`✅ <b>RESOLVED</b> - ${escapeHtml(inc.message)} <i>(duree: ${formatDuration(now - inc.opened_at)})</i>`);
      state.stats.resolved_sent++;
      delete state.incidents[key];
    }
  }

  // Nouvelles alertes / rappels
  for (const [key, issue] of Object.entries(currentIssues)) {
    openIncident(state.incidents, key, issue.severity, issue.message);
    const inc   = state.incidents[key];
    const isNew = inc.count === 0;

    if (shouldAlert(isNew ? null : inc, issue.severity)) {
      toSend.push(buildAlertMsg(issue.severity, issue.message, issue.detail, isNew, inc.opened_at));
      inc.count++;
      inc.last_alert_at = nowMs();
      state.stats.alerts_sent++;
    }
  }

  for (const msg of resolvedMsgs) await sendTelegram(msg + `\n\n🕐 ${parisTime()}`);
  for (const msg of toSend)       await sendTelegram(msg);

  const critCount = Object.values(currentIssues).filter(i => i.severity === "CRIT").length;
  const warnCount = Object.values(currentIssues).filter(i => i.severity === "WARN").length;
  state.metrics.last_health_score = Math.max(0, 100 - critCount * 40 - warnCount * 10);
  state.metrics.last_warn_count   = warnCount;
  state.metrics.last_crit_count   = critCount;
  state.last_check_ts             = now;

  ctx.log(`✅ Check OK - CRIT:${critCount} WARN:${warnCount} RESOLVED:${resolvedMsgs.length} envoyes:${toSend.length} score:${state.metrics.last_health_score}`);

  // ── 11. Rapport quotidien 08h UTC ─────────────────────────────────────────
  const hour     = new Date().getUTCHours();
  const todayKey = new Date().toISOString().slice(0, 10);

  if (hour >= CONFIG.daily_summary_hour_utc &&
      hour < CONFIG.daily_summary_hour_utc + 1 &&
      state.last_daily_summary_key !== todayKey) {

    const statusIcon = critCount > 0 ? "🔴" : warnCount > 0 ? "🟡" : "🟢";
    const statusText = critCount > 0 ? "DÉGRADÉ" : warnCount > 0 ? "AVERTISSEMENTS" : "NOMINAL";

    const tradingLines = Object.entries(agentSchedules).map(([id, interval]) => {
      const sf      = path.join(STATE_DIR, "memory", `${id}.state.json`);
      const as      = readJSON(sf, null);
      const lastRun = as?.stats?.last_run_ts ?? 0;
      if (!as || lastRun === 0) return `• ${id}: jamais tourne`;
      const elapsed = now - lastRun;
      const ok      = elapsed < interval * T.agent_stale_factor_warn;
      return `• ${id}: ${ok ? "✅" : "⚠️"} (il y a ${formatDuration(elapsed)})`;
    }).join("\n");

    const incidentSummary = critCount > 0 || warnCount > 0
      ? `\n<b>Incidents actifs - ${critCount} CRIT, ${warnCount} WARN</b>\n` +
        Object.values(currentIssues).map(i => `• [${i.severity}] ${escapeHtml(i.message)}`).join("\n")
      : "\n✅ Aucun incident actif";

    const summary =
      `${statusIcon} <b>Rapport sante - ${todayKey}</b>\n` +
      `Statut: <b>${statusText}</b> | Score: ${state.metrics.last_health_score}/100\n\n` +
      `<b>⚙️ Process</b>\n` +
      `• Trading poller: ${tradingOk ? "✅" : "❌"}\n` +
      `• Content poller: ${contentOk ? "✅" : "❌"}\n` +
      `• Container: ${containerOk ? "✅" : "❌"}\n\n` +
      `<b>💾 Stockage</b>\n` +
      `• poller.log: ${getMB(pollerLogBytes)}MB\n` +
      `• Bus trading: ${getMB(busDirBytes)}MB\n` +
      `• State total: ${getMB(stateDirBytes)}MB\n` +
      `• Disque libre: ${diskFree}%\n\n` +
      `<b>🤖 Agents trading (${Object.keys(agentSchedules).length})</b>\n` +
      tradingLines + "\n\n" +
      `<b>📊 Trading</b>\n` +
      `• Trades ${T.no_trade_warn_hours}h: ${tradeCount48h}${tradeCount48h === 0 ? " (normal si marche calme ou policy restrictive)" : ""}\n` +
      `• Kill switch: ${ks.state}` +
      incidentSummary +
      `\n\n🕐 ${parisTime()}`;

    await sendTelegram(summary);
    state.last_daily_summary_key = todayKey;
    state.stats.daily_summaries_sent++;
    ctx.log("📊 Rapport quotidien envoye");
  }
}
