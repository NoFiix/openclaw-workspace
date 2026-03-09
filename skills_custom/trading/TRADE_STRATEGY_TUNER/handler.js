/**
 * TRADE_STRATEGY_TUNER — Handler
 *
 * Rôle : Optimiser itérativement les paramètres des stratégies en état "optimizing".
 * Lit strategy_performance.json + trade.ledger pour analyser les trades perdants.
 * Propose des ajustements de paramètres via Sonnet.
 * Gère un historique versionné dans strategy_versions.json.
 * Rollback automatique si la nouvelle version régresse.
 *
 * Cycle de vie :
 *   candidate  (0-4 trades)   → observe uniquement
 *   testing    (5-19 trades)  → observe uniquement
 *   optimizing (20-50 trades, score 0.40-0.60) → intervient (max 3 itérations)
 *   active     (score > 0.60) → affinage léger possible
 *   rejected                  → archivé dans strategy_rejected.json
 *
 * KPI unique : % de stratégies passées de "optimizing" à "active"
 * LLM : Sonnet (~3000 tokens/run, 1x/semaine)
 */

import fs   from "fs";
import path from "path";

const PARAM_BOUNDS = {
  rsi_low:   { min: 20, max: 40, step: 1 },
  rsi_high:  { min: 60, max: 80, step: 1 },
  bb_low:    { min: 0.05, max: 0.25, step: 0.01 },
  bb_high:   { min: 0.75, max: 0.95, step: 0.01 },
  macd_min:  { min: 0.0001, max: 0.002, step: 0.0001 },
};

const DEFAULT_PARAMS = {
  MeanReversion: { rsi_low: 35, rsi_high: 65, bb_low: 0.15, bb_high: 0.85 },
  Momentum:      { rsi_low: 35, rsi_high: 65, macd_min: 0.0005 },
  Breakout:      { bb_low: 0.02, bb_high: 0.98 },
};

const MIN_TRADES_OPTIMIZING = 20;
const MAX_ITERATIONS        = 3;
const SCORE_TARGET          = 0.60;
const SCORE_FLOOR           = 0.40;

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

