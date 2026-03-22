const { saveWaitingSelection } = require("./pending");
/**
 * scraper.js - Skill de scraping crypto pour CryptoRizon
 * 
 * Sources EN : cointelegraph.com, coindesk.com, theblock.co, decrypt.co
 * Sources FR : cryptoast.fr, journalducoin.com
 * 
 * Output : workspace/intel/DAILY-INTEL.md + workspace/intel/data/YYYY-MM-DD.json
 * Notification : Telegram avec liste numérotée
 */

const https  = require("https");
const http   = require("http");
const path   = require("path");
const fs     = require("fs");

const WORKSPACE = "/home/node/.openclaw/workspace";

const SOURCES = [
  { name: "CoinTelegraph", url: "https://cointelegraph.com/rss", lang: "EN" },
  { name: "CoinDesk",      url: "https://www.coindesk.com/arc/outboundfeeds/rss", lang: "EN" },
  { name: "The Block",     url: "https://www.theblock.co/rss.xml", lang: "EN" },
  { name: "Decrypt",       url: "https://decrypt.co/feed", lang: "EN" },
  { name: "Cryptoast",     url: "https://cryptoast.fr/feed/", lang: "FR" },
  { name: "JournalDuCoin", url: "https://journalducoin.com/feed/", lang: "FR" },
];

/**
 * Fetch une URL avec redirect support
 */
function fetchUrl(url, maxRedirects = 5) {
  return new Promise((resolve, reject) => {
    if (maxRedirects === 0) return reject(new Error("Too many redirects"));

    const client = url.startsWith("https") ? https : http;
    const req = client.get(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; CryptoRizon-Bot/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
      },
      timeout: 10000,
    }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        return resolve(fetchUrl(res.headers.location, maxRedirects - 1));
      }
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve(data));
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("Timeout")); });
  });
}

/**
 * Parse un feed RSS simple
 */
