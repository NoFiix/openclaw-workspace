/**
 * strategy_utils.js — Helper partagé unique pour le registry multi-stratégies
 *
 * Centralise TOUTE la logique registry / wallet / auto-init / circuit breaker.
 * Aucun autre composant ne duplique cette logique.
 */

import fs   from "fs";
import path from "path";

const STATE_DIR = process.env.STATE_DIR ?? "/home/node/.openclaw/workspace/state/trading";

// ─── Registry ──────────────────────────────────────────────────────────────

const REGISTRY_PATH = path.join(STATE_DIR, "configs", "strategies_registry.json");

const REQUIRED_FIELDS = [
  "strategy_id", "enabled", "wallet_id", "wallet_mode",
  "execution_target", "initial_capital", "min_cash_threshold",
  "risk_params", "state_dir",
];

const REQUIRED_RISK_FIELDS = [
  "max_risk_per_trade_pct", "max_open_positions", "min_confidence",
];

const VALID_WALLET_MODES      = ["virtual", "real"];
const VALID_EXECUTION_TARGETS = ["paper", "testnet", "live"];

/**
 * Validate the full registry. Returns { valid, errors }.
 */
export function validateRegistry(registry) {
  const errors = [];
  const walletIds = new Set();
  const stateDirs = new Set();

  for (const [key, entry] of Object.entries(registry)) {
    const prefix = `[${key}]`;

    // Key must match strategy_id
    if (entry.strategy_id !== key) {
      errors.push(`${prefix} strategy_id "${entry.strategy_id}" !== key "${key}"`);
    }

    // Required fields
    for (const field of REQUIRED_FIELDS) {
      if (entry[field] === undefined || entry[field] === null) {
        errors.push(`${prefix} missing required field: ${field}`);
      }
    }

    // Required risk_params fields
    if (entry.risk_params) {
      for (const rf of REQUIRED_RISK_FIELDS) {
        if (entry.risk_params[rf] === undefined) {
          errors.push(`${prefix} risk_params missing: ${rf}`);
        }
      }
    }

    // Numeric validations
    if (entry.initial_capital !== undefined && entry.initial_capital <= 0) {
      errors.push(`${prefix} initial_capital must be > 0, got ${entry.initial_capital}`);
    }
    if (entry.min_cash_threshold !== undefined && entry.min_cash_threshold < 0) {
      errors.push(`${prefix} min_cash_threshold must be >= 0, got ${entry.min_cash_threshold}`);
    }

    // Enum validations
    if (entry.wallet_mode && !VALID_WALLET_MODES.includes(entry.wallet_mode)) {
      errors.push(`${prefix} invalid wallet_mode: "${entry.wallet_mode}"`);
    }
    if (entry.execution_target && !VALID_EXECUTION_TARGETS.includes(entry.execution_target)) {
      errors.push(`${prefix} invalid execution_target: "${entry.execution_target}"`);
    }

    // Live guard
    if (entry.execution_target === "live" && entry.live_approved !== true) {
      errors.push(`${prefix} execution_target is "live" but live_approved is not true — BLOCKED`);
    }

    // Uniqueness checks
    if (entry.wallet_id) {
      if (walletIds.has(entry.wallet_id)) {
        errors.push(`${prefix} duplicate wallet_id: "${entry.wallet_id}"`);
      }
      walletIds.add(entry.wallet_id);
    }
    if (entry.state_dir) {
      if (stateDirs.has(entry.state_dir)) {
        errors.push(`${prefix} duplicate state_dir: "${entry.state_dir}"`);
      }
      stateDirs.add(entry.state_dir);
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Load and validate the registry. Throws on invalid registry.
 */
export function loadRegistry() {
  if (!fs.existsSync(REGISTRY_PATH)) {
    throw new Error(`[strategy_utils] Registry not found: ${REGISTRY_PATH}`);
  }
  const registry = JSON.parse(fs.readFileSync(REGISTRY_PATH, "utf-8"));
  const { valid, errors } = validateRegistry(registry);
  if (!valid) {
    throw new Error(`[strategy_utils] Invalid registry:\n  ${errors.join("\n  ")}`);
  }
  return registry;
}

// ─── Strategy config resolution ─────────────────────────────────────────────

/**
 * Return full config for a given strategy_id, including risk_params.
 */
export function resolveStrategyConfig(strategyId) {
  const registry = loadRegistry();
  const config = registry[strategyId];
  if (!config) {
    throw new Error(`[strategy_utils] Strategy not found in registry: ${strategyId}`);
  }
  return config;
}

/**
 * Return the execution_target for a given strategy_id.
 */
export function resolveExecutionTarget(strategyId) {
  return resolveStrategyConfig(strategyId).execution_target;
}

// ─── State directory & auto-init ────────────────────────────────────────────

function strategyStateDir(strategyId) {
  const config = resolveStrategyConfig(strategyId);
  return path.join(STATE_DIR, config.state_dir);
}

/**
 * Create the state directory and initial files if they don't exist.
 */
export function initStrategyState(strategyId) {
  const config = resolveStrategyConfig(strategyId);
  const dir    = path.join(STATE_DIR, config.state_dir);

  if (fs.existsSync(path.join(dir, "wallet.json"))) {
    return; // Already initialized
  }

  fs.mkdirSync(dir, { recursive: true });

  const now = new Date().toISOString();
  const wallet = {
    strategy_id:      strategyId,
    wallet_id:        config.wallet_id,
    wallet_mode:      config.wallet_mode,
    initial_capital:  config.initial_capital,
    cash:             config.initial_capital,
    equity:           config.initial_capital,
    allocated:        0,
    realized_pnl:     0,
    unrealized_pnl:   0,
    roi_pct:          0,
    max_drawdown:     0,
    peak_equity:      config.initial_capital,
    trade_count:      0,
    win_count:        0,
    status:           "active",
    suspended_reason: null,
    created_at:       now,
    updated_at:       now,
  };

  writeJSONSafe(path.join(dir, "wallet.json"), wallet);
  writeJSONSafe(path.join(dir, "positions.json"), []);

  if (!fs.existsSync(path.join(dir, "trades_history.jsonl"))) {
    fs.writeFileSync(path.join(dir, "trades_history.jsonl"), "");
  }
  if (!fs.existsSync(path.join(dir, "metrics.json"))) {
    fs.writeFileSync(path.join(dir, "metrics.json"), "null");
  }

  console.log(`[strategy_utils] Auto-init: ${strategyId} — wallet $${config.initial_capital}`);
}

// ─── Wallet operations ──────────────────────────────────────────────────────

function writeJSONSafe(p, data) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(data, null, 2));
}

/**
 * Load wallet for a strategy. Auto-inits if missing.
 */
export function loadWallet(strategyId) {
  initStrategyState(strategyId); // defensive auto-init
  const dir = strategyStateDir(strategyId);
  const p   = path.join(dir, "wallet.json");
  return JSON.parse(fs.readFileSync(p, "utf-8"));
}

/**
 * Save wallet for a strategy.
 */
export function saveWallet(strategyId, wallet) {
  const dir = strategyStateDir(strategyId);
  wallet.updated_at = new Date().toISOString();
  writeJSONSafe(path.join(dir, "wallet.json"), wallet);
}

// ─── Circuit breaker ────────────────────────────────────────────────────────

// ─── Wallet tracking helpers ────────────────────────────────────────────────

/**
 * Update wallet after opening a position.
 * Deducts allocated capital from cash.
 * Guard BUG-004-b: skip if cash after deduction would be below min_cash_threshold.
 */
export function walletOnOpen(strategyId, valueUsd) {
  const wallet = loadWallet(strategyId);

  // Guard BUG-004-b: prevent double deduction in same run from corrupting wallet
  const minCash = 50; // matches strategies_registry default min_cash_threshold
  const cashAfter = wallet.equity - ((wallet.allocated ?? 0) + valueUsd);
  if (cashAfter < minCash) {
    console.log(
      `[walletOnOpen] SKIP ${strategyId}: cash after deduction would be ` +
      `$${cashAfter.toFixed(2)} < threshold $${minCash} ` +
      `(equity=$${wallet.equity} allocated=$${wallet.allocated ?? 0} value=$${valueUsd.toFixed(2)})`
    );
    return wallet;
  }

  wallet.allocated   = (wallet.allocated ?? 0) + valueUsd;
  wallet.cash        = wallet.equity - wallet.allocated;
  wallet.updated_at  = new Date().toISOString();
  saveWallet(strategyId, wallet);
  return wallet;
}

/**
 * Update wallet after closing a position.
 * Returns capital + PnL to cash, updates metrics.
 */
export function walletOnClose(strategyId, valueUsd, pnlUsd) {
  const wallet = loadWallet(strategyId);
  wallet.allocated    = Math.max(0, (wallet.allocated ?? 0) - valueUsd);
  wallet.realized_pnl = (wallet.realized_pnl ?? 0) + pnlUsd;
  // Recalculate from invariants — immune to Open/Close desync (BUG-020)
  wallet.equity       = wallet.initial_capital + wallet.realized_pnl;
  wallet.cash         = wallet.equity - wallet.allocated;
  wallet.roi_pct      = parseFloat(((wallet.equity - wallet.initial_capital) / wallet.initial_capital * 100).toFixed(4));
  wallet.trade_count  = (wallet.trade_count ?? 0) + 1;
  if (pnlUsd > 0) wallet.win_count = (wallet.win_count ?? 0) + 1;
  wallet.peak_equity  = Math.max(wallet.peak_equity ?? wallet.initial_capital, wallet.equity);
  wallet.max_drawdown = Math.max(
    wallet.max_drawdown ?? 0,
    parseFloat(((wallet.peak_equity - wallet.equity) / wallet.peak_equity * 100).toFixed(4))
  );
  wallet.updated_at   = new Date().toISOString();
  saveWallet(strategyId, wallet);
  return wallet;
}

// ─── Circuit breaker ────────────────────────────────────────────────────────

/**
 * Returns true if circuit breaker is tripped (cash below threshold).
 */
export function isCircuitBreakerTripped(wallet, config) {
  return wallet.cash < (config.min_cash_threshold ?? 0);
}

/**
 * Suspend a strategy: set status to "suspended", log, optionally notify Telegram.
 */
export function suspendStrategy(strategyId, reason) {
  const wallet = loadWallet(strategyId);
  wallet.status           = "suspended";
  wallet.suspended_reason = reason;
  saveWallet(strategyId, wallet);

  console.log(`[strategy_utils] SUSPENDED: ${strategyId} — ${reason}`);

  // Telegram notification (non-blocking)
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;
  if (token && chatId) {
    fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        chat_id:    chatId,
        text:       `🚨 *CIRCUIT BREAKER*\nStratégie: ${strategyId}\nRaison: ${reason}`,
        parse_mode: "Markdown",
      }),
    }).catch(() => {});
  }
}

