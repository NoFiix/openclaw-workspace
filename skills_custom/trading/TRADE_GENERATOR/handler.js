/**
 * TRADE_GENERATOR — Handler
 * Premier agent LLM du pipeline trading.
 * Lit les features (1m/1h/4h), le régime, le killswitch.
 * Génère des TradeProposal via Claude Haiku.
 * Émet : trading.strategy.trade.proposal
 */

import fs   from "fs";
import path from "path";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";
const MAX_TOKENS    = 600;
const TIMEOUT_MS    = 20000;
const SYMBOLS       = ["BTCUSDT", "ETHUSDT", "BNBUSDT"];
const COOLDOWN_MS   = 30 * 60 * 1000; // 30 minutes par asset

// ─── Helpers bus ──────────────────────────────────────────────────────────

function getLastEvent(bus, topic, filterFn, limit = 5000) {
  const { events } = bus.readSince(topic, 0, limit);
  const filtered   = events.filter(filterFn);
  return filtered.length > 0 ? filtered[filtered.length - 1] : null;
}


// ─── Chargement des stratégies actives ──────────────────────────────────

function loadActiveStrategies(stateDir) {
  const BUILTIN = [
    { name: "MeanReversion", description: "Retour à la moyenne sur support/résistance clé", entry_rules: "RSI oversold/overbought + BB extremes + volume faible", exit_rules: "TP au niveau médian, SL hors de la range" },
    { name: "Momentum",      description: "Suivi de tendance sur breakout confirmé",         entry_rules: "MACD haussier + EMA alignment + volume spike",          exit_rules: "TP trailing, SL sous dernier pivot" },
    { name: "NewsTrading",   description: "Trade sur catalyseur fondamental majeur",          entry_rules: "News urgency >= 8 + mouvement prix > 1% + volume",      exit_rules: "TP rapide 1-2%, SL serré" },
    { name: "Breakout",      description: "Cassure de niveau clé avec volume",               entry_rules: "Prix casse résistance + volume > 2x moyenne + MACD+",   exit_rules: "TP +2R au prochain niveau, SL sous cassure" },
  ];

  try {
    const candidatesFile = path.join(stateDir, "learning", "strategy_candidates.json");
    const perfFile       = path.join(stateDir, "learning", "strategy_performance.json");
    const candidates     = JSON.parse(fs.readFileSync(candidatesFile, "utf-8"));
    const perf           = JSON.parse(fs.readFileSync(perfFile, "utf-8"));

    // Garder candidates avec exit_rules valides (pas "Non spécifiées")
    const external = candidates.filter(s =>
      (s.status === "active" || s.status === "candidate") &&
      s.exit_rules && !s.exit_rules.toLowerCase().includes("non spécifié") &&
      s.exit_rules.length > 15
    );

    // Exclure les doublons avec BUILTIN
    const builtinNames = new Set(BUILTIN.map(s => s.name.toLowerCase()));
    const newOnes = external.filter(s => !builtinNames.has(s.name.toLowerCase()));

    return [...BUILTIN, ...newOnes];
  } catch {
    return BUILTIN;
  }
}

function formatStrategiesForPrompt(strategies, perfData = {}) {
  return strategies.map(s => {
    const p = perfData[s.name];
    const perfStr = p && p.trades_count >= 5
      ? ` [WR=${p.win_rate}% PF=${p.profit_factor} n=${p.trades_count}]`
      : " [en cours de test]";
    return `- ${s.name}${perfStr}: ${s.description}`;
  }).join("\n");
}

function getRecentNews(bus, symbol, maxAge_ms = 2 * 60 * 60 * 1000) {
  const { events } = bus.readSince("trading.intel.news.event", 0, 500);
  const now        = Date.now();
  return events
    .filter(e => {
      const age       = now - (e.ts ?? e.event_id ?? 0);
      const entities  = e.payload?.entities ?? [];
      const ticker    = symbol.replace("USDT", "");
      const relevant  = entities.length === 0
        || entities.includes(ticker)
        || entities.includes("BTC")   // BTC news = macro, toujours pertinent
        || entities.includes("MARKET");
      return relevant && age < maxAge_ms;
    })
    .map(e => e.payload)
    .slice(-5); // max 5 news récentes
}

function getFeatures(bus, symbol, timeframe) {
  const evt = getLastEvent(
    bus,
    "trading.intel.market.features",
    e => e.payload?.symbol === symbol && e.payload?.timeframe === timeframe
  );
  return evt?.payload ?? null;
}

function getRegime(bus) {
  const evt = getLastEvent(bus, "trading.intel.regime", () => true, 100);
  return evt?.payload ?? null;
}

function getKillswitch(stateDir) {
  const p = path.join(stateDir, "exec", "killswitch.json");
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); }
  catch { return { state: "ARMED" }; }
}

function checkCooldown(cooldowns, symbol) {
  const last = cooldowns[symbol] ?? 0;
  return (Date.now() - last) < COOLDOWN_MS;
}

// ─── Prompt ───────────────────────────────────────────────────────────────

