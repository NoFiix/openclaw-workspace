/**
 * TRADE_STRATEGY_TUNER — Handler v3
 *
 * Règles fondamentales :
 *   1. Aucune modification avant 30 trades réels
 *   2. Un seul changement de paramètre par itération
 *   3. Amplitude de changement bornée (relative au paramètre actuel)
 *   4. Rollback automatique vers best_version si sous-performance (10+ nouveaux trades)
 *   5. Jamais toucher aux paramètres de sécurité / risk
 *   6. Comparer par régime dominant, pas seulement globalement
 *   7. Rejeter seulement après 3 itérations significatives (≥10 nouveaux trades chacune)
 *   8. Anti-oscillation : ne pas retester un (param, valeur) des 3 dernières versions
 *   9. Plafond 0.70 : arrêt du tuning si score déjà > 0.70
 *
 * KPI principal  : % stratégies optimizing → active
 * KPI secondaire : uplift moyen expectancy
 * LLM : Sonnet (~2000 tokens/run, 1x/semaine)
 */

import fs   from "fs";
import path from "path";

// ─── Constantes ───────────────────────────────────────────────────────────────

const MIN_TRADES_FIRST_RUN  = 30;
const MIN_NEW_TRADES_ITER   = 10;
const MAX_SIGNIFICANT_ITERS = 3;
const SCORE_TARGET          = 0.60;
const SCORE_FLOOR           = 0.40;
const SCORE_TUNING_CEILING  = 0.70;  // Règle 9 : arrêt si déjà performant
const ROLLBACK_MIN_TRADES   = 10;
const ANTI_OSCILLATION_WINDOW = 3;   // Règle 8 : fenêtre de mémoire

const PARAM_MAX_DELTA = {
  rsi_low:   3,
  rsi_high:  3,
  bb_low:    0.03,
  bb_high:   0.03,
  macd_min:  0.0003,
};

const PARAM_BOUNDS = {
  rsi_low:   { min: 20,     max: 40   },
  rsi_high:  { min: 60,     max: 80   },
  bb_low:    { min: 0.05,   max: 0.25 },
  bb_high:   { min: 0.75,   max: 0.95 },
  macd_min:  { min: 0.0001, max: 0.002 },
};

const PARAM_BLACKLIST = new Set([
  "max_position_size", "leverage", "kill_switch_threshold",
  "risk_pct", "max_concurrent_positions", "stop_loss_pct",
  "max_drawdown_limit", "position_size_usd",
]);

const DEFAULT_PARAMS = {
  MeanReversion: { rsi_low: 35, rsi_high: 65, bb_low: 0.15, bb_high: 0.85 },
  Momentum:      { rsi_low: 35, rsi_high: 65, macd_min: 0.0005 },
  Breakout:      { bb_low: 0.02, bb_high: 0.98 },
};

const BUILTINS = ["MeanReversion", "Momentum", "Breakout", "NewsTrading"];

// ─── Helpers fichiers ─────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

function appendJSONL(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.appendFileSync(p, JSON.stringify(obj) + "\n");
}

// ─── Telegram ─────────────────────────────────────────────────────────────────

async function sendTelegram(token, chatId, text) {
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch (e) {
    console.error("[TRADE_STRATEGY_TUNER] Telegram error:", e.message);
  }
}

// ─── Score composite (identique à STRATEGY_GATEKEEPER) ───────────────────────

function scoreStrategy(perf) {
  const expNorm     = Math.min(Math.max((perf.expectancy_usd ?? 0) / 100, -1), 1);
  const expScore    = (expNorm + 1) / 2;
  const pfScore     = Math.min((perf.profit_factor ?? 0) / 2, 1);
  const ddScore     = Math.max(1 - (perf.max_drawdown_pct ?? 0) / 25, 0);
  const sharpeNorm  = Math.min(Math.max((perf.sharpe_ratio ?? 0) / 2, -1), 1);
  const sharpeScore = (sharpeNorm + 1) / 2;
  const countScore  = Math.min((perf.trades_count ?? 0) / 50, 1);
  return parseFloat((
    expScore    * 0.35 +
    pfScore     * 0.30 +
    ddScore     * 0.20 +
    sharpeScore * 0.10 +
    countScore  * 0.05
  ).toFixed(3));
}

// ─── Règle 8 : Anti-oscillation ───────────────────────────────────────────────

