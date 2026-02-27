/**
 * cleanup.js - Purge automatique des mémoires selon RETENTION.md
 * 
 * Règles :
 * 7 jours  → scraper/memory/, publisher/memory/
 * 10 jours → copywriter/memory/
 * 30 jours → email/memory/ (sauf drafts/)
 * 90 jours → builder/memory/
 * 
 * Tourne chaque dimanche à 3h du matin (configuré dans recipes/)
 */

const fs   = require("fs");
const path = require("path");

const WORKSPACE = process.env.OPENCLAW_WORKSPACE_DIR || "/home/node/.openclaw/workspace";

const RETENTION_RULES = [
  { dir: "agents/scraper/memory",     days: 7  },
  { dir: "agents/publisher/memory",   days: 7  },
  { dir: "agents/copywriter/memory",  days: 10 },
  { dir: "agents/email/memory",       days: 30 },
  { dir: "agents/builder/memory",     days: 90 },
];

// Fichiers à ne jamais supprimer
const PROTECTED_FILES = [
  "preferences.md",
  "SOUL.md",
  "AGENTS.md",
];

function getAgeInDays(filePath) {
  try {
    const stat = fs.statSync(filePath);
    const ageMs = Date.now() - stat.mtimeMs;
    return ageMs / (1000 * 60 * 60 * 24);
  } catch {
    return 0;
  }
}

function purgeDirectory(relDir, maxDays) {
  const absDir = path.join(WORKSPACE, relDir);

  if (!fs.existsSync(absDir)) {
    console.log(`[skip] ${relDir} — dossier inexistant`);
    return { skipped: 0, deleted: 0, errors: 0 };
  }

  const files = fs.readdirSync(absDir);
  let deleted = 0, skipped = 0, errors = 0;

  for (const file of files) {
    // Ne jamais supprimer les fichiers protégés
    if (PROTECTED_FILES.includes(file)) {
      skipped++;
      continue;
    }

    // Ne supprimer que les fichiers .md et .json
    if (!file.endsWith(".md") && !file.endsWith(".json") && !file.endsWith(".jsonl")) {
      skipped++;
      continue;
    }

    const filePath = path.join(absDir, file);
    const ageDays  = getAgeInDays(filePath);

    if (ageDays > maxDays) {
      try {
        fs.unlinkSync(filePath);
        console.log(`[deleted] ${relDir}/${file} (${Math.floor(ageDays)}j > ${maxDays}j)`);
        deleted++;
      } catch (e) {
        console.error(`[error] ${relDir}/${file} — ${e.message}`);
        errors++;
      }
    } else {
      skipped++;
    }
  }

  return { skipped, deleted, errors };
}

function purgeIntelData(maxDays = 7) {
  const absDir = path.join(WORKSPACE, "intel/data");

  if (!fs.existsSync(absDir)) return;

  const files = fs.readdirSync(absDir);
  let deleted = 0;

  for (const file of files) {
    const filePath = path.join(absDir, file);
    const ageDays  = getAgeInDays(filePath);
    if (ageDays > maxDays) {
      try {
        fs.unlinkSync(filePath);
        console.log(`[deleted] intel/data/${file} (${Math.floor(ageDays)}j)`);
        deleted++;
      } catch {}
    }
  }

  console.log(`[intel/data] ${deleted} fichiers supprimés`);
}

function logCleanup(summary) {
  try {
    const logPath = path.join(WORKSPACE, "state", "cleanup-log.jsonl");
    fs.appendFileSync(logPath, JSON.stringify({
      timestamp: new Date().toISOString(),
      ...summary
    }) + "\n");
  } catch {}
}

function runCleanup() {
  console.log(`\n=== CLEANUP ${new Date().toISOString()} ===\n`);

  let totalDeleted = 0;
  let totalErrors  = 0;
  const results    = {};

  for (const rule of RETENTION_RULES) {
    const result = purgeDirectory(rule.dir, rule.days);
    results[rule.dir] = result;
    totalDeleted += result.deleted;
    totalErrors  += result.errors;
    console.log(`[${rule.dir}] supprimés: ${result.deleted}, ignorés: ${result.skipped}, erreurs: ${result.errors}`);
  }

  // Purge intel/data (7 jours)
  purgeIntelData(7);

  const summary = {
    totalDeleted,
    totalErrors,
    details: results,
  };

  logCleanup(summary);

  console.log(`\n=== RÉSUMÉ ===`);
  console.log(`Total supprimés : ${totalDeleted}`);
  console.log(`Total erreurs   : ${totalErrors}`);
  console.log(`Log : state/cleanup-log.jsonl\n`);
}

runCleanup();
