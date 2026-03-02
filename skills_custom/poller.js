/**
 * poller.js v2 - Workflow complet Publisher → Draft → Validation → Twitter
 *
 * Tout se passe dans la conv Publisher :
 * 1. Tu envoies tes numéros → Claude génère le thread
 * 2. Draft + boutons [✅ Publier] [✏️ Modifier] [❌ Annuler]
 * 3a. Publier → postTweet() sur @CryptoRizon (post unique Premium)
 * 3b. Modifier → tu expliques → nouveau draft + boutons
 * 3c. Annuler → fin
 */

const https  = require("https");
const fs     = require("fs");
const path   = require("path");

const { isSelectionMessage, getSelectedArticles, clearWaitingSelection } = require("./pending");
const { postTweet, postThread, uploadMedia, postTweetWithMedia } = require("./twitter");

const WORKSPACE   = "/home/node/.openclaw/workspace";
const OFFSET_FILE = path.join(WORKSPACE, "state", "poller_offset.json");
const DRAFT_FILE       = path.join(WORKSPACE, "state", "current_draft.json");
const DAILY_DRAFT_FILE = path.join(WORKSPACE, "state", "daily_draft.json");

const BUILDER_TOKEN = process.env.BUILDER_TELEGRAM_BOT_TOKEN;
const BUILDER_CHAT  = process.env.BUILDER_TELEGRAM_CHAT_ID;
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY;
const CHANNEL_ID    = process.env.CRYPTORIZON_CHANNEL_ID;

// ---------- État modification en cours ----------
let waitingModification = false;

// ---------- Telegram ----------
function tgRequest(token, method, body) {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify(body);
    const req = https.request({
      hostname: "api.telegram.org",
      path:     `/bot${token}/${method}`,
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
    req.on("error", reject);
    req.write(data);
    req.end();
  });
}

function sendMessage(text, replyMarkup = null) {
  const body = {
    chat_id:    BUILDER_CHAT,
    text,
    parse_mode: "HTML",
  };
  if (replyMarkup) body.reply_markup = replyMarkup;
  return tgRequest(BUILDER_TOKEN, "sendMessage", body);
}

function answerCallback(callbackQueryId, text) {
  return tgRequest(BUILDER_TOKEN, "answerCallbackQuery", {
    callback_query_id: callbackQueryId,
    text,
    show_alert: false,
  });
}

function getUpdates(offset) {
  return tgRequest(BUILDER_TOKEN, "getUpdates", {
    offset,
    timeout:         2,
    allowed_updates: ["message", "callback_query"],
  });
}

// ---------- Offset ----------
function getOffset() {
  try { return JSON.parse(fs.readFileSync(OFFSET_FILE, "utf8")).offset || 0; }
  catch { return 0; }
}
function saveOffset(offset) {
  fs.writeFileSync(OFFSET_FILE, JSON.stringify({ offset }));
}

// ---------- Draft persistance ----------
function saveDraft(content, imageUrl = null) {
  const draft = loadDraft();
  const existingImageUrl = imageUrl || (draft && draft.imageUrl) || null;
  const existingTweets = (draft && draft.tweets && draft.tweets.length > 1) ? draft.tweets : [content];
  fs.writeFileSync(DRAFT_FILE, JSON.stringify({ content, imageUrl: existingImageUrl, tweets: existingTweets, savedAt: new Date().toISOString() }));
}
function loadDraft() {
  try { return JSON.parse(fs.readFileSync(DRAFT_FILE, "utf8")); }
  catch { return null; }
}
function clearDraft() {
  try { if (fs.existsSync(DRAFT_FILE)) fs.unlinkSync(DRAFT_FILE); } catch {}
}
function saveDailyDraft(content, imageUrl = null) {
  fs.writeFileSync(DAILY_DRAFT_FILE, JSON.stringify({ content, imageUrl, tweets: [content], type: "daily", savedAt: new Date().toISOString() }));
}
function loadDailyDraft() {
  try { return JSON.parse(fs.readFileSync(DAILY_DRAFT_FILE, "utf8")); }
  catch { return null; }
}
function clearDailyDraft() {
  try { if (fs.existsSync(DAILY_DRAFT_FILE)) fs.unlinkSync(DAILY_DRAFT_FILE); } catch {}
}
function getActiveDraft() {
  const hourly = loadDraft();
  if (hourly) return { draft: hourly, type: "hourly" };
  const daily = loadDailyDraft();
  if (daily) return { draft: daily, type: "daily" };
  return { draft: null, type: null };
}