function isOscillating(key, proposedValue, versions) {
  const recentVersions = (versions?.versions ?? []).slice(-ANTI_OSCILLATION_WINDOW);
  return recentVersions.some(v =>
    v.param_changed === key &&
    v.change?.to === proposedValue
  );
}

// ─── Validation ajustements (Règles 2, 3, 5, 8) ──────────────────────────────

function validateAndClampAdjustment(key, proposedValue, currentValue, versions) {
  if (PARAM_BLACKLIST.has(key))    return null;
  if (!PARAM_BOUNDS[key])          return null;

  // Règle 8 : anti-oscillation
  if (isOscillating(key, proposedValue, versions)) return null;

  const maxDelta     = PARAM_MAX_DELTA[key];
  const bounds       = PARAM_BOUNDS[key];
  const delta        = proposedValue - currentValue;
  const clampedDelta = Math.max(-maxDelta, Math.min(maxDelta, delta));
  let   validated    = currentValue + clampedDelta;

  validated = Math.min(Math.max(validated, bounds.min), bounds.max);
  validated = key.startsWith("rsi")
    ? Math.round(validated)
    : parseFloat(validated.toFixed(4));

  if (validated === currentValue) return null;

  // Règle 8 : vérifier aussi la valeur clampée finale
  if (isOscillating(key, validated, versions)) return null;

  return { key, from: currentValue, to: validated, delta: parseFloat((validated - currentValue).toFixed(4)) };
}

// Règle 2 : un seul ajustement
function applySingleAdjustment(rawAdj, currentParams, versions) {
  for (const [key, proposedValue] of Object.entries(rawAdj)) {
    const currentValue = currentParams[key];
    if (currentValue === undefined) continue;
    const validated = validateAndClampAdjustment(key, proposedValue, currentValue, versions);
    if (validated !== null) return validated;
  }
  return null;
}

// ─── Eligibilité (Règles 1, 7, 9) ────────────────────────────────────────────

function getEligibility(perf, versions) {
  const trades = perf.trades_count ?? 0;
  const score  = scoreStrategy(perf);

  // Règle 1
  if (trades < MIN_TRADES_FIRST_RUN)
    return { eligible: false, reason: `${trades}/${MIN_TRADES_FIRST_RUN} trades min requis` };

  // Règle 9 : plafond de tuning
  if (score > SCORE_TUNING_CEILING)
    return { eligible: false, reason: `Score ${score} > ${SCORE_TUNING_CEILING} — stratégie saine, tuning arrêté` };

  // Déjà dans la zone cible mais pas au plafond → continue légèrement
  if (score > SCORE_TARGET && score <= SCORE_TUNING_CEILING)
    return { eligible: false, reason: `Score ${score} entre ${SCORE_TARGET} et ${SCORE_TUNING_CEILING} — laisser STRATEGY_GATEKEEPER décider` };

  // Itérations significatives
  const significantIters = (versions?.versions ?? []).filter(v =>
    (v.trades_since_last_version ?? MIN_NEW_TRADES_ITER) >= MIN_NEW_TRADES_ITER
  ).length;

  if (significantIters >= MAX_SIGNIFICANT_ITERS)
    return { eligible: false, rejected: true, reason: `${MAX_SIGNIFICANT_ITERS} itérations significatives sans amélioration` };

  // Nouveaux trades depuis dernière version
  const lastVersion = versions?.versions?.slice(-1)[0];
  if (lastVersion) {
    const newTrades = trades - (lastVersion.trades ?? 0);
    if (newTrades < MIN_NEW_TRADES_ITER)
      return { eligible: false, reason: `${newTrades} nouveaux trades depuis v${lastVersion.v} (min ${MIN_NEW_TRADES_ITER})` };
  }

  return { eligible: true, score, trades, significantIters };
}

// ─── Rollback (Règle 4) ───────────────────────────────────────────────────────

function checkRollback(versions, perf) {
  if (!versions?.versions?.length) return null;

  const currentV = versions.versions.find(v => v.v === versions.current_version);
  const bestV    = versions.versions.find(v => v.v === versions.best_version);

  if (!currentV || !bestV || currentV.v === bestV.v) return null;

  const currentScore       = scoreStrategy(perf);
  const tradesSinceCurrent = (perf.trades_count ?? 0) - (currentV.trades ?? 0);

  if (tradesSinceCurrent >= ROLLBACK_MIN_TRADES && currentScore < (bestV.score ?? 0)) {
    return {
      shouldRollback: true,
      from:   versions.current_version,
      to:     versions.best_version,
      reason: `Score actuel ${currentScore} < v${bestV.v} (${bestV.score}) sur ${tradesSinceCurrent} trades`,
    };
  }
  return { shouldRollback: false };
}

