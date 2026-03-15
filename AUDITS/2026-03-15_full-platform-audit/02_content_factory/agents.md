# agents.md — Inventaire des agents Content Factory

**Date** : 2026-03-15
**Scope** : Tous les agents dans `workspace/agents/` (content + trading legacy)

---

## Agents Content (actifs)

### 1. ANALYST (YouTube Intelligence)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Veille concurrentielle YouTube crypto — analyse 6 chaînes (3 FR, 3 EN) | [OBSERVÉ] |
| Inputs | YouTube Data API v3 (search, videos) | [OBSERVÉ] |
| Outputs | Rapports daily/weekly/monthly dans `agents/analyst/reports/`, références dans `agents/analyst/references/` | [OBSERVÉ] |
| LLM | `claude-sonnet-4-20250514` | [OBSERVÉ] |
| Coût estimé | ~0.01-0.05$/appel (analyse courte) | [DÉDUIT] |
| State lus | `references/top_performers.json`, `references/titles.json` | [OBSERVÉ] |
| State écrits | `reports/daily/YYYY-MM-DD.json`, `references/top_performers.json` | [OBSERVÉ] |
| Fréquence | Daily (08:00), Weekly (dim 20:00), Monthly (1er du mois) | [OBSERVÉ] |
| Dépendances | YouTube API key (`YOUTUBE_API_KEY`) | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] — structure de fichiers peuplée |

### 2. SCRAPER (Veille RSS)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Collecte 6 flux RSS crypto, déduplication, traduction EN→FR | [OBSERVÉ] |
| Inputs | RSS feeds (CoinTelegraph, CoinDesk, Bitcoin Magazine, The Defiant, Cryptoast, JournalDuCoin) | [OBSERVÉ] |
| Outputs | `intel/DAILY-INTEL.md`, `intel/data/YYYY-MM-DD.json`, notification Telegram | [OBSERVÉ] |
| LLM | `claude-haiku-4-5-20251001` (traduction titres, 60 tokens max) | [OBSERVÉ] |
| Coût estimé | ~0.001$/article traduit × 20 articles = ~0.02$/jour | [DÉDUIT] |
| State lus | — | |
| State écrits | `intel/DAILY-INTEL.md`, `intel/data/YYYY-MM-DD.json`, `state/waiting_selection.json` | [OBSERVÉ] |
| Fréquence | 1×/jour (19:15 UTC via cron) | [OBSERVÉ] |
| Dépendances | → COPYWRITER (consomme DAILY-INTEL.md) ; Telegram Bot | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] — cron vérifié, fichiers intel/data/ peuplés |

### 3. COPYWRITER (Rédaction)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Rédige les posts Twitter dans la voix CryptoRizon (style Ogilvy/Halbert) | [OBSERVÉ] |
| Inputs | Articles sélectionnés par Daniel + `intel/DAILY-INTEL.md` | [OBSERVÉ] |
| Outputs | Drafts Twitter validés, logs dans `memory/YYYY-MM-DD.md` | [OBSERVÉ] |
| LLM | `claude-sonnet-4-5` / `claude-sonnet-4-6` (1500 tokens max) | [OBSERVÉ] |
| Coût estimé | ~0.02-0.10$/post (Sonnet, ~1000 tokens I/O) | [DÉDUIT] |
| State lus | `intel/DAILY-INTEL.md`, `preferences.md` | [OBSERVÉ] |
| State écrits | `memory/YYYY-MM-DD.md` | [OBSERVÉ] |
| Fréquence | On-demand (sélection Daniel via Telegram) | [OBSERVÉ] |
| Dépendances | ← SCRAPER (source) ; → PUBLISHER (publication) | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] — logique intégrée dans poller.js |

