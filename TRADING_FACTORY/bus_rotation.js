/**
 * Bus Rotation — exécuté quotidiennement via cron ou manuellement.
 * Règles :
 *   trading.raw.*   → archivé + tronqué après 7 jours
 *   trading.intel.* → conservé 30 jours
 *   trading.audit.* → jamais tronqué automatiquement
 *
 * Usage : node bus_rotation.js
 */

import fs   from "fs";
import path from "path";

const STATE_DIR = process.env.STATE_DIR ?? "/home/node/.openclaw/workspace/state/trading";
const BUS_DIR   = path.join(STATE_DIR, "bus");
const ARCH_DIR  = path.join(STATE_DIR, "bus_archive");

const RETENTION = {
  "trading_raw_":   7  * 24 * 3600,   // 7 jours
  "trading_intel_": 30 * 24 * 3600,   // 30 jours
  "trading_audit_": Infinity,          // jamais
};

function getRetention(filename) {
  for (const [prefix, secs] of Object.entries(RETENTION)) {
    if (filename.startsWith(prefix)) return secs;
  }
  return 30 * 24 * 3600; // défaut 30j
}

function countLines(p) {
  return fs.readFileSync(p, "utf-8").split("\n").filter(Boolean).length;
}

function archiveAndTruncate(filePath, archDir) {
  const filename  = path.basename(filePath);
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const archPath  = path.join(archDir, `${filename}.${timestamp}`);
  fs.mkdirSync(archDir, { recursive: true });
  fs.copyFileSync(filePath, archPath);
  fs.writeFileSync(filePath, "", "utf-8");
  return archPath;
}

async function main() {
  if (!fs.existsSync(BUS_DIR)) {
    console.log("[rotation] Bus dir introuvable, rien à faire.");
    return;
  }

  const files = fs.readdirSync(BUS_DIR).filter(f => f.endsWith(".jsonl"));
  const nowSec = Math.floor(Date.now() / 1000);

  for (const file of files) {
    const filePath  = path.join(BUS_DIR, file);
    const retention = getRetention(file);

    if (retention === Infinity) {
      console.log(`[rotation] ⏭  ${file} — audit, jamais tronqué`);
      continue;
    }

    const stat = fs.statSync(filePath);
    const ageSec = nowSec - Math.floor(stat.mtimeMs / 1000);
    const lines  = countLines(filePath);

    if (ageSec >= retention) {
      const archPath = archiveAndTruncate(filePath, ARCH_DIR);
      console.log(`[rotation] 🗜  ${file} — ${lines} lignes archivées → ${path.basename(archPath)}`);
    } else {
      const daysLeft = Math.floor((retention - ageSec) / 86400);
      console.log(`[rotation] ✅ ${file} — ${lines} lignes, rotation dans ${daysLeft}j`);
    }
  }
}

main().catch(e => { console.error("[rotation] FATAL", e); process.exit(1); });
