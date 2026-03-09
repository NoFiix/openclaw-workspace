/**
 * POLICY_ENGINE — Handler
 *
 * Vérifie qu'un order.plan respecte les règles du système.
 * Produit : trading.strategy.policy.decision
 *
 * Décisions : APPROVED / BLOCKED / HUMAN_APPROVAL_REQUIRED
 * Zéro LLM. Logique de règles pure.
 * Fréquence : 30s
 */

import fs   from "fs";
import path from "path";

// ─── Helpers ──────────────────────────────────────────────────────────────────

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

// ─── Lecture bus ──────────────────────────────────────────────────────────────

function readNewOrderPlans(bus, cursor) {
  const { events, nextCursor } = bus.readSince(
    "trading.strategy.order.plan", cursor, 100
  );
  return { plans: events, nextCursor };
}

// ─── Kill switch ──────────────────────────────────────────────────────────────

function getKillswitch(stateDir) {
  const p = path.join(stateDir, "exec", "killswitch.json");
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return { state: "ARMED" }; }
}

// ─── Plage horaire ────────────────────────────────────────────────────────────

function isTimeWindowAllowed(cfg) {
  if (!cfg.time_windows?.enabled) return true;
  const forbidden = cfg.time_windows.forbidden_hours_utc ?? [];
  if (!forbidden.length) return true;
  const hourUTC = new Date().getUTCHours();
  return !forbidden.includes(hourUTC);
}

// ─── A/B testing ──────────────────────────────────────────────────────────────

function resolveVariant(strategyId, cfg) {
  if (!cfg.ab_testing?.enabled) {
    return { variant_id: "A", experiment_id: null };
  }

  const experiments = cfg.ab_testing.experiments ?? [];
  const exp = experiments.find(e =>
    e.strategy_id === strategyId && e.active
  );

  if (!exp) return { variant_id: "A", experiment_id: null };

  // Shadow testing : A exécute, B observe
  // Alternance simple basée sur le timestamp
  const slot = Math.floor(Date.now() / 60000) % 2; // alterne chaque minute
  const variant = slot === 0 ? "A" : "B";

  return {
    variant_id:    variant,
    experiment_id: exp.experiment_id,
  };
}

// ─── Vérification des règles ──────────────────────────────────────────────────

function checkPolicy(plan, cfg, ks) {
  const checks = {
    killswitch_armed:          false,
    asset_allowed:             false,
    not_blacklisted:           false,
    strategy_allowed:          false,
    env_allowed:               false,
    time_window_allowed:       false,
    notional_below_threshold:  false,
  };

  let blockedReason = null;

  // 1. Kill switch
  checks.killswitch_armed = ks.state !== "TRIPPED";
  if (!checks.killswitch_armed) {
    return { decision: "BLOCKED", reason: `killswitch_tripped: ${ks.reason ?? "unknown"}`, checks };
  }

  // 2. Asset autorisé
  checks.asset_allowed = (cfg.allowed_assets ?? []).includes(plan.symbol);
  if (!checks.asset_allowed) {
    return { decision: "BLOCKED", reason: `asset_not_allowed: ${plan.symbol}`, checks };
  }

  // 3. Asset non blacklisté
  checks.not_blacklisted = !(cfg.blacklisted_assets ?? []).includes(plan.symbol);
  if (!checks.not_blacklisted) {
    return { decision: "BLOCKED", reason: `asset_blacklisted: ${plan.symbol}`, checks };
  }

  // 4. Stratégie autorisée
  checks.strategy_allowed = (cfg.allowed_strategies ?? []).includes(plan.strategy);
  if (!checks.strategy_allowed) {
    return { decision: "BLOCKED", reason: `strategy_not_allowed: ${plan.strategy}`, checks };
  }

  // 5. Environnement cohérent
  const currentEnv = process.env.TRADING_ENV ?? cfg.env ?? "paper";
  checks.env_allowed = plan.env === currentEnv;
  if (!checks.env_allowed) {
    return { decision: "BLOCKED", reason: `env_mismatch: plan=${plan.env} system=${currentEnv}`, checks };
  }

  // 6. Plage horaire
  checks.time_window_allowed = isTimeWindowAllowed(cfg);
  if (!checks.time_window_allowed) {
    const h = new Date().getUTCHours();
    return { decision: "BLOCKED", reason: `forbidden_time_window: ${h}h UTC`, checks };
  }

  // 7. Notional — approbation humaine si dépassé
  const notional   = plan.setup?.value_usd ?? 0;
  const threshold  = cfg.notional_human_approval_usd ?? 5000;
  checks.notional_below_threshold = notional < threshold;
  if (!checks.notional_below_threshold) {
    return {
      decision: "HUMAN_APPROVAL_REQUIRED",
      reason:   `notional_above_threshold: $${notional} > $${threshold}`,
      checks,
    };
  }

  return { decision: "APPROVED", reason: "all_policies_passed", checks };
}

