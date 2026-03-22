/**
 * STRATEGY_SCOUT — Handler
 * Unique agent de decouverte de strategies. Remplace STRATEGY_RESEARCHER.
 *
 * Cycle complet a chaque run :
 *   1. cleanupExpiredCandidates() — TTL 14j pending, purge rejected/expired
 *   2. processApprovedCandidates() — sync validated candidates to registry
 *   3. Decouverte — scrape Reddit, analyse LLM, 1 candidate max par run
 *   4. addCandidate() + sendCandidateTelegram() — notification informative
 *
 * Frequence : 48h. Max 1 candidate par run. Aucune ecriture directe dans le registry.
 */

import fs   from "fs";
import path from "path";
import { logTokens } from "../_shared/logTokens.js";
import {
  loadCandidates, addCandidate, findDuplicateCandidate,
  sendCandidateTelegram, processApprovedCandidates,
  cleanupExpiredCandidates,
} from "../_shared/strategy_utils.js";

const ANTHROPIC_API  = "https://api.anthropic.com/v1/messages";
const MODEL          = "claude-sonnet-4-20250514";
const TIMEOUT_MS     = 45000;

const SOURCES = [
  { name: "Reddit AlgoTrading", url: "https://www.reddit.com/r/algotrading/top.json?t=week&limit=10" },
  { name: "Reddit Quant",       url: "https://www.reddit.com/r/quant/top.json?t=week&limit=10" },
  { name: "Reddit Trading",     url: "https://www.reddit.com/r/trading/top.json?t=week&limit=10" },
];

async function fetchWithTimeout(url, timeout = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    return await fetch(url, { signal: controller.signal, headers: { "User-Agent": "CryptoRizon-Scout/1.0" } });
  } finally { clearTimeout(timer); }
}

async function fetchRedditPosts(source) {
  try {
    const res  = await fetchWithTimeout(source.url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    return (data?.data?.children ?? [])
      .filter(p => p.data.score > 30)
      .map(p => ({
        title: p.data.title, text: p.data.selftext?.slice(0, 600) ?? "",
        score: p.data.score, url: `https://reddit.com${p.data.permalink}`, source: source.name,
      }))
      .slice(0, 5);
  } catch { return []; }
}

async function analyzeAndClassify(apiKey, posts, stateDir) {
  if (!posts.length) return [];
  const postsText = posts.map(p => `[${p.source}] TITRE: ${p.title}\nCONTENU: ${p.text}\nURL: ${p.url}`).join("\n\n---\n\n");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(ANTHROPIC_API, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-api-key": apiKey, "anthropic-version": "2023-06-01" },
      body: JSON.stringify({
        model: MODEL, max_tokens: 1500,
        messages: [{ role: "user", content:
`Tu es un analyste quant specialise en crypto algo-trading.
Analyse ces posts et identifie LA MEILLEURE strategie concrete et implementable.
Retourne exactement 1 strategie ou un tableau vide.

INDICATEURS DISPONIBLES (MARKET_EYE sur 5m/1h/4h) :
RSI_14, MACD (macd + signal + histogram), Bollinger Bands (upper/lower/mid/pct_b/width),
ATR_14, volume_zscore, trend_strength (EMA20 vs EMA50)

CLASSIFICATION :
- "config_ready" : utilise UNIQUEMENT les indicateurs ci-dessus
- "dev_required" : necessite des indicateurs absents ou logique specifique

POSTS :
${postsText}

Reponds en JSON strict, aucun texte autour :
[{
  "strategy_name": "Nom court",
  "strategy_label": "Nom - description courte",
  "source": "Reddit AlgoTrading",
  "source_url": "https://...",
  "summary": "2 phrases",
  "who_uses_it": "Contexte d utilisation",
  "why_it_might_work": "Pourquoi edge",
  "entry_logic": "Conditions entree precises",
  "exit_logic": "Conditions sortie (TP + SL)",
  "markets": ["BTCUSDT"],
  "timeframes": ["1h", "4h"],
  "indicators_required": ["RSI", "BB"],
  "confidence_score": 0.72,
  "compatibility": "config_ready",
  "compatibility_reason": "Explication",
  "implementation_notes": "Notes techniques"
}]` }],
      }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`API ${res.status}`);
    const data = await res.json();
    if (data.usage) logTokens(stateDir, "STRATEGY_SCOUT", MODEL, data.usage, "scout_analysis");
    const text = data.content?.[0]?.text?.trim() ?? "[]";
    const clean = text.replace(/```json|```/g, "").trim();
    try { return JSON.parse(clean); } catch {
      const f = text.indexOf("["), l = text.lastIndexOf("]");
      if (f !== -1 && l > f) { try { return JSON.parse(text.substring(f, l + 1)); } catch {} }
      return [];
    }
  } catch { return []; }
  finally { clearTimeout(timer); }
}

export async function handler(ctx) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) { ctx.log("ANTHROPIC_API_KEY manquant"); return; }

  // 1. Cleanup expired candidates
  cleanupExpiredCandidates(ctx.log);

  // 2. Process approved/rejected candidates (sync to registry)
  processApprovedCandidates(ctx.log);

  // 3. Guard: run discovery at most once per 47h
  const now = Date.now();
  const lastTs = ctx.state.last_run_ts ?? 0;
  if (now - lastTs < 47 * 3600 * 1000) {
    const hoursAgo = ((now - lastTs) / 3600000).toFixed(1);
    ctx.log(`Discovery skip - dernier run il y a ${hoursAgo}h`);
    return;
  }

  ctx.log("STRATEGY_SCOUT - decouverte de strategies");

  // 4. Collect posts
  let allPosts = [];
  for (const source of SOURCES) {
    ctx.log(`  ${source.name}`);
    const posts = await fetchRedditPosts(source);
    ctx.log(`    ${posts.length} posts`);
    allPosts.push(...posts);
    await new Promise(r => setTimeout(r, 1500));
  }

  if (!allPosts.length) {
    ctx.log("Aucun post recupere");
    ctx.state.last_run_ts = now;
    return;
  }

  // 5. Analyze with LLM
  const strategies = await analyzeAndClassify(apiKey, allPosts, ctx.stateDir);
  if (!strategies?.length) {
    ctx.log("Aucune strategie valide identifiee");
    ctx.state.last_run_ts = now;
    return;
  }

  const best = strategies[0];
  ctx.log(`  Candidate: "${best.strategy_name}" - ${best.compatibility}`);

  // 6. Dedup
  const data = loadCandidates();
  const dup = findDuplicateCandidate(data, best.strategy_name);
  if (dup) {
    ctx.log(`  Doublon detecte : "${dup.strategy_name}" (${dup.status}) - ignore`);
    ctx.state.last_run_ts = now;
    return;
  }

  // 7. Add + send Telegram
  const result = addCandidate(best);
  if (!result.added) {
    ctx.log(`  Non ajoutee : ${result.reason}`);
    ctx.state.last_run_ts = now;
    return;
  }

  ctx.log(`  Candidate ajoutee : ${result.candidate.candidate_id} (${result.candidate.candidate_seq})`);

  const msgId = await sendCandidateTelegram(result.candidate.candidate_id);
  if (msgId) {
    ctx.log(`  Telegram envoye - message_id: ${msgId}`);
  } else {
    ctx.log("  Telegram non envoye (erreur ou token absent)");
  }

  ctx.state.last_run_ts = now;
  ctx.log("STRATEGY_SCOUT termine - 1 candidate soumise");
}
