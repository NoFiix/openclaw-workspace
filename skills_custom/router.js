/**
 * router.js - Skill de routing intelligent des modèles IA
 * 
 * Score total → choix du modèle optimal
 * 3-4   → claude-haiku-4-5      (ultra rapide, économique)
 * 5-6   → gpt-4o-mini           (léger)
 * 7-8   → gpt-4o                (intermédiaire)
 * 9-11  → claude-sonnet-4-5     (créatif, analyse)
 * 12-15 → claude-opus-4-6       (code, critique, TOUJOURS pour dev)
 */

const MODELS = {
  ULTRA_LIGHT: "anthropic/claude-haiku-4-5",
  LIGHT:       "openai/gpt-4o-mini",
  MEDIUM:      "openai/gpt-4o",
  SMART:       "anthropic/claude-sonnet-4-5",
  HEAVY:       "anthropic/claude-opus-4-6",
};

const KEYWORDS = {
  importance: {
    high: [
      "urgent", "critique", "important", "priorité", "deadline",
      "erreur", "bug", "publication", "code", "script", "déboguer",
      "déployer", "modifier fichier", "skill", "développer"
    ],
    low: [
      "résumé", "liste", "trier", "classer", "vérifier",
      "lire", "notifier", "afficher"
    ],
  },
  sensitivity: {
    high: [
      "clé api", "secret", "token", "mot de passe", "credentials",
      "modifier", "supprimer", "déployer", "code", "script",
      "fichier", "skill", "automatiser", "déboguer"
    ],
    low: [
      "lire", "afficher", "résumer", "lister",
      "scraper", "trier", "notifier"
    ],
  },
  complexity: {
    high: [
      "code", "script", "développer", "créer un skill", "automatiser",
      "architecture", "déboguer", "débogage", "debug", "fix",
      "corriger", "analyser", "rédiger", "copywriting", "storytelling",
      "thread", "modifier fichier", "générer", "implémenter", "refactoriser"
    ],
    low: [
      "résumé", "liste", "trier", "classification",
      "score", "notifier", "répondre", "afficher"
    ],
  },
};

// Tâches qui vont TOUJOURS sur Opus — pas de discussion
const FORCE_OPUS = [
  "code", "script", "déboguer", "débogage", "debug", "fix bug",
  "corriger le code", "générer un skill", "créer un skill",
  "implémenter", "refactoriser", "automatiser", "développer",
  "modifier fichier", "self_improve", "auto-amélioration"
];

// Tâches qui vont TOUJOURS sur Sonnet
const FORCE_SONNET = [
  "copywriting", "storytelling", "thread twitter",
  "rédiger post", "analyser", "stratégie"
];

function scoreAxis(text, axis) {
  const lower = text.toLowerCase();
  let score = 2;
  for (const kw of KEYWORDS[axis].high) {
    if (lower.includes(kw)) score = Math.min(5, score + 1);
  }
  for (const kw of KEYWORDS[axis].low) {
    if (lower.includes(kw)) score = Math.max(1, score - 1);
  }
  return score;
}

function routeTask(task, overrides = {}) {
  const lower = task.toLowerCase();

  // Force Opus pour tout ce qui touche au code
  for (const kw of FORCE_OPUS) {
    if (lower.includes(kw)) {
      const result = {
        model: MODELS.HEAVY,
        scores: { importance: 5, sensitivity: 5, complexity: 5 },
        total: 15,
        reason: `Forcé sur Opus — tâche code/développement détectée (${kw})`,
        task: task.slice(0, 100),
        timestamp: new Date().toISOString(),
      };
      logDecision(result);
      return result;
    }
  }

  // Force Sonnet pour copywriting et analyse
  for (const kw of FORCE_SONNET) {
    if (lower.includes(kw)) {
      const result = {
        model: MODELS.SMART,
        scores: { importance: 4, sensitivity: 2, complexity: 5 },
        total: 11,
        reason: `Forcé sur Sonnet — tâche créative/analyse détectée (${kw})`,
        task: task.slice(0, 100),
        timestamp: new Date().toISOString(),
      };
      logDecision(result);
      return result;
    }
  }

  // Scoring dynamique pour tout le reste
  const scores = {
    importance:  overrides.importance  ?? scoreAxis(task, "importance"),
    sensitivity: overrides.sensitivity ?? scoreAxis(task, "sensitivity"),
    complexity:  overrides.complexity  ?? scoreAxis(task, "complexity"),
  };

  const total = scores.importance + scores.sensitivity + scores.complexity;

  let model, reason;

  if (total <= 4) {
    model  = MODELS.ULTRA_LIGHT;
    reason = "Tâche ultra légère — Haiku suffisant";
  } else if (total <= 6) {
    model  = MODELS.LIGHT;
    reason = "Tâche légère — gpt-4o-mini suffisant";
  } else if (total <= 8) {
    model  = MODELS.MEDIUM;
    reason = "Tâche intermédiaire — gpt-4o recommandé";
  } else if (total <= 11) {
    model  = MODELS.SMART;
    reason = "Tâche créative/analyse — claude-sonnet recommandé";
  } else {
    model  = MODELS.HEAVY;
    reason = "Tâche critique/code — claude-opus requis";
  }

  const result = { model, scores, total, reason, task: task.slice(0, 100), timestamp: new Date().toISOString() };
  logDecision(result);
  return result;
}

function logDecision(result) {
  try {
    const fs   = require("fs");
    const path = require("path");
    const logPath = path.join(
      process.env.OPENCLAW_WORKSPACE_DIR || "/home/node/.openclaw/workspace",
      "state", "router-log.jsonl"
    );
    fs.appendFileSync(logPath, JSON.stringify(result) + "\n");
  } catch (e) {}
}

const TASK_PRESETS = {
  // Haiku
  notify:        () => routeTask("notifier",         { importance: 1, sensitivity: 1, complexity: 1 }),
  email_triage:  () => routeTask("trier emails",     { importance: 2, sensitivity: 1, complexity: 1 }),
  summarize:     () => routeTask("résumé simple",    { importance: 1, sensitivity: 1, complexity: 2 }),
  support:       () => routeTask("répondre support", { importance: 2, sensitivity: 1, complexity: 1 }),
  // GPT-4o-mini
  scraping:      () => routeTask("scraper sources",  { importance: 2, sensitivity: 1, complexity: 2 }),
  classify:      () => routeTask("classifier",       { importance: 2, sensitivity: 2, complexity: 2 }),
  // GPT-4o
  email_draft:   () => routeTask("rédiger draft email", { importance: 3, sensitivity: 3, complexity: 2 }),
  // Sonnet
  copywriting:   () => routeTask("rédiger post copywriting"),
  analysis:      () => routeTask("analyser stratégie"),
  publish:       () => routeTask("publier twitter",  { importance: 4, sensitivity: 3, complexity: 2 }),
  // Opus — toujours
  code_generate: () => routeTask("générer un script code"),
  code_review:   () => routeTask("déboguer le code"),
  self_improve:  () => routeTask("auto-amélioration code"),
};

module.exports = { routeTask, TASK_PRESETS, MODELS };
