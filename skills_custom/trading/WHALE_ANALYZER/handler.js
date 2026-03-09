/**
 * WHALE_ANALYZER — Handler
 *
 * Transforme les transferts whale bruts en signal consultatif par actif.
 * Aucun LLM. Zéro coût token. Logique pure.
 *
 * Input  : trading.raw.whale.transfer
 * Output : trading.intel.whale.signal
 *
 * Fréquence : 300s (5min), jitter +60s → tourne après WHALE_FEED
 * Adresses  : chargées depuis state/trading/configs/exchange_addresses.json
 */

import fs   from "fs";
import path from "path";

const STABLECOINS = new Set(["USDT", "USDC", "DAI", "BUSD"]);

// ─── Helpers ──────────────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

// ─── Chargement adresses depuis fichier externe ───────────────────────────────

function loadAddressSets(stateDir) {
  const file = path.join(stateDir, "configs", "exchange_addresses.json");
  const data = readJSON(file, {});

  const exchangeAddrs  = new Set();
  const bridgeAddrs    = new Set();
  const protocolAddrs  = new Set();
  const mmAddrs        = new Set(); // market makers — contexte seulement
  const stableIssuers  = new Set();

  // Exchanges → signal TO/FROM_EXCHANGE
  for (const wallets of Object.values(data.exchanges ?? {})) {
    for (const addr of wallets) exchangeAddrs.add(addr.toLowerCase());
  }

  // Bridges + protocoles → à filtrer
  for (const wallets of Object.values(data.bridges ?? {})) {
    for (const addr of wallets) bridgeAddrs.add(addr.toLowerCase());
  }
  for (const wallets of Object.values(data.protocol_contracts ?? {})) {
    for (const addr of wallets) protocolAddrs.add(addr.toLowerCase());
  }

  // Market makers → catégorie séparée (pas exchange)
  for (const wallets of Object.values(data.market_makers ?? {})) {
    for (const addr of wallets) mmAddrs.add(addr.toLowerCase());
  }

  // Stablecoin issuers → STABLE_MINT signal
  for (const wallets of Object.values(data.stablecoin_issuers ?? {})) {
    for (const addr of wallets) stableIssuers.add(addr.toLowerCase());
  }

  return { exchangeAddrs, bridgeAddrs, protocolAddrs, mmAddrs, stableIssuers };
}

// ─── Lecture bus ──────────────────────────────────────────────────────────────

function readBusTopic(busDir, topic, cursor) {
  const file = path.join(busDir, `${topic.replace(/\./g, "_")}.jsonl`);
  if (!fs.existsSync(file)) return { events: [], newCursor: cursor };
  const lines = fs.readFileSync(file, "utf-8").trim().split("\n").filter(Boolean);
  const events = [];
  for (let i = cursor; i < lines.length; i++) {
    try { events.push(JSON.parse(lines[i])); } catch { /* skip */ }
  }
  return { events, newCursor: lines.length };
}

// ─── Classification ───────────────────────────────────────────────────────────

function classifyTransfer(payload, sets) {
  const from  = (payload.from || "").toLowerCase();
  const to    = (payload.to   || "").toLowerCase();
  const asset = payload.asset;

  const fromExchange  = sets.exchangeAddrs.has(from);
  const toExchange    = sets.exchangeAddrs.has(to);
  const fromBridge    = sets.bridgeAddrs.has(from)   || sets.protocolAddrs.has(from);
  const toBridge      = sets.bridgeAddrs.has(to)     || sets.protocolAddrs.has(to);
  const fromMM        = sets.mmAddrs.has(from);
  const toMM          = sets.mmAddrs.has(to);
  const fromIssuer    = sets.stableIssuers.has(from);
  const isStable      = STABLECOINS.has(asset);

  // ── Filtres faux positifs ──────────────────────────────────────────────────
  if (fromBridge || toBridge)           return null; // bridge/protocole
  if (fromExchange && toExchange)       return null; // interne exchange
  if (fromMM && toMM)                   return null; // interne MM

  // ── Stablecoin mint (issuer → marché) ─────────────────────────────────────
  if (fromIssuer && isStable)           return "STABLE_MINT"; // liquidité créée

  // ── Stablecoin vers exchange ───────────────────────────────────────────────
  if (isStable && toExchange)           return "STABLE_TO_EXCHANGE"; // buying power entrant

  // ── Flux exchange ─────────────────────────────────────────────────────────
  if (toExchange)                       return "TO_EXCHANGE";    // pression vendeuse
  if (fromExchange)                     return "FROM_EXCHANGE";  // accumulation

  // ── Market maker context ───────────────────────────────────────────────────
  if ((fromMM || toMM) && !isStable)    return "MM_FLOW"; // contexte seulement

  // ── Stable inflow générique (unknown → unknown mais stable) ───────────────
  if (isStable && !fromExchange && !toExchange) return "STABLE_INFLOW";

  return null; // unknown→unknown sans contexte : skip Sprint 1
}