### 4. PUBLISHER (Publication multi-canal)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Publie sur Twitter @CryptoRizon + Telegram canal après validation | [OBSERVÉ] |
| Inputs | Drafts validés (bouton "Publish" Telegram) | [OBSERVÉ] |
| Outputs | Tweets publiés, logs dans `agents/publisher/memory/YYYY-MM-DD.md` | [OBSERVÉ] |
| LLM | `gpt-4o-mini` (tâche technique de publication) | [OBSERVÉ] |
| Coût estimé | ~0.001$/publication (léger) | [DÉDUIT] |
| State lus | `state/drafts.json` | [OBSERVÉ] |
| State écrits | `agents/publisher/memory/YYYY-MM-DD.md`, `state/content_publish_history.json` | [OBSERVÉ] |
| Fréquence | On-demand (après validation humaine) | [OBSERVÉ] |
| Dépendances | ← COPYWRITER ; Twitter API (OAuth 1.0a), Telegram Bot API | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] — twitter.js fonctionnel |

### 5. EMAIL (Tri email)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Tri et résumé des emails (tutorizonofficiel@gmail.com, khuddan@gmail.com) | [OBSERVÉ] |
| Inputs | Emails non lus (Gmail API) | [OBSERVÉ] |
| Outputs | Rapport prioritaire Telegram, brouillons de réponse pour score ≥4 | [OBSERVÉ] |
| LLM | `gpt-4o-mini` (tri) + `claude-sonnet-4-5` (brouillons) | [OBSERVÉ] |
| Coût estimé | ~0.01-0.05$/jour | [DÉDUIT] |
| State écrits | `memory/YYYY-MM-DD.md`, `preferences.md` | [OBSERVÉ] |
| Fréquence | Continue (polling) | [OBSERVÉ] |
| Dépendances | Gmail API | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] — template preferences.md existe |

### 6. BUILDER (Auto-amélioration)

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Génère et déploie de nouveaux skills, modifications de code | [OBSERVÉ] |
| Inputs | Instructions Daniel via Telegram | [OBSERVÉ] |
| Outputs | Diffs pour approbation, code déployé dans `skills_custom/` | [OBSERVÉ] |
| LLM | `claude-opus-4-6` (génération de code) | [OBSERVÉ] |
| Coût estimé | ~0.50-2.00$/intervention (Opus, tâches complexes) | [DÉDUIT] |
| State écrits | `memory/YYYY-MM-DD.md`, `preferences.md` | [OBSERVÉ] |
| Fréquence | On-demand | [OBSERVÉ] |
| Dépendances | Telegram API, Claude API | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] — agent infrastructure central |

---

## Agents Trading (dans agents/ — dormants)

Ces agents sont la partie JS de la Trading Factory. Ils ne font PAS partie de la Content Factory mais partagent le répertoire `agents/`.

### 7. LEARNER

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Analyse post-mortem des trades, détection de patterns | [OBSERVÉ] |
| LLM | Aucun (rules-based) | [OBSERVÉ] |
| State | `memory/state.json` : 0 runs, patterns vides, last_run_ts=0 | [OBSERVÉ] |
| Statut | **DORMANT** | [OBSERVÉ] — state.json confirme 0 exécutions |

### 8. NEWS_SCORING

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Scoring de fiabilité des news, filtrage anti-manipulation | [OBSERVÉ] |
| LLM | Aucun (scoring déterministe) | [OBSERVÉ] |
| State | `memory/state.json` : 0 runs, dedup_hashes vides, last_run_ts=0 | [OBSERVÉ] |
| Statut | **DORMANT** | [OBSERVÉ] |

### 9. PERFORMANCE_ANALYST

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Comptabilité daily des performances trading, alertes drawdown | [OBSERVÉ] |
| LLM | Aucun (calculs quantitatifs) | [OBSERVÉ] |
| State | `memory/state.json` : 0 runs, last_reports vide | [OBSERVÉ] |
| Statut | **DORMANT** | [OBSERVÉ] |

### 10. STRATEGY_TUNER

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Optimisation hebdomadaire des paramètres de stratégies | [OBSERVÉ] |
| LLM | Aucun (rules-based) | [OBSERVÉ] |
| State | `memory/state.json` : 0 runs, pending_suggestions vide | [OBSERVÉ] |
| Statut | **DORMANT** | [OBSERVÉ] |

