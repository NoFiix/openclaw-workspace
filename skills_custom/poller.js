/**
 * poller.js v3 - Workflow Publisher → Draft → Validation → Twitter
 */

const https = require("https");
const fs    = require("fs");
const path  = require("path");

const { isSelectionMessage, getSelectedArticles, clearWaitingSelection } = require("./pending");
const { postTweet, uploadMedia, postTweetWithMedia }                     = require("./twitter");
const { createDraft, getDraft, updateDraft, deleteDraft, sendDraft, tgRequest, loadDrafts } = require("./drafts");

const WORKSPACE   = "/home/node/.openclaw/workspace";
const STATE_DIR   = path.join(WORKSPACE, "state");
const OFFSET_FILE = path.join(STATE_DIR, "poller_offset.json");

const BUILDER_TOKEN = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
const BUILDER_CHAT  = process.env.BUILDER_TELEGRAM_CHAT_ID;
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const CHANNEL_ID    = process.env.CRYPTORIZON_CHANNEL_ID;

// waitingModification = null | "#3"
let waitingModification = null;

// ── HISTORIQUE PUBLICATIONS (dashboard) ──────────────────────────────────────

const HISTORY_FILE = path.join(STATE_DIR, "content_publish_history.json");

const SOURCE_MAP = {
  "cointelegraph.com": "CoinTelegraph",
  "coindesk.com":      "CoinDesk",
  "decrypt.co":        "Decrypt",
  "theblock.co":       "The Block",
  "blockworks.co":     "Blockworks",
  "cryptoslate.com":   "CryptoSlate",
  "journalducoin.com": "JournalDuCoin",
};

function extractSource(url) {
  if (!url) return null;
  try {
    const domain = new URL(url).hostname.replace(/^www\./, "");
    return SOURCE_MAP[domain] || domain;
  } catch { return null; }
}

function appendHistory(entry) {
  let data;
  try { data = JSON.parse(fs.readFileSync(HISTORY_FILE, "utf8")); }
  catch { data = { entries: [] }; }
  data.entries.unshift(entry);
  const cutoff = Date.now() - 30 * 24 * 3600 * 1000;
  data.entries = data.entries.filter(e => e.ts > cutoff).slice(0, 200);
  data.last_updated = Date.now();
  try { fs.writeFileSync(HISTORY_FILE, JSON.stringify(data)); } catch {}
}

// ============================================================
// TELEGRAM
// ============================================================

function sendMessage(text, replyMarkup = null) {
  const body = { chat_id: BUILDER_CHAT, text, parse_mode: "HTML" };
  if (replyMarkup) body.reply_markup = replyMarkup;
  return tgRequest("sendMessage", body);
}

function answerCallback(callbackQueryId) {
  return tgRequest("answerCallbackQuery", { callback_query_id: callbackQueryId, show_alert: false });
}

function getUpdates(offset) {
  return tgRequest("getUpdates", { offset, timeout: 2, allowed_updates: ["message", "callback_query"] });
}

// ============================================================
// OFFSET
// ============================================================

function getOffset() {
  try { return JSON.parse(fs.readFileSync(OFFSET_FILE, "utf8")).offset || 0; }
  catch { return 0; }
}
function saveOffset(offset) {
  fs.writeFileSync(OFFSET_FILE, JSON.stringify({ offset }));
}

// ============================================================
// CLAUDE
// ============================================================

async function callClaude(system, user) {
  const body = JSON.stringify({
    model:      "claude-sonnet-4-6",
    max_tokens: 1500,
    system,
    messages:   [{ role: "user", content: user }],
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
        try { resolve(JSON.parse(raw).content?.[0]?.text?.trim() || ""); }
        catch { reject(new Error("Erreur parsing Claude")); }
      });
    });
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

const HOURLY_SYSTEM = `Tu es le copywriter de CryptoRizon. Tu rédiges des posts Twitter crypto en français dans le style @Crypto__Goku. Phrases courtes, ton direct, une idée par ligne. Zéro hashtag. Zéro lien. NE PAS mettre la source. Langue : français uniquement. 500 caractères MAX.`;