// ─── Régime ───────────────────────────────────────────────────────────────────

function getDominantRegime(trades) {
  const counts = {};
  for (const t of trades) {
    const r = t.regime ?? "UNKNOWN";
    counts[r] = (counts[r] ?? 0) + 1;
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "UNKNOWN";
}

function getRegimeStats(trades) {
  const byRegime = {};
  for (const t of trades) {
    const r = t.regime ?? "UNKNOWN";
    if (!byRegime[r]) byRegime[r] = { wins: 0, losses: 0, pnl: 0 };
    if ((t.pnl_usd ?? 0) > 0) byRegime[r].wins++;
    else byRegime[r].losses++;
    byRegime[r].pnl += t.pnl_usd ?? 0;
  }
  return byRegime;
}

// ─── Sonnet ───────────────────────────────────────────────────────────────────

async function callSonnet(apiKey, prompt) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method:  "POST",
    headers: {
      "Content-Type":      "application/json",
      "x-api-key":         apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model:      "claude-sonnet-4-20250514",
      max_tokens: 1024,
      messages:   [{ role: "user", content: prompt }],
      system: `Tu es un expert en optimisation prudente de stratégies de trading algorithmique.

Ton rôle : identifier si une stratégie légèrement déficiente peut être améliorée
par un ajustement paramétrique simple, mesurable et robuste.

Tu ne cherches PAS à "faire gagner" une stratégie coûte que coûte.
Tu cherches à savoir si un paramètre est structurellement mal calibré.

Règles strictes :
- Tu proposes UN SEUL ajustement
- L'ajustement doit être petit (RSI ±3 max, BB ±0.03 max)
- Si tu ne vois pas de signal clair, dis-le explicitement
- Tu ne touches jamais : max_position_size, leverage, risk_pct, kill_switch

Tu réponds UNIQUEMENT en JSON valide, sans markdown.
Format :
{
  "hypothesis": "Hypothèse précise sur pourquoi ce paramètre est mal calibré",
  "adjustments": { "param_name": nouvelle_valeur },
  "expected_effect": "Effet attendu en termes de trades filtrés ou améliorés",
  "confidence": "low|medium|high",
  "no_change_reason": null
}

Si tu ne vois pas d'ajustement justifié :
{
  "hypothesis": null,
  "adjustments": {},
  "expected_effect": null,
  "confidence": "low",
  "no_change_reason": "Explication pourquoi aucun ajustement n'est justifié"
}`,
    }),
  });

  if (!res.ok) throw new Error(`Anthropic API ${res.status}: ${await res.text()}`);
  const data = await res.json();
  const text = data.content?.[0]?.text ?? "";
  try {
    return JSON.parse(text);
  } catch {
    const match = text.match(/\{[\s\S]*\}/);
    if (match) return JSON.parse(match[0]);
    throw new Error(`Réponse non parseable : ${text.slice(0, 200)}`);
  }
}

// ─── Prompt ───────────────────────────────────────────────────────────────────