// ---------- Boutons validation ----------
const VALIDATION_BUTTONS = {
  inline_keyboard: [[
    { text: "✅ Publier",  callback_data: "publish" },
    { text: "✏️ Modifier texte", callback_data: "modify" },
    { text: "🖼 Modifier image", callback_data: "modify_image" },
    { text: "❌ Annuler",  callback_data: "cancel"  },
  ]],
};

// ---------- Claude Sonnet ----------
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

const HOURLY_SYSTEM = `Tu es le copywriter de CryptoRizon. Tu rédiges des posts Twitter crypto en français dans le style @Crypto__Goku. Phrases courtes, ton direct, une idée par ligne. Zéro hashtag. Zéro lien. Langue : français uniquement.`;
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

Exemple :
1/5\nParadigm lève 1,5 milliard de dollars. Le fonds s'ouvre à l'IA et la robotique. Selon le WSJ, c'est leur plus gros véhicule à ce jour.

RÈGLES :
- POST ENTIER = 2000 caractères MAXIMUM. Vise 1500.
- Chaque actus = 1 seul bloc de texte, sans retour à la ligne interne.
- On saute une ligne uniquement entre deux actus.
- 2-3 phrases max par actus. Un fait + une implication. Pas plus.
- Mentionne la source naturellement (ex : "Selon Bloomberg...").
- Extraire uniquement les faits. Jamais copier les formulations sources.
- Factuel. Zéro conseil financier. Zéro promesse de gain.
- Zéro CTA à la fin. On termine sur la dernière actus.
- Rien d'autre. Pas d'introduction. Pas de commentaire autour du post.
`;

async function generatePost(selected) {
  const articlesText = selected.map((a, i) =>
    `${i + 1}. ${a.title} (${a.source})`
  ).join("\n");

  const user = `Voici les ${selected.length} articles sélectionnés.\nRédige un thread Twitter percutant dans le style CryptoRizon.\n\n${articlesText}`;

  return callClaude(type === "daily" ? COPYWRITER_SYSTEM : HOURLY_SYSTEM, user);
}

async function modifyPost(currentThread, instructions, articleBody = null, type = "hourly") {
  const context = articleBody ? `\n\nArticle original :\n${articleBody}` : "";
  const user = `Voici le post actuel :\n\n${currentThread}${context}\n\nInstructions de Daniel :\n${instructions}\n\nRédige la version corrigée en gardant le même style CryptoRizon.`;
  return callClaude(type === "daily" ? COPYWRITER_SYSTEM : HOURLY_SYSTEM, user);
}

// ---------- Parse tweets ----------
function parseTweets(threadText) {
  // Supprimer la numérotation générée par Claude (ex: "1/8", "2/8")
  return threadText
    .split(/\n\s*\n/)
    .map(t => t.trim().replace(/^\d+\/\d+\s*/gm, "").trim())
    .filter(t => t.length > 0 && t.length <= 280);
}

async function sendDraft(content, imageUrl = null) {
  saveDraft(content, imageUrl);
  const draft = loadDraft();
  const img = imageUrl || (draft && draft.imageUrl) || null;
  const msg = `✍️ <b>DRAFT — @CryptoRizon</b>\n\n${content}`;
  if (img) {
    const t = content.length > 800 ? content.slice(0, 800).replace(/\n[^\n]*$/, "") : content;
    const caption = `✍️ <b>DRAFT — @CryptoRizon</b>\n\n${t}`;
    await tgRequest(BUILDER_TOKEN, "sendPhoto", { chat_id: BUILDER_CHAT, photo: img, caption, parse_mode: "HTML", reply_markup: VALIDATION_BUTTONS });
  } else {
    await sendMessage(msg, VALIDATION_BUTTONS);
  }
}

// ---------- Handlers ----------
async function handleSelection(text) {
  const result = getSelectedArticles(text);

  if (!result) {
    await sendMessage("⚠️ Aucune liste en attente. Lance d'abord le scraper.");
    return;
  }

  const { selected } = result;
  await sendMessage(`⏳ Génération du thread pour ${selected.length} articles...`);

  try {
    const thread = await generatePost(selected);
    clearWaitingSelection();
    saveDailyDraft(thread);
    const msg = `✍️ <b>DRAFT JOURNALIER — @CryptoRizon</b>\n\n${thread.slice(0, 800)}`;
    await sendMessage(msg, VALIDATION_BUTTONS);
    console.log(`[poller] Draft généré — ${selected.length} articles`);
  } catch (e) {
    console.error("[poller] Erreur génération:", e.message);
    await sendMessage(`❌ Erreur : ${e.message}`);
  }
}

async function publishToChannel(draft) {
  if (!CHANNEL_ID) { console.error("[canal] CRYPTORIZON_CHANNEL_ID manquant"); return; }
  try {
    // Extraire le nom de la source depuis tweet2 (ex: "🗞 https://cointelegraph.com/...")
    const tweet2 = (draft.tweets && draft.tweets[1]) || "";
    const url = tweet2.replace("🗞 ", "").trim();
    const sourceMap = {
      "cointelegraph.com":   "CoinTelegraph",
      "coindesk.com":        "CoinDesk",
      "bitcoinmagazine.com": "Bitcoin Magazine",
      "thedefiant.io":       "The Defiant",
      "cryptoast.fr":        "Cryptoast",
      "journalducoin.com":   "Journal du Coin",
    };
    let sourceName = "CryptoRizon";
    for (const [domain, name] of Object.entries(sourceMap)) {
      if (url.includes(domain)) { sourceName = name; break; }
    }
    const text = `${draft.content}\n\n- ${sourceName}`;
    if (draft.imageUrl) {
      const t = text.length > 1024 ? text.slice(0, 1020) + "..." : text;
      await tgRequest(BUILDER_TOKEN, "sendPhoto", {
        chat_id:    CHANNEL_ID,
        photo:      draft.imageUrl,
        caption:    t,
        parse_mode: "HTML",
      });
    } else {
      await tgRequest(BUILDER_TOKEN, "sendMessage", {
        chat_id:    CHANNEL_ID,
        text,
        parse_mode: "HTML",
      });
    }
    console.log(`[canal] ✅ Publié sur @CryptoRizon canal`);
  } catch (e) {
    console.error("[canal] Erreur:", e.message);
  }
}

async function handlePublish() {
  const { draft, type } = getActiveDraft();
  if (!draft) { await sendMessage("❌ Aucun draft en attente."); return; }
  await sendMessage("🚀 Publication en cours sur @CryptoRizon...");

  // Upload image si disponible
  let mediaId = null;
  if (draft.imageUrl) {
    try {
      const client = draft.imageUrl.startsWith("https") ? require("https") : require("http");
      const imageBuffer = await new Promise((resolve, reject) => {
        client.get(draft.imageUrl, { headers: { "User-Agent": "Mozilla/5.0" } }, (res) => {
          const chunks = [];
          res.on("data", c => chunks.push(c));
          res.on("end", () => resolve(Buffer.concat(chunks)));
        }).on("error", reject);
      });
      const ext = draft.imageUrl.split("?")[0].split(".").pop().toLowerCase();
      const mime = ext === "png" ? "image/png" : ext === "gif" ? "image/gif" : "image/jpeg";
      const uploaded = await uploadMedia(imageBuffer, mime);
      if (uploaded.success) { mediaId = uploaded.mediaId; console.log(`[poller] Image uploadée: ${mediaId}`); }
      else { console.error("[poller] Échec upload image:", JSON.stringify(uploaded.error)); }
    } catch (e) { console.error("[poller] Erreur image:", e.message); }
  }
  // Publication tweet unique avec image si dispo
  const result = mediaId
    ? await postTweetWithMedia(draft.content, mediaId)
    : await postTweet(draft.content);
  if (result.success) {
    await sendMessage(`✅ Publié !\n🔗 ${result.url}`);
    await publishToChannel(draft);
    type === "daily" ? clearDailyDraft() : clearDraft();
  } else {
    await sendMessage(`❌ Échec.\n${JSON.stringify(result.error)}`);
  }
}
async function handleModify() {
  waitingModification = true;
  await sendMessage("✏️ Dis-moi ce que tu veux modifier :");
}

async function handleModificationInstructions(instructions) {
  waitingModification = false;
  const { draft, type } = getActiveDraft();
  if (!draft) { await sendMessage("❌ Aucun draft en attente."); return; }
  await sendMessage("⏳ Modification en cours...");
  try {
    // Re-scraper l'article si l'URL est disponible
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
          .replace(/<nav[\s\S]*?<\/nav>/gi, "")
          .replace(/<header[\s\S]*?<\/header>/gi, "")
          .replace(/<footer[\s\S]*?<\/footer>/gi, "")
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ").trim().slice(0, 3000);
        console.log(`[poller] Article re-fetché: ${articleBody.length} chars`);
      } catch (e) { console.error("[poller] Impossible de re-fetcher l'article:", e.message); }
    }
    const newThread = await modifyPost(draft.content, instructions, articleBody, type);
    if (type === "daily") {
      saveDailyDraft(newThread);
      await sendMessage(`✍️ <b>DRAFT JOURNALIER — @CryptoRizon</b>\n\n${newThread.slice(0, 800)}`, VALIDATION_BUTTONS);
    } else {
      await sendDraft(newThread);
    }
    console.log("[poller] Thread modifié");
  } catch (e) {
    console.error("[poller] Erreur modification:", e.message);
    await sendMessage(`❌ Erreur : ${e.message}`);
  }
}

async function handleModifyImage() {
  const { draft, type } = getActiveDraft();
  if (!draft) { await sendMessage("❌ Aucun draft en attente."); return; }
  await sendMessage("⏳ Recherche d'une nouvelle image...");
  // Tentative 1 : 2ème image de l'article original
  try {
    const https = require("https");
    const http  = require("http");
    const tweet2 = draft.tweets ? draft.tweets[1] : "";
    const articleUrl = tweet2.replace("🗞 ", "").trim();
    const client = articleUrl.startsWith("https") ? https : http;
    const html = await new Promise((resolve, reject) => {
      client.get(articleUrl, { headers: { "User-Agent": "Mozilla/5.0" }, timeout: 8000 }, (res) => {
        let data = ""; res.on("data", c => data += c); res.on("end", () => resolve(data));
      }).on("error", reject);
    });
    // Cherche toutes les og:image ou <img src>
    const ogMatches = [...html.matchAll(/<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']+)["']/gi)];
    const imgMatches = [...html.matchAll(/<img[^>]*src=["']([^"']+\.(?:jpg|jpeg|png|webp)[^"']*)["']/gi)];
    const currentImg = draft.imageUrl || "";
    const allImages = [...ogMatches.map(m => m[1]), ...imgMatches.map(m => m[1])]
      .map(u => u.replace(/&amp;/g, "&"))
      .filter(u => u.startsWith("http") && u !== currentImg);
    if (allImages.length > 0) {
      const newImg = allImages[0];
      console.log(`[poller] Nouvelle image: ${newImg}`);
      await sendDraft(draft.content, newImg);
      return;
    }
  } catch (e) { console.error("[poller] Erreur fetch image:", e.message); }
  // Tentative 2 : demander upload manuel
  await sendMessage("⚠️ Aucune autre image trouvée automatiquement.\n\nEnvoie-moi une image directement ici et je l'utiliserai.");
}
async function handleCancel() {
  clearDraft(); clearDailyDraft();
  clearWaitingSelection();
  waitingModification = false;
  await sendMessage("❌ Draft annulé.");
}

// ---------- Boucle principale ----------
async function pollLoop() {
  console.log("[poller] v2 démarré — conv CryptoRizon Publisher");

  if (!BUILDER_TOKEN || !BUILDER_CHAT) {
    console.error("[poller] Variables BUILDER manquantes");
    process.exit(1);
  }

  let offset = getOffset();

  while (true) {
    try {
      const response = await getUpdates(offset);
      const updates  = response.result || [];

      for (const update of updates) {
        offset = update.update_id + 1;
        saveOffset(offset);

        // Boutons
        if (update.callback_query) {
          const cq     = update.callback_query;
          const chatId = String(cq.message?.chat?.id || "");
          if (chatId !== String(BUILDER_CHAT)) continue;

          await answerCallback(cq.id, "");

          if      (cq.data === "publish") await handlePublish();
          else if (cq.data === "modify")  await handleModify();
          else if (cq.data === "cancel")  await handleCancel();
          else if (cq.data === "modify_image") await handleModifyImage();
          continue;
        }

        // Messages
        const msg  = update.message;
        if (!msg) continue;

        const text = (msg.text || "").trim();
        const from = String(msg.chat?.id || "");
        if (from !== String(BUILDER_CHAT)) continue;

        console.log(`[poller] Message: "${text}"`);

        if (waitingModification) {
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
