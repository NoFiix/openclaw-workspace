# token_monitoring.md — Monitoring des coûts LLM

**Date** : 2026-03-15
**Scope** : GLOBAL_TOKEN_TRACKER, GLOBAL_TOKEN_ANALYST, poly_log_tokens.py

---

## Résumé exécutif

Le tracking LLM repose sur 3 composants : `poly_log_tokens.py` (écriture POLY), `GLOBAL_TOKEN_TRACKER` (agrégation horaire), `GLOBAL_TOKEN_ANALYST` (analyse IA bi-hebdomadaire). Le système couvre le Trading Factory et POLY_FACTORY mais **ignore complètement la Content Factory** (hourly_scraper, poller, scraper). [OBSERVÉ]

---

## Composants

### 1. poly_log_tokens.py

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Logger chaque appel LLM des agents POLY vers JSONL | [OBSERVÉ] |
| Fichier output | `POLY_FACTORY/state/llm/token_costs.jsonl` | [OBSERVÉ] |
| Taille actuelle | **0 bytes** (vide) | [OBSERVÉ] |
| Modèles pricés | Sonnet 4-6 ($3/$15), Haiku 4-5 ($0.80/$4), Opus 4-6 ($15/$75) | [OBSERVÉ] |
| Champ `system` | `"polymarket"` (constant) | [OBSERVÉ] |
| Gestion erreurs | Silencieuse (try/except pass) — ne casse jamais l'agent | [OBSERVÉ] |

**Pourquoi vide ?** Les agents POLY qui utilisent des LLM (opp_scorer via Sonnet, no_scanner via Haiku) appellent `log_tokens()` après chaque réponse. Mais opp_scorer et no_scanner étaient disabled (C-10), et même après réactivation, ils n'ont pas encore reçu de résolutions nécessitant un appel LLM. [DÉDUIT]

### 2. GLOBAL_TOKEN_TRACKER

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Agrège les coûts des 2 systèmes + rapport Telegram quotidien 20h UTC | [OBSERVÉ] |
| Fréquence | Horaire (schedulé par poller trading) | [OBSERVÉ] |
| Sources | `state/learning/token_costs.jsonl` (trading) + `POLY_FACTORY/state/llm/token_costs.jsonl` (POLY) | [OBSERVÉ] |
| Output | `state/learning/token_summary.json` | [OBSERVÉ] |
| Telegram | `TRADER_TELEGRAM_BOT_TOKEN` + `TRADER_TELEGRAM_CHAT_ID` | [OBSERVÉ] |
| Rapport | Top 5 agents, breakdown par système, projection mensuelle | [OBSERVÉ] |
| Dédup | `token_tracker_sent.json` empêche les envois doubles | [OBSERVÉ] |

### 3. GLOBAL_TOKEN_ANALYST

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Analyse IA des coûts + recommandations d'optimisation | [OBSERVÉ] |
| Fréquence | Lundi + Jeudi à 08h UTC | [OBSERVÉ] |
| LLM | Claude Sonnet (`claude-sonnet-4-20250514`) | [OBSERVÉ] |
| Input | `token_summary.json` (créé par TRACKER) | [OBSERVÉ] |
| Output | `state/learning/token_recommendations.json` | [OBSERVÉ] |
| Telegram | `TRADER_TELEGRAM_BOT_TOKEN` + `TRADER_TELEGRAM_CHAT_ID` | [OBSERVÉ] |
| Coût propre | ~$0.01-0.02 par exécution (2×/semaine = ~$0.16/mois) | [DÉDUIT] |

---

## Ce qui est tracké vs ce qui ne l'est pas

| Système | Tracké ? | Détails | Tag |
|---------|----------|---------|-----|
| Trading Factory agents | ✅ Oui | Tous les agents LLM loggent via `logTokens.js` | [OBSERVÉ] |
| POLY_FACTORY agents | ⚠️ Partiellement | `poly_log_tokens.py` existe mais fichier vide (0 bytes) — agents LLM pas encore exécutés | [OBSERVÉ] |
| Content Factory | ❌ **Non** | hourly_scraper (Haiku+Sonnet), scraper (Haiku), poller (Sonnet) — **aucun logTokens** | [OBSERVÉ] |
| GLOBAL_TOKEN_ANALYST | ❌ Non | Son propre appel Sonnet n'est pas loggé | [DÉDUIT] |
| NEWS_SCORING | ✅ Oui | Tracké via logTokens.js côté trading | [DÉDUIT] |

