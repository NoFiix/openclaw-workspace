/**
 * TOKEN_TRACKER v2 — Handler
 * Agrège token_costs.jsonl pour trading ET content.
 * Envoie bilan quotidien sur Telegram à 20h UTC.
 * Zéro LLM.
 */
import fs   from "fs";
import path from "path";

function readJSON(p, def) {
  try { return JSON.parse(fs.readFileSync(p, "utf-8")); } catch { return def; }
}
function writeJSON(p, d) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(d, null, 2));
}

async function sendTelegram(token, chatId, text) {
  try {
    await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
  } catch {}
}

function fmtCost(n) { return `$${n.toFixed(4)}`; }
function fmtNum(n)  { return n.toLocaleString("fr-FR"); }

export async function handler(ctx) {
  const token  = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;

  const learnDir  = path.join(ctx.stateDir, "learning");
  const costsFile = path.join(learnDir, "token_costs.jsonl");
  const outFile   = path.join(learnDir, "token_summary.json");

  if (!fs.existsSync(costsFile)) {
    ctx.log("Pas de token_costs.jsonl — rien à agréger");
    return;
  }

  const lines = fs.readFileSync(costsFile, "utf-8").split("\n").filter(Boolean);
  const entries = lines.map(l => { try { return JSON.parse(l); } catch { return null; } })
                       .filter(Boolean);

  if (!entries.length) { ctx.log("Fichier vide"); return; }

  const today   = new Date().toISOString().slice(0, 10);
  const weekAgo = new Date(Date.now() - 7 * 24 * 3600 * 1000).toISOString().slice(0, 10);

  const todayEntries = entries.filter(e => e.date === today);
  const weekEntries  = entries.filter(e => e.date >= weekAgo);

  // ── Agrégation par agent (tous systèmes) ─────────────────────────────
  const byAgent = {};
  for (const e of entries) {
    if (!byAgent[e.agent]) byAgent[e.agent] = {
      agent: e.agent, system: e.system, calls: 0,
      input: 0, output: 0, total: 0, cost_usd: 0
    };
    const a = byAgent[e.agent];
    a.calls++; a.input += e.input; a.output += e.output;
    a.total += e.total; a.cost_usd += e.cost_usd;
  }

  // ── Agrégation par système ────────────────────────────────────────────
  const bySystem = {};
  for (const e of entries) {
    const sys = e.system ?? "unknown";
    if (!bySystem[sys]) bySystem[sys] = { calls: 0, total: 0, cost_usd: 0 };
    bySystem[sys].calls++; bySystem[sys].total += e.total;
    bySystem[sys].cost_usd += e.cost_usd;
  }

  // ── Totaux aujourd'hui ────────────────────────────────────────────────
  const dayTotals = {
    input:    todayEntries.reduce((s, e) => s + e.input, 0),
    output:   todayEntries.reduce((s, e) => s + e.output, 0),
    cost_usd: todayEntries.reduce((s, e) => s + e.cost_usd, 0),
  };

  // ── Totaux semaine ────────────────────────────────────────────────────
  const weekTotals = {
    input:    weekEntries.reduce((s, e) => s + e.input, 0),
    output:   weekEntries.reduce((s, e) => s + e.output, 0),
    cost_usd: weekEntries.reduce((s, e) => s + e.cost_usd, 0),
  };

  // ── Projection mensuelle ──────────────────────────────────────────────
  const daysTracked = new Set(entries.map(e => e.date)).size || 1;
  const avgPerDay   = entries.reduce((s, e) => s + e.cost_usd, 0) / daysTracked;
  const monthlyProj = avgPerDay * 30;

  // Arrondir
  for (const a of Object.values(byAgent)) a.cost_usd = parseFloat(a.cost_usd.toFixed(6));
  for (const s of Object.values(bySystem)) s.cost_usd = parseFloat(s.cost_usd.toFixed(6));

  const summary = {
    global: {
      total_calls:   entries.length,
      total_tokens:  entries.reduce((s, e) => s + e.total, 0),
      total_cost_usd: parseFloat(entries.reduce((s, e) => s + e.cost_usd, 0).toFixed(6)),
      avg_per_day_usd: parseFloat(avgPerDay.toFixed(6)),
      monthly_proj_usd: parseFloat(monthlyProj.toFixed(4)),
      days_tracked:   daysTracked,
      updated_at:     new Date().toISOString(),
    },
    today:    { ...dayTotals,  cost_usd: parseFloat(dayTotals.cost_usd.toFixed(6)) },
    week:     { ...weekTotals, cost_usd: parseFloat(weekTotals.cost_usd.toFixed(6)) },
    by_agent:  byAgent,
    by_system: bySystem,
  };
  writeJSON(outFile, summary);

  ctx.log(`✅ ${entries.length} appels | aujourd'hui: ${fmtCost(dayTotals.cost_usd)} | semaine: ${fmtCost(weekTotals.cost_usd)}`);

  // ── Bilan Telegram — 20h UTC seulement ──────────────────────────────
  const hour        = new Date().getUTCHours();
  const telegramKey = `daily_token_report_${today}`;
  const sent        = readJSON(path.join(learnDir, "token_tracker_sent.json"), {});

  if (hour >= 20 && !sent[telegramKey] && token && chatId) {
    // Top 5 agents par coût total
    const topAgents = Object.values(byAgent)
      .sort((a, b) => b.cost_usd - a.cost_usd)
      .slice(0, 5);

    const totalCost = summary.global.total_cost_usd;
    const topLines  = topAgents.map((a, i) => {
      const pct = totalCost > 0 ? Math.round(a.cost_usd / totalCost * 100) : 0;
      return `${i + 1}. *${a.agent}* — ${fmtCost(a.cost_usd)} (${pct}%)`;
    }).join("\n");

    const systemLines = Object.entries(bySystem)
      .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
      .map(([sys, d]) => `• ${sys}: ${fmtCost(d.cost_usd)}`)
      .join("\n");

    const msg =
`💰 *BILAN TOKENS — ${today}*

📊 *Aujourd'hui*
Input  : ${fmtNum(dayTotals.input)} tokens
Output : ${fmtNum(dayTotals.output)} tokens
Coût   : ${fmtCost(dayTotals.cost_usd)}

📊 *Cette semaine*
Input  : ${fmtNum(weekTotals.input)} tokens
Output : ${fmtNum(weekTotals.output)} tokens
Coût   : ${fmtCost(weekTotals.cost_usd)}

🔝 *Top consommateurs*
${topLines}

⚙️ *Par système*
${systemLines}

📈 Projection mois : *${fmtCost(monthlyProj)}*`;

    await sendTelegram(token, chatId, msg);
    sent[telegramKey] = Date.now();
    writeJSON(path.join(learnDir, "token_tracker_sent.json"), sent);
    ctx.log("📱 Bilan tokens envoyé sur Telegram");
  }
}
