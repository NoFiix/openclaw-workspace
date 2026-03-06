/**
 * TRADING_PUBLISHER v3 — Handler
 * Formats inspirés du "CryptoRizon AI Trading Desk"
 * Templates fixes + Haiku uniquement pour la ligne Setup (économie tokens)
 * Types : position_open, position_close, daily_recap, weekly_recap, viral, educational
 */

import fs   from "fs";
import path from "path";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-haiku-4-5-20251001";
const TIMEOUT_MS    = 15000;

// ─── Telegram ────────────────────────────────────────────────────────────

async function sendTelegram(token, chatId, text) {
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
    if (!res.ok) throw new Error(`Telegram HTTP ${res.status}`);
    return true;
  } catch (e) {
    console.error("[TRADING_PUBLISHER] Telegram error:", e.message);
    return false;
  }
}

// ─── Haiku — ligne Setup uniquement (max 2 phrases, ~30 tokens) ──────────

async function generateSetup(apiKey, type, data) {
  const prompts = {
    open: `Explique en 1-2 phrases courtes et directes pourquoi ce trade a été ouvert.
Style: technique, factuel. Pas de majuscules inutiles. Pas d'émojis.
Données: stratégie=${data.strategy} régime=${data.regime} side=${data.side} symbol=${data.symbol}
Exemple: "Support testé → rebond technique attendu." ou "Rejet sur résistance + perte de momentum."`,

    win: `Explique en 1 phrase courte pourquoi ce trade a gagné.
Style: factuel, confiant. Pas d'arrogance.
Données: stratégie=${data.strategy} pnl=${data.pnl_pct}% durée=${Math.round((data.hold_ms??0)/60000)}min
Exemple: "Mean Reversion sur support clé. Discipline respectée → TP touché."`,

    loss: `Explique en 2 phrases courtes pourquoi ce trade a perdu. Tire une leçon concrète.
Style: honnête, pédagogique. Pas d'excuse.
Données: stratégie=${data.strategy} durée=${Math.round((data.hold_ms??0)/60000)}min exit_reason=${data.exit_reason}
Exemple: "Momentum vendeur invalidé. Entrée trop précoce sur retournement haussier."`,

    educational: `Explique en 3-4 lignes courtes le principe de la stratégie ${data.strategy} en trading crypto.
Format:
Principe : [1 phrase]
Les agents détectent :
• [signal 1]
• [signal 2]
• [signal 3]
Résultat : [1 phrase conclusion]`,
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
        max_tokens: 180,
        messages:   [{ role: "user", content: prompts[type] }],
      }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`API HTTP ${res.status}`);
    const d = await res.json();
    return d.content?.[0]?.text?.trim() ?? null;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Formatage prix ───────────────────────────────────────────────────────

function fmtPrice(p) {
  if (!p) return "—";
  return parseFloat(p).toLocaleString("fr-FR", { maximumFractionDigits: 4 });
}

function fmtConf(c) {
  return Math.round((c ?? 0) * 100);
}

function fmtDuration(ms) {
  if (!ms) return "—";
  const min = Math.round(ms / 60000);
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h}h${m}min` : `${h}h`;
}

// ─── Templates ───────────────────────────────────────────────────────────

function tplPositionOpen(pos, tradeNum, setup) {
  const dir   = pos.side === "BUY" ? "🚀 LONG" : "🔻 SHORT";
  const pair  = pos.symbol.replace("USDT", "/USDT");
  const conf  = fmtConf(pos.confidence ?? 0);
  const rr    = pos.risk_reward ?? 2;

  return (
`${dir} OUVERT — ${pair}
#${tradeNum} • Confidence ${conf}/100

📥 Entry      \`$${fmtPrice(pos.entry_fill)}\`
🛑 Stop       \`$${fmtPrice(pos.stop)}\`
🎯 TakeProfit \`$${fmtPrice(pos.tp)}\`

⚖️ Risk/Reward : 1:${rr}
💰 Risk : $${pos.risk_usd?.toFixed(0) ?? 100}

🧠 Setup
${setup ?? "Signal technique détecté."}

⚠️ PAPER TRADING`
  );
}

