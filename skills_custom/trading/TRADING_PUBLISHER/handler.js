/**
 * TRADING_PUBLISHER — Handler
 * Surveille les positions et events importants.
 * Envoie des messages Telegram formatés style CryptoRizon.
 * Phase 1 : Telegram uniquement.
 * Phase 2 : Twitter (à connecter quand le compte est créé).
 * Pas de LLM pour les messages simples. Haiku pour les messages riches.
 */

import fs   from "fs";
import path from "path";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";
const MAX_TOKENS    = 400;
const TIMEOUT_MS    = 15000;

// ─── Telegram ────────────────────────────────────────────────────────────

async function sendTelegram(token, chatId, text) {
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id:    chatId,
        text,
        parse_mode: "Markdown",
      }),
    });
    if (!res.ok) throw new Error(`Telegram HTTP ${res.status}`);
    return true;
  } catch (e) {
    console.error("[TRADING_PUBLISHER] Telegram error:", e.message);
    return false;
  }
}

// ─── Haiku pour messages riches ───────────────────────────────────────────

async function generateRichMessage(apiKey, type, data) {
  const prompts = {
    position_open: `Tu es TRADING_PUBLISHER pour CryptoRizon.
Style: David Ogilvy — première ligne qui arrête le scroll, faits concrets, pas de jargon, pas de FOMO.
Règles:
- Ligne 1: accroche factuelle et directe (ex: "Le marché a peur. Moi j'achète.")
- Ligne 2-3: les chiffres clés (entry, stop, cible, R/R)
- Ligne 4: pourquoi maintenant en 1 phrase (signal technique ou news)
- Max 200 caractères total
- Pas de hashtags. Max 2 émojis. Format Markdown Telegram (*gras*, _italique_).
- Toujours préciser que c'est du PAPER TRADING
Données: ${JSON.stringify(data)}`,

    position_close: `Tu es TRADING_PUBLISHER pour CryptoRizon.
Style: David Ogilvy — honnêteté totale, chiffres précis, leçon claire.
Règles:
- Si profit: ligne 1 = résultat net. Ligne 2 = pourquoi ça a marché. Pas d'arrogance.
- Si perte: ligne 1 = résultat net. Ligne 2 = ce que ça apprend. Pas d'excuse.
- Max 200 caractères. Max 2 émojis. Format Markdown Telegram.
- Toujours préciser PAPER TRADING et la durée de la position
Données: ${JSON.stringify(data)}`,

    daily_recap: `Tu es TRADING_PUBLISHER pour CryptoRizon.
Style: David Ogilvy — rapport de fin de journée, chiffres d'abord, opinion ensuite.
Structure obligatoire:
- Ligne 1: PnL du jour en $ et % (le fait brut)
- Ligne 2: win rate + nombre de trades
- Ligne 3: meilleur trade (symbol + PnL)
- Ligne 4: 1 leçon concrète tirée de la journée
- Ligne 5: état du système demain (régime de marché attendu)
- Max 350 caractères. Format Markdown. Ton: analytique, pas commercial.
Données: ${JSON.stringify(data)}`,
  };

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
        messages:   [{ role: "user", content: prompts[type] }],
      }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`API HTTP ${res.status}`);
    const data2 = await res.json();
    return data2.content?.[0]?.text?.trim() ?? null;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Messages formatés simples (fallback sans LLM) ───────────────────────

function formatPositionOpen(pos) {
  const emoji = pos.side === "BUY" ? "🟢" : "🔴";
  const dir   = pos.side === "BUY" ? "LONG" : "SHORT";
  return `${emoji} *[PAPER] ${dir} ${pos.symbol}*\n\n` +
    `💵 Entrée: \`${pos.entry_fill}\`\n` +
    `🛑 Stop: \`${pos.stop}\`\n` +
    `🎯 Cible: \`${pos.tp}\`\n` +
    `📊 R/R: ${pos.risk_reward}x | Risque: $${pos.risk_usd?.toFixed(2)}\n` +
    `🧠 Stratégie: _${pos.strategy}_\n` +
    `📰 Régime: ${pos.regime}`;
}

function formatPositionClose(pos) {
  const win   = pos.pnl_usd >= 0;
  const emoji = win ? "💰" : "💸";
  const pnlStr = `${pos.pnl_usd >= 0 ? "+" : ""}$${pos.pnl_usd?.toFixed(2)} (${pos.pnl_pct >= 0 ? "+" : ""}${pos.pnl_pct?.toFixed(2)}%)`;
  const reason = pos.exit_reason === "TAKE_PROFIT" ? "✅ Take Profit" : "❌ Stop Loss";
  const holdMin = Math.round((pos.hold_ms ?? 0) / 60000);
  return `${emoji} *[PAPER] CLÔTURE ${pos.symbol}*\n\n` +
    `${reason}\n` +
    `📈 PnL: *${pnlStr}*\n` +
    `⏱ Durée: ${holdMin} min\n` +
    `🔄 Entrée: ${pos.entry_fill} → Sortie: ${pos.exit_price}`;
}

function formatKillSwitch(ks) {
  return `🚨 *KILL SWITCH DÉCLENCHÉ*\n\n` +
    `Raison: _${ks.reason}_\n` +
    `Toutes les positions sont bloquées.\n` +
    `Action requise: vérifier le système et reset manuellement.`;
}

function formatDailyRecap(data) {
  const pnlEmoji = data.daily_pnl >= 0 ? "📈" : "📉";
  return `📊 *Recap Journalier — CryptoRizon Paper Trading*\n\n` +
    `${pnlEmoji} PnL: *${data.daily_pnl >= 0 ? "+" : ""}$${data.daily_pnl?.toFixed(2)}*\n` +
    `🔢 Trades: ${data.total_trades} (${data.wins}✅ ${data.losses}❌)\n` +
    `📉 Win rate: ${data.win_rate?.toFixed(0)}%\n` +
    `💼 Positions ouvertes: ${data.open_positions}`;
}