### 11. TRADE_GENERATOR

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Génération de signaux et propositions de trades | [OBSERVÉ] |
| LLM | Aucun (règles de confluence) | [OBSERVÉ] |
| State | `memory/state.json` : 0 runs, cooldowns vides | [OBSERVÉ] |
| Statut | **DORMANT** | [OBSERVÉ] |

---

## Agents Trading — Exécution (dans agents/)

### 12. POLICY_ENGINE

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Validateur déterministe de règles pour approbation d'ordres | [OBSERVÉ] |
| LLM | Aucun (zero-cost) | [OBSERVÉ] |
| Fréquence | Poll 30s + 5s jitter | [OBSERVÉ] |
| Statut | **INCONNU** — pas de state.json trouvé | [OBSERVÉ] |

### 13. TRADING_ORCHESTRATOR

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Corrélation d'ordres et routage vers exécution | [OBSERVÉ] |
| LLM | Aucun (state machine) | [OBSERVÉ] |
| Fréquence | Poll 10s + 2s jitter | [OBSERVÉ] |
| Statut | **INCONNU** — pas de state.json trouvé | [OBSERVÉ] |

---

## Agents Whale Monitoring (dans agents/)

### 14. WHALE_FEED

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Collecte de transferts whale (Etherscan API) | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Fréquence | Horaire (3600s) | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] — Sprint 1 implémenté |

### 15. WHALE_ANALYZER

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Interprétation des signaux whale, scoring [-1.0, +1.0] | [OBSERVÉ] |
| LLM | Aucun (scoring déterministe) | [OBSERVÉ] |
| Fréquence | Horaire + 300s jitter | [OBSERVÉ] |
| Statut | **ACTIF** | [DÉDUIT] — Sprint 1 |

### 16. SYSTEM_WATCHDOG

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Rôle | Monitoring santé système, alertes Telegram (WARN/CRIT/RESOLVED) | [OBSERVÉ] |
| LLM | Aucun | [OBSERVÉ] |
| Fréquence | Continu + résumé daily 08:00 UTC | [OBSERVÉ] |
| Statut | **ACTIF** | [OBSERVÉ] — cron */15min vérifié |

---

## Tableau récapitulatif

| Agent | Catégorie | Statut | LLM | Fréquence | Coût estimé/jour |
|-------|-----------|--------|-----|-----------|------------------|
| ANALYST | Content | ACTIF | claude-sonnet-4 | Daily | ~0.05$ |
| SCRAPER | Content | ACTIF | claude-haiku-4-5 | Daily | ~0.02$ |
| COPYWRITER | Content | ACTIF | claude-sonnet-4-5/4-6 | On-demand | ~0.10-0.50$ |
| PUBLISHER | Content | ACTIF | gpt-4o-mini | On-demand | ~0.01$ |
| EMAIL | Content | ACTIF | gpt-4o-mini + sonnet | Continu | ~0.05$ |
| BUILDER | Content | ACTIF | claude-opus-4-6 | On-demand | ~0-2.00$ |
| LEARNER | Trading | DORMANT | Aucun | — | 0$ |
| NEWS_SCORING | Trading | DORMANT | Aucun | — | 0$ |
| PERFORMANCE_ANALYST | Trading | DORMANT | Aucun | — | 0$ |
| STRATEGY_TUNER | Trading | DORMANT | Aucun | — | 0$ |
| TRADE_GENERATOR | Trading | DORMANT | Aucun | — | 0$ |
| POLICY_ENGINE | Trading | INCONNU | Aucun | — | 0$ |
| TRADING_ORCHESTRATOR | Trading | INCONNU | Aucun | — | 0$ |
| WHALE_FEED | Data | ACTIF | Aucun | Horaire | 0$ |
| WHALE_ANALYZER | Data | ACTIF | Aucun | Horaire | 0$ |
| SYSTEM_WATCHDOG | Infra | ACTIF | Aucun | */15min | 0$ |

**Coût LLM estimé Content Factory** : ~0.25-2.75$/jour [DÉDUIT]