function buildSystemPrompt(soulPath) {
  const defaultSoul = `Tu es TRADE_GENERATOR. Tu proposes des trades crypto basés sur des données techniques.
Tu es froid, factuel, anti-FOMO. Tu préfères HOLD à un trade incertain.
Réponds UNIQUEMENT en JSON valide. Aucun texte avant ou après.`;

  try {
    const soul = fs.readFileSync(soulPath, "utf-8");
    return soul + "\n\nRéponds UNIQUEMENT en JSON valide. Aucun texte avant ou après.";
  } catch {
    return defaultSoul;
  }
}

function buildUserPrompt(symbol, f1m, f1h, f4h, regime, recentNews = [], strategies = [], perfData = {}) {
  const stratList = formatStrategiesForPrompt(strategies, perfData);
  return `Analyse les données suivantes et génère une TradeProposal pour ${symbol}.

## Régime de marché
- Régime global: ${regime?.regime ?? "UNKNOWN"}
- Confidence: ${regime?.confidence ?? 0}
- Divergence: ${regime?.divergence ?? false}
- Régime ${symbol}: ${regime?.by_symbol?.[symbol]?.regime ?? "UNKNOWN"}

## Indicateurs techniques

### 1m (court terme — bruit)
- Prix: ${f1m?.price ?? "N/A"}
- RSI_14: ${f1m?.rsi_14 ?? "N/A"}
- BB_pct_b: ${f1m?.bb_pct_b ?? "N/A"} (0=lower band, 1=upper band)
- MACD_hist: ${f1m?.macd_histogram ?? "N/A"}
- Volume_zscore: ${f1m?.volume_zscore ?? "N/A"}
- Trend_strength: ${f1m?.trend_strength ?? "N/A"}

### 1h (signal principal)
- RSI_14: ${f1h?.rsi_14 ?? "N/A"}
- BB_pct_b: ${f1h?.bb_pct_b ?? "N/A"}
- MACD_hist: ${f1h?.macd_histogram ?? "N/A"}
- ATR_14: ${f1h?.atr_14 ?? "N/A"}
- Volume_zscore: ${f1h?.volume_zscore ?? "N/A"}

### 4h (tendance de fond)
- RSI_14: ${f4h?.rsi_14 ?? "N/A"}
- BB_pct_b: ${f4h?.bb_pct_b ?? "N/A"}
- MACD_hist: ${f4h?.macd_histogram ?? "N/A"}
- Trend_strength: ${f4h?.trend_strength ?? "N/A"} (positif=haussier, négatif=baissier)
- ATR_14: ${f4h?.atr_14 ?? "N/A"}


## News récentes (dernières 2h)
${recentNews.length === 0
  ? "Aucune news récente significative"
  : recentNews.map(n =>
      `- [${n.category}] urgency=${n.urgency} fiab=${n.reliability?.score} | ${n.headline?.slice(0,100)}`
    ).join("\n")
}

## Signal NewsTrading
${recentNews.some(n => n.urgency >= 8 && n.reliability?.score >= 0.7)
  ? "⚡ NEWS CRITIQUE DÉTECTÉE — considérer strategy=NewsTrading si concordant avec les indicateurs"
  : "Pas de news critique dans la fenêtre"
}

## Stratégies disponibles (choisis parmi celles-ci uniquement)
${stratList}

## Règles ABSOLUES
- Si régime = PANIC → side = "HOLD" obligatoire
- Si confidence < 0.5 → side = "HOLD"
- Si moins de 2 signaux concordants → side = "HOLD"
- Stop-loss OBLIGATOIRE si side != "HOLD"
- Risk/reward minimum: 2.0
- Jamais de leverage

## Format de réponse JSON
{
  "symbol": "${symbol}",
  "strategy": "${strategies.map(s=>s.name).join('|')}",
  "side": "BUY|SELL|HOLD",
  "confidence": 0.0,
  "setup": {
    "entry": 0,
    "stop": 0,
    "tp": 0,
    "risk_reward": 0
  },
  "time_horizon": "minutes|hours|days",
  "reasons": [],
  "signals_used": []
}`;
}

// ─── Appel LLM ────────────────────────────────────────────────────────────

async function callHaiku(apiKey, systemPrompt, userPrompt) {
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
        model:      MODEL,
        max_tokens: MAX_TOKENS,
        system:     systemPrompt,
        messages:   [{ role: "user", content: userPrompt }],
      }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`Anthropic API HTTP ${res.status}`);
    const data = await res.json();
    return data.content?.[0]?.text ?? null;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Validation proposal ──────────────────────────────────────────────────

