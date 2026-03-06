/**
 * NEWS_FEED — Handler v2
 * Sources :
 *   1. RSS crypto (CoinTelegraph, CoinDesk, Bitcoin Magazine, The Defiant, Cryptoast, JournalDuCoin)
 *   2. CryptoPanic API (token gratuit requis — CRYPTOPANIC_TOKEN dans .env)
 *   3. SEC EDGAR RSS (annonces officielles)
 *   4. Fear & Greed Index (alternative.me)
 * Nitter supprimé — mort depuis 2025.
 * Émet : trading.raw.news.article + trading.raw.social.post (Fear&Greed)
 */

import crypto from "crypto";

const TIMEOUT_MS = 10000;

// ── Sources RSS ──────────────────────────────────────────────────────────────
const RSS_SOURCES = [
  { name: "CoinTelegraph",   url: "https://cointelegraph.com/rss",                          lang: "en", priority: "HIGH" },
  { name: "CoinDesk",        url: "https://www.coindesk.com/arc/outboundfeeds/rss/",         lang: "en", priority: "HIGH" },
  { name: "BitcoinMagazine", url: "https://bitcoinmagazine.com/.rss/full/",                  lang: "en", priority: "MEDIUM" },
  { name: "TheDefiant",      url: "https://thedefiant.io/feed",                              lang: "en", priority: "MEDIUM" },
  { name: "Cryptoast",       url: "https://cryptoast.fr/feed/",                              lang: "fr", priority: "MEDIUM" },
  { name: "JournalDuCoin",   url: "https://journalducoin.com/feed/",                         lang: "fr", priority: "MEDIUM" },
  { name: "SEC_EDGAR", url: "https://efts.sec.gov/LATEST/search-index?q=%22bitcoin%22+OR+%22cryptocurrency%22+OR+%22digital+asset%22&forms=8-K&dateRange=custom&startdt=2025-01-01", lang: "en", priority: "CRITICAL" },
];

function makeHash(source, content) {
  return crypto.createHash("sha256")
    .update(`${source}:${content.slice(0, 100)}`)
    .digest("hex")
    .slice(0, 16);
}

async function fetchWithTimeout(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(url, {
      signal: controller.signal,
      headers: { "User-Agent": "Mozilla/5.0 (compatible; CryptoRizonBot/1.0)" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } finally {
    clearTimeout(timer);
  }
}

// Parse RSS/Atom générique
function parseFeed(xml, sourceName) {
  const items = [];

  // Atom <entry>
  const entryRegex = /<entry>([\s\S]*?)<\/entry>/g;
  let match;
  while ((match = entryRegex.exec(xml)) !== null) {
    const block   = match[1];
    const title   = extractTag(block, "title");
    const link    = /<link[^>]+href="([^"]+)"/.exec(block)?.[1]
                 ?? extractTag(block, "link");
    const updated = extractTag(block, "updated") || extractTag(block, "published");
    if (title) items.push({ title: cleanCdata(title), url: link ?? "", published: updated, source: sourceName });
  }

  // RSS <item>
  const itemRegex = /<item>([\s\S]*?)<\/item>/g;
  while ((match = itemRegex.exec(xml)) !== null) {
    const block   = match[1];
    const title   = extractTag(block, "title");
    const link    = extractTag(block, "link");
    const pubDate = extractTag(block, "pubDate");
    if (title) items.push({ title: cleanCdata(title), url: link ?? "", published: pubDate, source: sourceName });
  }

  return items;
}

function extractTag(xml, tag) {
  return new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, "i").exec(xml)?.[1]?.trim() ?? null;
}

function cleanCdata(str) {
  return str.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1").replace(/<[^>]+>/g, "").trim();
}

async function scrapeRSS(source, seenHashes, ctx) {
  try {
    const xml   = await fetchWithTimeout(source.url);
    const items = parseFeed(xml, source.name);
    let emitted = 0;

    for (const item of items.slice(0, 15)) {
      if (!item.title || item.title.length < 10) continue;
      const hash = makeHash(source.name, item.title);
      if (seenHashes.has(hash)) continue;
      seenHashes.add(hash);

      ctx.emit(
        "trading.raw.news.article",
        "raw.news.article.v1",
        { asset: "MARKET" },
        {
          headline:  item.title.slice(0, 300),
          url:       item.url,
          source:    source.name,
          lang:      source.lang,
          priority:  source.priority,
          published: item.published ?? "",
          hash,
          feed:      "rss",
        }
      );
      emitted++;
    }

    ctx.log(`  ✅ ${source.name} → ${emitted} nouveaux articles (${items.length} total)`);
    return emitted;

  } catch (e) {
    ctx.log(`  ⚠️ ${source.name} KO: ${e.message}`);
    return 0;
  }
}

