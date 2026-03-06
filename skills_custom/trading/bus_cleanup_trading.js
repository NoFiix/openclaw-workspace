/**
 * bus_cleanup_trading.js v2
 * Architecture mémoire 4 couches validée :
 *   Layer 1 — Live       : données temps réel, TTL court
 *   Layer 2 — Context    : régime + news, TTL moyen
 *   Layer 3 — Learning   : ledger + perf + stratégies, TTL long
 *   Layer 4 — Risk/Audit : incidents + kill switch, TTL très long
 *
 * Règle d'or : ne pas supprimer ce que personne ne lit encore,
 *              mais ne pas laisser grossir indéfiniment le bruit.
 */

import fs   from "fs";
import path from "path";

const STATE_DIR = process.env.STATE_DIR
  ?? "/home/node/.openclaw/workspace/state/trading";

const DAY = 24 * 3600 * 1000;

const RETENTION = {
  // ── Layer 1 — Live (décisions temps réel) ─────────────────────────────
  "trading_intel_price_feed":           1  * DAY,   // 24h — tick brut inutile après
  "trading_raw_market_ticker":          1  * DAY,   // 24h
  "trading_raw_market_ohlcv":           1  * DAY,   // 24h — remplacé par ohlcv structuré
  "trading_intel_market_features":      3  * DAY,   // 72h — debug + comparaison hier/aujourd'hui
  "trading_exec_position_snapshot":     30 * DAY,   // 30j — snapshots positions

  // ── Layer 2 — Context (comprendre le marché) ──────────────────────────
  "trading_intel_regime":               90 * DAY,   // 90j — précieux pour LEARNER
  "trading_raw_news_article":           3  * DAY,   // 3j — feed brut
  "trading_raw_social_post":            3  * DAY,   // 3j — feed brut
  "trading_intel_news_event":           30 * DAY,   // 30j — news scorées utiles pour analyse
  "trading_intel_prediction":           7  * DAY,   // 7j  — prédictions PREDICTOR

  // ── Layer 3 — Learning (ce qui marche vraiment) ───────────────────────
  "trading_strategy_trade_proposal":    90 * DAY,   // 90j — LEARNER analyse les proposals
  "trading_strategy_block":             90 * DAY,   // 90j — trades bloqués = source d'apprentissage
  "trading_strategy_order_plan":        90 * DAY,   // 90j — plans validés par RISK_MANAGER
  "trading_exec_trade_ledger":          365 * DAY,  // 365j — ne jamais supprimer (PnL, audit, fiscalité)

  // ── Layer 4 — Risk / Audit ────────────────────────────────────────────
  "trading_ops_killswitch_state":       90 * DAY,   // 90j — historique déclenchements
  "trading_ops_alert":                  90 * DAY,   // 90j — alertes opérationnelles
};

// ── Helpers ───────────────────────────────────────────────────────────────

function sizeOf(p) {
  try { return fs.statSync(p).size; } catch { return 0; }
}

