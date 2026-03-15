# CHANGELOG — Audits OpenClaw

## 2026-03-15 — Full Platform Audit — Phase 5 Shared Components

- **Phase 5** : audit complet des composants partagés et transverses (7 fichiers dans `05_shared_components/`)
- **SYSTEM_WATCHDOG** : couvre 80% du système (21 agents trading, content, POLY, infra) mais n'est pas lui-même supervisé — SPOF critique
- **Token monitoring** : Trading tracké ✅, POLY partiellement (fichier vide), Content Factory **non tracké** (~30% des coûts LLM invisibles)
- **Telegram** : 4 bots, 14 fichiers émetteurs, canal TRADER surchargé (8 agents), aucun fallback
- **Dashboard** : Express.js 17 endpoints + React 8 pages, auth x-api-key, **HTTP sans TLS** (API key en clair)
- **Content scripts** : 9 scripts JS (3 actifs, 4 modules, 2 dormants), cleanup.js non schedulé, router.js orphelin
- **Infrastructure** : POLY_FACTORY/.env **world-readable (664)** avec wallet private key, ports Docker exposés sans firewall, pas de UFW, backups stales (12j)
- **Nouveaux conflits** : 4 (C-13 .env perms, C-14 HTTP sans TLS, C-15 watchdog SPOF, C-16 backups stales)
- **Nouvelles inconnues** : 3 (U-16 à U-18)
- **Points critiques** : .env 664 avec clés privées (P0 immédiat), pas de firewall (P0), HTTPS manquant (P1), backups (P1)

## 2026-03-15 — Full Platform Audit — Phase 4 POLY_FACTORY

- **Phase 4** : audit complet de POLY_FACTORY Python (8 fichiers dans `04_poly_factory/`)
- **Composants audités** : 46 (6 core, 5 feeds, 5 analysis, 9 strategies, 4 execution, 6 risk, 7 evaluation, 3 system, 3 connectors)
- **Bus topics** : 20 topics Python, 6 orphelins (dont `news:high_impact` sans producteur)
- **Bus saturation** : 70k events pending vs 22k processed (19 Mo), compaction insuffisante
- **Agents disabled** : 11 sur 19 (exec_router, binance_feed, msa, binance_sig, wallet_feed, wallet_tracker, data_validator, arb_scanner, latency_arb, brownian, pair_cost)
- **Trades** : **0 trades en 1.5 jours** — aucune stratégie n'a émis de `trade:signal`
- **CPU** : poly-orchestrator à **98%** (single-threaded + bus I/O thrashing)
- **Risques identifiés** : 21 (1 critique, 5 élevé, 6 moyen, 5 faible)
- **Recommandations** : 19 (3 P0, 4 P1, 5 P2, 3 P3, 4 P4)
- **Nouveaux conflits** : 3 (C-10 agents disabled, C-11 bus backlog/CPU, C-12 news_strat zombie)
- **Nouvelles inconnues** : 4 (U-12 à U-15)
- **Point critique** : exec_router DISABLED → pipeline structurellement mort, aucun trade ne peut être exécuté même si un signal passait les 7 filtres

## 2026-03-15 — Full Platform Audit — Phase 3 Trading Factory

- **Phase 3** : audit complet de la Trading Factory JS (8 fichiers dans `03_trading_factory/`)
- **Agents audités** : 24 (4 data feeds, 3 signal gen, 2 intel, 3 risk/policy, 3 orchestration/exec, 3 publication, 4 learning, 2 monitoring)
- **Bus topics** : 18 topics JSONL, ~170 Mo, 1 topic orphelin (PREDICTOR)
- **Risques identifiés** : 21 (1 critique, 4 élevé, 7 moyen, 6 faible)
- **Recommandations** : 17 (3 P0, 4 P1, 4 P2, 3 P3, 3 P4)
- **Nouveaux conflits** : 3 (C-07 kill switch défaillant, C-08 double cleanup, C-09 human approval mort)
- **Nouvelles inconnues** : 3 (U-09 à U-11)
- **Point critique** : KILL_SWITCH_GUARDIAN a 27 399 erreurs (115% taux d'erreur) — sécurité capitale non fonctionnelle

## 2026-03-15 — Full Platform Audit — Phase 2 Content Factory

- **Phase 2** : audit complet de la Content Factory (6 fichiers dans `02_content_factory/`)
- **Agents audités** : 16 (6 content actifs, 5 trading dormants, 5 infra/data)
- **Risques identifiés** : 11 (0 critique, 2 élevé, 6 moyen, 3 faible)
- **Recommandations** : 11 (2 P1, 3 P2, 4 P3, 2 P4)
- **Nouveaux conflits** : 3 (C-04, C-05, C-06)
- **Nouvelles inconnues** : 4 (U-05 à U-08)

## 2026-03-15 — Full Platform Audit (Phase 0 + Phase 1)

- **Créé** : structure complète de l'audit (`2026-03-15_full-platform-audit/`)
- **Phase 0** : inventaire brut (commandes système, snapshots)
- **Phase 1** : analyse globale de l'environnement (5 fichiers dans `01_global_environment/`)
- **Appendices** : 7 snapshots bruts dans `99_appendices/`
- **Conflits détectés** : 3 (voir `00_index.md`)
- **Inconnues majeures** : 4 (voir `01_global_environment/unknowns_and_gaps.md`)

### Fix 2026-03-15 — Conflit C-02 résolu
- trading-poller retiré de PM2
- Poller trading relancé dans Docker container
- KILL_SWITCH_GUARDIAN et POLY_TRADING_PUBLISHER ont maintenant accès aux variables Telegram

### Fixes 2026-03-15
**C-02 résolu** — trading-poller retiré de PM2, relancé dans Docker
**R-01 découvert** — content poller était mort (Terminated), relancé manuellement
**Action requise** — les deux pollers doivent être supervisés pour éviter les crashs silencieux
