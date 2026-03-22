/**
 * hourly_scraper.js - Scraper horaire CryptoRizon
 *
 * Tourne toutes les heures de 7h à 23h via cron sur le host
 * → Fetch 6 RSS → filtre 2h (ou 4h si rien) → Claude choisit + rédige → Draft → Builder
 *
 * Cron host (openclawadmin) :
 *   0 7-23 * * * docker exec openclaw-openclaw-gateway-1 node /home/node/.openclaw/workspace/skills_custom/hourly_scraper.js >> /home/openclawadmin/openclaw/workspace/state/hourly_scraper.log 2>&1
 */

const https = require("https");
const http  = require("http");
const fs    = require("fs");
const path  = require("path");

const { createDraft, sendDraft } = require("./drafts");

const WORKSPACE   = "/home/node/.openclaw/workspace";
const SEEN_FILE   = path.join(WORKSPACE, "state", "seen_articles.json");

const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const BUILDER_TOKEN = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
const BUILDER_CHAT  = process.env.BUILDER_TELEGRAM_CHAT_ID;

const SEEN_TTL_MS = 24 * 60 * 60 * 1000;

const SOURCES = [
  { name: "CoinTelegraph",   url: "https://cointelegraph.com/rss",                        lang: "EN" },
  { name: "CoinDesk",        url: "https://www.coindesk.com/arc/outboundfeeds/rss",       lang: "EN" },
  { name: "Bitcoin Magazine", url: "https://bitcoinmagazine.com/feed",                    lang: "EN" },
  { name: "The Defiant",     url: "https://thedefiant.io/api/feed",                       lang: "EN" },
  { name: "Cryptoast",       url: "https://cryptoast.fr/feed/",                           lang: "FR" },
  { name: "JournalDuCoin",   url: "https://journalducoin.com/feed/",                      lang: "FR" },
];

// ─────────────────────────────────────────
// SEEN ARTICLES (anti-doublon 24h)
// ─────────────────────────────────────────

function loadSeen() {
  try {
    if (!fs.existsSync(SEEN_FILE)) return [];
    const data = JSON.parse(fs.readFileSync(SEEN_FILE, "utf8"));
    const now  = Date.now();
    return (data.urls || []).filter(e => (now - new Date(e.seenAt).getTime()) < SEEN_TTL_MS);
  } catch { return []; }
}

function saveSeen(currentEntries, newUrl) {
  const now    = Date.now();
  const purged = currentEntries.filter(e => (now - new Date(e.seenAt).getTime()) < SEEN_TTL_MS);
  purged.push({ url: newUrl, seenAt: new Date().toISOString() });
  fs.mkdirSync(path.dirname(SEEN_FILE), { recursive: true });
  fs.writeFileSync(SEEN_FILE, JSON.stringify({ urls: purged }, null, 2));
  try { fs.chmodSync(SEEN_FILE, 0o664); } catch {}
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
      headers: { "User-Agent": "Mozilla/5.0 (compatible; CryptoRizon-Bot/1.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*" },
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
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#039;/g, "'")
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
    } catch (e) { console.error(`[rss] ${src.name} erreur: ${e.message}`); }
  }
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
// CLAUDE — sélection (Haiku) + rédaction (Sonnet)
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

STRUCTURE OBLIGATOIRE :
- Ligne 1 = UNE SEULE phrase courte et impactante qui résume toute l'actu.
- Ensuite = détails factuels, un paragraphe par idée, séparés par une ligne vide.

LONGUEUR :
- 500 caractères MAX pour tous les posts, sans exception.
- 3-4 phrases maximum. Une idée par ligne. Zéro remplissage.
- Si tu dépasses 500 caractères, supprime la dernière idée complète. Ne coupe jamais une phrase en plein milieu.

