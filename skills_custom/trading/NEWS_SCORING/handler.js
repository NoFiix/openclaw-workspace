/**
 * NEWS_SCORING — Handler
 * Catégorise et score les raw news/posts via Claude Haiku.
 * Fast path : si social.post.priority = CRITICAL → traitement immédiat.
 * Émet : trading.intel.news.event + trading.ops.alert (si urgency >= 9 ET fiabilité >= 0.7)
 */

import fs   from "fs";
import path from "path";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";
const MAX_TOKENS    = 400;
const TIMEOUT_MS    = 15000;

// Mots extrêmes déclenchant la protection anti-manipulation
const EXTREME_WORDS = ["hack", "exploit", "ban", "crash", "shutdown", "arrest", "seized", "scam", "rug"];

function hasSocialNonOfficialSource(item) {
  return item.feed === "nitter" || item.source === "nitter";
}

function hasExtremeWords(text) {
  const lower = text.toLowerCase();
  return EXTREME_WORDS.some(w => lower.includes(w));
}

function getBaseReliability(item) {
  const priority = item.priority ?? "UNKNOWN";
  if (priority === "CRITICAL")      return 0.85;
  if (priority === "MARKET_MOVERS") return 0.60;
  if (priority === "NARRATIVE")     return 0.30;
  if (item.feed === "cryptopanic")  return 0.65;
  return 0.50;
}

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

function buildSystemPrompt() {
  return `Tu es NEWS_SCORING, un agent d'analyse de news crypto.
Analyse la news fournie et retourne UNIQUEMENT un objet JSON valide, sans texte avant ou après.

Format de réponse :
{
  "category": "REGULATION|HACK|LISTING|ETF|MACRO|PARTNERSHIP|SOCIAL_INFLUENCER",
  "urgency": 0,
  "entities": ["BTC", "ETH"],
  "summary": "max 2 phrases factuelles"
}

Règles urgency (0-10) :
- 9-10 : ETF approval/rejection, hack majeur exchange, sanction SEC, décision Fed, listing majeur
- 7-8 : Listing Binance/Coinbase, décision réglementaire, partenariat tier-1
- 5-6 : Déclaration influenceur, rumeur corroborée, analyse macro importante
- 1-4 : News de fond, opinion, faible impact estimé
- 0 : Bruit, hors sujet crypto/finance

Ne jamais inventer d'informations. Si incertain → urgency bas.`;
}

function buildUserPrompt(item) {
  const text = item.headline ?? item.content ?? "";
  const src  = item.source ?? item.handle ?? "unknown";
  return `Source: ${src}\nTexte: ${text}`;
}

async function sendTelegramAlert(token, chatId, event) {
  try {
    const msg = `🚨 *NEWS CRITIQUE*\n\n` +
      `📰 ${event.headline}\n\n` +
      `📊 Urgence: ${event.urgency}/10 | Fiabilité: ${(event.reliability.score * 100).toFixed(0)}%\n` +
      `🏷️ ${event.category} | ${event.entities.join(", ")}\n\n` +
      `📝 ${event.summary}`;

    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: msg, parse_mode: "Markdown" }),
    });
  } catch (e) {
    console.error("[NEWS_SCORING] Telegram alert error:", e.message);
  }
}