function buildPrompt(stratName, perf, currentParams, stratTrades, versions) {
  const losingTrades      = stratTrades.filter(t => (t.pnl_usd ?? 0) < 0 || t.exit_reason === "STOP_LOSS");
  const regimeStats       = getRegimeStats(stratTrades);
  const dominantRegime    = getDominantRegime(stratTrades);
  const significantIters  = (versions?.versions ?? []).filter(v =>
    (v.trades_since_last_version ?? MIN_NEW_TRADES_ITER) >= MIN_NEW_TRADES_ITER
  ).length;

  // Règle 8 : indiquer à Sonnet les combinaisons déjà testées à éviter
  const recentTested = (versions?.versions ?? []).slice(-ANTI_OSCILLATION_WINDOW).map(v =>
    `${v.param_changed} = ${v.change?.to}`
  );

  return `Stratégie : ${stratName}
Itération : ${significantIters + 1}/${MAX_SIGNIFICANT_ITERS}
Régime dominant : ${dominantRegime}

=== PERFORMANCE GLOBALE ===
Trades : ${perf.trades_count} | Win rate : ${perf.win_rate}%
PnL : $${perf.pnl_usd} | Expectancy : $${perf.expectancy_usd}
Profit Factor : ${perf.profit_factor} | Sharpe : ${perf.sharpe_ratio}
Max Drawdown : ${perf.max_drawdown_pct}%
Score : ${scoreStrategy(perf)} (cible > ${SCORE_TARGET})

=== PERFORMANCE PAR RÉGIME ===
${JSON.stringify(regimeStats, null, 2)}

=== PARAMÈTRES ACTUELS ===
${JSON.stringify(currentParams, null, 2)}

=== HISTORIQUE VERSIONS ===
${JSON.stringify((versions?.versions ?? []).map(v => ({
  v: v.v, param_changed: v.param_changed, change: v.change,
  score: v.score, hypothesis: v.hypothesis, trades_since_last: v.trades_since_last_version,
})), null, 2)}

=== COMBINAISONS DÉJÀ TESTÉES — NE PAS REPRODUIRE ===
${recentTested.length ? recentTested.join("\n") : "aucune"}

=== ${losingTrades.length} TRADES PERDANTS ===
${JSON.stringify(losingTrades.slice(0, 15).map(t => ({
  symbol: t.symbol, side: t.side, pnl_usd: t.pnl_usd,
  exit_reason: t.exit_reason, regime: t.regime, hold_ms: t.hold_ms,
})), null, 2)}

=== AMPLITUDES MAX (delta relatif) ===
RSI ± 3 | BB ± 0.03 | MACD ± 0.0003

Analyse les trades perdants par régime dominant (${dominantRegime}).
Propose un seul ajustement non déjà testé. Si signal pas clair, dis-le.`;
}

// ─── Handler principal ────────────────────────────────────────────────────────

