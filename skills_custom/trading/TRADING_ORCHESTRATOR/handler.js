/**
 * TRADING_ORCHESTRATOR — Handler
 *
 * Corrèle order.plan + policy.decision.
 * Orchestre l'exécution via trading.exec.order.submit.
 *
 * États : PENDING_POLICY → APPROVED/BLOCKED/PENDING_HUMAN/EXPIRED → EXECUTED
 * Zéro LLM. Logique d'état pure.
 * Fréquence : 10s
 */

import fs   from "fs";
import path from "path";

const PIPELINE_TTL_MS     = 10 * 60 * 1000; // 10 minutes
const TELEGRAM_BOT_TOKEN  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
const TELEGRAM_CHAT_ID    = process.env.TRADER_TELEGRAM_CHAT_ID;

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

// ─── Telegram notification approbation humaine ────────────────────────────────

async function notifyHumanApproval(entry) {
  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) return;
  const msg =
    `👤 *APPROBATION REQUISE*\n` +
    `Symbol: ${entry.plan.symbol} ${entry.plan.side}\n` +
    `Strategy: ${entry.plan.strategy}\n` +
    `Notional: $${entry.plan.setup?.value_usd?.toFixed(0) ?? "?"}\n` +
    `Raison: ${entry.policy_reason}\n` +
    `Ref: \`${entry.order_plan_ref}\`\n\n` +
    `Approuve via commande manuelle dans policy_overrides.json`;

  try {
    await fetch(
      `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`,
      {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          chat_id:    TELEGRAM_CHAT_ID,
          text:       msg,
          parse_mode: "Markdown",
        }),
      }
    );
  } catch (e) {
    // Non-bloquant
  }
}

// ─── Lecture bus incrémentale ─────────────────────────────────────────────────

function readSince(bus, topic, cursor) {
  const { events, nextCursor } = bus.readSince(topic, cursor, 200);
  return { events, nextCursor };
}

// ─── Handler principal ────────────────────────────────────────────────────────

