/**
 * RISK_MANAGER — Handler
 * Valide les TradeProposal de TRADE_GENERATOR.
 * Calcule la taille de position selon Kelly criterion simplifié.
 * Émet : trading.strategy.order.plan (validé) ou trading.strategy.block (rejeté)
 * Pas de LLM. Règles de risk management pures.
 */

import fs   from "fs";
import path from "path";
import { loadWallet, resolveStrategyConfig, isCircuitBreakerTripped, suspendStrategy } from "../_shared/strategy_utils.js";

// ─── Paramètres de risk par défaut (fallback si registry indisponible) ────
const DEFAULT_RISK_PARAMS = {
  capital_usd:           10000,
  max_risk_per_trade_pct: 1.0,
  max_open_positions:     3,
  max_daily_loss_pct:     3.0,
  min_confidence:         0.45,
  min_risk_reward:        2.0,
  max_slippage_bps:       30,
};

// ─── Helpers ──────────────────────────────────────────────────────────────

function getLastEvents(bus, topic, limit = 1000) {
  const { events } = bus.readSince(topic, 0, limit);
  return events;
}

function getOpenPositions(stateDir) {
  const p = path.join(stateDir, "exec", "positions.json");
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return []; }
}

function getDailyPnL(stateDir) {
  const p = path.join(stateDir, "exec", "daily_pnl.json");
  try {
    const data = JSON.parse(fs.readFileSync(p, "utf-8"));
    const today = new Date().toISOString().slice(0, 10);
    return data[today] ?? 0;
  } catch { return 0; }
}

function calcPositionSize(capital, riskPct, entry, stop) {
  const riskAmount   = capital * (riskPct / 100);
  const stopDistance = Math.abs(entry - stop);
  if (stopDistance <= 0) return 0;
  const qty = riskAmount / stopDistance;
  return parseFloat(qty.toFixed(6));
}

function calcPositionValueUSD(qty, entry) {
  return parseFloat((qty * entry).toFixed(2));
}

// ─── Moteurs de validation ────────────────────────────────────────────────

