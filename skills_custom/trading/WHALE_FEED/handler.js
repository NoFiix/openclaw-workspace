/**
 * WHALE_FEED — Handler
 *
 * Collecteur de données whales brutes.
 * Sources : Etherscan REST (ETH natif + ERC20 : USDT/USDC/WBTC)
 * Aucun LLM. Zéro coût token. Logique pure.
 *
 * Outputs :
 *   trading.raw.whale.transfer
 *
 * Fréquence : 300s (5min)
 * Quota Etherscan gratuit : ~1440 calls/jour sur 100k dispo
 */

import fs   from "fs";
import path from "path";

const ETHERSCAN_BASE = "https://api.etherscan.io/api";
const TIMEOUT_MS     = 10000;

// Adresses ERC20 à surveiller
const ERC20_TOKENS = [
  { symbol: "USDT",  address: "0xdac17f958d2ee523a2206206994597c13d831ec7", decimals: 6  },
  { symbol: "USDC",  address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", decimals: 6  },
  { symbol: "WBTC",  address: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", decimals: 8  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ─── Déduplication TTL 2h ─────────────────────────────────────────────────────

function isDuplicate(seen, key) {
  const now   = Date.now();
  const TTL   = 2 * 60 * 60 * 1000; // 2h
  const entry = seen[key];
  if (entry && now - entry < TTL) return true;
  seen[key] = now;
  return false;
}

function cleanOldEntries(seen) {
  const now = Date.now();
  const TTL = 2 * 60 * 60 * 1000;
  for (const k of Object.keys(seen)) {
    if (now - seen[k] > TTL) delete seen[k];
  }
}

// ─── Prix ETH (simple fetch CoinGecko sans clé) ───────────────────────────────

async function getEthPriceUsd() {
  try {
    const data = await fetchWithTimeout(
      "https://api.coingecko.com/api/v3/simple/price?ids=ethereum,bitcoin&vs_currencies=usd"
    );
    return {
      ETH:  data?.ethereum?.usd ?? 2000,
      WBTC: data?.bitcoin?.usd  ?? 60000,
    };
  } catch {
    return { ETH: 2000, WBTC: 60000 };
  }
}

// ─── Etherscan — bloc actuel ──────────────────────────────────────────────────

async function getCurrentBlock(apiKey) {
  const data = await fetchWithTimeout(
    `${ETHERSCAN_BASE}?module=proxy&action=eth_blockNumber&apikey=${apiKey}`
  );
  return parseInt(data.result, 16);
}

// ─── Etherscan — transferts ETH natifs ───────────────────────────────────────

async function fetchEthTransfers(apiKey, fromBlock, toBlock) {
  const url = `${ETHERSCAN_BASE}?module=account&action=txlist` +
    `&startblock=${fromBlock}&endblock=${toBlock}` +
    `&sort=desc&page=1&offset=100&apikey=${apiKey}`;
  const data = await fetchWithTimeout(url);
  if (data.status !== "1" || !Array.isArray(data.result)) return [];
  return data.result;
}

// ─── Etherscan — transferts ERC20 ────────────────────────────────────────────

async function fetchERC20Transfers(apiKey, contractAddress, fromBlock, toBlock) {
  const url = `${ETHERSCAN_BASE}?module=account&action=tokentx` +
    `&contractaddress=${contractAddress}` +
    `&startblock=${fromBlock}&endblock=${toBlock}` +
    `&sort=desc&page=1&offset=100&apikey=${apiKey}`;
  const data = await fetchWithTimeout(url);
  if (data.status !== "1" || !Array.isArray(data.result)) return [];
  return data.result;
}

// ─── Handler principal ────────────────────────────────────────────────────────

export async function handler(ctx) {
  const apiKey = process.env.ETHERSCAN_API_KEY;
  if (!apiKey) {
    ctx.log("[WHALE_FEED] ETHERSCAN_API_KEY manquant — abort");
    return;
  }

  // Charger config
  const configFile = path.join(ctx.stateDir, "configs", "WHALE_FEED.config.json");
  const cfg        = readJSON(configFile, {});
  const thresholds = cfg.thresholds_usd ?? {
    ETH: 500000, WBTC: 500000, USDT: 1000000, USDC: 1000000
  };
  const lookback = cfg.etherscan?.lookback_blocks ?? 25;

  // Charger état (dédup + last_block)
  const stateFile = path.join(ctx.stateDir, "memory", "WHALE_FEED.state.json");
  const state     = readJSON(stateFile, {
    agent_id: "WHALE_FEED", version: 1,
    etherscan: { last_block: 0 },
    dedup: { seen: {} },
    stats: { runs: 0, errors: 0, last_run_ts: 0 },
  });

  if (!state.dedup?.seen) state.dedup = { seen: {} };
  cleanOldEntries(state.dedup.seen);

  let published = 0;
  let errors    = 0;

  try {
    // Bloc actuel
    const currentBlock = await getCurrentBlock(apiKey);
    const fromBlock    = state.etherscan.last_block > 0
      ? state.etherscan.last_block + 1
      : currentBlock - lookback;
    const toBlock = currentBlock;

    if (fromBlock > toBlock) {
      ctx.log(`[WHALE_FEED] Aucun nouveau bloc (from=${fromBlock} to=${toBlock})`);
      state.stats.runs++;
      state.stats.last_run_ts = Date.now();
      writeJSON(stateFile, state);
      return;
    }

    ctx.log(`[WHALE_FEED] Scan blocs ${fromBlock} → ${toBlock} (${toBlock - fromBlock + 1} blocs)`);

    // Prix actuels
    const prices = await getEthPriceUsd();

    // ── ETH natif ────────────────────────────────────────────────────────────
    let ethTxs;
    try {
      ethTxs = await fetchEthTransfers(apiKey, fromBlock, toBlock);
    } catch (e) {
      ctx.log(`[WHALE_FEED] Erreur ETH transfers : ${e.message}`);
      ethTxs = [];
      errors++;
    }

    for (const tx of ethTxs) {
      if (tx.isError === "1") continue;
      const amount    = parseInt(tx.value) / 1e18;
      const amountUsd = amount * prices.ETH;
      if (amountUsd < thresholds.ETH) continue;

      const dedupKey = `eth:${tx.hash}`;
      if (isDuplicate(state.dedup.seen, dedupKey)) continue;

      ctx.emit(
        "trading.raw.whale.transfer",
        "raw.whale.transfer.v1",
        { agent_id: "WHALE_FEED" },
        {
          chain:         "ethereum",
          asset:         "ETH",
          token_address: null,
          tx_hash:       tx.hash,
          block_number:  parseInt(tx.blockNumber),
          from:          tx.from.toLowerCase(),
          to:            tx.to.toLowerCase(),
          amount:        parseFloat(amount.toFixed(4)),
          amount_usd:    parseFloat(amountUsd.toFixed(2)),
          detected_at:   new Date().toISOString(),
          source:        "etherscan",
          raw_type:      "native_transfer",
        },
        { asset: "ETH", chain: "ethereum" }
      );
      published++;
      ctx.log(`  🐋 ETH transfer $${(amountUsd/1e6).toFixed(2)}M — ${tx.from.slice(0,8)}→${tx.to.slice(0,8)}`);
    }

    // ── ERC20 ─────────────────────────────────────────────────────────────────
    for (const token of ERC20_TOKENS) {
      if (!(token.symbol in thresholds)) continue;

      let txs;
      try {
        txs = await fetchERC20Transfers(apiKey, token.address, fromBlock, toBlock);
      } catch (e) {
        ctx.log(`[WHALE_FEED] Erreur ${token.symbol} transfers : ${e.message}`);
        errors++;
        continue;
      }

      for (const tx of txs) {
        const amount    = parseInt(tx.value) / Math.pow(10, token.decimals);
        const amountUsd = token.symbol === "WBTC"
          ? amount * prices.WBTC
          : amount; // USDT/USDC ≈ 1:1

        if (amountUsd < thresholds[token.symbol]) continue;

        const dedupKey = `${token.symbol.toLowerCase()}:${tx.hash}`;
        if (isDuplicate(state.dedup.seen, dedupKey)) continue;

        ctx.emit(
          "trading.raw.whale.transfer",
          "raw.whale.transfer.v1",
          { agent_id: "WHALE_FEED" },
          {
            chain:         "ethereum",
            asset:         token.symbol,
            token_address: token.address,
            tx_hash:       tx.hash,
            block_number:  parseInt(tx.blockNumber),
            from:          tx.from.toLowerCase(),
            to:            tx.to.toLowerCase(),
            amount:        parseFloat(amount.toFixed(4)),
            amount_usd:    parseFloat(amountUsd.toFixed(2)),
            detected_at:   new Date().toISOString(),
            source:        "etherscan",
            raw_type:      "erc20_transfer",
          },
          { asset: token.symbol, chain: "ethereum" }
        );
        published++;
        ctx.log(`  🐋 ${token.symbol} transfer $${(amountUsd/1e6).toFixed(2)}M — ${tx.from.slice(0,8)}→${tx.to.slice(0,8)}`);
      }

      // Rate limit Etherscan gratuit : 5 req/s
      await new Promise(r => setTimeout(r, 250));
    }

    state.etherscan.last_block = toBlock;

  } catch (e) {
    ctx.log(`[WHALE_FEED] Erreur fatale : ${e.message}`);
    errors++;
  }

  state.stats.runs++;
  state.stats.errors  += errors;
  state.stats.last_run_ts = Date.now();
  writeJSON(stateFile, state);

  ctx.log(`[WHALE_FEED] ✅ ${published} événements publiés, ${errors} erreurs`);
}