function tplPositionCloseWin(pos, tradeNum, setup) {
  const pair = pos.symbol.replace("USDT", "/USDT");
  const dir  = pos.side === "BUY" ? "LONG" : "SHORT";
  const conf = fmtConf(pos.confidence ?? 0);

  return (
`✅ TRADE GAGNANT — ${pair} (${dir})
#${tradeNum} • Confidence ${conf}/100

💰 +${pos.pnl_usd?.toFixed(0)}$ (+${pos.pnl_pct?.toFixed(2)}%)

📥 Entry : \`$${fmtPrice(pos.entry_fill)}\`
📤 Exit  : \`$${fmtPrice(pos.exit_price)}\`

⏱ Durée : ${fmtDuration(pos.hold_ms)}

🧠 Setup
${setup ?? "Discipline respectée → TP touché."}

⚠️ PAPER TRADING`
  );
}

function tplPositionCloseLoss(pos, tradeNum, setup) {
  const pair = pos.symbol.replace("USDT", "/USDT");
  const dir  = pos.side === "BUY" ? "LONG" : "SHORT";
  const conf = fmtConf(pos.confidence ?? 0);

  return (
`❌ TRADE PERDANT — ${pair} (${dir})
#${tradeNum} • Confidence ${conf}/100

📉 ${pos.pnl_usd?.toFixed(0)}$ (${pos.pnl_pct?.toFixed(2)}%)

📥 Entry : \`$${fmtPrice(pos.entry_fill)}\`
🛑 Stop  : \`$${fmtPrice(pos.exit_price)}\`

⏱ Durée : ${fmtDuration(pos.hold_ms)}

🧠 Analyse
${setup ?? "Signal invalidé. Stop respecté."}

⚠️ PAPER TRADING`
  );
}

function tplDailyRecap(data) {
  const pnlSign  = data.daily_pnl >= 0 ? "+" : "";
  const roiSign  = data.roi_pct >= 0 ? "+" : "";
  const best     = data.best_trade;
  const worst    = data.worst_trade;

  return (
`📊 BILAN JOURNALIER

Trades : ${data.total_trades}
✅ Gagnants : ${data.wins}
❌ Perdants : ${data.losses}

📈 ROI jour : ${roiSign}${data.roi_pct?.toFixed(2)}%
💰 PnL jour : ${pnlSign}$${data.daily_pnl?.toFixed(0)}

${best ? `Meilleur trade\n${best.symbol.replace("USDT","")} +${best.pnl_pct?.toFixed(2)}%` : ""}
${worst ? `\nPire trade\n${worst.symbol.replace("USDT","")} ${worst.pnl_pct?.toFixed(2)}%` : ""}

📉 Winrate : ${data.win_rate?.toFixed(0)}%
📊 Profit Factor : ${data.profit_factor?.toFixed(2) ?? "—"}

⚠️ PAPER TRADING`
  );
}

function tplWeeklyRecap(data) {
  const pnlSign = data.daily_pnl >= 0 ? "+" : "";
  const roiSign = data.roi_pct >= 0 ? "+" : "";
  const best    = data.best_trade;
  const worst   = data.worst_trade;

  return (
`📊 BILAN SEMAINE

Trades : ${data.total_trades}
✅ Gagnants : ${data.wins}
❌ Perdants : ${data.losses}

📈 ROI semaine : ${roiSign}${data.roi_pct?.toFixed(2)}%
💰 PnL semaine : ${pnlSign}$${data.daily_pnl?.toFixed(0)}

${best  ? `Meilleur trade\n${best.symbol.replace("USDT","")} +${best.pnl_pct?.toFixed(2)}%` : ""}
${worst ? `\nPire trade\n${worst.symbol.replace("USDT","")} ${worst.pnl_pct?.toFixed(2)}%` : ""}

📉 Winrate : ${data.win_rate?.toFixed(0)}%
📊 Profit Factor : ${data.profit_factor?.toFixed(2) ?? "—"}

⚠️ PAPER TRADING`
  );
}

function tplViral(tradeCount) {
  return (
`🤖 Ces trades sont générés par mes agents IA.

Ils analysent :

• momentum et volumes
• supports / résistances
• régime de marché
• sentiment et news crypto

📊 ${tradeCount} trades publiés. Résultats transparents chaque jour.

Rejoins le canal pour suivre les prochains trades en temps réel.`
  );
}

function tplEducational(strategy, content) {
  const names = {
    MeanReversion:   "Mean Reversion",
    Momentum:        "Momentum",
    NewsTrading:     "News Trading",
    Breakout:        "Breakout",
    WhaleFollowing:  "Whale Following",
    SentimentExtremes: "Sentiment Extremes",
  };
  return (
`🧠 SETUP DU JOUR

${names[strategy] ?? strategy}

${content}`
  );
}

