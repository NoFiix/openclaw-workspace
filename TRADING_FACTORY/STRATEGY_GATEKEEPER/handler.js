/**
 * STRATEGY_GATEKEEPER — Handler
 * Lit strategy_performance.json et strategy_candidates.json.
 * Applique les règles de scoring pondéré pour activer/désactiver les stratégies.
 * Met à jour strategy_candidates.json (status: candidate → active | rejected | testing).
 * Notifie via Telegram si changement de statut.
 * Pas de LLM — logique pure.
 *
 * Seuils (min 20 trades pour décision) :
 *   Score >= 0.60 → active
 *   Score 0.40-0.59 → testing (continue)
 *   Score < 0.40  → rejected
 *
 * Pondération :
 *   Expectancy    35%
 *   Profit Factor 30%
 *   Max Drawdown  20%
 *   Sharpe Ratio  10%
 *   Trade count   5%
 */

import fs   from "fs";
import path from "path";

const MIN_TRADES_DECISION = 20;
const MIN_TRADES_SIGNAL   = 5; // Signal préliminaire dès 5 trades

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
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
    console.error("[STRATEGY_GATEKEEPER] Telegram error:", e.message);
  }
}

// ─── Score pondéré ────────────────────────────────────────────────────────

function scoreStrategy(perf) {
  const scores = {};

  // 1. Expectancy (35%) — normalisé sur $100 max attendu
  const expNorm = Math.min(Math.max((perf.expectancy_usd ?? 0) / 100, -1), 1);
  scores.expectancy = (expNorm + 1) / 2; // 0-1

  // 2. Profit Factor (30%) — PF 1.0=neutre, 2.0=excellent, 0=catastrophe
  const pfNorm = Math.min((perf.profit_factor ?? 0) / 2, 1);
  scores.profit_factor = pfNorm;

  // 3. Max Drawdown (20%) — inversé : 0% DD = score 1.0, 25%+ DD = score 0
  const ddNorm = Math.max(1 - (perf.max_drawdown_pct ?? 0) / 25, 0);
  scores.drawdown = ddNorm;

  // 4. Sharpe Ratio (10%) — normalisé sur 2.0 max
  const sharpeNorm = Math.min(Math.max((perf.sharpe_ratio ?? 0) / 2, -1), 1);
  scores.sharpe = (sharpeNorm + 1) / 2;

  // 5. Trade count (5%) — confiance statistique
  const countNorm = Math.min((perf.trades_count ?? 0) / 50, 1);
  scores.count = countNorm;

  // Score final pondéré
  const total =
    scores.expectancy    * 0.35 +
    scores.profit_factor * 0.30 +
    scores.drawdown      * 0.20 +
    scores.sharpe        * 0.10 +
    scores.count         * 0.05;

  return {
    total:    parseFloat(total.toFixed(3)),
    details:  scores,
  };
}

function decideStatus(score, trades, currentStatus) {
  if (trades < MIN_TRADES_SIGNAL)   return { status: "candidate",  reason: "Pas assez de trades (< 5)" };
  if (trades < MIN_TRADES_DECISION) return { status: "testing",    reason: `Signal préliminaire (${trades}/${MIN_TRADES_DECISION} trades)` };

  if (score >= 0.60) return { status: "active",    reason: `Score ${score} ≥ 0.60 — stratégie rentable` };
  if (score >= 0.40) return { status: "testing",   reason: `Score ${score} entre 0.40-0.60 — surveillance` };
  return               { status: "rejected",  reason: `Score ${score} < 0.40 — stratégie non rentable` };
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;

  const learnDir    = path.join(ctx.stateDir, "learning");
  const candFile    = path.join(learnDir, "strategy_candidates.json");
  const perfFile    = path.join(learnDir, "strategy_performance.json");
  const builtinFile = path.join(learnDir, "builtin_performance.json");

  const candidates = readJSON(candFile, []);
  const perf       = readJSON(perfFile, {});

  // Stratégies builtin à évaluer aussi
  const BUILTINS = ["MeanReversion", "Momentum", "NewsTrading", "Breakout"];

  let changes = [];

  // ── 1. Évaluer les stratégies candidates ─────────────────────────────
  const updatedCandidates = candidates.map(s => {
    const p = perf[s.name];
    if (!p) return s; // Pas encore de données

    const { total: score, details } = scoreStrategy(p);
    const { status: newStatus, reason } = decideStatus(score, p.trades_count, s.status);

    if (newStatus !== s.status) {
      changes.push({
        name:       s.name,
        old_status: s.status,
        new_status: newStatus,
        score,
        reason,
        trades:     p.trades_count,
      });
    }

    return {
      ...s,
      status:          newStatus,
      score,
      score_details:   details,
      last_evaluated:  new Date().toISOString(),
      evaluation_reason: reason,
      test_trades:     p.trades_count,
      pnl_usd:         p.pnl_usd,
      win_rate:        p.win_rate,
      profit_factor:   p.profit_factor,
    };
  });

  writeJSON(candFile, updatedCandidates);

  // ── 2. Évaluer les builtins (pour info, pas de désactivation auto) ───
  const builtinEval = {};
  for (const name of BUILTINS) {
    const p = perf[name];
    if (!p) continue;
    const { total: score, details } = scoreStrategy(p);
    const { status, reason } = decideStatus(score, p.trades_count, "active");
    builtinEval[name] = {
      score, status, reason,
      trades_count:   p.trades_count,
      win_rate:       p.win_rate,
      profit_factor:  p.profit_factor,
      expectancy_usd: p.expectancy_usd,
      last_evaluated: new Date().toISOString(),
    };

    // Signaler si une builtin performe mal
    if (p.trades_count >= MIN_TRADES_DECISION && score < 0.40) {
      changes.push({
        name,
        old_status: "active",
        new_status: "warning",
        score,
        reason:     `Stratégie builtin sous-performante — envisager désactivation manuelle`,
        trades:     p.trades_count,
      });
    }
  }
  writeJSON(builtinFile, builtinEval);

  ctx.log(`📊 ${Object.keys(perf).length} stratégies évaluées, ${changes.length} changements`);

  // ── 3. Log + Telegram sur les changements ────────────────────────────
  for (const c of changes) {
    const emoji = c.new_status === "active"  ? "✅" :
                  c.new_status === "rejected" ? "❌" :
                  c.new_status === "warning"  ? "⚠️" : "🔬";

    ctx.log(`  ${emoji} ${c.name}: ${c.old_status} → ${c.new_status} (score=${c.score}, ${c.trades} trades)`);
    ctx.log(`     Raison: ${c.reason}`);

    if (token && chatId) {
      const statusLabel = {
        active:   "✅ STRATÉGIE ACTIVÉE",
        rejected: "❌ STRATÉGIE DÉSACTIVÉE",
        warning:  "⚠️ ALERTE PERFORMANCE",
        testing:  "🔬 EN COURS DE TEST",
      }[c.new_status] ?? c.new_status;

      const msg =
`🤖 *STRATEGY_GATEKEEPER*

${statusLabel} — *${c.name}*

Score : ${(c.score * 100).toFixed(0)}/100
Trades : ${c.trades}
Raison : ${c.reason}

⚠️ PAPER TRADING`;

      await sendTelegram(token, chatId, msg);
    }
  }

  if (!changes.length) ctx.log("✅ Aucun changement de statut");
}
