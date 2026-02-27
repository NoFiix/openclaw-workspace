const { routeTask, TASK_PRESETS } = require("./router");

console.log("=== TEST ROUTER ===\n");

const tests = [
  "notifier Daniel d'un événement",
  "trier mes emails",
  "résumer les news du jour",
  "scraper les sources crypto",
  "rédiger un post twitter copywriting percutant",
  "publier sur Twitter",
  "analyser les données de performance",
  "générer un script pour automatiser le scraping",
  "déboguer le code du skill publisher",
];

for (const task of tests) {
  const result = routeTask(task);
  console.log(`📋 "${task}"`);
  console.log(`   Score : ${result.scores.importance}+${result.scores.sensitivity}+${result.scores.complexity} = ${result.total}`);
  console.log(`   Modèle : ${result.model}`);
  console.log(`   Raison : ${result.reason}\n`);
}

console.log("=== PRESETS ===\n");
for (const [name, fn] of Object.entries(TASK_PRESETS)) {
  const r = fn();
  console.log(`⚡ ${name.padEnd(15)} → ${r.model.padEnd(35)} (score: ${r.total})`);
}
