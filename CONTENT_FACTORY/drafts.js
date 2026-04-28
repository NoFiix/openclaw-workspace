/**
 * drafts.js - Module partagé de gestion des drafts
 *
 * Utilisé par : poller.js, hourly_scraper.js
 *
 * - Stockage dans state/drafts.json
 * - IDs #1→#100 avec reset
 * - Purge auto des drafts > 24h
 * - sendDraft() envoie dans Builder avec lien visible uniquement dans le chat
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const WORKSPACE    = "/home/node/.openclaw/workspace";
const STATE_DIR    = path.join(WORKSPACE, "state");
const DRAFTS_FILE  = path.join(STATE_DIR, "drafts.json");
const COUNTER_FILE = path.join(STATE_DIR, "draft_counter.json");

const BUILDER_TOKEN = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
const BUILDER_CHAT  = process.env.BUILDER_TELEGRAM_CHAT_ID;

const DRAFT_TTL_MS = 24 * 60 * 60 * 1000; // 24h

// ============================================================
// SOURCE MAP
// ============================================================

const SOURCE_MAP = {
  "cointelegraph.com":   "CoinTelegraph",
  "coindesk.com":        "CoinDesk",
  "theblock.co":         "The Block",
  "decrypt.co":          "Decrypt",
  "bitcoinmagazine.com": "Bitcoin Magazine",
  "thedefiant.io":       "The Defiant",
  "cryptoast.fr":        "Cryptoast",
  "journalducoin.com":   "JournalDuCoin",
};

function getSourceName(url) {
  if (!url) return null;
  for (const [domain, name] of Object.entries(SOURCE_MAP)) {
    if (url.includes(domain)) return name;
  }
  return null;
}

// ============================================================
// STOCKAGE
// ============================================================

function loadDrafts() {
  try { return JSON.parse(fs.readFileSync(DRAFTS_FILE, "utf8")); }
  catch { return {}; }
}

function saveDrafts(drafts) {
  fs.mkdirSync(STATE_DIR, { recursive: true });
  fs.writeFileSync(DRAFTS_FILE, JSON.stringify(drafts, null, 2));
}

function getCounter() {
  try { return JSON.parse(fs.readFileSync(COUNTER_FILE, "utf8")).counter || 0; }
  catch { return 0; }
}

function incrementCounter() {
  const current = getCounter();
  const next = current >= 100 ? 1 : current + 1;
  fs.writeFileSync(COUNTER_FILE, JSON.stringify({ counter: next }));
  return next;
}

// ============================================================
// PURGE
// ============================================================

function purgeDrafts(drafts) {
  const now     = Date.now();
  const cleaned = {};
  for (const [id, draft] of Object.entries(drafts)) {
    if (now - draft.createdAt < DRAFT_TTL_MS) {
      cleaned[id] = draft;
    } else {
      console.log(`[drafts] Purgé ${id} (> 24h)`);
    }
  }
  return cleaned;
}

// ============================================================
// CRUD
// ============================================================

/**
 * Crée un nouveau draft.
 * - type "hourly" : injecte "- NomSource" dans le contenu, stocke articleUrl
 * - type "daily"  : contenu tel quel, pas de source
 */
function createDraft(content, type = "hourly", imageUrl = null, articleUrl = null) {
  const num    = incrementCounter();
  const id     = `#${num}`;
  const drafts = purgeDrafts(loadDrafts());

  let finalContent = content;

  if (type === "hourly") {
    // Extraire le lien 🗞 du contenu si articleUrl pas fourni
    const linkMatch = content.match(/🗞\s*(https?:\/\/\S+)/);
    const url = articleUrl || (linkMatch ? linkMatch[1] : null);

    // Nettoyer la ligne 🗞 du contenu
    finalContent = content.replace(/\n?🗞\s*https?:\/\/\S+/g, "").trimEnd();

    // Injecter - NomSource à la fin
    const sourceName = getSourceName(url);
    if (sourceName) finalContent += `\n\n- ${sourceName}`;

    // Stocker l'URL pour affichage dans Builder
    if (url && !articleUrl) articleUrl = url;
  }

  drafts[id] = {
    id,
    content: finalContent,
    imageUrl,
    articleUrl,
    type,
    createdAt: Date.now(),
  };

  saveDrafts(drafts);
  console.log(`[drafts] Créé ${id} (${type})`);
  return id;
}