// ─── Score glissant ───────────────────────────────────────────────────────────

function computeScore(events, weights, windowHours) {
  const cutoff = Date.now() - windowHours * 60 * 60 * 1000;
  const recent = events.filter(e => e.ts > cutoff);

  const components = {
    to_exchange_count:       0,
    from_exchange_count:     0,
    stable_to_exchange_count: 0,
    stable_mint_count:       0,
    stable_inflow_count:     0,
    mm_flow_count:           0,
    dex_whale_buy_count:     0,
    dex_whale_sell_count:    0,
  };
  const notional = {
    to_exchange:        0,
    from_exchange:      0,
    stable_to_exchange: 0,
    stable_mint:        0,
    stable_inflow:      0,
    dex_buys:           0,
    dex_sells:          0,
  };

  let raw = 0;

  for (const e of recent) {
    switch (e.type) {
      case "TO_EXCHANGE":
        raw += weights.to_exchange ?? -0.35;
        components.to_exchange_count++;
        notional.to_exchange += e.usd;
        break;
      case "FROM_EXCHANGE":
        raw += weights.from_exchange ?? 0.35;
        components.from_exchange_count++;
        notional.from_exchange += e.usd;
        break;
      case "STABLE_TO_EXCHANGE":
        raw += weights.stable_to_exchange ?? 0.30; // buying power entrant = bullish
        components.stable_to_exchange_count++;
        notional.stable_to_exchange += e.usd;
        break;
      case "STABLE_MINT":
        raw += weights.stable_mint ?? 0.20; // liquidité créée = bullish
        components.stable_mint_count++;
        notional.stable_mint += e.usd;
        break;
      case "STABLE_INFLOW":
        raw += weights.stable_inflow ?? 0.15;
        components.stable_inflow_count++;
        notional.stable_inflow += e.usd;
        break;
      case "MM_FLOW":
        // neutre — contexte seulement, pas de contribution au score
        components.mm_flow_count++;
        break;
      case "DEX_WHALE_BUY":
        raw += weights.dex_whale_buy ?? 0.15;
        components.dex_whale_buy_count++;
        notional.dex_buys += e.usd;
        break;
      case "DEX_WHALE_SELL":
        raw += weights.dex_whale_sell ?? -0.15;
        components.dex_whale_sell_count++;
        notional.dex_sells += e.usd;
        break;
    }
  }

  const score = Math.max(-1, Math.min(1, raw));
  return { score, components, notional, eventCount: recent.length };
}

function getBias(score, thresholdBull, thresholdBear) {
  if (score >  thresholdBull) return "BULLISH";
  if (score <  thresholdBear) return "BEARISH";
  return "NEUTRAL";
}

function getConfidence(components, eventCount) {
  const types = Object.values(components).filter(v => v > 0).length;
  const base  = Math.min(eventCount / 10, 1.0);
  const bonus = types > 2 ? 0.15 : types > 1 ? 0.08 : 0;
  return parseFloat(Math.min(base + bonus, 1.0).toFixed(2));
}

function buildInterpretation(bias, asset, windowHours, eventCount, components) {
  if (eventCount === 0) {
    return `No significant whale activity on ${asset} in the last ${windowHours}h.`;
  }
  const dir = {
    BULLISH: "Net whale accumulation bias",
    BEARISH: "Net whale distribution bias",
    NEUTRAL: "Mixed or neutral whale activity",
  }[bias];

  const details = [];
  if (components.stable_to_exchange_count > 0)
    details.push(`${components.stable_to_exchange_count} stable→exchange (buying power)`);
  if (components.from_exchange_count > 0)
    details.push(`${components.from_exchange_count} exchange outflows`);
  if (components.to_exchange_count > 0)
    details.push(`${components.to_exchange_count} exchange inflows`);
  if (components.stable_mint_count > 0)
    details.push(`${components.stable_mint_count} stable mints`);

  const detail = details.length ? ` (${details.join(", ")})` : "";
  return `${dir} detected on ${asset} over ${windowHours}h${detail}.`;
}

// ─── Handler principal ────────────────────────────────────────────────────────