// ─── Helpers state ────────────────────────────────────────────────────────

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}

function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

function getTradeNumber(state) {
  state.trade_counter = (state.trade_counter ?? 0) + 1;
  return state.trade_counter;
}

// ─── Calcul métriques journalières ───────────────────────────────────────

function calcDailyMetrics(trades, capitalUSD = 10000) {
  if (!trades.length) return null;
  const wins   = trades.filter(t => t.pnl_usd >= 0);
  const losses = trades.filter(t => t.pnl_usd < 0);
  const pnl    = trades.reduce((s, t) => s + (t.pnl_usd ?? 0), 0);
  const totalWins   = wins.reduce((s, t) => s + t.pnl_usd, 0);
  const totalLosses = Math.abs(losses.reduce((s, t) => s + t.pnl_usd, 0));
  const avgWin  = wins.length   ? totalWins   / wins.length   : 0;
  const avgLoss = losses.length ? totalLosses / losses.length : 0;
  const winRate = trades.length ? wins.length / trades.length : 0;
  const profitFactor = totalLosses > 0 ? totalWins / totalLosses : totalWins > 0 ? 99 : 0;
  const expectancy = (winRate * avgWin) - ((1 - winRate) * avgLoss);
  const sorted = [...trades].sort((a, b) => (b.pnl_usd ?? 0) - (a.pnl_usd ?? 0));

  return {
    total_trades:  trades.length,
    wins:          wins.length,
    losses:        losses.length,
    daily_pnl:     parseFloat(pnl.toFixed(2)),
    roi_pct:       parseFloat((pnl / capitalUSD * 100).toFixed(4)),
    win_rate:      parseFloat((winRate * 100).toFixed(1)),
    profit_factor: parseFloat(profitFactor.toFixed(2)),
    expectancy:    parseFloat(expectancy.toFixed(2)),
    best_trade:    sorted[0]   ?? null,
    worst_trade:   sorted[sorted.length - 1] ?? null,
  };
}

// ─── Handler principal ────────────────────────────────────────────────────