async function scrapeCryptoPanic(seenHashes, ctx) {
  const token = process.env.CRYPTOPANIC_TOKEN;
  if (!token) {
    ctx.log("  ⏭  CryptoPanic — CRYPTOPANIC_TOKEN manquant (inscription gratuite sur cryptopanic.com)");
    return 0;
  }

  try {
    const url  = `https://cryptopanic.com/api/v1/posts/?auth_token=${token}&public=true&kind=news&currencies=BTC,ETH,BNB`;
    const text = await fetchWithTimeout(url);
    const data = JSON.parse(text);

    if (!data.results) return 0;
    let emitted = 0;

    for (const post of data.results.slice(0, 20)) {
      const content = post.title ?? "";
      const hash    = makeHash("cryptopanic", content);
      if (seenHashes.has(hash)) continue;
      seenHashes.add(hash);

      ctx.emit(
        "trading.raw.news.article",
        "raw.news.article.v1",
        { asset: "MARKET" },
        {
          headline:   content.slice(0, 300),
          url:        post.url ?? "",
          source:     post.source?.title ?? "cryptopanic",
          lang:       "en",
          priority:   "HIGH",
          published:  post.published_at ?? "",
          currencies: (post.currencies ?? []).map(c => c.code),
          votes:      post.votes ?? {},
          hash,
          feed:       "cryptopanic",
        }
      );
      emitted++;
    }

    ctx.log(`  ✅ CryptoPanic → ${emitted} nouveaux articles`);
    return emitted;

  } catch (e) {
    ctx.log(`  ⚠️ CryptoPanic KO: ${e.message}`);
    return 0;
  }
}

async function scrapeFearGreed(seenHashes, ctx) {
  try {
    const text = await fetchWithTimeout("https://api.alternative.me/fng/?limit=1");
    const data = JSON.parse(text);
    const item = data.data?.[0];
    if (!item) return 0;

    const content = `Fear & Greed Index: ${item.value} (${item.value_classification})`;
    const hash    = makeHash("feargreed", item.timestamp);
    if (seenHashes.has(hash)) return 0;
    seenHashes.add(hash);

    ctx.emit(
      "trading.raw.social.post",
      "raw.social.post.v1",
      { asset: "MARKET" },
      {
        handle:    "FearGreedIndex",
        priority:  "MARKET_MOVERS",
        content,
        value:     parseInt(item.value),
        classification: item.value_classification,
        timestamp: item.timestamp,
        hash,
        source:    "alternative.me",
        feed:      "fear_greed",
      }
    );

    ctx.log(`  ✅ Fear & Greed → ${item.value} (${item.value_classification})`);
    return 1;

  } catch (e) {
    ctx.log(`  ⚠️ Fear & Greed KO: ${e.message}`);
    return 0;
  }
}

export async function handler(ctx) {
  const seenHashes  = new Set(ctx.state.cache?.seen_hashes ?? []);
  const initialSize = seenHashes.size;

  ctx.log(`🔭 NEWS_FEED démarrage — ${seenHashes.size} hashes connus`);

  let totalArticles = 0;

  // 1. RSS sources
  for (const source of RSS_SOURCES.filter(s => s.name !== "SEC_EDGAR")) {
    totalArticles += await scrapeRSS(source, seenHashes, ctx);
  }

  // 1b. SEC EDGAR
  totalArticles += await scrapeSecEdgar(RSS_SOURCES.find(s => s.name === "SEC_EDGAR"), seenHashes, ctx);

  // 2. CryptoPanic (si token configuré)
  totalArticles += await scrapeCryptoPanic(seenHashes, ctx);

  // 3. Fear & Greed Index
  const fgCount = await scrapeFearGreed(seenHashes, ctx);

  // Sauvegarder hashes (max 1000)
  ctx.state.cache              = ctx.state.cache ?? {};
  ctx.state.cache.seen_hashes  = Array.from(seenHashes).slice(-1000);

  ctx.log(
    `✅ Terminé — ${totalArticles} articles + ${fgCount} fear&greed` +
    ` | ${seenHashes.size - initialSize} nouveaux | ${seenHashes.size} hashes total`
  );
}

// SEC EDGAR JSON parser
async function scrapeSecEdgar(source, seenHashes, ctx) {
  try {
    const res  = await fetch(source.url, { headers: { "User-Agent": "CryptoRizonBot/1.0 contact@cryptorizon.com" } });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const hits = data?.hits?.hits ?? [];
    let emitted = 0;

    for (const hit of hits.slice(0, 10)) {
      const s     = hit._source ?? {};
      const names = (s.display_names ?? []).join(", ").slice(0, 100);
      const form  = (s.root_forms ?? ["8-K"])[0];
      const date  = s.file_date ?? "";
      const adsh  = s.adsh ?? "";
      const cik   = (s.ciks?.[0] ?? "").replace(/^0+/, "");
      const adshClean = adsh.replace(/-/g, "");
      const url   = `https://www.sec.gov/Archives/edgar/data/${cik}/${adshClean}/`;
      const title = `SEC ${form}: ${names}`;
      const hash  = makeHash("sec_edgar", adsh);

      if (!adsh || seenHashes.has(hash)) continue;
      seenHashes.add(hash);

      ctx.emit("trading.raw.news.article", "raw.news.article.v1", { asset: "MARKET" }, {
        headline: title.slice(0, 300), url, source: "SEC_EDGAR", lang: "en",
        priority: "CRITICAL", published: date, hash, feed: "sec_edgar",
      });
      emitted++;
    }
    ctx.log(`  ✅ SEC_EDGAR → ${emitted} nouveaux filings crypto (${hits.length} total)`);
    return emitted;
  } catch (e) {
    ctx.log(`  ⚠️ SEC_EDGAR KO: ${e.message}`);
    return 0;
  }
}
