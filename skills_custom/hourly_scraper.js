/**
 * hourly_scraper.js - Scraper horaire CryptoRizon
 *
 * Tourne toutes les heures de 7h à 23h via cron sur le host
 * → Fetch 6 RSS → filtre 2h (ou 4h si rien) → Claude choisit + rédige → Telegram + boutons
 * → Le poller existant gère publish/modify/cancel sans modification
 *
 * Cron host (openclawadmin) :
 *   0 7-23 * * * docker exec openclaw-openclaw-gateway-1 node /home/node/.openclaw/workspace/skills_custom/hourly_scraper.js >> /home/openclawadmin/openclaw/workspace/state/hourly_scraper.log 2>&1
 */

const https   = require("https");
const http    = require("http");
const fs      = require("fs");
const path    = require("path");

const WORKSPACE   = "/home/node/.openclaw/workspace";
const SEEN_FILE   = path.join(WORKSPACE, "state", "seen_articles.json");
const DRAFT_FILE  = path.join(WORKSPACE, "state", "current_draft.json");

const BUILDER_TOKEN = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
const BUILDER_CHAT  = process.env.BUILDER_TELEGRAM_CHAT_ID;
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;

const SEEN_TTL_MS = 24 * 60 * 60 * 1000; // 24h

const SOURCES = [
  { name: "CoinTelegraph", url: "https://cointelegraph.com/rss",                          lang: "EN" },
  { name: "CoinDesk",      url: "https://www.coindesk.com/arc/outboundfeeds/rss",         lang: "EN" },
  { name: "The Block",     url: "https://www.theblock.co/rss.xml",                        lang: "EN" },
  { name: "Decrypt",       url: "https://decrypt.co/feed",                                lang: "EN" },
  { name: "Cryptoast",     url: "https://cryptoast.fr/feed/",                             lang: "FR" },
  { name: "JournalDuCoin", url: "https://journalducoin.com/feed/",                        lang: "FR" },
];

// ─────────────────────────────────────────
// SEEN ARTICLES  (anti-doublon 24h)
// ─────────────────────────────────────────

function loadSeen() {
  try {
    if (!fs.existsSync(SEEN_FILE)) return [];
    const data = JSON.parse(fs.readFileSync(SEEN_FILE, "utf8"));
    const now  = Date.now();
    // On purge les entrées > 24h à chaque lecture
    return (data.urls || []).filter(e => (now - new Date(e.seenAt).getTime()) < SEEN_TTL_MS);
  } catch { return []; }
}

function saveSeen(currentEntries, newUrl) {
  const now    = Date.now();
  const purged = currentEntries.filter(e => (now - new Date(e.seenAt).getTime()) < SEEN_TTL_MS);
  purged.push({ url: newUrl, seenAt: new Date().toISOString() });
  fs.mkdirSync(path.dirname(SEEN_FILE), { recursive: true });
  fs.writeFileSync(SEEN_FILE, JSON.stringify({ urls: purged }, null, 2));
  console.log(`[seen] +1 URL enregistrée (total: ${purged.length})`);
}

// ─────────────────────────────────────────
// RSS FETCH / PARSE
// ─────────────────────────────────────────

function fetchUrl(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    if (maxRedirects === 0) return reject(new Error("Too many redirects"));
    const client = url.startsWith("https") ? https : http;
    const req = client.get(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; CryptoRizon-Bot/1.0)",
        "Accept":     "application/rss+xml, application/xml, text/xml, */*",
      },
      timeout: 10000,
    }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location)
        return resolve(fetchUrl(res.headers.location, maxRedirects - 1));
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => resolve(data));
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("Timeout")); });
  });
}

function extractTag(xml, tag) {
  const m = xml.match(new RegExp(`<${tag}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]><\\/${tag}>`, "i"))
           || xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return m ? m[1].trim() : null;
}

function cleanText(text) {
  return text
    .replace(/<!\[CDATA\[|\]\]>/g, "")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g,  "&")
    .replace(/&lt;/g,   "<")
    .replace(/&gt;/g,   ">")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .trim();
}

