/**
 * twitter.js - Skill de publication Twitter/X
 * Utilise OAuth 1.0 pour publier sur @CryptoRizon
 */

const crypto = require("crypto");
const https  = require("https");

const CREDENTIALS = {
  apiKey:             process.env.TWITTER_API_KEY,
  apiSecret:          process.env.TWITTER_API_SECRET,
  accessToken:        process.env.TWITTER_ACCESS_TOKEN,
  accessTokenSecret:  process.env.TWITTER_ACCESS_TOKEN_SECRET,
};

/**
 * Génère la signature OAuth 1.0
 */
function generateOAuthSignature(method, url, params, consumerSecret, tokenSecret) {
  const sortedParams = Object.keys(params)
    .sort()
    .map(k => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
    .join("&");

  const baseString = [
    method.toUpperCase(),
    encodeURIComponent(url),
    encodeURIComponent(sortedParams),
  ].join("&");

  const signingKey = `${encodeURIComponent(consumerSecret)}&${encodeURIComponent(tokenSecret)}`;

  return crypto
    .createHmac("sha1", signingKey)
    .update(baseString)
    .digest("base64");
}

/**
 * Génère le header Authorization OAuth 1.0
 */
function generateOAuthHeader(method, url, extraParams = {}) {
  const oauthParams = {
    oauth_consumer_key:     CREDENTIALS.apiKey,
    oauth_nonce:            crypto.randomBytes(16).toString("hex"),
    oauth_signature_method: "HMAC-SHA1",
    oauth_timestamp:        Math.floor(Date.now() / 1000).toString(),
    oauth_token:            CREDENTIALS.accessToken,
    oauth_version:          "1.0",
  };

  const allParams = { ...oauthParams, ...extraParams };

  oauthParams.oauth_signature = generateOAuthSignature(
    method,
    url,
    allParams,
    CREDENTIALS.apiSecret,
    CREDENTIALS.accessTokenSecret
  );

  const headerParts = Object.keys(oauthParams)
    .filter(k => k.startsWith("oauth_"))
    .map(k => `${encodeURIComponent(k)}="${encodeURIComponent(oauthParams[k])}"`)
    .join(", ");

  return `OAuth ${headerParts}`;
}

/**
 * Publie un tweet
 * @param {string} text - Contenu du tweet (max 280 chars)
 * @returns {object} - { success, tweetId, url, error }
 */
async function postTweet(text) {
  if (!text || text.length === 0) {
    return { success: false, error: "Tweet vide" };
  }
  if (text.length > 25000) {
    return { success: false, error: `Tweet trop long: ${text.length} chars (max 25000)` };
  }

  const url    = "https://api.twitter.com/2/tweets";
  const body   = JSON.stringify({ text });
  const auth   = generateOAuthHeader("POST", url);

  return new Promise((resolve) => {
    const req = https.request(url, {
      method:  "POST",
      headers: {
        "Authorization":  auth,
        "Content-Type":   "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", chunk => data += chunk);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode === 201 && parsed.data?.id) {
            const tweetId = parsed.data.id;
            resolve({
              success: true,
              tweetId,
              url: `https://twitter.com/CryptoRizon/status/${tweetId}`,
            });
          } else {
            resolve({ success: false, error: parsed, statusCode: res.statusCode });
          }
        } catch (e) {
          resolve({ success: false, error: e.message });
        }
      });
    });

    req.on("error", e => resolve({ success: false, error: e.message }));
    req.write(body);
    req.end();
  });
}

/**
 * Publie un thread (liste de tweets)
 * @param {string[]} tweets - Array de tweets dans l'ordre
 * @returns {object[]} - Résultats de chaque tweet
 */