export async function handler(ctx) {
  const stateFile    = path.join(ctx.stateDir, "memory", "TRADING_ORCHESTRATOR.state.json");
  const pipelineFile = path.join(ctx.stateDir, "memory", "pipeline_state.json");
  const auditFile    = path.join(ctx.stateDir, "memory", "orchestrator_audit.jsonl");

  // Charger état
  const state = ctx.state;
  if (!state.cursors) state.cursors = {
    "trading.strategy.order.plan":      0,
    "trading.strategy.policy.decision": 0,
  };
  if (!state.stats) state.stats = {
    runs: 0, submitted: 0, blocked: 0,
    expired: 0, human_required: 0, errors: 0,
    last_run_ts: 0,
  };

  // Pipeline en cours (keyed by order_plan_ref)
  const pipeline = readJSON(pipelineFile, {});

  // ── 1. Lire nouveaux order.plans ──────────────────────────────────────────
  const { events: newPlans, nextCursor: planCursor } = readSince(
    ctx.bus,
    "trading.strategy.order.plan",
    state.cursors["trading.strategy.order.plan"] ?? 0
  );

  for (const event of newPlans) {
    const plan = event.payload ?? event;
    const ref  = event.event_id ?? event.id ?? `plan_${Date.now()}`;

    if (pipeline[ref]) continue; // déjà connu

    pipeline[ref] = {
      order_plan_ref:  ref,
      status:          "PENDING_POLICY",
      plan,
      policy_decision: null,
      policy_reason:   null,
      created_at:      Date.now(),
      updated_at:      Date.now(),
    };

    ctx.log(`📥 ${plan.symbol} ${plan.side} [${plan.strategy}] → PENDING_POLICY (ref=${ref.slice(-8)})`);
  }
  state.cursors["trading.strategy.order.plan"] = planCursor;

  // ── 2. Lire nouvelles policy.decisions ────────────────────────────────────
  const { events: newDecisions, nextCursor: decisionCursor } = readSince(
    ctx.bus,
    "trading.strategy.policy.decision",
    state.cursors["trading.strategy.policy.decision"] ?? 0
  );

  for (const event of newDecisions) {
    const decision = event.payload ?? event;
    const planRef  = decision.order_plan_ref;
    if (!planRef || !pipeline[planRef]) continue;

    const entry = pipeline[planRef];
    if (entry.status !== "PENDING_POLICY") continue; // déjà traité

    entry.policy_decision = decision.decision;
    entry.policy_reason   = decision.reason;
    entry.variant_id      = decision.variant_id ?? "A";
    entry.experiment_id   = decision.experiment_id ?? null;
    entry.policy_event_id = event.event_id ?? null;
    entry.updated_at      = Date.now();

    switch (decision.decision) {

      case "APPROVED": {
        const submit = {
          order_plan_ref:      planRef,
          policy_decision_ref: entry.policy_event_id,
          symbol:              entry.plan.symbol,
          side:                entry.plan.side,
          strategy_id:         entry.plan.strategy,
          variant_id:          entry.variant_id,
          experiment_id:       entry.experiment_id,
          setup: {
            entry:     entry.plan.setup?.entry,
            stop:      entry.plan.setup?.stop,
            tp:        entry.plan.setup?.tp,
            qty:       entry.plan.setup?.qty,
            value_usd: entry.plan.setup?.value_usd,
          },
          env:          entry.plan.env ?? "paper",
          submitted_at: Date.now(),
        };

        ctx.emit(
          "trading.exec.order.submit",
          "exec.order.submit.v1",
          { asset: entry.plan.symbol },
          submit
        );

        entry.status     = "EXECUTED";
        entry.submit     = submit;
        state.stats.submitted++;

        ctx.log(`✅ ${entry.plan.symbol} ${entry.plan.side} → EXECUTED (submit envoyé)`);
        appendJSONL(auditFile, { ...entry, event: "SUBMITTED", ts: Date.now() });
        break;
      }

      case "BLOCKED": {
        entry.status = "BLOCKED";
        state.stats.blocked++;
        ctx.log(`🚫 ${entry.plan.symbol} ${entry.plan.side} → BLOCKED — ${decision.reason}`);
        appendJSONL(auditFile, { ...entry, event: "BLOCKED", ts: Date.now() });
        break;
      }

      case "HUMAN_APPROVAL_REQUIRED": {
        entry.status = "PENDING_HUMAN";
        state.stats.human_required++;
        ctx.log(`👤 ${entry.plan.symbol} ${entry.plan.side} → PENDING_HUMAN — ${decision.reason}`);
        appendJSONL(auditFile, { ...entry, event: "PENDING_HUMAN", ts: Date.now() });
        await notifyHumanApproval(entry);
        break;
      }
    }
  }
  state.cursors["trading.strategy.policy.decision"] = decisionCursor;

  // ── 3. Expirer les entrées trop vieilles ──────────────────────────────────
  const now = Date.now();
  for (const [ref, entry] of Object.entries(pipeline)) {
    if (entry.status !== "PENDING_POLICY" && entry.status !== "PENDING_HUMAN") continue;
    if (now - entry.created_at > PIPELINE_TTL_MS) {
      entry.status     = "EXPIRED";
      entry.updated_at = now;
      state.stats.expired++;
      ctx.log(`⏰ ${entry.plan?.symbol} → EXPIRED (${Math.round((now - entry.created_at) / 60000)}min)`);
      appendJSONL(auditFile, { ...entry, event: "EXPIRED", ts: now });
    }
  }

  // ── 4. Nettoyer pipeline — garder seulement les 200 derniers ──────────────
  const entries  = Object.entries(pipeline);
  const terminal = ["EXECUTED", "BLOCKED", "EXPIRED"];
  const active   = entries.filter(([, e]) => !terminal.includes(e.status));
  const done     = entries
    .filter(([, e]) => terminal.includes(e.status))
    .sort(([, a], [, b]) => b.updated_at - a.updated_at)
    .slice(0, 100);

  const cleaned = Object.fromEntries([...active, ...done]);
  writeJSON(pipelineFile, cleaned);

  // ── 5. Sauvegarder état ───────────────────────────────────────────────────
  // agentRuntime sauvegarde ctx.state automatiquement

  const pending = active.length;
  if (pending > 0 || newPlans.length > 0) {
    ctx.log(
      `[TRADING_ORCHESTRATOR] ✅ ` +
      `submitted=${state.stats.submitted} blocked=${state.stats.blocked} ` +
      `expired=${state.stats.expired} pending=${pending}`
    );
  }
}