export async function handler(ctx) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;

  if (!apiKey) {
    ctx.log("[TRADE_STRATEGY_TUNER] ANTHROPIC_API_KEY manquant — abort");
    return;
  }

  const learnDir     = path.join(ctx.stateDir, "learning");
  const busDir       = path.join(ctx.stateDir, "bus");
  const perfFile     = path.join(learnDir, "strategy_performance.json");
  const candFile     = path.join(learnDir, "strategy_candidates.json");
  const versionsFile = path.join(learnDir, "strategy_versions.json");
  const rejectedFile = path.join(learnDir, "strategy_rejected.json");
  const auditFile    = path.join(learnDir, "tuner_audit.jsonl");
  const ledgerFile   = path.join(busDir,   "trading_exec_trade_ledger.jsonl");

  const perf     = readJSON(perfFile, {});
  let candidates = readJSON(candFile, []);
  let versions   = readJSON(versionsFile, {});
  let rejected   = readJSON(rejectedFile, []);

  // Trades réels uniquement (TESTNET_EXECUTOR)
  let allTrades = [];
  if (fs.existsSync(ledgerFile)) {
    try {
      allTrades = fs.readFileSync(ledgerFile, "utf-8")
        .split("\n").filter(Boolean)
        .map(l => JSON.parse(l))
        .filter(e => e.producer?.agent_id === "TESTNET_EXECUTOR")
        .map(e => e.trace?.causation_id ?? e.payload)
        .filter(t => t && t.status === "closed");
    } catch (e) {
      ctx.log(`[TRADE_STRATEGY_TUNER] Erreur ledger : ${e.message}`);
    }
  }

  const allStratNames = [...new Set([...BUILTINS, ...candidates.map(c => c.name)])];
  ctx.log(`[TRADE_STRATEGY_TUNER] ${allStratNames.length} stratégies, ${allTrades.length} trades réels`);

  let optimized = 0, promoted = 0, rejectedCount = 0, rolledBack = 0;
  const expectancyUplift = [];

  for (const stratName of allStratNames) {
    const p = perf[stratName];
    if (!p) { ctx.log(`  ⏭  ${stratName} — pas de données`); continue; }

    const v           = versions[stratName];
    const stratTrades = allTrades.filter(t => t.strategy === stratName);
    const currentScore = scoreStrategy(p);

    // Rollback (Règle 4)
    const rollback = checkRollback(v, p);
    if (rollback?.shouldRollback) {
      ctx.log(`  🔄 ${stratName} — ROLLBACK v${rollback.from} → v${rollback.to} (${rollback.reason})`);
      const bestVEntry = v.versions.find(ver => ver.v === v.best_version);
      versions[stratName].current_version = v.best_version;
      const candIdx = candidates.findIndex(c => c.name === stratName);
      if (candIdx !== -1) { candidates[candIdx].params = bestVEntry.params; candidates[candIdx].last_tuned = new Date().toISOString(); }
      writeJSON(versionsFile, versions); writeJSON(candFile, candidates);
      appendJSONL(auditFile, { ts: new Date().toISOString(), strategy: stratName, action: "rollback", from_version: rollback.from, to_version: rollback.to, reason: rollback.reason, score: currentScore });
      rolledBack++;
      if (token && chatId) await sendTelegram(token, chatId, `🤖 *TRADE_STRATEGY_TUNER*\n\n🔄 *${stratName}* — Rollback v${rollback.from} → v${rollback.to}\n${rollback.reason}\n\n⚠️ TESTNET`);
      continue;
    }

    // Eligibilité (Règles 1, 7, 9)
    const { eligible, rejected: shouldReject, reason, score, trades, significantIters } = getEligibility(p, v);

    if (!eligible) {
      ctx.log(`  ⏭  ${stratName} — skip (${reason})`);
      if (shouldReject) {
        ctx.log(`  ❌ ${stratName} — rejeté`);
        const v1Score = v?.versions?.[0]?.score ?? null;
        if (v1Score !== null) expectancyUplift.push(currentScore - v1Score);
        rejected.push({ name: stratName, rejected_at: new Date().toISOString(), reason, final_score: currentScore, trades: p.trades_count, versions: v?.versions ?? [] });
        const candIdx = candidates.findIndex(c => c.name === stratName);
        if (candIdx !== -1) { candidates[candIdx].status = "rejected"; candidates[candIdx].rejection_reason = reason; }
        rejectedCount++;
        writeJSON(rejectedFile, rejected); writeJSON(candFile, candidates);
        if (token && chatId) await sendTelegram(token, chatId, `🤖 *TRADE_STRATEGY_TUNER*\n\n❌ *${stratName}* — Rejetée\n${reason}\nScore final : ${currentScore}\nTrades : ${p.trades_count}\n\n→ STRATEGY_GATEKEEPER décidera.`);
      }
      continue;
    }

    ctx.log(`  🔧 ${stratName} — optimizing (score=${score}, trades=${trades}, iter=${(significantIters ?? 0) + 1}/${MAX_SIGNIFICANT_ITERS})`);
    optimized++;

    const currentVersionEntry = v?.versions?.find(ver => ver.v === v?.current_version);
    const currentParams       = currentVersionEntry?.params ?? DEFAULT_PARAMS[stratName] ?? {};

    // Appel Sonnet
    let sonnetResult;
    try {
      ctx.log(`    → Sonnet (${stratTrades.length} trades, ${stratTrades.filter(t => t.pnl_usd < 0).length} perdants)`);
      sonnetResult = await callSonnet(apiKey, buildPrompt(stratName, p, currentParams, stratTrades, v));
    } catch (e) {
      ctx.log(`    ✗ Erreur Sonnet : ${e.message}`); continue;
    }

    if (sonnetResult.no_change_reason) {
      ctx.log(`    ℹ️  Pas d'ajustement : ${sonnetResult.no_change_reason}`);
      appendJSONL(auditFile, { ts: new Date().toISOString(), strategy: stratName, action: "no_change", reason: sonnetResult.no_change_reason, score, trades });
      continue;
    }

    // Règles 2, 3, 5, 8
    const adjustment = applySingleAdjustment(sonnetResult.adjustments ?? {}, currentParams, v);
    if (!adjustment) {
      ctx.log(`    ⚠  Aucun ajustement valide (oscillation détectée ou hors bornes)`);
      appendJSONL(auditFile, { ts: new Date().toISOString(), strategy: stratName, action: "blocked", reason: "oscillation ou hors bornes", proposed: sonnetResult.adjustments, score });
      continue;
    }

    // Nouvelle version
    const prevVersions       = v?.versions ?? [];
    const newVersionNumber   = (v?.current_version ?? 0) + 1;
    const newParams          = { ...currentParams, [adjustment.key]: adjustment.to };
    const tradesSinceLastVer = trades - (currentVersionEntry?.trades ?? 0);
    const bestVersionEntry   = prevVersions.reduce((best, ver) => (ver.score ?? 0) > (best.score ?? 0) ? ver : best, prevVersions[0] ?? { v: 1, score: 0 });

    versions[stratName] = {
      current_version: newVersionNumber,
      best_version:    bestVersionEntry.v,
      versions: [...prevVersions, {
        v: newVersionNumber, params: newParams, trades, trades_since_last_version: tradesSinceLastVer,
        score, hypothesis: sonnetResult.hypothesis, param_changed: adjustment.key,
        change: { from: adjustment.from, to: adjustment.to }, expected_effect: sonnetResult.expected_effect,
        confidence: sonnetResult.confidence ?? "medium", regime_dominant: getDominantRegime(stratTrades),
        applied_at: new Date().toISOString().split("T")[0],
      }],
    };
    writeJSON(versionsFile, versions);

    const candIdx = candidates.findIndex(c => c.name === stratName);
    const newStatus = score >= SCORE_TARGET ? "active" : "optimizing";
    if (candIdx !== -1) {
      candidates[candIdx].params = newParams; candidates[candIdx].status = newStatus;
      candidates[candIdx].last_tuned = new Date().toISOString(); candidates[candIdx].current_version = newVersionNumber;
    } else if (BUILTINS.includes(stratName)) {
      candidates.push({ name: stratName, description: `Builtin optimisée par TRADE_STRATEGY_TUNER`, params: newParams, status: newStatus, last_tuned: new Date().toISOString(), current_version: newVersionNumber, source: "builtin", discovered_at: new Date().toISOString(), test_trades: p.trades_count, pnl_usd: p.pnl_usd, win_rate: p.win_rate, profit_factor: p.profit_factor });
    }
    writeJSON(candFile, candidates);

    appendJSONL(auditFile, { ts: new Date().toISOString(), strategy: stratName, action: "optimized", version: newVersionNumber, param_changed: adjustment.key, change: { from: adjustment.from, to: adjustment.to }, score_before: score, trades, trades_since_last: tradesSinceLastVer, hypothesis: sonnetResult.hypothesis, expected_effect: sonnetResult.expected_effect, confidence: sonnetResult.confidence, regime_dominant: getDominantRegime(stratTrades) });

    ctx.log(`    ✅ v${newVersionNumber} : ${adjustment.key} ${adjustment.from} → ${adjustment.to}`);
    ctx.log(`    💡 ${sonnetResult.hypothesis}`);

    if (score >= SCORE_TARGET) {
      promoted++;
      const v1Score = v?.versions?.[0]?.score ?? score;
      expectancyUplift.push(score - v1Score);
      if (token && chatId) await sendTelegram(token, chatId, `🤖 *TRADE_STRATEGY_TUNER*\n\n✅ *${stratName}* — PROMUE ACTIVE\n\nScore : ${score} ≥ ${SCORE_TARGET}\nVersion : v${newVersionNumber} | Trades : ${p.trades_count}\nAjustement : \`${adjustment.key}\` ${adjustment.from} → ${adjustment.to}\nHypothèse : ${sonnetResult.hypothesis}\n\n→ STRATEGY_GATEKEEPER validera.`);
    } else {
      if (token && chatId) await sendTelegram(token, chatId, `🤖 *TRADE_STRATEGY_TUNER*\n\n🔧 *${stratName}* — v${newVersionNumber}\n\nScore : ${score} | Iter : ${(significantIters ?? 0) + 1}/${MAX_SIGNIFICANT_ITERS}\nAjustement : \`${adjustment.key}\` ${adjustment.from} → ${adjustment.to}\nConfiance : ${sonnetResult.confidence ?? "?"}\nHypothèse : ${sonnetResult.hypothesis}\n\n⚠️ TESTNET`);
    }
  }

  // Bilan
  const total     = allStratNames.filter(n => perf[n]).length;
  const kpiMain   = optimized > 0 ? ((promoted / optimized) * 100).toFixed(0) : "N/A";
  const avgUplift = expectancyUplift.length > 0 ? (expectancyUplift.reduce((a, b) => a + b, 0) / expectancyUplift.length).toFixed(3) : "N/A";
  ctx.log(`\n📊 BILAN TRADE_STRATEGY_TUNER`);
  ctx.log(`   Stratégies évaluées   : ${total}`);
  ctx.log(`   En optimisation       : ${optimized}`);
  ctx.log(`   Promues active        : ${promoted}`);
  ctx.log(`   Rejetées              : ${rejectedCount}`);
  ctx.log(`   Rollbacks             : ${rolledBack}`);
  ctx.log(`   KPI principal         : ${kpiMain}% (optimizing→active)`);
  ctx.log(`   KPI uplift expectancy : ${avgUplift}`);
}