async function postThread(tweets, mediaId = null) {
  if (!Array.isArray(tweets) || tweets.length === 0) {
    return [{ success: false, error: "Thread vide" }];
  }

  const results  = [];
  let replyToId  = null;

  for (let i = 0; i < tweets.length; i++) {
    const text = tweets[i];

    if (text.length > 25000) {
      results.push({ success: false, error: `Tweet ${i+1} trop long: ${text.length} chars` });
      break;
    }

    const url  = "https://api.twitter.com/2/tweets";
    const bodyObj = replyToId
      ? { text, reply: { in_reply_to_tweet_id: replyToId } }
      : (i === 0 && mediaId ? { text, media: { media_ids: [mediaId] } } : { text });
    const body = JSON.stringify(bodyObj);
    const auth = generateOAuthHeader("POST", url);

    const result = await new Promise((resolve) => {
      const req = https.request(url, {
        method: "POST",
        headers: {
          "Authorization":  auth,
          "Content-Type":   "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      }, (res) => {
        let data = "";
        res.on("data", chunk => data += chunk);
        res.on("end", () => {
          try {
            const parsed = JSON.parse(data);
            if (res.statusCode === 201 && parsed.data?.id) {
              resolve({
                success:  true,
                tweetId:  parsed.data.id,
                url:      `https://twitter.com/CryptoRizon/status/${parsed.data.id}`,
                position: i + 1,
              });
            } else {
              resolve({ success: false, error: parsed, position: i + 1 });
            }
          } catch (e) {
            resolve({ success: false, error: e.message, position: i + 1 });
          }
        });
      });

      req.on("error", e => resolve({ success: false, error: e.message, position: i + 1 }));
      req.write(body);
      req.end();
    });

    results.push(result);

    if (!result.success) {
      console.error(`[twitter] Échec tweet ${i+1}, arrêt du thread`);
      break;
    }

    replyToId = result.tweetId;

    // Délai entre tweets pour éviter le rate limit
    if (i < tweets.length - 1) {
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  logPublication(results);
  return results;
}

/**
 * Log les publications dans memory/
 */
function logPublication(results) {
  try {
    const fs   = require("fs");
    const path = require("path");
    const WORKSPACE = process.env.OPENCLAW_WORKSPACE_DIR || "/home/node/.openclaw/workspace";
    const today = new Date().toISOString().split("T")[0];
    const logPath = path.join(WORKSPACE, "agents/publisher/memory", `${today}.md`);

    const lines = results.map(r =>
      r.success
        ? `- ✅ Tweet ${r.position} publié : ${r.url}`
        : `- ❌ Tweet ${r.position} échoué : ${JSON.stringify(r.error)}`
    ).join("\n");

    const entry = `\n## ${new Date().toISOString()}\n${lines}\n`;
    fs.appendFileSync(logPath, entry);
  } catch {}
}

// Test rapide si lancé directement
if (require.main === module) {
  (async () => {
    console.log("=== TEST TWITTER ===");
    console.log("Credentials chargés :", {
      apiKey:      CREDENTIALS.apiKey ? "✅" : "❌",
      apiSecret:   CREDENTIALS.apiSecret ? "✅" : "❌",
      accessToken: CREDENTIALS.accessToken ? "✅" : "❌",
      accessSecret:CREDENTIALS.accessTokenSecret ? "✅" : "❌",
    });

    // Test sans publier — juste vérifier les credentials
    console.log("\n⚠️  Pour tester la publication réelle, décommente la ligne ci-dessous");
    // const result = await postTweet("🦞 Test OpenClaw — ignore ce tweet !");
    // console.log("Résultat :", result);
  })();
}


/**
 * Upload une image vers Twitter via API v1.1
 * @param {Buffer} imageBuffer - Buffer de l'image
 * @param {string} mimeType - ex: "image/jpeg"
 * @returns {object} - { success, mediaId, error }
 */
async function uploadMedia(imageBuffer, mimeType = "image/jpeg") {
  const base64 = imageBuffer.toString("base64");
  const url    = "https://upload.twitter.com/1.1/media/upload.json";
  const body   = `media_data=${encodeURIComponent(base64)}`;
  const auth   = generateOAuthHeader("POST", url, { media_data: base64 });

  return new Promise((resolve) => {
    const req = https.request(url, {
      method: "POST",
      headers: {
        "Authorization":  auth,
        "Content-Type":   "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          if (parsed.media_id_string) {
            console.log(`[twitter] Media uploadé: ${parsed.media_id_string}`);
            resolve({ success: true, mediaId: parsed.media_id_string });
          } else {
            resolve({ success: false, error: parsed });
          }
        } catch (e) { resolve({ success: false, error: e.message }); }
      });
    });
    req.on("error", e => resolve({ success: false, error: e.message }));
    req.write(body);
    req.end();
  });
}

/**
 * Publie un tweet avec image (v2 + mediaId uploadé via v1.1)
 * @param {string} text
 * @param {string} mediaId - ID retourné par uploadMedia()
 * @returns {object} - { success, tweetId, url, error }
 */
async function postTweetWithMedia(text, mediaId) {
  const url  = "https://api.twitter.com/2/tweets";
  const body = JSON.stringify({ text, media: { media_ids: [mediaId] } });
  const auth = generateOAuthHeader("POST", url);

  return new Promise((resolve) => {
    const req = https.request(url, {
      method: "POST",
      headers: {
        "Authorization":  auth,
        "Content-Type":   "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    }, (res) => {
      let data = "";
      res.on("data", c => data += c);
      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode === 201 && parsed.data?.id) {
            resolve({ success: true, tweetId: parsed.data.id, url: `https://twitter.com/CryptoRizon/status/${parsed.data.id}` });
          } else {
            resolve({ success: false, error: parsed, statusCode: res.statusCode });
          }
        } catch (e) { resolve({ success: false, error: e.message }); }
      });
    });
    req.on("error", e => resolve({ success: false, error: e.message }));
    req.write(body);
    req.end();
  });
}


module.exports = { postTweet, postThread, uploadMedia, postTweetWithMedia };