function validateProposal(p, symbol) {
  const errors = [];

  if (!["BUY", "SELL", "HOLD"].includes(p.side))
    errors.push(`side invalide: ${p.side}`);

  if (p.side !== "HOLD") {
    if (!p.setup?.entry || p.setup.entry <= 0)
      errors.push("entry manquant ou invalide");
    if (!p.setup?.stop || p.setup.stop <= 0)
      errors.push("stop manquant — REJET");
    if (!p.setup?.tp || p.setup.tp <= 0)
      errors.push("take-profit manquant");
    if (p.setup?.risk_reward < 2.0)
      errors.push(`risk_reward trop faible: ${p.setup?.risk_reward} < 2.0`);
  }

  if (p.confidence < 0 || p.confidence > 1)
    errors.push(`confidence hors range: ${p.confidence}`);

  if (!p.reasons || p.reasons.length === 0)
    errors.push("reasons vide");

  return errors;
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) { ctx.log("❌ ANTHROPIC_API_KEY manquant"); return; }

  // Killswitch check
  const ks = getKillswitch(ctx.stateDir);
  if (ks.state === "TRIPPED") {
    ctx.log(`🛑 KILL SWITCH TRIPPED — ${ks.reason} — aucune proposal`);
    return;
  }

  // Régime global
  const regime = getRegime(ctx.bus);
  if (!regime) {
    ctx.log("⚠️ Aucun régime disponible — REGIME_DETECTOR doit tourner en premier");
    return;
  }

  ctx.log(`📊 Régime: ${regime.regime} (conf=${regime.confidence})`);


  // Soul TRADE_GENERATOR
  const soulPath = path.join(
    ctx.stateDir.replace("/state/trading", ""),
    "agents", "trade_generator", "SOUL.md"
  );
  const systemPrompt = buildSystemPrompt(soulPath);

  // Cooldowns
  ctx.state.cooldowns = ctx.state.cooldowns ?? {};
  let proposals = 0;

  for (const symbol of SYMBOLS) {
    // Cooldown check
    if (checkCooldown(ctx.state.cooldowns, symbol)) {
      const remaining = Math.ceil((COOLDOWN_MS - (Date.now() - ctx.state.cooldowns[symbol])) / 60000);
      ctx.log(`⏳ ${symbol}: cooldown actif (${remaining} min restantes)`);
      continue;
    }

    // Features
    const f1m = getFeatures(ctx.bus, symbol, "1m");
    const f1h = getFeatures(ctx.bus, symbol, "1h");
    const f4h = getFeatures(ctx.bus, symbol, "4h");

    if (!f1m || !f1h || !f4h) {
      ctx.log(`⚠️ ${symbol}: features incomplètes (1m=${!!f1m} 1h=${!!f1h} 4h=${!!f4h})`);
      continue;
    }

    ctx.log(`🤔 ${symbol}: génération proposal...`);

    try {
      const recentNews = getRecentNews(ctx.bus, symbol);
      const strategies = loadActiveStrategies(ctx.stateDir);
      let perfData = {};
      try {
        const pf = path.join(ctx.stateDir, "learning", "strategy_performance.json");
        perfData = JSON.parse(fs.readFileSync(pf, "utf-8"));
      } catch {}
      const userPrompt = buildUserPrompt(symbol, f1m, f1h, f4h, regime, recentNews, strategies, perfData);
      const raw        = await callHaiku(apiKey, systemPrompt, userPrompt);

      if (!raw) { ctx.log(`⚠️ ${symbol}: réponse vide Haiku`); continue; }

      // Parse JSON
      let proposal;
      try {
        const clean = raw.replace(/```json|```/g, "").trim();
        proposal    = JSON.parse(clean);
      } catch {
        ctx.log(`⚠️ ${symbol}: JSON invalide — ${raw.slice(0, 100)}`);
        continue;
      }

      // Validation
      const errors = validateProposal(proposal, symbol);
      if (errors.length > 0 && proposal.side !== "HOLD") {
        ctx.log(`⚠️ ${symbol}: proposal invalide — ${errors.join(", ")}`);
        // Si stop manquant → force HOLD
        if (errors.some(e => e.includes("stop"))) {
          proposal.side = "HOLD";
          proposal.reasons = [...(proposal.reasons ?? []), "AUTO_HOLD: stop manquant"];
        }
      }

      // Emit
      ctx.emit(
        "trading.strategy.trade.proposal",
        "strategy.trade.proposal.v1",
        { asset: symbol },
        {
          ...proposal,
          symbol,
          generated_at:  Date.now(),
          regime:        regime.regime,
          regime_conf:   regime.confidence,
          validation_errors: errors,
        }
      );

      // Cooldown seulement si proposal active (pas HOLD)
      if (proposal.side !== "HOLD") {
        ctx.state.cooldowns[symbol] = Date.now();
      }

      const emoji = proposal.side === "BUY" ? "🟢"
                  : proposal.side === "SELL" ? "🔴" : "⚪";

      ctx.log(
        `${emoji} ${symbol}: ${proposal.side} ` +
        `strat=${proposal.strategy} ` +
        `conf=${proposal.confidence} ` +
        `${proposal.side !== "HOLD" ? `entry=${proposal.setup?.entry} stop=${proposal.setup?.stop} tp=${proposal.setup?.tp} rr=${proposal.setup?.risk_reward}` : ""}`
      );

      proposals++;

    } catch (e) {
      ctx.log(`⚠️ ${symbol}: erreur — ${e.message}`);
    }
  }

  ctx.log(`✅ ${proposals} proposals générées`);
}