function fmt(bytes) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes/1024).toFixed(1)}KB`;
  return `${(bytes/1024/1024).toFixed(2)}MB`;
}

function cleanBusFile(filePath, maxAge) {
  if (!fs.existsSync(filePath)) return null;
  const before  = sizeOf(filePath);
  const now     = Date.now();
  const lines   = fs.readFileSync(filePath, "utf-8").split("\n").filter(Boolean);
  const kept    = lines.filter(l => {
    try { return (now - (JSON.parse(l).ts ?? 0)) < maxAge; }
    catch { return false; }
  });
  fs.writeFileSync(filePath, kept.join("\n") + (kept.length ? "\n" : ""));
  return { removed: lines.length - kept.length, kept: kept.length, saved: before - sizeOf(filePath), before };
}

function cleanRunsDir(dir, maxAge = 24 * 3600 * 1000) {
  if (!fs.existsSync(dir)) return 0;
  let n = 0;
  for (const f of fs.readdirSync(dir)) {
    const fp = path.join(dir, f);
    if ((Date.now() - fs.statSync(fp).mtimeMs) > maxAge) { fs.unlinkSync(fp); n++; }
  }
  return n;
}

function cleanPublisherSent(p, maxAge = 7 * 24 * 3600 * 1000) {
  if (!fs.existsSync(p)) return 0;
  try {
    const d = JSON.parse(fs.readFileSync(p, "utf-8"));
    const now = Date.now(); let n = 0;
    for (const [k, ts] of Object.entries(d)) {
      if ((now - ts) > maxAge) { delete d[k]; n++; }
    }
    fs.writeFileSync(p, JSON.stringify(d, null, 2));
    return n;
  } catch { return 0; }
}

// ── Initialise les fichiers MVP s'ils n'existent pas ─────────────────────

function initMvpFiles() {
  const dirs = ["live", "context", "learning", "risk"];
  for (const d of dirs) {
    fs.mkdirSync(path.join(STATE_DIR, d), { recursive: true });
  }

  const defaults = {
    "context/regime_current.json":       { regime: null, confidence: 0, ts: null },
    "context/news_events.json":          [],
    "learning/strategy_performance.json": {},
    "risk/policy_decisions.json":        [],
    "risk/killswitch_events.json":       [],
  };

  let created = 0;
  for (const [rel, def] of Object.entries(defaults)) {
    const fp = path.join(STATE_DIR, rel);
    if (!fs.existsSync(fp)) {
      fs.writeFileSync(fp, JSON.stringify(def, null, 2));
      console.log(`  📁 Créé: state/trading/${rel}`);
      created++;
    }
  }
  if (created === 0) console.log("  📁 Fichiers MVP déjà présents");
}

// ── Main ──────────────────────────────────────────────────────────────────

console.log("[bus_cleanup_trading] 🧹 v2 — Architecture 4 couches");
console.log(`[bus_cleanup_trading] STATE_DIR: ${STATE_DIR}\n`);

// 1. Init fichiers MVP
console.log("── Initialisation fichiers MVP ───────────────────────────────");
initMvpFiles();

// 2. Nettoyage bus JSONL
console.log("\n── Nettoyage bus JSONL ───────────────────────────────────────");
const busDir = path.join(STATE_DIR, "bus");
let totalSaved = 0, totalRemoved = 0;

if (fs.existsSync(busDir)) {
  for (const file of fs.readdirSync(busDir).filter(f => f.endsWith(".jsonl"))) {
    const key    = file.replace(".jsonl", "").replace(/\./g, "_");
    const maxAge = RETENTION[key];
    const fp     = path.join(busDir, file);

    if (!maxAge) {
      console.log(`  ⏭  ${file} — pas de règle, ignoré`);
      continue;
    }

    const r = cleanBusFile(fp, maxAge);
    if (!r) continue;

    const days = Math.round(maxAge / DAY);
    totalSaved   += r.saved;
    totalRemoved += r.removed;

    console.log(
      `  ${r.removed > 0 ? "✅" : "⚪"} ${file}` +
      ` — TTL:${days}j | -${r.removed} events` +
      ` | ${fmt(r.before)} → ${fmt(sizeOf(fp))}` +
      ` | gardé: ${r.kept}`
    );
  }
}

// 3. Nettoyage runs/
const runsRemoved = cleanRunsDir(path.join(STATE_DIR, "runs"));
console.log(`\n  🗑  runs/: ${runsRemoved} fichiers supprimés`);

// 4. Nettoyage publisher_sent
const sentRemoved = cleanPublisherSent(
  path.join(STATE_DIR, "exec", "publisher_sent.json")
);
console.log(`  🗑  publisher_sent.json: ${sentRemoved} entrées purgées`);

// 5. Rapport taille bus
console.log("\n── Taille actuelle du bus ────────────────────────────────────");
if (fs.existsSync(busDir)) {
  let totalSize = 0;
  for (const f of fs.readdirSync(busDir)) {
    const s = sizeOf(path.join(busDir, f));
    totalSize += s;
    if (s > 100 * 1024) console.log(`  ⚠️  ${f}: ${fmt(s)}`);
  }
  console.log(`  📦 Total bus: ${fmt(totalSize)}`);
}

console.log(
  `\n[bus_cleanup_trading] ✅ Terminé` +
  ` — ${totalRemoved} events purgés` +
  ` — ${fmt(totalSaved)} libérés`
);