function parseRSS(xml, sourceName, lang) {
  const items     = [];
  const itemRegex = /<item[^>]*>([\s\S]*?)<\/item>/gi;
  let match;
  while ((match = itemRegex.exec(xml)) !== null) {
    const item  = match[1];
    const title = extractTag(item, "title");
    const link  = extractTag(item, "link");
    const date  = extractTag(item, "pubDate") || extractTag(item, "dc:date");
    if (title && link) {
      items.push({
        title:  cleanText(title),
        link:   cleanText(link),
        source: sourceName,
        lang,
        date:   date ? new Date(date).toISOString() : new Date().toISOString(),
      });
    }
  }
  return items.slice(0, 10);
}

async function fetchAllArticles() {
  const all = [];
  for (const src of SOURCES) {
    try {
      const xml   = await fetchUrl(src.url);
      const items = parseRSS(xml, src.name, src.lang);
      console.log(`[rss] ${src.name} → ${items.length} articles`);
      all.push(...items);
    } catch (e) {
      console.error(`[rss] ${src.name} erreur: ${e.message}`);
    }
  }
  // Tri chronologique inversé (plus récent en premier)
  all.sort((a, b) => new Date(b.date) - new Date(a.date));
  return all;
}

// ─────────────────────────────────────────
// FILTRAGE
// ─────────────────────────────────────────

function filterByWindow(articles, hoursBack) {
  const cutoff = new Date(Date.now() - hoursBack * 60 * 60 * 1000);
  return articles.filter(a => new Date(a.date) > cutoff);
}

function removeSeen(articles, seenEntries) {
  const seenUrls = new Set(seenEntries.map(e => e.url));
  return articles.filter(a => !seenUrls.has(a.link));
}

// ─────────────────────────────────────────
// CLAUDE — sélection + rédaction (1 seul appel)
// ─────────────────────────────────────────


const SYSTEM_PROMPT = `Tu es le copywriter de CryptoRizon. Tu rédiges des posts Twitter crypto en français dans le style exact de @Crypto__Goku.

RÈGLE EMOJI — commence TOUJOURS par UN seul emoji parmi :
🚨 breaking news, hack, arrestation, alerte urgente
⚠️ risque, fraude, arnaque, régulation hostile
💰 levée de fonds, résultats, acquisition, business
📉 chute de prix, liquidations, faillite, perte
🏦 institution, banque, ETF, gouvernement, SEC/Fed
🇺🇸🇬🇧🇨🇳🇫🇷 si l'actu concerne spécifiquement ce pays
⚡ record battu, annonce ultra-rapide

STYLE :
- Première phrase = LE FAIT CLÉ. Chiffres précis si disponibles.
- Paragraphes courts séparés par une ligne vide.
- Longueur proportionnelle à l'importance :
  • Actu mineure = 2-3 phrases
  • Actu normale = 4-6 phrases
  • Actu majeure = 7-10 phrases
- Extrais UNIQUEMENT les faits du corps de l'article. Zéro invention.
- Zéro hashtag. Zéro lien. Zéro CTA. Zéro conseil financier.
- Zéro formule creuse ("les mains faibles", "richesse de demain", etc.)
- NE PAS mettre la source — elle sera dans le tweet suivant.
- Langue : français uniquement.

EXEMPLES RÉELS :
⚠️ Tether a déjà gelé plus de 4,2 milliards de dollars d'USDT liés à des activités illicites dont 3,5 milliards depuis 2023.

Cette semaine encore, l'entreprise a aidé le ministère de la Justice américain à bloquer près de 61 millions de dollars liés à des arnaques de type pig-butchering.

Plus de 180 milliards de dollars d'USDT sont actuellement en circulation.

L'entreprise peut geler à distance les $USDT dans n'importe quel portefeuille, sur simple demande des autorités.
---
💰 Le cofondateur de Wikipédia, Jimmy Wales, estime que Bitcoin ne disparaîtra probablement pas.

Selon lui, sa conception est suffisamment robuste pour durer indéfiniment, sauf en cas de faille crypto majeure ou d'attaque à 51 %.

En revanche, il pense que Bitcoin échouera comme monnaie et réserve de valeur. Il pourrait valoir moins de 10 000 dollars d'ici 2050.

Il considère Bitcoin comme un actif spéculatif, davantage porté par des amateurs que par une adoption massive.`;