// ─── Handler principal ────────────────────────────────────────────────────────

export async function handler(ctx) {
  // Charger config
  const configFile = path.join(ctx.stateDir, "configs", "POLICY_ENGINE.config.json");
  const cfg = readJSON(configFile, {
    policy_version:               "2026-03-09-v1",
    env:                          "paper",
    allowed_assets:               ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
    allowed_strategies:           ["MeanReversion", "Momentum", "Breakout", "NewsTrading"],
    blacklisted_assets:           [],
    time_windows:                 { enabled: false, forbidden_hours_utc: [] },
    notional_human_approval_usd:  5000,
    ab_testing:                   { enabled: false, experiments: [] },
  });

  // Charger état (curseur bus)
  const state = ctx.state;
  if (!state.cursors) state.cursors = { "trading.strategy.order.plan": 0 };
  if (!state.stats)   state.stats   = { runs: 0, approved: 0, blocked: 0, human_required: 0, errors: 0, last_run_ts: 0 };

  // Kill switch
  const ks = getKillswitch(ctx.stateDir);

  // Lire nouveaux order.plans
  const { plans, nextCursor } = readNewOrderPlans(
    ctx.bus,
    state.cursors["trading.strategy.order.plan"] ?? 0
  );

  if (plans.length === 0) {
    return;
  }

  ctx.log(`[POLICY_ENGINE] ${plans.length} order.plan(s) à évaluer`);

  const auditFile = path.join(ctx.stateDir, "memory", "policy_decisions.jsonl");

  for (const event of plans) {
    const plan = event.payload ?? event;
    if (!plan.symbol) continue;

    try {
      // Vérifier les règles
      const { decision, reason, checks } = checkPolicy(plan, cfg, ks);

      // Résoudre variant A/B
      const { variant_id, experiment_id } = resolveVariant(plan.strategy, cfg);

      const policyDecision = {
        order_plan_ref:         event.event_id ?? event.id ?? null,
        symbol:                 plan.symbol,
        side:                   plan.side,
        strategy_id:            plan.strategy,
        variant_id,
        experiment_id,
        decision,
        reason,
        requires_human_approval: decision === "HUMAN_APPROVAL_REQUIRED",
        policy_version:         cfg.policy_version,
        checks,
        decided_at:             Date.now(),
      };

      // Émettre
      ctx.emit(
        "trading.strategy.policy.decision",
        "strategy.policy.decision.v1",
        { asset: plan.symbol },
        policyDecision
      );

      // Audit log
      appendJSONL(auditFile, policyDecision);

      // Stats + log
      const emoji = decision === "APPROVED"                ? "✅"
                  : decision === "HUMAN_APPROVAL_REQUIRED" ? "👤"
                  : "🚫";

      ctx.log(`  ${emoji} ${plan.symbol} ${plan.side} [${plan.strategy}] → ${decision} — ${reason}`);

      if (decision === "APPROVED")                state.stats.approved++;
      else if (decision === "BLOCKED")            state.stats.blocked++;
      else if (decision === "HUMAN_APPROVAL_REQUIRED") state.stats.human_required++;

    } catch (e) {
      ctx.log(`  ⚠️ ${plan.symbol}: erreur — ${e.message}`);
      state.stats.errors++;
    }
  }

  state.cursors["trading.strategy.order.plan"] = nextCursor;
  ctx.log(`[POLICY_ENGINE] ✅ approved=${state.stats.approved} blocked=${state.stats.blocked} human=${state.stats.human_required}`);

}