const COPYWRITER_SYSTEM = `Tu es le copywriter de CryptoRizon. Tu rédiges des threads Twitter crypto en français.

STYLE — David Ogilvy, Gary Halbert, Stan Leloup, Antoine BM :
- Phrases ultra-courtes. Une idée par ligne. Jamais deux.
- Rythme rapide. Tension. Le lecteur ne peut pas s'arrêter.
- Ton direct, proche, légèrement familier mais crédible.
- Jamais de remplissage. Chaque mot compte.
- Langue : français uniquement.
- Maximum 1 emoji par tweet, jamais en début de phrase.
- Zéro hashtag. Zéro lien dans les tweets.

STRUCTURE :
Ligne 1-2 = INTRO FIXE (copie exactement, remplace uniquement [X] par le nombre d'actus retenues) :
🗞️ Le briefing Web3 du jour :
Les [X] actus majeures des dernières 24h

Ensuite = maximum 5 actus. Si tu reçois plus de 5 articles, choisis les plus pertinents pour les lecteurs crypto. Si tu en reçois moins de 5, garde-les tous.
Format de chaque actus :
[numéro]/[total] [contenu en un seul bloc continu, sans saut de ligne interne]

RÈGLES :
- POST ENTIER = 2000 caractères MAXIMUM. Vise 1500.
- Chaque actus = 1 seul bloc de texte, sans retour à la ligne interne.
- On saute une ligne uniquement entre deux actus.
- 2-3 phrases max par actus. Un fait + une implication. Pas plus.
- Mentionne la source naturellement (ex : "Selon Bloomberg...").
- Factuel. Zéro conseil financier. Zéro promesse de gain.
- Zéro CTA à la fin. On termine sur la dernière actus.
- Rien d'autre. Pas d'introduction. Pas de commentaire autour du post.
`;

async function generatePost(selected) {
  const articlesText = selected.map((a, i) => `${i + 1}. ${a.title} (${a.source})`).join("\n");
  const user = `Voici les ${selected.length} articles sélectionnés.\nRédige un post Twitter dans le style CryptoRizon.\n\n${articlesText}`;
  return callClaude(COPYWRITER_SYSTEM, user);
}

async function modifyPost(currentContent, instructions, articleBody = null, type = "daily") {
  const context = articleBody ? `\n\nArticle original :\n${articleBody}` : "";
  const user = `Voici le post actuel :\n\n${currentContent}${context}\n\nInstructions de Daniel :\n${instructions}\n\nRédige la version corrigée en gardant le même style CryptoRizon.`;
  return callClaude(type === "hourly" ? HOURLY_SYSTEM : COPYWRITER_SYSTEM, user);
}

// ============================================================
// RÉSOLUTION IMAGE (file_id Telegram ou URL http)
// ============================================================

async function resolveImageBuffer(imageUrl) {
  if (!imageUrl.startsWith("http")) {
    const res = await tgRequest("getFile", { file_id: imageUrl });
    const filePath = res.result?.file_path;
    if (!filePath) throw new Error("getFile échoué");
    imageUrl = `https://api.telegram.org/file/bot${BUILDER_TOKEN}/${filePath}`;
  }
  const client = imageUrl.startsWith("https") ? require("https") : require("http");
  return new Promise((resolve, reject) => {
    client.get(imageUrl, { headers: { "User-Agent": "Mozilla/5.0" } }, (res) => {
      const chunks = [];
      res.on("data", c => chunks.push(c));
      res.on("end", () => resolve(Buffer.concat(chunks)));
    }).on("error", reject);
  });
}

// ============================================================
// HANDLERS
// ============================================================

async function handleSelection(text) {
  const result = getSelectedArticles(text);
  if (!result) {
    await sendMessage("⚠️ Aucune liste en attente. Lance d'abord le scraper.");
    return;
  }

  const { selected } = result;
  await sendMessage(`⏳ Génération du draft pour ${selected.length} articles...`);

  try {
    const content = await generatePost(selected);
    clearWaitingSelection();
    const id = createDraft(content, "daily");
    await sendDraft(id);
    console.log(`[poller] Draft ${id} généré — ${selected.length} articles`);
  } catch (e) {
    console.error("[poller] Erreur génération:", e.message);
    await sendMessage(`❌ Erreur : ${e.message}`);
  }
}