async function fetchArticleBody(url) {
  try {
    const html = await fetchUrl(url);
    const stripped = html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<nav[\s\S]*?<\/nav>/gi, "")
      .replace(/<header[\s\S]*?<\/header>/gi, "")
      .replace(/<footer[\s\S]*?<\/footer>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ").trim();
    console.log(`[article] Corps fetché: ${stripped.length} chars`);
    return stripped.slice(0, 3000);
  } catch (e) {
    console.error(`[article] Impossible de fetcher: ${e.message}`);
    return null;
  }
}

async function selectBestArticle(candidates) {
  const list = candidates.map((a, i) => `${i + 1}. [${a.source}] ${a.title}`).join("\n");
  const body = JSON.stringify({
    model: "claude-haiku-4-5-20251001", max_tokens: 80,
    system: `Éditeur crypto. Réponds UNIQUEMENT avec JSON valide : {"index": <numéro 1-based>}. Critères : breaking news > chiffres précis > impact marché > grand public.`,
    messages: [{ role: "user", content: `Choisis le meilleur article à tweeter :\n\n${list}` }],
  });
  return new Promise((resolve) => {
    const req = https.request({
      hostname: "api.anthropic.com", path: "/v1/messages", method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body), "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01" },
    }, (res) => {
      let raw = "";
      res.on("data", c => raw += c);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(JSON.parse(raw).content?.[0]?.text?.replace(/```json\n?|```/g, "").trim() || "{}");
          const idx = Math.min(Math.max((parsed.index || 1) - 1, 0), candidates.length - 1);
          console.log(`[haiku] Sélectionné #${idx+1}: "${candidates[idx].title}"`);
          resolve(candidates[idx]);
        } catch { console.error("[haiku] Fallback #1"); resolve(candidates[0]); }
      });
    });
    req.on("error", () => resolve(candidates[0]));
    req.write(body); req.end();
  });
}

async function writePost(article, bodyText) {
  const content = bodyText
    ? `Titre : ${article.title}\nSource : ${article.source}\n\nCorps :\n${bodyText}`
    : `Titre : ${article.title}\nSource : ${article.source}\nRésumé : ${article.summary || ""}`;
  const body = JSON.stringify({
    model: "claude-sonnet-4-6", max_tokens: 600,
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: `Rédige le post Twitter pour cette actu :\n\n${content}` }],
  });
  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: "api.anthropic.com", path: "/v1/messages", method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body), "x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01" },
    }, (res) => {
      let raw = "";
      res.on("data", c => raw += c);
      res.on("end", () => {
        try {
          const text = JSON.parse(raw).content?.[0]?.text?.trim() || "";
          if (!text) throw new Error("Réponse vide");
          resolve(text);
        } catch (e) { reject(new Error(`Erreur Sonnet: ${e.message}`)); }
      });
    });
    req.on("error", reject);
    req.write(body); req.end();
  });
}
// ─────────────────────────────────────────
// TELEGRAM
// ─────────────────────────────────────────

function tgRequest(method, body) {
  return new Promise((resolve) => {
    const data = JSON.stringify(body);
    const req  = https.request({
      hostname: "api.telegram.org",
      path:     `/bot${BUILDER_TOKEN}/${method}`,
      method:   "POST",
      headers:  {
        "Content-Type":   "application/json",
        "Content-Length": Buffer.byteLength(data),
      },
    }, (res) => {
      let raw = "";
      res.on("data", c => raw += c);
      res.on("end", () => { try { resolve(JSON.parse(raw)); } catch { resolve({}); } });
    });
    req.on("error", () => resolve({}));
    req.write(data);
    req.end();
  });
}

async function sendToTelegram(tweet1, tweet2) {
  const hour = new Date().toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" });
  const preview = `⚡ <b>POST HORAIRE ${hour} — @CryptoRizon</b>\n\n<b>Tweet 1 :</b>\n${tweet1}\n\n<b>Tweet 2 :</b>\n${tweet2}`;
  return tgRequest("sendMessage", {
    chat_id: BUILDER_CHAT,
    text: preview,
    parse_mode: "HTML",
    reply_markup: { inline_keyboard: [[{ text: "✅ Publier", callback_data: "publish" },{ text: "✏️ Modifier", callback_data: "modify" },{ text: "❌ Annuler", callback_data: "cancel" }]] },
  });
}

