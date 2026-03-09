/**
 * TOKEN_ANALYST — Handler
 * Lit token_summary.json, analyse les dépenses, propose des optimisations.
 * Utilise Sonnet — tourne 1 fois par semaine (lundi 8h UTC).
 * Envoie un résumé sur Telegram.
 */
import fs   from "fs";
import path from "path";

const ANTHROPIC_API = "https://api.anthropic.com/v1/messages";
const MODEL         = "claude-sonnet-4-20250514";

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

export async function handler(ctx) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const token  = process.env.TRADER_TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TRADER_TELEGRAM_CHAT_ID;

  if (!apiKey) { ctx.log("❌ ANTHROPIC_API_KEY manquant"); return; }

  // Vérification : lundi 8h UTC seulement
  const now = new Date();
  const day  = now.getUTCDay();
  const hour = now.getUTCHours();
  const today = now.toISOString().slice(0, 10);

  if ((day !== 1 && day !== 4) || hour < 8 || hour >= 9) {
    ctx.log(`⏭  TOKEN_ANALYST tourne lundi et jeudi 8h UTC (aujourd'hui: jour=${day} heure=${hour})`);
    return;
  }
  if (ctx.state.last_run_date === today) {
    ctx.log("⏭  Déjà tourné cette semaine");
    return;
  }

  const learnDir   = path.join(ctx.stateDir, "learning");
  const summary    = readJSON(path.join(learnDir, "token_summary.json"), null);
  const candidates = readJSON(path.join(learnDir, "strategy_candidates.json"), []);
  const stratPerf  = readJSON(path.join(learnDir, "strategy_performance.json"), {});

  if (!summary) { ctx.log("❌ token_summary.json introuvable — TOKEN_TRACKER a-t-il tourné ?"); return; }

  ctx.log("🔍 TOKEN_ANALYST — analyse hebdomadaire des coûts");

  // Préparer le contexte pour Sonnet
  const prompt = `Tu es un analyste IA pragmatique, froid et cartésien spécialisé dans l'optimisation des coûts LLM.

Voici les dépenses de tokens de la semaine pour le système de trading CryptoRizon :

## Résumé global
${JSON.stringify(summary.global, null, 2)}

## Par agent
${JSON.stringify(summary.by_agent, null, 2)}

## Par jour
${JSON.stringify(summary.by_day, null, 2)}

## Stratégies testées (${candidates.length} candidats)
${JSON.stringify(Object.keys(stratPerf), null, 2)}

Analyse ces dépenses et propose des optimisations concrètes et chiffrées.

Réponds en JSON strict :
{
  "total_cost_usd": 0.00,
  "biggest_spender": "AGENT_NAME",
  "weekly_projection_usd": 0.00,
  "monthly_projection_usd": 0.00,
  "optimizations": [
    {
      "agent": "AGENT_NAME",
      "issue": "description du problème",
      "fix": "solution concrète",
      "saving_pct": 30,
      "priority": "high|medium|low"
    }
  ],
  "verdict": "1 phrase de verdict global"
}`;

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
        max_tokens: 1000,
        messages:   [{ role: "user", content: prompt }],
      }),
    });

    const data = await res.json();
    const text = data.content?.[0]?.text?.trim() ?? "{}";
    const clean = text.replace(/```json|```/g, "").trim();
    const analysis = JSON.parse(clean);

    // Sauvegarder les recommandations
    writeJSON(path.join(learnDir, "token_recommendations.json"), {
      ...analysis,
      analyzed_at: new Date().toISOString(),
      period: { from: summary.global.first_entry, to: summary.global.last_entry },
    });

    ctx.state.last_run_date = today;

    ctx.log(`💰 Coût semaine: $${analysis.total_cost_usd}`);
    ctx.log(`📈 Projection mensuelle: $${analysis.monthly_projection_usd}`);
    ctx.log(`🔝 Plus gros consommateur: ${analysis.biggest_spender}`);

    for (const opt of analysis.optimizations ?? []) {
      ctx.log(`  [${opt.priority.toUpperCase()}] ${opt.agent}: ${opt.fix} (-${opt.saving_pct}%)`);
    }

    // Message Telegram
    if (token && chatId) {
      const opts = (analysis.optimizations ?? [])
        .filter(o => o.priority === "high")
        .map(o => `• *${o.agent}*: ${o.fix} (-${o.saving_pct}%)`)
        .join("\n");

      const msg =
`🤖 *TOKEN ANALYST — Rapport hebdomadaire*

💰 Coût semaine : *$${analysis.total_cost_usd}*
📈 Projection mois : *$${analysis.monthly_projection_usd}*
🔝 Plus gros consommateur : *${analysis.biggest_spender}*

${opts ? `⚡ Optimisations prioritaires :\n${opts}` : "✅ Aucune optimisation critique"}

_${analysis.verdict}_`;

      await sendTelegram(token, chatId, msg);
      ctx.log("📱 Rapport envoyé sur Telegram");
    }

  } catch (e) {
    ctx.log(`❌ Erreur analyse: ${e.message}`);
  }
}
