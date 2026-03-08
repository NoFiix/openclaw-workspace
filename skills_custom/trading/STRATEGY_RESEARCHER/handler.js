/**
 * STRATEGY_RESEARCHER — Handler
 * Veille quotidienne sur les meilleures stratégies de trading crypto.
 * Sources : Reddit, blogs quant, forums trading
 * Utilise Claude Sonnet pour analyser et extraire les stratégies prometteuses.
 * Écrit dans : state/trading/learning/strategy_candidates.json
 */

import fs   from "fs";
import path from "path";
import { logTokens } from "../_shared/logTokens.js";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL_RESEARCH = "claude-sonnet-4-20250514"; // Sonnet pour analyse qualitative
const MODEL_EXTRACT  = "claude-haiku-4-5-20251001"; // Haiku pour extraction JSON
const TIMEOUT_MS     = 45000;

// ─── Sources de veille ────────────────────────────────────────────────────

const SOURCES = [
  {
    name: "Reddit AlgoTrading",
    url:  "https://www.reddit.com/r/algotrading/top.json?t=week&limit=10",
    type: "reddit",
  },
  {
    name: "Reddit CryptoMarkets",
    url:  "https://www.reddit.com/r/CryptoMarkets/top.json?t=week&limit=10",
    type: "reddit",
  },
  {
    name: "Reddit Trading",
    url:  "https://www.reddit.com/r/trading/top.json?t=week&limit=10",
    type: "reddit",
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

async function fetchWithTimeout(url, timeout = 10000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const res = await fetch(url, {
      signal:  controller.signal,
      headers: { "User-Agent": "CryptoRizon-Research-Bot/1.0" },
    });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Fetch Reddit posts ───────────────────────────────────────────────────

async function fetchRedditPosts(source) {
  try {
    const res  = await fetchWithTimeout(source.url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const posts = data?.data?.children ?? [];

    return posts
      .filter(p => p.data.score > 50) // Filtre posts populaires
      .map(p => ({
        title: p.data.title,
        text:  p.data.selftext?.slice(0, 500) ?? "",
        score: p.data.score,
        url:   `https://reddit.com${p.data.permalink}`,
      }))
      .slice(0, 5);
  } catch (e) {
    return [];
  }
}

// ─── Analyse Sonnet : extrait les stratégies ─────────────────────────────

async function analyzeForStrategies(apiKey, posts, sourceName) {
  if (!posts.length) return [];

  const postsText = posts
    .map(p => `TITRE: ${p.title}\nCONTENU: ${p.text}`)
    .join("\n\n---\n\n");

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const res = await fetch(ANTHROPIC_API, {
      method:  "POST",
      headers: {
        "Content-Type":      "application/json",
        "x-api-key":         apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model:      MODEL_RESEARCH,
        max_tokens: 1500,
        messages: [{
          role:    "user",
          content: `Tu es un analyste quant spécialisé en trading crypto algorithmique.

Analyse ces posts de trading et identifie les stratégies concrètes et implémentables.

CRITÈRES pour retenir une stratégie :
- Elle doit être basée sur des signaux techniques mesurables (RSI, MACD, volume, price action...)
- Elle doit avoir des règles d'entrée ET de sortie claires
- Elle doit être réaliste pour du crypto intraday (15m, 1h, 4h)
- Elle ne doit pas nécessiter de données premium ou d'infrastructure complexe
- Elle doit avoir au moins un commentaire positif ou preuve de rentabilité

POSTS À ANALYSER :
${postsText}

Pour chaque stratégie valide trouvée, réponds en JSON strict :
[
  {
    "name": "Nom court de la stratégie",
    "description": "Description en 2 phrases",
    "signals": ["signal1", "signal2"],
    "entry_rules": "Conditions d'entrée précises",
    "exit_rules": "Conditions de sortie (TP et SL)",
    "timeframes": ["1h", "4h"],
    "assets": ["BTC", "ETH"],
    "source": "${sourceName}",
    "confidence_score": 0.7,
    "complexity": "simple|medium|complex"
  }
]

Si aucune stratégie valide, réponds : []
Réponds UNIQUEMENT en JSON, pas d'autre texte.`,
        }],
      }),
      signal: controller.signal,
    });

    if (!res.ok) throw new Error(`API ${res.status}`);
    const data = await res.json();
    if (data.usage) logTokens(ctx?.stateDir ?? "", "STRATEGY_RESEARCHER", MODEL_RESEARCH, data.usage, "strategy_extraction");
    const text = data.content?.[0]?.text?.trim() ?? "[]";

    // Nettoyage JSON
    const clean = text.replace(/```json|```/g, "").trim();
    return JSON.parse(clean);
  } catch (e) {
    return [];
  } finally {
    clearTimeout(timer);
  }
}

// ─── Déduplication par nom ────────────────────────────────────────────────

function deduplicateCandidates(existing, newOnes) {
  const existingNames = new Set(
    existing.map(s => s.name.toLowerCase().replace(/\s+/g, "_"))
  );

  return newOnes.filter(s => {
    const key = s.name.toLowerCase().replace(/\s+/g, "_");
    if (existingNames.has(key)) return false;
    existingNames.add(key);
    return true;
  });
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const apiKey   = process.env.ANTHROPIC_API_KEY;
  const learnDir = path.join(ctx.stateDir, "learning");
  const outFile  = path.join(learnDir, "strategy_candidates.json");

  if (!apiKey) {
    ctx.log("❌ ANTHROPIC_API_KEY manquant");
    return;
  }

  // Vérification : on ne tourne qu'une fois par jour
  const today     = new Date().toISOString().slice(0, 10);
  const lastRun   = ctx.state.last_run_date ?? "";
  if (lastRun === today) {
    ctx.log(`⏭  Déjà tourné aujourd'hui (${today}) — skip`);
    return;
  }

  ctx.log("🔍 STRATEGY_RESEARCHER — démarrage veille quotidienne");

  const existing   = readJSON(outFile, []);
  let   newFound   = 0;
  let   allNew     = [];

  // ── 1. Scrape chaque source ───────────────────────────────────────────
  for (const source of SOURCES) {
    ctx.log(`  📡 Scrape: ${source.name}`);

    const posts = await fetchRedditPosts(source);
    ctx.log(`    → ${posts.length} posts récupérés`);

    if (!posts.length) continue;

    const strategies = await analyzeForStrategies(apiKey, posts, source.name);
    ctx.log(`    → ${strategies.length} stratégies identifiées`);

    allNew.push(...strategies);
    await new Promise(r => setTimeout(r, 2000)); // Rate limit
  }

  // ── 2. Déduplication + enrichissement ────────────────────────────────
  const deduplicated = deduplicateCandidates(existing, allNew);

  for (const s of deduplicated) {
    s.id          = `strat_${s.name.toLowerCase().replace(/\s+/g, "_")}_${Date.now()}`;
    s.status      = "candidate"; // candidate → testing → active | rejected
    s.discovered_at = new Date().toISOString();
    s.test_trades   = 0;
    s.pnl_usd       = null;
    s.win_rate      = null;
    s.profit_factor = null;
    newFound++;
  }

  // ── 3. Sauvegarde ─────────────────────────────────────────────────────
  const updated = [...existing, ...deduplicated];
  writeJSON(outFile, updated);

  ctx.state.last_run_date = today;
  ctx.state.total_candidates = updated.length;

  ctx.log(`✅ ${newFound} nouvelles stratégies trouvées`);
  ctx.log(`📊 Total candidats: ${updated.length} (${updated.filter(s=>s.status==="candidate").length} en attente, ${updated.filter(s=>s.status==="active").length} actives)`);

  // ── 4. Log des nouvelles stratégies ───────────────────────────────────
  for (const s of deduplicated) {
    ctx.log(`  🆕 "${s.name}" — ${s.description?.slice(0, 80)}`);
  }
}