function getDraft(id) {
  const drafts = loadDrafts();
  return drafts[id] || null;
}

function updateDraft(id, fields) {
  const drafts = loadDrafts();
  if (!drafts[id]) return false;
  drafts[id] = { ...drafts[id], ...fields };
  saveDrafts(drafts);
  return true;
}

function deleteDraft(id) {
  const drafts = loadDrafts();
  if (!drafts[id]) return false;
  delete drafts[id];
  saveDrafts(drafts);
  return true;
}

// ============================================================
// TELEGRAM — ENVOI DU DRAFT DANS BUILDER
// ============================================================

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

const CHANNEL_LABELS = {
  TWITTER_ONLY:     "Twitter uniquement",
  TWITTER_TELEGRAM: "Twitter + Telegram",
  TWITTER_SITE:     "Twitter + Site",
  ALL:              "Partout",
};

function makeButtons(id) {
  return {
    inline_keyboard: [
      [
        { text: "🐦 Twitter",          callback_data: `pub_tw_${id}` },
        { text: "🐦+📣 Twitter+TG",    callback_data: `pub_tg_${id}` },
      ],
      [
        { text: "🐦+🌐 Twitter+Site",  callback_data: `pub_site_${id}` },
        { text: "🌐+📣+🐦 Partout",    callback_data: `pub_all_${id}` },
      ],
      [
        { text: "✏️ Modifier",          callback_data: `modify_${id}` },
        { text: "🖼 Image",             callback_data: `modify_image_${id}` },
        { text: "❌",                   callback_data: `cancel_${id}` },
      ],
    ],
  };
}

/**
 * Envoie le draft dans le chat Builder.
 * Affiche : header + contenu + lien (lien visible ici uniquement, pas publié)
 */
async function sendDraft(id) {
  const draft = getDraft(id);
  if (!draft) { console.error(`[drafts] sendDraft: ${id} introuvable`); return; }

  const recoLine = draft.channel
    ? `📡 Recommandation : ${CHANNEL_LABELS[draft.channel] || draft.channel} — ${draft.channelReason || ""}\n\n`
    : "";
  const header  = `${recoLine}${id} | ✍️ <b>DRAFT — @CryptoRizon</b>`;
  const linkLine = draft.articleUrl ? `\n${draft.articleUrl}` : "";
  const buttons  = makeButtons(id);

  if (draft.imageUrl) {
    const preview = draft.content.length > 800
      ? draft.content.slice(0, 800).replace(/\n[^\n]*$/, "") + "..."
      : draft.content;
    await tgRequest("sendPhoto", {
      chat_id:      BUILDER_CHAT,
      photo:        draft.imageUrl,
      caption:      `${header}\n\n${preview}${linkLine}`,
      parse_mode:   "HTML",
      reply_markup: buttons,
    });
  } else {
    await tgRequest("sendMessage", {
      chat_id:      BUILDER_CHAT,
      text:         `${header}\n\n${draft.content}${linkLine}`,
      parse_mode:   "HTML",
      reply_markup: buttons,
    });
  }
}

// ============================================================
// EXPORTS
// ============================================================

module.exports = {
  SOURCE_MAP,
  CHANNEL_LABELS,
  getSourceName,
  createDraft,
  getDraft,
  updateDraft,
  deleteDraft,
  purgeDrafts,
  loadDrafts,
  saveDrafts,
  sendDraft,
  makeButtons,
  tgRequest,
};