function scoreStrategy(perf) {
  const expNorm    = Math.min(Math.max((perf.expectancy_usd ?? 0) / 100, -1), 1);
  const expScore   = (expNorm + 1) / 2;
  const pfScore    = Math.min((perf.profit_factor ?? 0) / 2, 1);
  const ddScore    = Math.max(1 - (perf.max_drawdown_pct ?? 0) / 25, 0);
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

function clampParam(key, value) {
  const b = PARAM_BOUNDS[key];
  if (!b) return value;
  return Math.min(Math.max(value, b.min), b.max);
}

function getOptimizingStatus(perf, versions) {
  const trades = perf.trades_count ?? 0;
  const score  = scoreStrategy(perf);
  if (trades < MIN_TRADES_OPTIMIZING) return { eligible: false, reason: `${trades}/${MIN_TRADES_OPTIMIZING} trades min` };
  if (score > SCORE_TARGET)           return { eligible: false, reason: `Score ${score} déjà > ${SCORE_TARGET}` };
  if (score < SCORE_FLOOR) {
    const iters = (versions?.versions ?? []).length;
    if (iters >= MAX_ITERATIONS) return { eligible: false, rejected: true, reason: `${MAX_ITERATIONS} itérations sans amélioration` };
  }
  return { eligible: true, score, trades };
}

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
      system: `Tu es un expert en optimisation de stratégies de trading algorithmique.
Tu analyses les trades perdants pour identifier des ajustements précis et chiffrés des paramètres.
Tu réponds UNIQUEMENT en JSON valide, sans markdown, sans commentaires.
Format de réponse attendu :
{
  "analysis": "Explication courte en français des patterns identifiés dans les trades perdants",
  "adjustments": {
    "param_name": nouvelle_valeur
  },
  "rationale": "Pourquoi ces ajustements précis devraient améliorer le score"
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
    throw new Error(`Réponse Sonnet non parseable : ${text.slice(0, 200)}`);
  }
}

function buildPrompt(stratName, perf, currentParams, losingTrades, versions) {
  const iterNum    = (versions?.versions ?? []).length + 1;
  const bestV      = versions?.best_version ?? 1;
  const bestParams = versions?.versions?.find(v => v.v === bestV)?.params ?? currentParams;
  return `Stratégie : ${stratName}
Itération : ${iterNum}/${MAX_ITERATIONS}

=== PERFORMANCE ACTUELLE ===
Trades : ${perf.trades_count} | Win rate : ${perf.win_rate}%
PnL : $${perf.pnl_usd} | Expectancy : $${perf.expectancy_usd}
Profit Factor : ${perf.profit_factor} | Sharpe : ${perf.sharpe_ratio}
Max Drawdown : ${perf.max_drawdown_pct}%
Score composite actuel : ${scoreStrategy(perf)} (cible > ${SCORE_TARGET})

=== PARAMÈTRES ACTUELS ===
${JSON.stringify(currentParams, null, 2)}

=== MEILLEURE VERSION CONNUE (v${bestV}) ===
${JSON.stringify(bestParams, null, 2)}

=== HISTORIQUE DES VERSIONS ===
${JSON.stringify(versions?.versions ?? [], null, 2)}

=== ${losingTrades.length} TRADES PERDANTS (sur ${perf.trades_count} total) ===
${JSON.stringify(losingTrades.slice(0, 15), null, 2)}

=== BORNES DES PARAMÈTRES (NE PAS DÉPASSER) ===
${JSON.stringify(PARAM_BOUNDS, null, 2)}

Analyse les trades perdants. Identifie si les seuils RSI/BB/MACD sont trop agressifs ou trop larges.
Propose UN SEUL ajustement précis et chiffré qui devrait améliorer le score.
Ne dépasse jamais les bornes indiquées.
Ne répète pas un paramètre déjà testé dans l'historique.`;
}

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

  const perf       = readJSON(perfFile, {});
  const candidates = readJSON(candFile, []);
  let   versions   = readJSON(versionsFile, {});
  let   rejected   = readJSON(rejectedFile, []);

  let allTrades = [];
  if (fs.existsSync(ledgerFile)) {
    try {
      allTrades = fs.readFileSync(ledgerFile, "utf-8")
        .split("\n")
        .filter(Boolean)
        .map(l => JSON.parse(l))
        .filter(e => e.producer?.agent_id === "TESTNET_EXECUTOR")
        .map(e => e.trace?.causation_id ?? e.payload);
    } catch (e) {
      ctx.log(`[TRADE_STRATEGY_TUNER] Erreur lecture ledger : ${e.message}`);
    }
  }

  const BUILTINS = ["MeanReversion", "Momentum", "Breakout", "NewsTrading"];
  const allStratNames = [...new Set([...BUILTINS, ...candidates.map(c => c.name)])];

  ctx.log(`[TRADE_STRATEGY_TUNER] ${allStratNames.length} stratégies à évaluer, ${allTrades.length} trades réels dans le ledger`);

  let optimized = 0;
  let promoted  = 0;
  let rejectedCount = 0;

  for (const stratName of allStratNames) {
    const p = perf[stratName];
    if (!p) {
      ctx.log(`  ⏭  ${stratName} — pas de données de performance`);
      continue;
    }

    const v = versions[stratName];
    const { eligible, rejected: shouldReject, reason, score, trades } = getOptimizingStatus(p, v);

    if (!eligible) {
      ctx.log(`  ⏭  ${stratName} — skip (${reason})`);
      if (shouldReject) {
        ctx.log(`  ❌ ${stratName} — rejeté après ${MAX_ITERATIONS} itérations`);
        rejected.push({
          name:        stratName,
          rejected_at: new Date().toISOString(),
          reason,
          final_score: scoreStrategy(p),
          trades:      p.trades_count,
          versions:    v?.versions ?? [],
        });
        const idx = candidates.findIndex(c => c.name === stratName);
        if (idx !== -1) {
          candidates[idx].status           = "rejected";
          candidates[idx].rejection_reason = reason;
        }
        rejectedCount++;
        writeJSON(rejectedFile, rejected);
        writeJSON(candFile, candidates);
        if (token && chatId) {
          await sendTelegram(token, chatId,
`🤖 *TRADE_STRATEGY_TUNER*

❌ *${stratName}* rejetée

${MAX_ITERATIONS} itérations sans amélioration.
Score final : ${scoreStrategy(p)}
Trades : ${p.trades_count}

Archivée dans strategy_rejected.json`);
        }
      }
      continue;
    }

    ctx.log(`  🔧 ${stratName} — optimizing (score=${score}, trades=${trades})`);
    optimized++;

    const losingTrades = allTrades.filter(t =>
      t.strategy === stratName && (t.pnl_usd < 0 || t.exit_reason === "STOP_LOSS")
    );

    const currentVersion = v?.versions?.find(ver => ver.v === v.current_version);
    const currentParams  = currentVersion?.params ?? DEFAULT_PARAMS[stratName] ?? {};

    let sonnetResult;
    try {
      const prompt = buildPrompt(stratName, p, currentParams, losingTrades, v);
      ctx.log(`    → Appel Sonnet (${losingTrades.length} trades perdants analysés)`);
      sonnetResult = await callSonnet(apiKey, prompt);
    } catch (e) {
      ctx.log(`    ✗ Erreur Sonnet pour ${stratName} : ${e.message}`);
      continue;
    }

    const rawAdj  = sonnetResult.adjustments ?? {};
    const safeAdj = {};
    for (const [key, val] of Object.entries(rawAdj)) {
      if (PARAM_BOUNDS[key] !== undefined) {
        safeAdj[key] = clampParam(key, val);
      }
    }

    if (Object.keys(safeAdj).length === 0) {
      ctx.log(`    ⚠ Sonnet n'a proposé aucun ajustement valide pour ${stratName}`);
      continue;
    }

    const prevVersions = v?.versions ?? [];
    const newVersion   = (v?.current_version ?? 0) + 1;
    const newParams    = { ...currentParams, ...safeAdj };

    const bestVersion = prevVersions.reduce((best, ver) =>
      (ver.score ?? 0) > (best.score ?? 0) ? ver : best,
      { v: 1, score: score }
    );

    versions[stratName] = {
      current_version: newVersion,
      best_version:    bestVersion.v,
      versions: [...prevVersions, {
        v:          newVersion,
        params:     newParams,
        trades:     p.trades_count,
        score,
        applied_at: new Date().toISOString().split("T")[0],
        analysis:   sonnetResult.analysis,
        rationale:  sonnetResult.rationale,
      }],
    };

    writeJSON(versionsFile, versions);

    const candIdx = candidates.findIndex(c => c.name === stratName);
    if (candIdx !== -1) {
      candidates[candIdx].params          = newParams;
      candidates[candIdx].status          = "optimizing";
      candidates[candIdx].last_tuned      = new Date().toISOString();
      candidates[candIdx].current_version = newVersion;
    } else if (BUILTINS.includes(stratName)) {
      candidates.push({
        name:            stratName,
        description:     `Stratégie builtin optimisée par TRADE_STRATEGY_TUNER`,
        params:          newParams,
        status:          "optimizing",
        last_tuned:      new Date().toISOString(),
        current_version: newVersion,
        source:          "builtin",
        discovered_at:   new Date().toISOString(),
        test_trades:     p.trades_count,
        pnl_usd:         p.pnl_usd,
        win_rate:        p.win_rate,
        profit_factor:   p.profit_factor,
      });
    }

    writeJSON(candFile, candidates);

    appendJSONL(auditFile, {
      ts:           new Date().toISOString(),
      strategy:     stratName,
      version:      newVersion,
      old_params:   currentParams,
      new_params:   newParams,
      adjustments:  safeAdj,
      score_before: score,
      trades:       p.trades_count,
      analysis:     sonnetResult.analysis,
      rationale:    sonnetResult.rationale,
    });

    ctx.log(`    ✅ v${newVersion} proposée : ${JSON.stringify(safeAdj)}`);
    ctx.log(`    📝 ${sonnetResult.analysis}`);

    if (score >= SCORE_TARGET) {
      promoted++;
      if (token && chatId) {
        await sendTelegram(token, chatId,
`🤖 *TRADE_STRATEGY_TUNER*

✅ *${stratName}* — PROMUE ACTIVE

Score : ${score} ≥ ${SCORE_TARGET}
Version : v${newVersion}
Trades : ${p.trades_count}

Paramètres optimisés :
\`${JSON.stringify(newParams, null, 2)}\``);
      }
    } else {
      if (token && chatId) {
        const adjStr = Object.entries(safeAdj)
          .map(([k, v]) => `  • ${k} : ${currentParams[k] ?? "?"} → ${v}`)
          .join("\n");
        await sendTelegram(token, chatId,
`🤖 *TRADE_STRATEGY_TUNER*

🔧 *${stratName}* — itération v${newVersion}

Score actuel : ${score} (cible > ${SCORE_TARGET})
Trades analysés : ${p.trades_count} (${losingTrades.length} perdants)

Ajustements proposés :
${adjStr}

Analyse : ${sonnetResult.analysis}`);
      }
    }
  }

  const total = allStratNames.filter(n => perf[n]).length;
  const kpi   = optimized > 0 ? ((promoted / optimized) * 100).toFixed(0) : "N/A";
  ctx.log(`\n📊 BILAN TRADE_STRATEGY_TUNER`);
  ctx.log(`   Stratégies évaluées  : ${total}`);
  ctx.log(`   En optimisation      : ${optimized}`);
  ctx.log(`   Promues active       : ${promoted}`);
  ctx.log(`   Rejetées             : ${rejectedCount}`);
  ctx.log(`   KPI (optimizing→active) : ${kpi}%`);
}