---

## Fichiers JSONL sources et taille actuelle

| Fichier | Taille | Lignes estimées | Tag |
|---------|--------|----------------|-----|
| `state/learning/token_costs.jsonl` (trading) | ~1.6 Ko | ~20-30 lignes | [OBSERVÉ] |
| `POLY_FACTORY/state/llm/token_costs.jsonl` | **0 bytes** | 0 | [OBSERVÉ] |

---

## Coût estimé total par jour

| Système | Source | Coût/jour estimé | Tag |
|---------|--------|-----------------|-----|
| Trading Factory | token_summary.json | ~$0.50-1.30/jour | [DÉDUIT] |
| POLY_FACTORY | Calcul théorique (opp_scorer Sonnet + no_scanner Haiku) | ~$0.28/jour (quand actif) | [DÉDUIT] |
| Content Factory | **Non tracké** — estimation: ~17 appels Sonnet/jour + Haiku tris | ~$0.30-0.50/jour | [DÉDUIT] |
| **Total estimé** | — | **~$1.10-2.10/jour (~$33-63/mois)** | [DÉDUIT] |

---

## Dashboard Costs.jsx

| Aspect | Statut | Tag |
|--------|--------|-----|
| Affichage coûts trading | ✅ Fonctionne (lit token_costs.jsonl trading) | [OBSERVÉ] |
| Affichage coûts POLY | ⚠️ Montre 0 (fichier vide) | [OBSERVÉ] |
| Affichage coûts content | ❌ **Absent** — non tracké | [OBSERVÉ] |
| Breakdown par agent | ✅ | [OBSERVÉ] |
| Breakdown par modèle | ✅ (pie chart) | [OBSERVÉ] |
| Projection mensuelle | ✅ | [OBSERVÉ] |
| Sources distinctes (trading vs POLY) | ⚠️ Le tracker agrège mais le dashboard lit seulement le fichier trading + agrégats | [DÉDUIT] |

---

## Rotation des fichiers

| Fichier | Rotation automatique | Risque | Tag |
|---------|---------------------|--------|-----|
| `token_costs.jsonl` (trading) | **Aucune** | Croissance lente (~1.6 Ko actuel) mais illimitée | [OBSERVÉ] |
| `token_costs.jsonl` (POLY) | **Aucune** | Vide actuellement, croissance ~100 lignes/jour quand actif | [OBSERVÉ] |
| `token_summary.json` | Écrasé à chaque run (overwrite) | Pas de risque | [OBSERVÉ] |
| `token_recommendations.json` | Écrasé à chaque run | Pas de risque | [OBSERVÉ] |

**Risque** : `token_costs.jsonl` trading n'a pas de rotation. À ~30 lignes/jour, le fichier atteindra ~11k lignes/an (~500 Ko). Risque faible mais non nul sur longue période. [DÉDUIT]

---

## Lacunes et recommandations

| # | Lacune | Impact | Recommandation | Priorité |
|---|--------|--------|---------------|----------|
| 1 | **Content Factory non trackée** (~30% des coûts LLM) | Budget invisible | Ajouter `logTokens()` dans hourly_scraper.js, scraper.js, poller.js | P1 |
| 2 | POLY token_costs.jsonl vide | Coûts POLY invisibles | Sera résolu quand les agents LLM commenceront à émettre des signaux | P2 |
| 3 | GLOBAL_TOKEN_ANALYST ne tracke pas son propre coût | Sous-estimation ~$0.16/mois | Ajouter self-tracking | P3 |
| 4 | Pas de rotation token_costs.jsonl | Croissance illimitée | Ajouter purge >90 jours dans cleanup.js | P3 |
| 5 | Pas d'alerte budget (seuil quotidien) | Explosion non détectée | Ajouter dans SYSTEM_WATCHDOG : alerte si coût_daily > $5 | P2 |