async function handlePublish(id) {
  const draft = getDraft(id);
  if (!draft) { await sendMessage(`❌ Draft ${id} introuvable ou expiré.`); return; }

  await sendMessage(`${id} | 🚀 Publication en cours sur @CryptoRizon...`);

  let mediaId = null;
  if (draft.imageUrl) {
    try {
      const imageBuffer = await resolveImageBuffer(draft.imageUrl);
      const ext  = draft.imageUrl.startsWith("http")
        ? draft.imageUrl.split("?")[0].split(".").pop().toLowerCase()
        : "jpeg";
      const mime = ext === "png" ? "image/png" : ext === "gif" ? "image/gif" : "image/jpeg";
      const uploaded = await uploadMedia(imageBuffer, mime);
      if (uploaded.success) { mediaId = uploaded.mediaId; }
      else { console.error("[poller] Échec upload image:", JSON.stringify(uploaded.error)); }
    } catch (e) { console.error("[poller] Erreur image:", e.message); }
  }

  const result = mediaId
    ? await postTweetWithMedia(draft.content, mediaId)
    : await postTweet(draft.content);

  if (result.success) {
    await publishToChannel(draft);
    deleteDraft(id);
    appendHistory({
      ts:        Date.now(),
      draft_id:  id,
      action:    "published",
      preview:   draft.content.slice(0, 100),
      source:    extractSource(draft.articleUrl),
      tweet_url: result.url || null,
      type:      draft.type || "hourly",
    });
    await sendMessage(`✅ ${id} publié !\n🔗 ${result.url}`);
  } else {
    await sendMessage(`❌ ${id} — Échec.\n${JSON.stringify(result.error)}`);
  }
}

async function handleModify(id) {
  const draft = getDraft(id);
  if (!draft) { await sendMessage(`❌ Draft ${id} introuvable ou expiré.`); return; }
  waitingModification = id;
  await sendMessage(`${id} | ✏️ Dis-moi ce que tu veux modifier :`);
}

async function handleModificationInstructions(instructions) {
  const id = waitingModification;
  waitingModification = null;

  const draft = getDraft(id);
  if (!draft) { await sendMessage(`❌ Draft ${id} introuvable ou expiré.`); return; }

  await sendMessage(`⏳ Modification de ${id} en cours...`);

  try {
    let articleBody = null;
    if (draft.articleUrl) {
      try {
        const client = draft.articleUrl.startsWith("https") ? require("https") : require("http");
        const html = await new Promise((resolve, reject) => {
          client.get(draft.articleUrl, { headers: { "User-Agent": "Mozilla/5.0" }, timeout: 8000 }, (res) => {
            let data = ""; res.on("data", c => data += c); res.on("end", () => resolve(data));
          }).on("error", reject);
        });
        articleBody = html
          .replace(/<script[\s\S]*?<\/script>/gi, "")
          .replace(/<style[\s\S]*?<\/style>/gi, "")
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ").trim().slice(0, 3000);
      } catch (e) { console.error("[poller] Impossible de re-fetcher:", e.message); }
    }

    const newContent = await modifyPost(draft.content, instructions, articleBody, draft.type);
    updateDraft(id, { content: newContent });
    await sendDraft(id);
    console.log(`[poller] Draft ${id} modifié`);
  } catch (e) {
    console.error("[poller] Erreur modification:", e.message);
    await sendMessage(`❌ Erreur : ${e.message}`);
  }
}