RÈGLES :
- Extrais UNIQUEMENT les faits du corps de l'article. Zéro invention.
- Zéro hashtag. Zéro lien. Zéro CTA. Zéro conseil financier.
- NE PAS mettre la source — elle sera ajoutée automatiquement.
- Langue : français uniquement.`;

async function selectBestArticle(candidates) {
  const list = candidates.map((a, i) => `${i + 1}. [${a.source}] ${a.title}`).join("\n");
  const body = JSON.stringify({
    model: "claude-haiku-4-5-20251001", max_tokens: 80,
    system: `Éditeur crypto. Réponds UNIQUEMENT avec JSON valide : {"index": <numéro 1-based>}. Critères : breaking news > impact marché > grand public > chiffres précis.`,
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

async function fetchArticleBody(url) {
  try {
    const html = await fetchUrl(url);
    const ogImageMatch = html.match(/<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']+)["']/i)
      || html.match(/<meta[^>]*content=["']([^"']+)["'][^>]*property=["']og:image["']/i);
    const imageUrl = ogImageMatch ? ogImageMatch[1].replace(/&amp;/g, "&") : null;
    if (imageUrl) console.log(`[article] og:image trouvée: ${imageUrl}`);
    const stripped = html
      .replace(/<script[\s\S]*?<\/script>/gi, "")
      .replace(/<style[\s\S]*?<\/style>/gi, "")
      .replace(/<nav[\s\S]*?<\/nav>/gi, "")
      .replace(/<header[\s\S]*?<\/header>/gi, "")
      .replace(/<footer[\s\S]*?<\/footer>/gi, "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ").trim();
    return { body: stripped.slice(0, 3000), imageUrl };
  } catch (e) {
    console.error(`[article] Impossible de fetcher: ${e.message}`);
    return { body: null, imageUrl: null };
  }
}

async function writePost(article, bodyText) {
  const content = bodyText
    ? `Titre : ${article.title}\nSource : ${article.source}\n\nCorps :\n${bodyText}`
    : `Titre : ${article.title}\nSource : ${article.source}`;
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
          const json = JSON.parse(raw);
          if (json.error) {
            reject(new Error(`API ${res.statusCode}: ${json.error.message || JSON.stringify(json.error)}`));
            return;
          }
          const text = json.content?.[0]?.text?.trim() || "";
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
// MAIN
// ─────────────────────────────────────────

async function run() {
  console.log(`\n=== HOURLY SCRAPER ${new Date().toISOString()} ===`);

  if (!BUILDER_TOKEN || !BUILDER_CHAT || !ANTHROPIC_KEY) {
    console.error("[hourly] ❌ Variables d'environnement manquantes");
    process.exit(1);
  }

  const seenEntries = loadSeen();
  console.log(`[hourly] ${seenEntries.length} articles déjà vus dans les 24h`);

  const allArticles = await fetchAllArticles();
  console.log(`[hourly] Total brut: ${allArticles.length} articles`);

  // Stratégie fenêtre glissante
  let candidates = [];

  const unseen2h = removeSeen(filterByWindow(allArticles, 2), seenEntries);
  console.log(`[hourly] Fenêtre 2h: ${unseen2h.length} non-vus`);

  if (unseen2h.length > 0) {
    candidates = unseen2h;
  } else {
    const unseen4h = removeSeen(filterByWindow(allArticles, 4), seenEntries);
    console.log(`[hourly] Fenêtre 4h: ${unseen4h.length} non-vus`);

    if (unseen4h.length > 0) {
      candidates = unseen4h;
    } else {
      const unseenAll = removeSeen(allArticles, seenEntries);
      candidates = unseenAll.length > 0 ? unseenAll : allArticles.slice(0, 5);
      console.log(`[hourly] Fallback: ${candidates.length} articles`);
    }
  }

  // Haiku sélectionne le meilleur article
  const selected = await selectBestArticle(candidates);

  // Fetch le corps + image
  const { body: articleBody, imageUrl } = await fetchArticleBody(selected.link);

  // Sonnet rédige le post
  let post;
  try {
    post = await writePost(selected, articleBody);
    console.log(`[hourly] Post rédigé (${post.length} chars)`);
  } catch (e) {
    console.error(`[hourly] ❌ Erreur Sonnet: ${e.message}`);
    process.exit(1);
  }

  // Marquer comme vu
  saveSeen(seenEntries, selected.link);

  // Créer le draft (injecte - NomSource automatiquement)
  const id = createDraft(post, "hourly", imageUrl, selected.link);
  console.log(`[hourly] Draft ${id} créé`);

  // Envoyer dans Builder
  await sendDraft(id);
  console.log(`[hourly] ✅ Draft ${id} envoyé dans Builder`);
}

run().catch(e => {
  console.error("[hourly] ❌ Erreur fatale:", e.message);
  process.exit(1);
});