function parseRSS(xml, sourceName, lang) {
  const items = [];
  const itemRegex = /<item[^>]*>([\s\S]*?)<\/item>/gi;
  let match;

  while ((match = itemRegex.exec(xml)) !== null) {
    const item = match[1];

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

  return items.slice(0, 10); // max 10 par source
}

function extractTag(xml, tag) {
  const match = xml.match(new RegExp(`<${tag}[^>]*><!\\[CDATA\\[([\\s\\S]*?)\\]\\]><\\/${tag}>`, "i"))
    || xml.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i"));
  return match ? match[1].trim() : null;
}

function cleanText(text) {
  return text
    .replace(/<!\[CDATA\[|\]\]>/g, "")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .trim();
}

/**
 * Déduplique les articles par titre similaire
 */
function deduplicate(items) {
  const seen  = new Set();
  const clean = [];

  for (const item of items) {
    const key = item.title.toLowerCase().slice(0, 60);
    if (!seen.has(key)) {
      seen.add(key);
      clean.push(item);
    }
  }

  return clean;
}

/**
 * Envoie un message Telegram
 */
function sendTelegram(message) {
  return new Promise((resolve) => {
    const token  = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
    const chatId = process.env.BUILDER_TELEGRAM_CHAT_ID;

    if (!token || !chatId) {
      console.log("[telegram] Variables manquantes, skip");
      return resolve(false);
    }

    const body = JSON.stringify({
      chat_id:    chatId,
      text:       message,
      parse_mode: "HTML",
    });

    const req = https.request({
      hostname: "api.telegram.org",
      path:     `/bot${token}/sendMessage`,
      method:   "POST",
      headers:  {
        "Content-Type":   "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => resolve(true));
    });

    req.on("error", () => resolve(false));
    req.write(body);
    req.end();
  });
}

/**
 * Sauvegarde les résultats
 */
function saveResults(items) {
  const today     = new Date().toISOString().split("T")[0];
  const intelDir  = path.join(WORKSPACE, "intel");
  const dataDir   = path.join(intelDir, "data");

  [intelDir, dataDir].forEach(d => {
    try { fs.mkdirSync(d, { recursive: true }); } catch(e) {}
  });

  // Sauvegarde JSON brut
  const jsonPath = path.join(dataDir, `${today}.json`);
  fs.writeFileSync(jsonPath, JSON.stringify({ date: today, items }, null, 2));

  // Génère DAILY-INTEL.md avec liste numérotée
  const lines = [
    `# DAILY-INTEL — ${today}`,
    ``,
    `> Généré automatiquement par le scraper CryptoRizon`,
    `> ${items.length} articles collectés`,
    ``,
    `## 📰 News du jour`,
    ``,
  ];

  items.forEach((item, i) => {
    lines.push(`**${i + 1}.** [${item.title}](${item.link})`);
    lines.push(`   🔤 ${item.source} (${item.lang}) — ${item.date.slice(0, 10)}`);
    lines.push(``);
  });

  const mdPath = path.join(intelDir, "DAILY-INTEL.md");
  fs.writeFileSync(mdPath, lines.join("\n"));

  console.log(`[scraper] Sauvegardé : ${mdPath}`);
  console.log(`[scraper] Sauvegardé : ${jsonPath}`);

  return { mdPath, jsonPath, today };
}

/**
 * Fonction principale
 */
async function runScraper() {
  console.log(`\n=== SCRAPER CRYPTO ${new Date().toISOString()} ===\n`);

  const allItems = [];
  const errors   = [];

  for (const source of SOURCES) {
    try {
      console.log(`[fetch] ${source.name}...`);
      const xml   = await fetchUrl(source.url);
      const items = parseRSS(xml, source.name, source.lang);
      console.log(`[ok] ${source.name} → ${items.length} articles`);
      allItems.push(...items);
    } catch (e) {
      console.error(`[error] ${source.name} → ${e.message}`);
      errors.push({ source: source.name, error: e.message });
    }
  }

  // Tri par date (plus récent en premier) + déduplication
  allItems.sort((a, b) => new Date(b.date) - new Date(a.date));
  const items = deduplicate(allItems).slice(0, 20); // max 20 articles

  console.log(`\n[scraper] Total après dédup : ${items.length} articles\n`);

  // Sauvegarde
  saveResults(items);

  // Notification Telegram
  const lines = [`🦞 <b>CryptoRizon Daily Intel</b>\n`];
  lines.push(`📅 ${new Date().toISOString().slice(0, 10)}`);
  lines.push(`📊 ${items.length} articles collectés\n`);
  lines.push(`Sélectionne les numéros à publier :\n`);

  // Traduction des titres EN → FR via Claude Haiku
  // Traduction séquentielle pour éviter le rate limiting
  const titresFR = [];
  for (const item of items) {
    if (item.lang === "FR") {
      titresFR.push(item.title);
      continue;
    }
    try {
      await new Promise(r => setTimeout(r, 200)); // 200ms entre chaque appel
      const res = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": process.env.ANTHROPIC_API_KEY,
          "anthropic-version": "2023-06-01"
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001",
          max_tokens: 60,
          messages: [{ role: "user", content: "Traduis ce titre en français en une seule ligne, sans formatage: " + item.title }]
        })
      });
      const data = await res.json();
      const text = data.content?.[0]?.text?.trim() || item.title;
      titresFR.push(text);
    } catch { titresFR.push(item.title); }
  }

  items.forEach((item, i) => {
    lines.push(`<b>${i + 1}.</b> ${titresFR[i]}`);
    lines.push(`   — ${item.source}`);
  });

  lines.push(`\nRéponds avec les numéros (ex: 1,3,5) pour que le copywriter rédige les posts.`);

  await sendTelegram(lines.join("\n"));
  console.log(`[telegram] Notification envoyée`);
  saveWaitingSelection(items);

  return { items, errors };
}

// Lance directement si exécuté en standalone
if (require.main === module) {
  runScraper().then(({ items, errors }) => {
    console.log(`\n=== RÉSUMÉ ===`);
    console.log(`Articles : ${items.length}`);
    console.log(`Erreurs  : ${errors.length}`);
    if (errors.length) console.log("Erreurs:", errors);
  }).catch(console.error);
}

module.exports = { runScraper };
