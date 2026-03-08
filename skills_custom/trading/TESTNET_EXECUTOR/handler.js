/**
 * TESTNET_EXECUTOR — Handler
 * Remplace PAPER_EXECUTOR en mode testnet.
 * Envoie de vrais ordres sur testnet.binance.vision via API REST signée HMAC-SHA256.
 * Gère le cycle complet : open → monitor TP/SL → close.
 * Émet : trading.exec.trade.ledger + trading.exec.position.snapshot
 */

import fs          from "fs";
import path        from "path";
import crypto      from "crypto";

const BASE_URL     = process.env.BINANCE_TESTNET_BASE_URL ?? "https://testnet.binance.vision";
const API_KEY      = process.env.BINANCE_TESTNET_API_KEY;
const SECRET_KEY   = process.env.BINANCE_TESTNET_SECRET_KEY;
const TIMEOUT_MS   = 10000;
const SLIPPAGE_BPS = 10; // 0.10%

// ─── Helpers ──────────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

// ─── Signature HMAC-SHA256 ────────────────────────────────────────────────

function sign(queryString) {
  return crypto
    .createHmac("sha256", SECRET_KEY)
    .update(queryString)
    .digest("hex");
}

async function binanceRequest(method, endpoint, params = {}) {
  const timestamp = Date.now();
  const query = new URLSearchParams({ ...params, timestamp }).toString();
  const signature = sign(query);
  const url = `${BASE_URL}${endpoint}?${query}&signature=${signature}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(url, {
      method,
      headers: {
        "X-MBX-APIKEY": API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      signal: controller.signal,
    });

    const data = await res.json();
    if (!res.ok) throw new Error(`Binance API ${res.status}: ${JSON.stringify(data)}`);
    return data;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Prix actuel ──────────────────────────────────────────────────────────

async function getCurrentPrice(symbol) {
  const res = await fetch(
    `${BASE_URL}/api/v3/ticker/price?symbol=${symbol}`,
    { signal: AbortSignal.timeout(5000) }
  );
  const data = await res.json();
  return parseFloat(data.price);
}

// ─── Info symbol (précision lotSize/tickSize) ─────────────────────────────

async function getSymbolInfo(symbol) {
  const res = await fetch(`${BASE_URL}/api/v3/exchangeInfo?symbol=${symbol}`);
  const data = await res.json();
  const info = data.symbols?.[0];
  if (!info) throw new Error(`Symbol ${symbol} non trouvé`);

  const lotFilter  = info.filters.find(f => f.filterType === "LOT_SIZE");
  const priceFilter = info.filters.find(f => f.filterType === "PRICE_FILTER");

  const stepSize = parseFloat(lotFilter?.stepSize ?? "0.001");
  const tickSize = parseFloat(priceFilter?.tickSize ?? "0.01");

  return { stepSize, tickSize };
}

// ─── Arrondi selon stepSize / tickSize ───────────────────────────────────

function roundStep(value, step) {
  const precision = Math.round(-Math.log10(step));
  return parseFloat((Math.floor(value / step) * step).toFixed(precision));
}

// ─── Calculer la quantité depuis le risque en USD ─────────────────────────

function calcQty(entry, stop, riskUSD, stepSize) {
  const riskPerUnit = Math.abs(entry - stop);
  if (riskPerUnit === 0) throw new Error("entry === stop");
  const rawQty = riskUSD / riskPerUnit;
  return roundStep(rawQty, stepSize);
}

// ─── Passer un ordre market ───────────────────────────────────────────────

async function placeMarketOrder(symbol, side, quantity) {
  return binanceRequest("POST", "/api/v3/order", {
    symbol,
    side,        // BUY ou SELL
    type:        "MARKET",
    quantity:    String(quantity),
  });
}

// ─── Passer un ordre OCO (TP + SL simultanés) ────────────────────────────

async function placeOCO(symbol, side, quantity, tp, sl, tickSize) {
  // OCO : side = côté de CLÔTURE (inverse de l'entrée)
  const closeSide = side === "BUY" ? "SELL" : "BUY";
  const tpRound   = roundStep(tp, tickSize);
  const slRound   = roundStep(sl, tickSize);

  return binanceRequest("POST", "/api/v3/order/oco", {
    symbol,
    side:             closeSide,
    quantity:         String(quantity),
    price:            String(tpRound),          // Limit order (TP)
    stopPrice:        String(slRound),           // Stop trigger
    stopLimitPrice:   String(roundStep(slRound * (closeSide === "SELL" ? 0.999 : 1.001), tickSize)),
    stopLimitTimeInForce: "GTC",
  });
}

// ─── Vérifier si un OCO est toujours actif ────────────────────────────────

async function checkOCOStatus(orderListId) {
  return binanceRequest("GET", "/api/v3/orderList", { orderListId });
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  if (!API_KEY || !SECRET_KEY) {
    ctx.log("❌ BINANCE_TESTNET_API_KEY ou BINANCE_TESTNET_SECRET_KEY manquant");
    return;
  }

  const execDir  = path.join(ctx.stateDir, "exec");
  const posFile  = path.join(execDir, "positions_testnet.json");
  const pnlFile  = path.join(execDir, "daily_pnl_testnet.json");
  const ksFile   = path.join(execDir, "killswitch.json");

  const positions = readJSON(posFile, []);
  const dailyPnl  = readJSON(pnlFile, {});
  const ks        = readJSON(ksFile,  { state: "ACTIVE" });

  const today     = new Date().toISOString().slice(0, 10);
  const capital   = 10000;
  const riskUSD   = capital * 0.01; // 1% par trade

  // ── 0. Kill switch ────────────────────────────────────────────────────
  if (ks.state === "TRIPPED") {
    ctx.log("🚨 Kill switch actif — exécution bloquée");
    return;
  }

  // ── 1. Monitorer les positions ouvertes ───────────────────────────────
  const stillOpen = [];

  for (const pos of positions) {
    if (pos.status !== "open") continue;

    try {
      // Vérifier l'état de l'OCO sur Binance
      if (pos.oco_order_list_id) {
        const oco = await checkOCOStatus(pos.oco_order_list_id);

        if (oco.listOrderStatus === "ALL_DONE") {
          // Trouver l'ordre exécuté
          const executed = oco.orders?.find(o => o.status === "FILLED") ??
                           oco.orderReports?.find(r => r.status === "FILLED");

          const exitPrice  = parseFloat(executed?.price ?? executed?.stopPrice ?? pos.tp);
          const exitReason = exitPrice >= pos.tp * 0.999 ? "TAKE_PROFIT" : "STOP_LOSS";
          const pnlPerUnit = pos.side === "BUY"
            ? exitPrice - pos.entry_fill
            : pos.entry_fill - exitPrice;
          const pnlUSD     = pnlPerUnit * pos.qty;
          const pnlPct     = (pnlUSD / (pos.entry_fill * pos.qty)) * 100;
          const holdMs     = Date.now() - pos.opened_at;

          const closedPos = {
            ...pos,
            status:      "closed",
            exit_price:  exitPrice,
            exit_reason: exitReason,
            pnl_usd:     parseFloat(pnlUSD.toFixed(2)),
            pnl_pct:     parseFloat(pnlPct.toFixed(4)),
            hold_ms:     holdMs,
            closed_at:   Date.now(),
          };

          // Émettre dans le ledger
          ctx.emit("trading.exec.trade.ledger", "exec.trade.ledger.v1",
            { agent_id: "TESTNET_EXECUTOR" },
            { asset: pos.symbol },
            closedPos
          );

          // Mettre à jour le PnL journalier
          dailyPnl[today] = parseFloat(((dailyPnl[today] ?? 0) + pnlUSD).toFixed(2));
          writeJSON(pnlFile, dailyPnl);

          ctx.log(
            `📊 CLOSE ${pos.symbol} ${exitReason} — ` +
            `exit=$${exitPrice} pnl=${pnlUSD >= 0 ? "+" : ""}$${pnlUSD.toFixed(2)} ` +
            `(${pnlPct.toFixed(2)}%) durée=${Math.round(holdMs/60000)}min`
          );

          // Kill switch si daily loss limit
          const todayPnl = dailyPnl[today] ?? 0;
          if (todayPnl < -(capital * 0.03)) {
            ks.state      = "TRIPPED";
            ks.reason     = `Daily loss limit atteint: $${todayPnl.toFixed(2)}`;
            ks.tripped_at = Date.now();
            writeJSON(ksFile, ks);
            ctx.emit("trading.risk.kill_switch", "risk.kill_switch.v1",
              { agent_id: "TESTNET_EXECUTOR" }, {},
              { reason: ks.reason, tripped_at: ks.tripped_at }
            );
            ctx.log(`🚨 KILL SWITCH DÉCLENCHÉ: ${ks.reason}`);
          }

          continue; // Ne pas remettre dans stillOpen
        }
      }

      stillOpen.push(pos);
    } catch (e) {
      ctx.log(`⚠️ Erreur monitoring ${pos.symbol}: ${e.message}`);
      stillOpen.push(pos);
    }
  }

  // ── 2. Nouvelles proposals validées par RISK_MANAGER ─────────────────
  const cursor = ctx.state.cursors?.order_plan ?? 0;
  const { events: plans, nextCursor } =
    ctx.bus.readSince("trading.strategy.order.plan", cursor, 10);

  for (const event of plans) {
    const plan = event.payload;

    // Vérifications
    if (ks.state === "TRIPPED") break;
    if (stillOpen.length >= 3) {
      ctx.log(`⏭  Max positions atteint (3) — skip ${plan.symbol}`);
      continue;
    }
    if (stillOpen.find(p => p.symbol === plan.symbol)) {
      ctx.log(`⏭  Position déjà ouverte sur ${plan.symbol} — skip`);
      continue;
    }

    try {
      // Info symbol pour précision tickSize
      const { stepSize, tickSize } = await getSymbolInfo(plan.symbol);

      // Prix actuel
      const currentPrice = await getCurrentPrice(plan.symbol);
      const entryDiff    = Math.abs(currentPrice - (plan.setup?.entry ?? plan.entry)) / currentPrice;

      if (entryDiff > 0.02) {
        ctx.log(`⏭  Prix trop éloigné de l'entry (${(entryDiff*100).toFixed(2)}%) — skip ${plan.symbol}`);
        continue;
      }

      // Quantité calculée par RISK_MANAGER
      const rawQty = plan.setup?.qty ?? plan.qty;
      if (!rawQty || isNaN(rawQty) || rawQty <= 0) {
        ctx.log(`⚠️  Quantité invalide (${rawQty}) pour ${plan.symbol} — skip`);
        continue;
      }
      const qty = roundStep(rawQty, stepSize);

      // Ordre market d'entrée
      ctx.log(`📤 ORDER MARKET ${plan.side} ${plan.symbol} qty=${qty} @ ~$${currentPrice}`);
      const order = await placeMarketOrder(plan.symbol, plan.side, qty);

      const entryFill = parseFloat(order.fills?.[0]?.price ?? currentPrice);
      const slippage  = Math.abs(entryFill - currentPrice) / currentPrice;

      ctx.log(`✅ Filled @ $${entryFill} (slippage=${(slippage*100).toFixed(3)}%)`);

      // OCO pour TP + SL
      const oco = await placeOCO(plan.symbol, plan.side, qty, plan.setup?.tp ?? plan.tp, plan.setup?.stop ?? plan.stop, tickSize);
      ctx.log(`✅ OCO placé — orderListId=${oco.orderListId}`);

      // Enregistrer la position
      const pos = {
        id:               `testnet_${plan.symbol}_${Date.now()}`,
        symbol:           plan.symbol,
        side:             plan.side,
        strategy:         plan.strategy,
        confidence:       plan.confidence,
        qty,
        entry_fill:       entryFill,
        stop:             plan.setup?.stop ?? plan.stop,
        tp:               plan.setup?.tp ?? plan.tp,
        risk_reward:      plan.risk_reward,
        risk_usd:         riskUSD,
        value_usd:        parseFloat((entryFill * qty).toFixed(2)),
        regime:           plan.regime ?? "unknown",
        oco_order_list_id: oco.orderListId,
        opened_at:        Date.now(),
        status:           "open",
        env:              "testnet",
      };

      stillOpen.push(pos);

      // Émettre snapshot
      ctx.emit("trading.exec.position.snapshot", "exec.position.snapshot.v1",
        { agent_id: "TESTNET_EXECUTOR" },
        { asset: plan.symbol },
        pos
      );

      ctx.log(
        `🟢 OPEN ${plan.symbol} ${plan.side} @ $${entryFill} ` +
        `stop=$${plan.stop} tp=$${plan.tp} qty=${qty}`
      );

    } catch (e) {
      ctx.log(`❌ Erreur exécution ${plan.symbol}: ${e.message}`);
    }

    // Rate limit Binance
    await new Promise(r => setTimeout(r, 300));
  }

  ctx.state.cursors = { ...ctx.state.cursors, order_plan: nextCursor };

  // Sauvegarder les positions
  writeJSON(posFile, stillOpen);

  // Émettre snapshot global
  ctx.emit("trading.exec.position.snapshot", "exec.position.snapshot.v1",
    { agent_id: "TESTNET_EXECUTOR" }, {},
    { positions: stillOpen, count: stillOpen.length, updated_at: Date.now() }
  );

  ctx.log(`✅ ${stillOpen.length} position(s) ouverte(s) — PnL jour: $${dailyPnl[today] ?? 0}`);
}
