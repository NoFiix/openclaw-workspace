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

const SYSTEM_PROMPT = `Tu es le copywriter de CryptoRizon (@CryptoRizon sur Twitter).
Tu rédiges des posts Twitter crypto percutants en français.

STYLE — David Ogilvy, Gary Halbert, Stan Leloup :
- Phrases ultra-courtes. Une idée par ligne. Jamais deux.
- Rythme rapide. Tension. Accroche immédiate. Le lecteur ne peut pas s'arrêter.
- Ton direct, proche, légèrement familier mais crédible.
- Chaque mot compte. Zéro remplissage.
- Maximum 1 emoji par post, jamais en début de phrase.
- Zéro hashtag. Zéro lien dans le post.
- Langue : français uniquement.

CRITÈRES DE SÉLECTION DE L'ARTICLE :
- Priorité à l'article mentionné par le plus de sources (signe d'intérêt général du marché)
- Préfère les breaking news, chiffres clés, événements qui changent la donne
- Évite le contenu trop technique ou trop niche
- Si un titre apparaît sous plusieurs formes similaires → c'est lui qu'il faut choisir

FORMAT DE RÉPONSE — JSON strict, rien d'autre, pas de markdown :
{
  "selected_index": <numéro 1-based de l'article choisi>,
  "selected_url": "<url exacte copiée telle quelle>",
  "post": "<post Twitter complet, max 280 caractères>"
}`;

async function selectAndWrite(candidates) {
  const list = candidates.map((a, i) =>
    `${i + 1}. [${a.source}] ${a.title} — ${a.link}`
  ).join("\n");

  const userMsg = `Voici ${candidates.length} articles crypto récents.\n` +
    `Choisis le plus pertinent/viral et rédige un post Twitter style CryptoRizon.\n\n${list}`;

  const body = JSON.stringify({
    model:      "claude-sonnet-4-6",
    max_tokens: 500,
    system:     SYSTEM_PROMPT,
    messages:   [{ role: "user", content: userMsg }],
  });

  return new Promise((resolve, reject) => {
    const req = https.request({
      hostname: "api.anthropic.com",
      path:     "/v1/messages",
      method:   "POST",
      headers:  {
        "Content-Type":      "application/json",
        "Content-Length":    Buffer.byteLength(body),
        "x-api-key":         ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
      },
    }, (res) => {
      let raw = "";
      res.on("data", c => raw += c);
      res.on("end", () => {
        try {
          const text    = JSON.parse(raw).content?.[0]?.text?.trim() || "";
          const cleaned = text.replace(/```json\n?|```/g, "").trim();
          const parsed  = JSON.parse(cleaned);
          if (!parsed.post || !parsed.selected_url) throw new Error("Réponse Claude incomplète");
          resolve(parsed);
        } catch (e) {
          reject(new Error(`Parsing Claude échoué: ${e.message}`));
        }
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
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

  console.log(`[hourly] Candidats finaux: ${candidates.length} articles (fenêtre: ${windowUsed}h)`);

  // ── Claude : sélection + rédaction (1 seul appel) ──
  let result;
  try {
    result = await selectAndWrite(candidates);
    console.log(`[hourly] Claude a sélectionné l'article #${result.selected_index}`);
    console.log(`[hourly] URL: ${result.selected_url}`);
    console.log(`[hourly] Post (${result.post.length} chars): ${result.post.slice(0, 80)}...`);
  } catch (e) {
    console.error(`[hourly] ❌ Erreur Claude: ${e.message}`);
    process.exit(1);
  }
  const srcName = candidates.find(a => a.link === result.selected_url)?.source || "Source";
  const tweet2 = `🗞 ${result.selected_url}`;
  saveSeen(seenEntries, result.selected_url);
  saveDraft(result.post, tweet2);
  console.log("[hourly] Draft sauvegardé → current_draft.json");
  const tgResult = await sendToTelegram(result.post, tweet2);
  if (tgResult.ok) { console.log("[hourly] ✅ Post envoyé sur Telegram"); }
  else { console.error("[hourly] ❌ Erreur Telegram:", JSON.stringify(tgResult)); }
}
run().catch(e => {
  console.error("[hourly] ❌ Erreur fatale:", e.message);
  process.exit(1);
});