// ─── Candidate management (objet indexé par candidate_id) ──────────────────

const CANDIDATES_PATH = path.join(STATE_DIR, "configs", "candidates_pending.json");
const CANDIDATE_TTL_PENDING_DAYS  = 14;
const CANDIDATE_TTL_REJECTED_DAYS = 14;
const CANDIDATE_TTL_EXPIRED_DAYS  = 30;

function emptyCandidates() { return { last_seq: 0, candidates: {} }; }

export function loadCandidates() {
  if (!fs.existsSync(CANDIDATES_PATH)) return emptyCandidates();
  try {
    const raw = JSON.parse(fs.readFileSync(CANDIDATES_PATH, "utf-8"));
    // Migration: if candidates is an array, convert to object
    if (Array.isArray(raw.candidates)) {
      const obj = {};
      for (const c of raw.candidates) if (c.candidate_id) obj[c.candidate_id] = c;
      return { last_seq: raw.last_seq ?? Object.keys(obj).length, candidates: obj };
    }
    return { last_seq: raw.last_seq ?? 0, candidates: raw.candidates ?? {} };
  } catch { return emptyCandidates(); }
}

export function saveCandidates(data) {
  writeJSONSafe(CANDIDATES_PATH, data);
}

function normalizeStrategyName(name) {
  return (name ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function findDuplicateCandidate(data, candidateName) {
  const normalized = normalizeStrategyName(candidateName);
  for (const c of Object.values(data.candidates)) {
    if (c.status === "rejected" || c.status === "expired") continue;
    if (normalizeStrategyName(c.strategy_name) === normalized) return c;
  }
  return null;
}

export function addCandidate(candidate) {
  const data = loadCandidates();
  const dup = findDuplicateCandidate(data, candidate.strategy_name);
  if (dup) return { added: false, reason: "duplicate", existing: dup };

  data.last_seq = (data.last_seq ?? 0) + 1;
  const seq = data.last_seq;
  const now = new Date();
  const id = `cand_${now.toISOString().slice(0,10).replace(/-/g,"")}_${String(seq).padStart(3,"0")}`;

  const full = {
    candidate_id: id,
    candidate_seq: `#C-${String(seq).padStart(4,"0")}`,
    created_at: now.toISOString(),
    status: "pending_review",
    registry_synced: false,
    telegram_message_id: null,
    sent_at: null,
    compatibility: candidate.compatibility ?? "dev_required",
    compatibility_reason: candidate.compatibility_reason ?? "",
    strategy_name: candidate.strategy_name,
    strategy_label: candidate.strategy_label ?? candidate.strategy_name,
    source: candidate.source ?? "unknown",
    source_url: candidate.source_url ?? null,
    summary: candidate.summary ?? "",
    who_uses_it: candidate.who_uses_it ?? "",
    why_it_might_work: candidate.why_it_might_work ?? "",
    entry_logic: candidate.entry_logic ?? "",
    exit_logic: candidate.exit_logic ?? "",
    markets: candidate.markets ?? ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
    timeframes: candidate.timeframes ?? ["1h", "4h"],
    indicators_required: candidate.indicators_required ?? [],
    confidence_score: candidate.confidence_score ?? 0.5,
    implementation_notes: candidate.implementation_notes ?? "",
    validated_at: null,
    rejected_at: null,
    expired_at: null,
    rejection_reason: null,
  };

  data.candidates[id] = full;
  saveCandidates(data);
  return { added: true, candidate: full };
}

/**
 * Send plain-text Telegram notification for a candidate (no Markdown, no buttons).
 * Returns message_id or null. Stores sent_at only on success.
 */
export async function sendCandidateTelegram(candidateId) {
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;
  if (!token || !chatId) { console.log("[strategy_utils] Telegram tokens missing"); return null; }

  const data = loadCandidates();
  const cand = data.candidates[candidateId];
  if (!cand) { console.log(`[strategy_utils] Candidate ${candidateId} not found`); return null; }
  if (cand.telegram_message_id) { console.log(`[strategy_utils] ${candidateId} already sent (msg ${cand.telegram_message_id})`); return cand.telegram_message_id; }

  const compat = cand.compatibility === "config_ready" ? "Config-ready" : "Dev requis";

  const text = [
    "NOUVELLE STRATEGIE DETECTEE",
    "",
    `${cand.strategy_name}`,
    `${cand.candidate_seq} - ${cand.candidate_id}`,
    `Compatibilite : ${compat}`,
    "",
    "Qui l'utilise",
    cand.who_uses_it || "Non specifie",
    "",
    "Pourquoi ca peut marcher",
    cand.why_it_might_work || "Non specifie",
    "",
    "Entree",
    cand.entry_logic || "Non specifie",
    "",
    "Sortie",
    cand.exit_logic || "Non specifie",
    "",
    `Timeframes : ${(cand.timeframes ?? []).join(", ")}`,
    `Marches : ${(cand.markets ?? []).join(", ")}`,
    `Indicateurs : ${(cand.indicators_required ?? []).join(", ")}`,
    "",
    `Score de confiance : ${Math.round((cand.confidence_score ?? 0) * 100)}%`,
    "",
    "Notes d'implementation :",
    cand.implementation_notes || "Aucune",
    "",
    "Pour valider ou rejeter :",
    "Modifier le champ status dans candidates_pending.json",
    "",
    "Valeurs possibles :",
    "  approved_config_ready",
    "  approved_dev_required",
    "  rejected",
  ].join("\n");

  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text }),
    });
    const result = await res.json();
    if (result.ok && result.result?.message_id) {
      const msgId = result.result.message_id;
      cand.telegram_message_id = msgId;
      cand.sent_at = new Date().toISOString();
      saveCandidates(data);
      console.log(`[strategy_utils] Telegram sent for ${candidateId} — message_id: ${msgId}`);
      return msgId;
    }
    console.log(`[strategy_utils] Telegram send failed for ${candidateId}: ${JSON.stringify(result)}`);
    return null;
  } catch (e) {
    console.log(`[strategy_utils] Telegram error for ${candidateId}: ${e.message}`);
    return null;
  }
}