export async function handler(ctx) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const tgToken  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const tgChatId = process.env.TRADER_TELEGRAM_CHAT_ID;

  if (!apiKey) { ctx.log("❌ ANTHROPIC_API_KEY manquant"); return; }

  // Lire les nouveaux posts et articles depuis le bus
  const postCursor    = ctx.state.cursors?.social_posts ?? 0;
  const articleCursor = ctx.state.cursors?.news_articles ?? 0;

  const { events: posts,    nextCursor: nextPostCursor    } = ctx.bus.readSince("trading.raw.social.post",   postCursor,    50);
  const { events: articles, nextCursor: nextArticleCursor } = ctx.bus.readSince("trading.raw.news.article", articleCursor, 50);

  const items = [
    ...posts.map(e    => ({ ...e.payload, _event_id: e.event_id, _type: "social" })),
    ...articles.map(e => ({ ...e.payload, _event_id: e.event_id, _type: "article" })),
  ];

  if (items.length === 0) {
    ctx.log("Aucune nouvelle news à traiter");
    ctx.state.cursors = { ...ctx.state.cursors, social_posts: nextPostCursor, news_articles: nextArticleCursor };
    return;
  }

  ctx.log(`📰 ${items.length} items à scorer (${posts.length} posts + ${articles.length} articles)`);

  let scored = 0, alerts = 0;

  for (const item of items) {
    const text = item.headline ?? item.content ?? "";
    if (!text || text.length < 10) continue;

    try {
      // ── Appel Haiku ─────────────────────────────────────────
      const raw = await callHaiku(apiKey, buildSystemPrompt(), buildUserPrompt(item));
      if (!raw) { ctx.log(`⚠️ Haiku no response pour: ${text.slice(0, 50)}`); continue; }

      let parsed;
      try {
        const clean = raw.replace(/```json|```/g, "").trim();
        parsed = JSON.parse(clean);
      } catch {
        ctx.log(`⚠️ JSON invalide: ${raw.slice(0, 100)}`); continue;
      }

      // ── Calcul fiabilité ─────────────────────────────────────
      let reliability = getBaseReliability(item);

      // Protection anti-manipulation
      if (hasSocialNonOfficialSource(item) && hasExtremeWords(text)) {
        reliability = Math.min(reliability, 0.40);
      }

      // Boost si plusieurs sources confirment (cryptopanic votes)
      const confirmedBy = item.votes?.important ?? 0;
      if (confirmedBy >= 3) reliability = Math.min(reliability + 0.15, 0.95);

      // ── Event final ──────────────────────────────────────────
      const event = {
        headline:    text.slice(0, 200),
        category:    parsed.category ?? "MACRO",
        urgency:     Math.min(10, Math.max(0, parseInt(parsed.urgency) || 0)),
        reliability: {
          score:        parseFloat(reliability.toFixed(2)),
          confirmed_by: confirmedBy,
          sources_checked: [item.source ?? item.handle ?? "unknown"],
        },
        entities:         parsed.entities ?? [],
        summary:          parsed.summary ?? "",
        manipulation_flags: (hasSocialNonOfficialSource(item) && hasExtremeWords(text))
          ? ["social_non_official_extreme_words"]
          : [],
        source_refs: [{
          name: item.source ?? item.handle ?? "unknown",
          url:  item.url ?? "",
          type: item._type === "social" ? "social" : "media",
        }],
        original_event_id: item._event_id,
      };

      // Filtre : urgency trop basse → pas d'event
      if (event.urgency < 3) {
        ctx.log(`  ⏭  ${text.slice(0, 60)} → urgency=${event.urgency} (trop bas)`);
        continue;
      }

      ctx.emit("trading.intel.news.event", "intel.news.event.v1", { asset: "MARKET" }, event);
      scored++;

      ctx.log(
        `  ✅ ${event.category} urgency=${event.urgency} fiab=${reliability.toFixed(2)} ` +
        `| ${text.slice(0, 60)}`
      );

      // ── Alerte Telegram si critique ──────────────────────────
      if (event.urgency >= 9 && reliability >= 0.70 && tgToken && tgChatId) {
        await sendTelegramAlert(tgToken, tgChatId, event);
        ctx.emit("trading.ops.alert", "ops.alert.v1", {},
          { severity: "HIGH", message: event.headline, source: "NEWS_SCORING", urgency: event.urgency }
        );
        alerts++;
        ctx.log(`  🚨 ALERTE Telegram envoyée!`);
      }

    } catch (e) {
      ctx.log(`⚠️ Erreur scoring: ${e.message}`);
    }
  }

  // Mise à jour curseurs
  ctx.state.cursors = {
    ...ctx.state.cursors,
    social_posts:   nextPostCursor,
    news_articles:  nextArticleCursor,
  };

  ctx.log(`✅ ${scored} events émis | ${alerts} alertes Telegram`);
}