function validateProposal(proposal, openPositions, dailyPnl, riskParams, capitalUsd) {
  const blocks = [];

  // 1. HOLD → pas besoin de valider
  if (proposal.side === "HOLD") {
    return { valid: false, reason: "HOLD", blocks: [] };
  }

  // 2. Confidence minimum
  if (proposal.confidence < riskParams.min_confidence) {
    blocks.push(`confidence trop faible: ${proposal.confidence} < ${riskParams.min_confidence}`);
  }

  // 3. Risk/reward minimum
  if (proposal.setup?.risk_reward < riskParams.min_risk_reward) {
    blocks.push(`risk_reward insuffisant: ${proposal.setup?.risk_reward} < ${riskParams.min_risk_reward}`);
  }

  // 4. Stop-loss obligatoire
  if (!proposal.setup?.stop || proposal.setup.stop <= 0) {
    blocks.push("stop-loss manquant — rejet automatique");
  }

  // 5. Stop cohérent avec le side
  if (proposal.side === "BUY" && proposal.setup?.stop >= proposal.setup?.entry) {
    blocks.push(`stop BUY au-dessus du prix d'entrée: stop=${proposal.setup.stop} entry=${proposal.setup.entry}`);
  }
  if (proposal.side === "SELL" && proposal.setup?.stop <= proposal.setup?.entry) {
    blocks.push(`stop SELL en-dessous du prix d'entrée: stop=${proposal.setup.stop} entry=${proposal.setup.entry}`);
  }

  // 6. Max positions ouvertes (per-strategy)
  const strategyId  = proposal.strategy_id ?? proposal.strategy;
  const stratPositions = openPositions.filter(p => (p.strategy_id ?? p.strategy) === strategyId);
  const sameSymbol = stratPositions.filter(p => p.symbol === proposal.symbol);
  if (sameSymbol.length > 0) {
    blocks.push(`position déjà ouverte sur ${proposal.symbol} pour ${strategyId}`);
  }
  if (stratPositions.length >= riskParams.max_open_positions) {
    blocks.push(`max positions atteint pour ${strategyId}: ${stratPositions.length}/${riskParams.max_open_positions}`);
  }

  // 7. Daily loss limit
  const dailyLossPct = Math.abs(dailyPnl) / capitalUsd * 100;
  if (dailyPnl < 0 && dailyLossPct >= riskParams.max_daily_loss_pct) {
    blocks.push(`daily loss limit atteinte: ${dailyLossPct.toFixed(2)}% >= ${riskParams.max_daily_loss_pct}%`);
  }

  return { valid: blocks.length === 0, reason: blocks[0] ?? null, blocks };
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  // Curseur sur les proposals
  const cursor = ctx.state.cursors?.proposals ?? 0;
  const { events: proposals, nextCursor } =
    ctx.bus.readSince("trading.strategy.trade.proposal", cursor, 50);

  if (proposals.length === 0) {
    ctx.log("Aucune nouvelle proposal à traiter");
    ctx.state.cursors = { ...ctx.state.cursors, proposals: nextCursor };
    return;
  }

  ctx.log(`📋 ${proposals.length} proposals à évaluer`);

  const openPositions = getOpenPositions(ctx.stateDir);
  const dailyPnl      = getDailyPnL(ctx.stateDir);

  let approved = 0, blocked = 0, hold = 0;

  for (const event of proposals) {
    const p = event.payload;

    if (p.side === "HOLD") {
      hold++;
      ctx.log(`⚪ ${p.symbol}: HOLD — pas de validation nécessaire`);
      continue;
    }

    // Resolve per-strategy config and wallet
    const strategyId = p.strategy_id ?? p.strategy;
    let riskParams = DEFAULT_RISK_PARAMS;
    let capitalUsd = DEFAULT_RISK_PARAMS.capital_usd;

    try {
      const stratConfig = resolveStrategyConfig(strategyId);
      riskParams = { ...DEFAULT_RISK_PARAMS, ...stratConfig.risk_params };
      const wallet = loadWallet(strategyId);

      // Circuit breaker check
      if (isCircuitBreakerTripped(wallet, stratConfig)) {
        suspendStrategy(strategyId, `circuit_breaker: cash $${wallet.cash} < threshold $${stratConfig.min_cash_threshold}`);
        ctx.log(`🚨 ${p.symbol} ${p.side} — circuit breaker tripped for ${strategyId}`);
        blocked++;
        continue;
      }
      if (wallet.status === "suspended") {
        ctx.log(`⏸️ ${p.symbol} ${p.side} — ${strategyId} suspended: ${wallet.suspended_reason}`);
        blocked++;
        continue;
      }

      capitalUsd = wallet.cash;
    } catch (e) {
      ctx.log(`⚠️ ${strategyId}: registry/wallet error — using defaults: ${e.message}`);
    }

    const { valid, reason, blocks } = validateProposal(p, openPositions, dailyPnl, riskParams, capitalUsd);

    if (!valid) {
      ctx.emit(
        "trading.strategy.block",
        "strategy.block.v1",
        { asset: p.symbol },
        {
          proposal_ref:  event.event_id,
          symbol:        p.symbol,
          side:          p.side,
          strategy_id:   strategyId,
          reason:        reason ?? "validation échouée",
          all_reasons:   blocks,
          blocked_at:    Date.now(),
        }
      );
      blocked++;
      ctx.log(`🚫 ${p.symbol} ${p.side} [${strategyId}] BLOQUÉ — ${reason}`);
      continue;
    }

    // Calcul taille de position avec capital du wallet
    const qty      = calcPositionSize(
      capitalUsd,
      riskParams.max_risk_per_trade_pct,
      p.setup.entry,
      p.setup.stop
    );
    const valueUSD = calcPositionValueUSD(qty, p.setup.entry);
    const riskUSD  = capitalUsd * (riskParams.max_risk_per_trade_pct / 100);

    // Émettre l'order plan
    ctx.emit(
      "trading.strategy.order.plan",
      "strategy.order.plan.v1",
      { asset: p.symbol },
      {
        proposal_ref:      event.event_id,
        symbol:            p.symbol,
        side:              p.side,
        strategy:          p.strategy,
        strategy_id:       strategyId,
        wallet_id:         p.wallet_id ?? null,
        execution_target:  p.execution_target ?? "paper",
        confidence:        p.confidence,
        setup: {
          entry:        p.setup.entry,
          stop:         p.setup.stop,
          tp:           p.setup.tp,
          risk_reward:  p.setup.risk_reward,
          qty,
          value_usd:    valueUSD,
          risk_usd:     riskUSD,
          risk_pct:     riskParams.max_risk_per_trade_pct,
        },
        time_horizon:   p.time_horizon,
        regime:         p.regime,
        reasons:        p.reasons,
        created_at:     Date.now(),
        env:            process.env.TRADING_ENV ?? "paper",
      }
    );

    approved++;
    ctx.log(
      `✅ ${p.symbol} ${p.side} [${strategyId}] APPROUVÉ ` +
      `qty=${qty} value=$${valueUSD} risk=$${riskUSD.toFixed(2)} ` +
      `capital=$${capitalUsd} entry=${p.setup.entry} stop=${p.setup.stop} tp=${p.setup.tp}`
    );
  }

  ctx.state.cursors = { ...ctx.state.cursors, proposals: nextCursor };
  ctx.log(`✅ ${approved} approuvés | ${blocked} bloqués | ${hold} HOLD`);
}