/**
 * Process approved/rejected candidates found in the file.
 * Called by STRATEGY_SCOUT at each run.
 */
export function processApprovedCandidates(log = console.log) {
  const data = loadCandidates();
  let changed = false;

  for (const [id, cand] of Object.entries(data.candidates)) {
    if (cand.registry_synced) continue;

    if (cand.status === "approved_config_ready") {
      const strategyId = cand.strategy_name.replace(/[^a-zA-Z0-9]/g, "");
      const walletId   = "wallet_" + cand.strategy_name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/_+$/, "");

      const registry = loadRegistry();
      if (registry[strategyId]) {
        log(`[STRATEGY_SCOUT] ${cand.strategy_name} already in registry — marking synced`);
        cand.registry_synced = true;
        cand.validated_at = cand.validated_at ?? new Date().toISOString();
        changed = true;
        continue;
      }

      const newEntry = {
        strategy_id: strategyId, strategy_label: cand.strategy_label ?? cand.strategy_name,
        enabled: false, lifecycle_status: "paper_ready",
        wallet_id: walletId, wallet_mode: "virtual",
        execution_target: "paper", live_approved: false,
        initial_capital: 1000, min_cash_threshold: 50,
        risk_params: { max_risk_per_trade_pct: 2, max_open_positions: 2, max_daily_loss_pct: 5, min_confidence: 0.5, min_risk_reward: 2, cooldown_minutes: 30 },
        state_dir: `strategies/${strategyId}`,
      };

      registry[strategyId] = newEntry;
      const { valid, errors } = validateRegistry(registry);
      if (!valid) {
        log(`[STRATEGY_SCOUT] Registry validation failed for ${cand.strategy_name}: ${errors.join("; ")}`);
        continue;
      }

      const regPath = path.join(STATE_DIR, "configs", "strategies_registry.json");
      writeJSONSafe(regPath, registry);
      initStrategyState(strategyId);
      cand.registry_synced = true;
      cand.validated_at = cand.validated_at ?? new Date().toISOString();
      changed = true;
      log(`[STRATEGY_SCOUT] ${cand.strategy_name} added to registry — paper_ready, enabled:false`);

    } else if (cand.status === "approved_dev_required") {
      cand.registry_synced = true;
      cand.validated_at = cand.validated_at ?? new Date().toISOString();
      changed = true;
      log(`[STRATEGY_SCOUT] ${cand.strategy_name} approved (dev required) — not added to registry`);

    } else if (cand.status === "rejected") {
      cand.rejected_at = cand.rejected_at ?? new Date().toISOString();
      cand.registry_synced = true;
      changed = true;
    }
  }

  if (changed) saveCandidates(data);
}

