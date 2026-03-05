/**
 * KILL_SWITCH_GUARDIAN — Handler
 * Surveille les conditions d'arrêt automatique du trading.
 * Émet : trading.ops.killswitch.state + trading.ops.alert
 * Pas de LLM. Code pur. Poll toutes les 5 secondes.
 *
 * Conditions de déclenchement (TRIPPED) :
 *   1. Perte > 3% du capital total en 24h glissantes
 *   2. 3+ erreurs TRADER consécutives sans fill confirmé
 *   3. Exchange health DOWN depuis > 5 minutes
 *   4. Data quality DEGRADED depuis > 15 minutes
 */

import fs   from "fs";
import path from "path";

const TELEGRAM_API = "https://api.telegram.org";

async function sendTelegram(token, chatId, text) {
  try {
    const url = `${TELEGRAM_API}/bot${token}/sendMessage`;
    const res = await fetch(url, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        chat_id:    chatId,
        text,
        parse_mode: "Markdown",
      }),
    });
    return await res.json();
  } catch (e) {
    console.error("[KILL_SWITCH_GUARDIAN] Telegram error:", e.message);
    return null;
  }
}

function loadKillswitchState(stateDir) {
  const p = path.join(stateDir, "exec", "killswitch.json");
  if (!fs.existsSync(p)) return {
    state:      "ARMED",
    tripped_at: null,
    reason:     null,
    trip_count: 0,
  };
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return { state: "ARMED", tripped_at: null, reason: null, trip_count: 0 }; }
}

function saveKillswitchState(stateDir, ks) {
  const p = path.join(stateDir, "exec", "killswitch.json");
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(ks, null, 2), "utf-8");
}

function readLastEvents(bus, topic, n = 20) {
  const { events } = bus.readSince(topic, 0, 10000);
  return events.slice(-n);
}

function checkExecutorErrors(bus) {
  const errors = readLastEvents(bus, "trading.exec.order.error", 10);
  const fills  = readLastEvents(bus, "trading.exec.order.fill",  10);

  if (errors.length < 3) return null;

  // Vérifie si les 3 dernières erreurs sont consécutives sans fill entre elles
  const lastFillTs  = fills.length > 0 ? fills[fills.length - 1].ts : 0;
  const recentErrors = errors.filter(e => e.ts > lastFillTs);

  if (recentErrors.length >= 3) {
    return `${recentErrors.length} erreurs TRADER consécutives sans fill confirmé`;
  }
  return null;
}

function checkDataQuality(bus) {
  const events = readLastEvents(bus, "trading.ops.health.data", 5);
  if (events.length === 0) return null;

  const last = events[events.length - 1];
  if (last.payload?.status !== "DEGRADED" && last.payload?.status !== "DOWN") return null;

  // Dégradé depuis combien de temps ?
  const degradedSince = last.ts;
  const elapsedMin    = (Date.now() - degradedSince) / 60000;

  if (elapsedMin > 15) {
    return `Data quality ${last.payload.status} depuis ${elapsedMin.toFixed(0)} minutes`;
  }
  return null;
}

function checkExchangeHealth(bus) {
  const events = readLastEvents(bus, "trading.ops.health.exchange", 5);
  if (events.length === 0) return null;

  const last = events[events.length - 1];
  if (last.payload?.status !== "DOWN") return null;

  const downSince  = last.ts;
  const elapsedMin = (Date.now() - downSince) / 60000;

  if (elapsedMin > 5) {
    return `Exchange Binance DOWN depuis ${elapsedMin.toFixed(0)} minutes`;
  }
  return null;
}

function checkDailyLoss(bus) {
  const events  = readLastEvents(bus, "trading.exec.trade.ledger", 100);
  const since24h = Date.now() - 24 * 3600 * 1000;
  const trades24h = events.filter(e => e.ts >= since24h);

  if (trades24h.length === 0) return null;

  const totalPnl = trades24h.reduce((sum, e) => sum + (e.payload?.pnl_usd ?? 0), 0);
  const capital  = parseFloat(process.env.TRADING_MAX_HOT_WALLET_USD ?? "0");

  if (capital <= 0) return null; // Phase 1 paper — pas de capital réel

  const lossPct = Math.abs(totalPnl) / capital;
  if (totalPnl < 0 && lossPct > 0.03) {
    return `Perte journalière ${(lossPct * 100).toFixed(2)}% > 3% du capital`;
  }
  return null;
}

export async function handler(ctx) {
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;

  if (!token || !chatId) {
    ctx.log("⚠️  TRADER_TELEGRAM_BOT_TOKEN ou TRADER_TELEGRAM_CHAT_ID manquant");
    return;
  }

  const ks = loadKillswitchState(ctx.stateDir);

  // Si déjà TRIPPED — juste réémettre l'état et alerter périodiquement
  if (ks.state === "TRIPPED") {
    ctx.emit(
      "trading.ops.killswitch.state",
      "ops.killswitch.state.v1",
      {},
      { state: "TRIPPED", reason: ks.reason, tripped_at: ks.tripped_at }
    );

    // Alerte toutes les 30 runs (~2.5 min) pour ne pas spammer
    if ((ctx.state.stats.runs ?? 0) % 30 === 0) {
      await sendTelegram(token, chatId,
        `🛑 *KILL SWITCH ACTIF*\n\nRaison : ${ks.reason}\n\nDépuis : ${new Date(ks.tripped_at).toISOString()}\n\n_Reset manuel requis : supprimez state/trading/exec/killswitch.json_`
      );
    }
    ctx.log(`🛑 TRIPPED — ${ks.reason}`);
    return;
  }

  // ── Vérification des conditions ─────────────────────────────────────────
  const tripReason =
    checkExecutorErrors(ctx.bus)  ??
    checkDailyLoss(ctx.bus)       ??
    checkDataQuality(ctx.bus)     ??
    checkExchangeHealth(ctx.bus);

  if (tripReason) {
    // TRIP !
    ks.state      = "TRIPPED";
    ks.tripped_at = Date.now();
    ks.reason     = tripReason;
    ks.trip_count = (ks.trip_count ?? 0) + 1;
    saveKillswitchState(ctx.stateDir, ks);

    ctx.emit(
      "trading.ops.killswitch.state",
      "ops.killswitch.state.v1",
      {},
      { state: "TRIPPED", reason: tripReason, tripped_at: ks.tripped_at }
    );

    ctx.emit(
      "trading.ops.alert",
      "ops.alert.v1",
      {},
      { severity: "CRITICAL", message: tripReason, source: "KILL_SWITCH_GUARDIAN" }
    );

    await sendTelegram(token, chatId,
      `🚨 *KILL SWITCH DÉCLENCHÉ*\n\n⚠️ Raison : ${tripReason}\n\n🕐 ${new Date().toISOString()}\n\n_Tous les nouveaux ordres sont bloqués. Vérifiez l'état du système._`
    );

    ctx.log(`🚨 TRIPPED — ${tripReason}`);
    return;
  }

  // ── Tout va bien — émettre état ARMED ────────────────────────────────────
  ctx.emit(
    "trading.ops.killswitch.state",
    "ops.killswitch.state.v1",
    {},
    { state: "ARMED", reason: null, tripped_at: null }
  );

  // Log heartbeat toutes les 60 runs (~5 min) pour ne pas polluer les logs
  if ((ctx.state.stats.runs ?? 0) % 60 === 0) {
    ctx.log(`✅ ARMED — système nominal (run #${ctx.state.stats.runs})`);
  }
}