async function handleModifyImage(id) {
  const draft = getDraft(id);
  if (!draft) { await sendMessage(`❌ Draft ${id} introuvable ou expiré.`); return; }

  await sendMessage(`⏳ Recherche d'une nouvelle image pour ${id}...`);

  try {
    const articleUrl = draft.articleUrl || "";
    if (!articleUrl) throw new Error("Pas d'URL article");

    const client = articleUrl.startsWith("https") ? require("https") : require("http");
    const html = await new Promise((resolve, reject) => {
      client.get(articleUrl, { headers: { "User-Agent": "Mozilla/5.0" }, timeout: 8000 }, (res) => {
        let data = ""; res.on("data", c => data += c); res.on("end", () => resolve(data));
      }).on("error", reject);
    });

    const ogMatches  = [...html.matchAll(/<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']+)["']/gi)];
    const imgMatches = [...html.matchAll(/<img[^>]*src=["']([^"']+\.(?:jpg|jpeg|png|webp)[^"']*)["']/gi)];
    const currentImg = draft.imageUrl || "";
    const allImages  = [...ogMatches.map(m => m[1]), ...imgMatches.map(m => m[1])]
      .map(u => u.replace(/&amp;/g, "&"))
      .filter(u => u.startsWith("http") && u !== currentImg);

    if (allImages.length > 0) {
      updateDraft(id, { imageUrl: allImages[0] });
      await sendDraft(id);
      return;
    }
  } catch (e) { console.error("[poller] Erreur fetch image:", e.message); }

  await sendMessage(`⚠️ ${id} — Aucune autre image trouvée.\n\nEnvoie-moi une image directement ici.`);
}

async function handleCancel(id) {
  const existed = deleteDraft(id);
  if (waitingModification === id) waitingModification = null;
  if (existed) appendHistory({
    ts:        Date.now(),
    draft_id:  id,
    action:    "cancelled",
    preview:   existed.content?.slice(0, 100),
    source:    extractSource(existed.articleUrl),
    tweet_url: null,
    type:      existed.type || "hourly",
  });
  await sendMessage(existed ? `${id} | ❌ Draft annulé.` : `❌ Draft ${id} introuvable ou déjà supprimé.`);
}

// ============================================================
// PUBLICATION CANAL
// ============================================================

async function publishToChannel(draft) {
  if (!CHANNEL_ID) { console.error("[canal] CRYPTORIZON_CHANNEL_ID manquant"); return; }
  try {
    const text = draft.content;
    if (draft.imageUrl) {
      const t = text.length > 1024 ? text.slice(0, 1020) + "..." : text;
      await tgRequest("sendPhoto", { chat_id: CHANNEL_ID, photo: draft.imageUrl, caption: t, parse_mode: "HTML" });
    } else {
      await tgRequest("sendMessage", { chat_id: CHANNEL_ID, text, parse_mode: "HTML" });
    }
    console.log(`[canal] ✅ Publié sur le canal @CryptoRizon`);
  } catch (e) { console.error("[canal] Erreur:", e.message); }
}

// ============================================================
// PARSING CALLBACK
// ============================================================

function parseCallback(data) {
  const match = data.match(/^(publish|modify|modify_image|cancel)_(#\d+)$/);
  if (!match) return null;
  return { action: match[1], id: match[2] };
}

// ============================================================
// BOUCLE PRINCIPALE
// ============================================================

async function pollLoop() {
  console.log("[poller] v3 démarré — système multi-drafts IDs #1→#100");

  if (!BUILDER_TOKEN || !BUILDER_CHAT) {
    console.error("[poller] Variables BUILDER manquantes");
    process.exit(1);
  }

  try { fs.mkdirSync(STATE_DIR, { recursive: true }); } catch {}

  let offset = getOffset();

  while (true) {
    try {
      const response = await getUpdates(offset);
      const updates  = response.result || [];

      for (const update of updates) {
        offset = update.update_id + 1;
        saveOffset(offset);

        if (update.callback_query) {
          const cq     = update.callback_query;
          const chatId = String(cq.message?.chat?.id || "");
          if (chatId !== String(BUILDER_CHAT)) continue;

          await answerCallback(cq.id);

          const parsed = parseCallback(cq.data);
          if (!parsed) { console.warn(`[poller] Callback inconnu: ${cq.data}`); continue; }

          const { action, id } = parsed;
          if      (action === "publish")      await handlePublish(id);
          else if (action === "modify")       await handleModify(id);
          else if (action === "modify_image") await handleModifyImage(id);
          else if (action === "cancel")       await handleCancel(id);
          continue;
        }

        const msg = update.message;
        if (!msg) continue;
        const text = (msg.text || "").trim();
        const from = String(msg.chat?.id || "");
        if (from !== String(BUILDER_CHAT)) continue;

        console.log(`[poller] Message: "${text}"`);

        if (msg.photo) {
          const photoId = msg.photo[msg.photo.length - 1].file_id;
          const ids = Object.keys(loadDrafts());
          if (ids.length === 0) {
            await sendMessage("❌ Aucun draft en attente.");
          } else {
            const id = ids[ids.length - 1];
            updateDraft(id, { imageUrl: photoId });
            await sendDraft(id);
          }
        } else if (waitingModification) {
          await handleModificationInstructions(text);
        } else if (isSelectionMessage(text)) {
          await handleSelection(text);
        }
      }

    } catch (e) {
      console.error("[poller] Erreur:", e.message);
    }

    await new Promise(r => setTimeout(r, 2000));
  }
}

pollLoop();