export async function handler(ctx) {
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;
  const apiKey = process.env.ANTHROPIC_API_KEY;

  if (!token || !chatId) {
    ctx.log("❌ TRADER_TELEGRAM_BOT_TOKEN ou TRADER_TELEGRAM_CHAT_ID manquant");
    return;
  }

  const execDir  = path.join(ctx.stateDir, "exec");
  const sentFile = path.join(execDir, "publisher_sent.json");
  const pnlFile  = path.join(execDir, "daily_pnl.json");
  const posFile  = path.join(execDir, "positions.json");

  let sent      = readJSON(sentFile, {});
  const positions = readJSON(posFile, []);
  let published = 0;

  // ── 1. Positions ouvertes ────────────────────────────────────────────
  for (const pos of positions) {
    if (pos.status !== "open") continue;
    const key = `open_${pos.id}`;
    if (sent[key]) continue;

    const tradeNum = getTradeNumber(ctx.state);
    pos._trade_num = tradeNum;

    let setup = null;
    if (apiKey) setup = await generateSetup(apiKey, "open", pos);

    const msg = tplPositionOpen(pos, tradeNum, setup);
    await sendTelegram(token, chatId, msg);
    sent[key] = Date.now();
    published++;
    ctx.log(`📤 OPEN ${pos.symbol} ${pos.side} #${tradeNum}`);
  }

  // ── 2. Positions fermées (ledger) ────────────────────────────────────
  const cursor = ctx.state.cursors?.ledger ?? 0;
  const { events: ledger, nextCursor } =
    ctx.bus.readSince("trading.exec.trade.ledger", cursor, 20);

  for (const event of ledger) {
    const pos = event.payload;
    const key = `close_${pos.id ?? event.event_id}`;
    if (sent[key]) continue;

    const tradeNum = ctx.state.trade_counter ?? getTradeNumber(ctx.state);
    const isWin    = (pos.pnl_usd ?? 0) >= 0;

    let setup = null;
    if (apiKey) setup = await generateSetup(apiKey, isWin ? "win" : "loss", pos);

    const msg = isWin
      ? tplPositionCloseWin(pos, tradeNum, setup)
      : tplPositionCloseLoss(pos, tradeNum, setup);

    await sendTelegram(token, chatId, msg);
    sent[key] = Date.now();
    published++;
    ctx.log(`📤 CLOSE ${pos.symbol} ${isWin ? "WIN" : "LOSS"} $${pos.pnl_usd}`);
  }

  ctx.state.cursors = { ...ctx.state.cursors, ledger: nextCursor };

  // ── 3. Kill switch ────────────────────────────────────────────────────
  const ksFile = path.join(ctx.stateDir, "exec", "killswitch.json");
  try {
    const ks = readJSON(ksFile, {});
    if (ks.state === "TRIPPED" && !sent[`ks_${ks.tripped_at}`]) {
      const msg = `🚨 *KILL SWITCH DÉCLENCHÉ*\n\nRaison: _${ks.reason}_\nTous les trades sont bloqués.\nAction requise: reset manuel.`;
      await sendTelegram(token, chatId, msg);
      sent[`ks_${ks.tripped_at}`] = Date.now();
      published++;
    }
  } catch {}

  // ── 4. Bilan journalier (19h UTC = 21h Paris) ─────────────────────
  const hour  = new Date().getUTCHours();
  const today = new Date().toISOString().slice(0, 10);
  const recapKey = `recap_daily_${today}`;

  if (hour >= 19 && !sent[recapKey]) {
    const { events: allTrades } = ctx.bus.readSince("trading.exec.trade.ledger", 0, 1000);
    const todayTrades = allTrades
      .filter(e => new Date(e.payload?.closed_at ?? 0).toISOString().slice(0, 10) === today)
      .map(e => e.payload);

    const dailyPnl = readJSON(pnlFile, {});
    const metrics  = calcDailyMetrics(todayTrades);

    if (metrics && metrics.total_trades > 0) {
      metrics.daily_pnl = dailyPnl[today] ?? metrics.daily_pnl;
      const msg = tplDailyRecap(metrics);
      await sendTelegram(token, chatId, msg);
      sent[recapKey] = Date.now();
      published++;
      ctx.log("📊 Bilan journalier envoyé");
    }
  }

  // ── 5. Bilan hebdomadaire (dimanche 20h UTC) ──────────────────────
  const dayOfWeek = new Date().getUTCDay();
  const weekKey   = `recap_weekly_${today}`;

  if (dayOfWeek === 0 && hour >= 20 && !sent[weekKey]) {
    const { events: allTrades } = ctx.bus.readSince("trading.exec.trade.ledger", 0, 5000);
    const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
    const weekTrades = allTrades
      .filter(e => (e.payload?.closed_at ?? 0) > weekAgo)
      .map(e => e.payload);

    const metrics = calcDailyMetrics(weekTrades);
    if (metrics && metrics.total_trades > 0) {
      const msg = tplWeeklyRecap(metrics);
      await sendTelegram(token, chatId, msg);
      sent[weekKey] = Date.now();
      published++;
      ctx.log("📊 Bilan hebdomadaire envoyé");
    }
  }

  // ── 6. Message viral tous les 10 trades ───────────────────────────
  const tradeCount  = ctx.state.trade_counter ?? 0;
  const lastViral   = ctx.state.last_viral_at ?? 0;
  const viralEvery  = 10;

  if (tradeCount > 0 && tradeCount % viralEvery === 0 && tradeCount !== lastViral) {
    const msg = tplViral(tradeCount);
    await sendTelegram(token, chatId, msg);
    ctx.state.last_viral_at = tradeCount;
    published++;
    ctx.log(`📣 Message viral envoyé (${tradeCount} trades)`);
  }

  // ── 7. Message éducatif (lundi 9h UTC = 11h Paris) ────────────────
  const eduKey = `educational_${today}`;
  if (dayOfWeek === 1 && hour >= 9 && hour < 10 && !sent[eduKey]) {
    const strategies = ["MeanReversion", "Momentum", "Breakout", "NewsTrading"];
    const strategy   = strategies[Math.floor(Math.random() * strategies.length)];
    let content = null;
    if (apiKey) content = await generateSetup(apiKey, "educational", { strategy });
    if (content) {
      const msg = tplEducational(strategy, content);
      await sendTelegram(token, chatId, msg);
      sent[eduKey] = Date.now();
      published++;
      ctx.log(`🧠 Message éducatif envoyé: ${strategy}`);
    }
  }

  // ── Sauvegarde ────────────────────────────────────────────────────
  writeJSON(sentFile, sent);
  ctx.log(`✅ ${published} messages publiés`);
}