/**
 * Clean up expired candidates based on TTL rules.
 */
export function cleanupExpiredCandidates(log = console.log) {
  const data = loadCandidates();
  const now  = Date.now();
  let changed = false;

  for (const [id, cand] of Object.entries(data.candidates)) {
    const ageMs = now - new Date(cand.created_at).getTime();
    const ageDays = ageMs / (24 * 3600 * 1000);
    const seq = cand.candidate_seq ?? id;

    if (cand.status === "pending_review" && ageDays > CANDIDATE_TTL_PENDING_DAYS) {
      cand.status = "expired";
      cand.expired_at = new Date().toISOString();
      changed = true;
      log(`[cleanup] ${id} (${seq}) expire - ${Math.floor(ageDays)} jours sans traitement`);
    } else if (cand.status === "rejected" && ageDays > CANDIDATE_TTL_REJECTED_DAYS) {
      delete data.candidates[id];
      changed = true;
      log(`[cleanup] ${id} (${seq}) purge - rejected depuis ${Math.floor(ageDays)} jours`);
    } else if (cand.status === "expired" && ageDays > CANDIDATE_TTL_EXPIRED_DAYS) {
      delete data.candidates[id];
      changed = true;
      log(`[cleanup] ${id} (${seq}) purge - expired depuis ${Math.floor(ageDays)} jours`);
    }
  }

  if (changed) saveCandidates(data);
}