// ─── Handler ──────────────────────────────────────────────────────────────

export async function handler(ctx) {
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;
  const apiKey = process.env.ANTHROPIC_API_KEY;

  if (!token || !chatId) {
    ctx.log("❌ TRADER_TELEGRAM_BOT_TOKEN ou TRADER_TELEGRAM_CHAT_ID manquant");
    return;
  }

  const execDir   = path.join(ctx.stateDir, "exec");
  const sentFile  = path.join(execDir, "publisher_sent.json");
  const pnlFile   = path.join(execDir, "daily_pnl.json");
  const posFile   = path.join(execDir, "positions.json");

  let sent = {};
  try { sent = JSON.parse(fs.readFileSync(sentFile, "utf-8")); } catch {}

  let published = 0;

  // ── 1. Nouvelles positions ouvertes ──────────────────────────────────
  const positions = (() => {
    try { return JSON.parse(fs.readFileSync(posFile, "utf-8")); } catch { return []; }
  })();

  for (const pos of positions) {
    if (pos.status !== "open") continue;
    const sentKey = `open_${pos.id}`;
    if (sent[sentKey]) continue;

    let msg;
    if (apiKey) {
      msg = await generateRichMessage(apiKey, "position_open", {
        symbol:     pos.symbol,
        side:       pos.side,
        entry:      pos.entry_fill,
        stop:       pos.stop,
        tp:         pos.tp,
        risk_reward: pos.risk_reward,
        risk_usd:   pos.risk_usd,
        strategy:   pos.strategy,
        regime:     pos.regime,
      });
    }
    if (!msg) msg = formatPositionOpen(pos);

    await sendTelegram(token, chatId, msg);
    sent[sentKey] = Date.now();
    published++;
    ctx.log(`📤 Position ouverte publiée: ${pos.symbol} ${pos.side}`);
  }

  // ── 2. Positions fermées (depuis le ledger) ───────────────────────────
  const cursor = ctx.state.cursors?.ledger ?? 0;
  const { events: ledger, nextCursor } =
    ctx.bus.readSince("trading.exec.trade.ledger", cursor, 20);

  for (const event of ledger) {
    const pos     = event.payload;
    const sentKey = `close_${pos.id ?? event.event_id}`;
    if (sent[sentKey]) continue;

    let msg;
    if (apiKey) {
      msg = await generateRichMessage(apiKey, "position_close", {
        symbol:      pos.symbol,
        side:        pos.side,
        pnl_usd:     pos.pnl_usd,
        pnl_pct:     pos.pnl_pct,
        exit_reason: pos.exit_reason,
        hold_ms:     pos.hold_ms,
        entry:       pos.entry_fill,
        exit:        pos.exit_price,
        strategy:    pos.strategy,
      });
    }
    if (!msg) msg = formatPositionClose(pos);

    await sendTelegram(token, chatId, msg);
    sent[sentKey] = Date.now();
    published++;
    ctx.log(`📤 Clôture publiée: ${pos.symbol} PnL=$${pos.pnl_usd}`);
  }

  ctx.state.cursors = { ...ctx.state.cursors, ledger: nextCursor };

  // ── 3. Kill switch ────────────────────────────────────────────────────
  const ksFile = path.join(ctx.stateDir, "exec", "killswitch.json");
  try {
    const ks = JSON.parse(fs.readFileSync(ksFile, "utf-8"));
    if (ks.state === "TRIPPED" && !sent[`ks_${ks.tripped_at}`]) {
      const msg = formatKillSwitch(ks);
      await sendTelegram(token, chatId, msg);
      sent[`ks_${ks.tripped_at}`] = Date.now();
      published++;
      ctx.log("🚨 Kill switch notifié");
    }
  } catch {}

  // ── 4. Recap journalier (une fois par jour à partir de 20h) ──────────
  const hour    = new Date().getUTCHours();
  const today   = new Date().toISOString().slice(0, 10);
  const recapKey = `recap_${today}`;

  if (hour >= 19 && !sent[recapKey]) {
    const dailyPnl = (() => {
      try { return JSON.parse(fs.readFileSync(pnlFile, "utf-8")); } catch { return {}; }
    })();

    const { events: allTrades } = ctx.bus.readSince("trading.exec.trade.ledger", 0, 1000);
    const todayTrades = allTrades.filter(e => {
      const d = new Date(e.payload?.closed_at ?? 0).toISOString().slice(0, 10);
      return d === today;
    });

    const wins   = todayTrades.filter(e => e.payload.pnl_usd >= 0).length;
    const losses = todayTrades.filter(e => e.payload.pnl_usd < 0).length;
    const total  = todayTrades.length;

    const recapData = {
      daily_pnl:      dailyPnl[today] ?? 0,
      total_trades:   total,
      wins,
      losses,
      win_rate:       total > 0 ? (wins / total * 100) : 0,
      open_positions: positions.filter(p => p.status === "open").length,
    };

    let msg;
    if (apiKey && total > 0) {
      msg = await generateRichMessage(apiKey, "daily_recap", recapData);
    }
    if (!msg) msg = formatDailyRecap(recapData);

    await sendTelegram(token, chatId, msg);
    sent[recapKey] = Date.now();
    published++;
    ctx.log("📊 Recap journalier envoyé");
  }

  // Sauvegarde
  fs.mkdirSync(execDir, { recursive: true });
  fs.writeFileSync(sentFile, JSON.stringify(sent, null, 2));

  ctx.log(`✅ ${published} messages publiés`);
}