// ─────────────────────────────────────────
// DRAFT → poller existant le gère
// ─────────────────────────────────────────

function saveDraft(tweet1, tweet2) {
  fs.mkdirSync(path.dirname(DRAFT_FILE), { recursive: true });
  fs.writeFileSync(DRAFT_FILE, JSON.stringify({ content: tweet1, tweets: [tweet1, tweet2], type: "hourly", savedAt: new Date().toISOString() }, null, 2));
}
async function run() {
  const startTime = new Date().toISOString();
  console.log(`\n=== HOURLY SCRAPER ${startTime} ===`);

  // Vérification variables d'environnement
  if (!BUILDER_TOKEN || !BUILDER_CHAT || !ANTHROPIC_KEY) {
    console.error("[hourly] ❌ Variables d'environnement manquantes (BUILDER_TELEGRAM_BOT_TOKEN / BUILDER_TELEGRAM_CHAT_ID / ANTHROPIC_API_KEY)");
    process.exit(1);
  }

  // Charge les URLs déjà vues (anti-doublon 24h)
  const seenEntries = loadSeen();
  console.log(`[hourly] ${seenEntries.length} articles déjà vus dans les 24h`);

  // Fetch toutes les sources RSS
  const allArticles = await fetchAllArticles();
  console.log(`[hourly] Total brut: ${allArticles.length} articles`);

  // ── Stratégie fenêtre glissante ──
  let candidates = [];
  let windowUsed = 0;

  // 1. Fenêtre 2h — articles récents non-vus
  const fresh2h    = filterByWindow(allArticles, 2);
  const unseen2h   = removeSeen(fresh2h, seenEntries);
  console.log(`[hourly] Fenêtre 2h: ${fresh2h.length} articles, ${unseen2h.length} non-vus`);

  if (unseen2h.length > 0) {
    candidates = unseen2h;
    windowUsed = 2;
  } else {
    // 2. Élargissement à 4h si aucun article non-vu dans les 2h
    const fresh4h  = filterByWindow(allArticles, 4);
    const unseen4h = removeSeen(fresh4h, seenEntries);
    console.log(`[hourly] Fenêtre 4h: ${fresh4h.length} articles, ${unseen4h.length} non-vus`);

    if (unseen4h.length > 0) {
      candidates = unseen4h;
      windowUsed = 4;
    } else {
      // 3. Fallback absolu : prend tous les articles non-vus (rare en fin de journée)
      const unseenAll = removeSeen(allArticles, seenEntries);
      console.log(`[hourly] Fallback total: ${unseenAll.length} articles non-vus`);

      if (unseenAll.length === 0) {
        // Situation extrêmement rare : tous les articles du jour ont déjà été envoyés
        // On prend quand même le plus récent pour ne jamais faire silence
        candidates = allArticles.slice(0, 5);
        windowUsed = 999; // flag pour le log
        console.log("[hourly] ⚠️  Tous les articles déjà vus — fallback sur les 5 plus récents");
      } else {
        candidates = unseenAll;
        windowUsed = 0;
      }
    }
  }
  // ── Étape 1 : Haiku sélectionne le meilleur article (cheap) ──
  const selected = await selectBestArticle(candidates);
  // ── Étape 2 : Fetch le corps de l'article ──
  const articleBody = await fetchArticleBody(selected.link);
  // ── Étape 3 : Sonnet rédige le post avec le vrai contenu ──
  let post;
  try {
    post = await writePost(selected, articleBody);
    console.log(`[hourly] Post rédigé (${post.length} chars)`);
  } catch (e) {
    console.error(`[hourly] ❌ Erreur Sonnet: ${e.message}`);
    process.exit(1);
  }
  const tweet2 = `🗞 ${selected.link}`;
  saveSeen(seenEntries, selected.link);
  saveDraft(post, tweet2);
  console.log("[hourly] Draft sauvegardé → current_draft.json");
  const tgResult = await sendToTelegram(post, tweet2);
  if (tgResult.ok) { console.log("[hourly] ✅ Post envoyé sur Telegram"); }
  else { console.error("[hourly] ❌ Erreur Telegram:", JSON.stringify(tgResult)); }
}
run().catch(e => {
  console.error("[hourly] ❌ Erreur fatale:", e.message);
  process.exit(1);
});
