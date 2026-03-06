/**
 * PAPER_EXECUTOR — Handler
 * Simule l'exécution des order.plan sans argent réel.
 * Gère le cycle de vie des positions : open → filled → closed (TP ou SL)
 * Émet : trading.exec.trade.ledger + trading.exec.position.snapshot
 * Pas de LLM.
 */

import fs   from "fs";
import path from "path";

const SLIPPAGE_BPS = 10; // 0.10% de slippage simulé

// ─── Helpers fichiers ──────────────────────────────────────────────────────

function readJSON(filePath, defaultVal) {
  try { return JSON.parse(fs.readFileSync(filePath, "utf-8")); }
  catch { return defaultVal; }
}

function writeJSON(filePath, data) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

function getCurrentPrice(bus, symbol) {
  const { events } = bus.readSince("trading.intel.market.features", 0, 5000);
  const filtered   = events.filter(e => e.payload?.symbol === symbol && e.payload?.timeframe === "1m");
  return filtered.length > 0 ? filtered[filtered.length - 1].payload.price : null;
}

function applySlippage(price, side) {
  const factor = side === "BUY"
    ? 1 + SLIPPAGE_BPS / 10000
    : 1 - SLIPPAGE_BPS / 10000;
  return parseFloat((price * factor).toFixed(4));
}

// ─── Ouverture de position ─────────────────────────────────────────────────

function openPosition(plan, fillPrice) {
  return {
    id:            `pos_${plan.symbol}_${Date.now()}`,
    proposal_ref:  plan.proposal_ref,
    symbol:        plan.symbol,
    side:          plan.side,
    strategy:      plan.strategy,
    qty:           plan.setup.qty,
    entry_target:  plan.setup.entry,
    entry_fill:    fillPrice,
    stop:          plan.setup.stop,
    tp:            plan.setup.tp,
    risk_reward:   plan.setup.risk_reward,
    value_usd:     parseFloat((plan.setup.qty * fillPrice).toFixed(2)),
    risk_usd:      plan.setup.risk_usd,
    regime:        plan.regime,
    opened_at:     Date.now(),
    status:        "open",
    env:           plan.env ?? "paper",
  };
}

// ─── Vérification TP/SL sur positions ouvertes ───────────────────────────

function checkExits(positions, bus, ctx) {
  const closed  = [];
  const still   = [];

  for (const pos of positions) {
    const price = getCurrentPrice(bus, pos.symbol);
    if (!price) { still.push(pos); continue; }

    let exitReason = null;
    let exitPrice  = price;

    if (pos.side === "BUY") {
      if (price <= pos.stop) { exitReason = "STOP_LOSS"; exitPrice = pos.stop; }
      if (price >= pos.tp)   { exitReason = "TAKE_PROFIT"; exitPrice = pos.tp; }
    } else { // SELL
      if (price >= pos.stop) { exitReason = "STOP_LOSS"; exitPrice = pos.stop; }
      if (price <= pos.tp)   { exitReason = "TAKE_PROFIT"; exitPrice = pos.tp; }
    }

    if (exitReason) {
      const fillExit = applySlippage(exitPrice, pos.side === "BUY" ? "SELL" : "BUY");
      const pnl      = pos.side === "BUY"
        ? (fillExit - pos.entry_fill) * pos.qty
        : (pos.entry_fill - fillExit) * pos.qty;

      const closedPos = {
        ...pos,
        exit_price:  fillExit,
        exit_reason: exitReason,
        pnl_usd:     parseFloat(pnl.toFixed(2)),
        pnl_pct:     parseFloat((pnl / pos.value_usd * 100).toFixed(4)),
        closed_at:   Date.now(),
        hold_ms:     Date.now() - pos.opened_at,
        status:      "closed",
      };

      closed.push(closedPos);

      ctx.emit(
        "trading.exec.trade.ledger",
        "exec.trade.ledger.v1",
        { asset: pos.symbol },
        closedPos
      );

      const emoji = pnl >= 0 ? "💰" : "💸";
      ctx.log(
        `${emoji} ${pos.symbol} ${pos.side} FERMÉ (${exitReason}) ` +
        `PnL=$${pnl.toFixed(2)} (${closedPos.pnl_pct}%) ` +
        `entry=${pos.entry_fill} exit=${fillExit}`
      );
    } else {
      // Unrealized PnL
      const unrealized = pos.side === "BUY"
        ? (price - pos.entry_fill) * pos.qty
        : (pos.entry_fill - price) * pos.qty;
      still.push({ ...pos, current_price: price, unrealized_pnl: parseFloat(unrealized.toFixed(2)) });
    }
  }

  return { closed, still };
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const execDir      = path.join(ctx.stateDir, "exec");
  const posFile      = path.join(execDir, "positions.json");
  const pnlFile      = path.join(execDir, "daily_pnl.json");
  const today        = new Date().toISOString().slice(0, 10);

  let positions = readJSON(posFile, []);
  let dailyPnl  = readJSON(pnlFile, {});
  dailyPnl[today] = dailyPnl[today] ?? 0;

  // ── 1. Vérifier exits sur positions existantes ──────────────────────────
  const { closed, still } = checkExits(positions, ctx.bus, ctx);

  for (const c of closed) {
    dailyPnl[today] = parseFloat((dailyPnl[today] + c.pnl_usd).toFixed(2));
  }

  // ── 2. Traiter les nouveaux order.plan ────────────────────────────────
  const cursor = ctx.state.cursors?.order_plans ?? 0;
  const { events: plans, nextCursor } =
    ctx.bus.readSince("trading.strategy.order.plan", cursor, 20);

  let opened = 0;

  for (const event of plans) {
    const plan  = event.payload;
    const price = getCurrentPrice(ctx.bus, plan.symbol);

    if (!price) {
      ctx.log(`⚠️ ${plan.symbol}: prix non disponible, order.plan ignoré`);
      continue;
    }

    // Vérifie que le prix est proche de l'entry (max 0.5% d'écart)
    const priceDiff = Math.abs(price - plan.setup.entry) / plan.setup.entry;
    if (priceDiff > 0.005) {
      ctx.log(
        `⚠️ ${plan.symbol}: prix trop éloigné de l'entry ` +
        `(current=${price} entry=${plan.setup.entry} diff=${(priceDiff*100).toFixed(2)}%)`
      );
      continue;
    }

    const fillPrice = applySlippage(price, plan.side);
    const position  = openPosition(plan, fillPrice);
    still.push(position);
    opened++;

    ctx.log(
      `📈 ${plan.symbol} ${plan.side} OUVERT ` +
      `fill=${fillPrice} qty=${plan.setup.qty} ` +
      `stop=${plan.setup.stop} tp=${plan.setup.tp} ` +
      `risk=$${plan.setup.risk_usd?.toFixed(2)}`
    );
  }

  // ── 3. Sauvegarde état ────────────────────────────────────────────────
  writeJSON(posFile, still);
  writeJSON(pnlFile, dailyPnl);

  ctx.state.cursors = { ...ctx.state.cursors, order_plans: nextCursor };

  // ── 4. Snapshot positions ─────────────────────────────────────────────
  ctx.emit(
    "trading.exec.position.snapshot",
    "exec.position.snapshot.v1",
    { asset: "MARKET" },
    {
      positions:     still,
      open_count:    still.length,
      daily_pnl_usd: dailyPnl[today],
      date:          today,
      ts:            Date.now(),
    }
  );

  ctx.log(
    `✅ ${opened} ouvertes | ${closed.length} fermées | ` +
    `${still.length} actives | PnL today=$${dailyPnl[today]}`
  );
}