export async function handler(ctx) {
  const configFile = path.join(ctx.stateDir, "configs", "WHALE_ANALYZER.config.json");
  const cfg = readJSON(configFile, {});

  const windowHours   = cfg.scoring_window_hours    ?? 6;
  const thresholdBull = cfg.signal_threshold_bullish ?? 0.30;
  const thresholdBear = cfg.signal_threshold_bearish ?? -0.30;
  const weights       = cfg.weights ?? {};

  // Charger adresses depuis fichier externe
  const sets = loadAddressSets(ctx.stateDir);
  ctx.log(`[WHALE_ANALYZER] Adresses chargées : ${sets.exchangeAddrs.size} exchanges, ${sets.bridgeAddrs.size + sets.protocolAddrs.size} filtres, ${sets.mmAddrs.size} MM, ${sets.stableIssuers.size} issuers`);

  const stateFile = path.join(ctx.stateDir, "memory", "WHALE_ANALYZER.state.json");
  const state = readJSON(stateFile, {
    agent_id:     "WHALE_ANALYZER",
    version:      1,
    cursors:      { "trading.raw.whale.transfer": 0 },
    asset_memory: {},
    stats:        { runs: 0, errors: 0, last_run_ts: 0 },
  });

  if (!state.cursors)      state.cursors      = { "trading.raw.whale.transfer": 0 };
  if (!state.asset_memory) state.asset_memory = {};

  const busDir = path.join(ctx.stateDir, "bus");

  // ── Lire nouveaux transferts ───────────────────────────────────────────────
  const { events: rawTransfers, newCursor } = readBusTopic(
    busDir,
    "trading.raw.whale.transfer",
    state.cursors["trading.raw.whale.transfer"] ?? 0
  );

  ctx.log(`[WHALE_ANALYZER] ${rawTransfers.length} nouveaux transferts à analyser`);

  let classified = 0;
  let filtered   = 0;

  for (const raw of rawTransfers) {
    const payload = raw.payload ?? raw;
    const asset   = payload.asset;
    if (!asset) continue;

    const type = classifyTransfer(payload, sets);
    if (!type) { filtered++; continue; }

    if (!state.asset_memory[asset]) state.asset_memory[asset] = { events: [] };

    state.asset_memory[asset].events.push({
      type,
      usd:     payload.amount_usd ?? 0,
      ts:      Date.now(),
      tx_hash: payload.tx_hash,
    });

    classified++;
    ctx.log(`  📊 ${asset} → ${type} ($${((payload.amount_usd ?? 0) / 1e6).toFixed(2)}M)`);
  }

  state.cursors["trading.raw.whale.transfer"] = newCursor;

  // ── Pruner hors fenêtre ────────────────────────────────────────────────────
  const cutoff = Date.now() - (windowHours + 1) * 60 * 60 * 1000;
  for (const asset of Object.keys(state.asset_memory)) {
    state.asset_memory[asset].events =
      state.asset_memory[asset].events.filter(e => e.ts > cutoff);
  }

  // ── Calculer et publier signal par asset ───────────────────────────────────
  let published = 0;

  for (const asset of Object.keys(state.asset_memory)) {
    const mem = state.asset_memory[asset];
    if (!mem.events.length) continue;

    const { score, components, notional, eventCount } =
      computeScore(mem.events, weights, windowHours);

    const bias          = getBias(score, thresholdBull, thresholdBear);
    const confidence    = getConfidence(components, eventCount);
    const interpretation = buildInterpretation(bias, asset, windowHours, eventCount, components);

    ctx.emit(
      "trading.intel.whale.signal",
      "intel.whale.signal.v1",
      { agent_id: "WHALE_ANALYZER" },
      {
        asset,
        chain:            "ethereum",
        window:           `${windowHours}h`,
        whale_flow_score: parseFloat(score.toFixed(3)),
        bias,
        confidence,
        components,
        notional_summary_usd: {
          to_exchange:        Math.round(notional.to_exchange),
          from_exchange:      Math.round(notional.from_exchange),
          stable_to_exchange: Math.round(notional.stable_to_exchange),
          stable_mint:        Math.round(notional.stable_mint),
          stable_inflow:      Math.round(notional.stable_inflow),
          dex_buys:           Math.round(notional.dex_buys),
          dex_sells:          Math.round(notional.dex_sells),
        },
        entity_labels:        {},
        is_exchange_internal: false,
        is_bridge_related:    false,
        interpretation,
      },
      { asset, chain: "ethereum" }
    );

    published++;
    ctx.log(`  🎯 ${asset} : ${bias} score=${score.toFixed(2)} conf=${confidence}`);
  }

  state.stats.runs++;
  state.stats.last_run_ts = Date.now();
  writeJSON(stateFile, state);

  ctx.log(`[WHALE_ANALYZER] ✅ classifiés=${classified} filtrés=${filtered} signaux=${published}`);
}
