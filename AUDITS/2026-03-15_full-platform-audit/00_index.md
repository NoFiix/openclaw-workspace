# 00_index.md — Full Platform Audit 2026-03-15

**Status** : `DISCOVERY_DONE` (Phase 0 + Phase 1 + Phase 2 + Phase 3 complete)
**Date** : 2026-03-15
**Auditeur** : Claude Code (claude-sonnet-4-6)
**Scope** : Environnement global OpenClaw (VPS srv1425899)

---

## Sommaire exécutif

L'environnement OpenClaw tourne sur un VPS Ubuntu 22.04 (8 Go RAM, 97 Go disque).
Trois systèmes coexistent : Content Factory (scraping/publication), Trading Factory (JS, crypto spot), et POLY_FACTORY (Python, prediction markets).

**Constat principal** : `poly-orchestrator` consomme 98% CPU en continu (boucle de polling à 2s sans yield efficace). Le système fonctionne mais avec un overhead significatif.

---

## Phases

| Phase | Status | Fichiers |
|-------|--------|----------|
| Phase 0 — Structure + snapshots | DONE | `README.md`, `CHANGELOG.md`, `00_index.md`, `99_appendices/*` |
| Phase 1 — Environnement global | DONE | `01_global_environment/*` (5 fichiers) |
| Phase 2 — Content Factory | DISCOVERY_DONE | `02_content_factory/*` (6 fichiers) |
| Phase 3 — Trading Factory | DISCOVERY_DONE | `03_trading_factory/*` (8 fichiers) |
| Phase 4 — POLY_FACTORY | TODO | `04_poly_factory/` |
| Phase 5 — Composants partagés | TODO | `05_shared_components/` |
| Phase 6 — Analyse cross-system | TODO | `06_cross_system_analysis/` |

---

## Conflits détectés

| # | Conflit | Sévérité | Détails |
|---|---------|----------|---------|
| C-01 | `poly-orchestrator` à 98% CPU | HIGH | Boucle polling 2s sans sleep efficace quand le tick prend ~0ms. Voir `01_global_environment/process_map.md` |
| C-02 | Double lancement `trading/poller.js` | MEDIUM | Lancé par `@reboot` cron ET par PM2 `trading-poller`. Risque de duplication de données. Voir `01_global_environment/process_map.md` |
| C-03 | Deux systèmes de trading indépendants | MEDIUM | TRADING_FACTORY (JS) et POLY_FACTORY (Python) avec state dirs séparés, pas de coordination. Voir `01_global_environment/filesystem_map.md` |
| C-04 | hourly_scraper vs scraper : dedup non partagée | LOW | Deux mécanismes de dedup différents sur les mêmes RSS feeds. Voir `02_content_factory/triggers_cron.md` |
| C-05 | Noms confusants : poller.js × 2 | LOW | Content poller et trading poller même nom, chemins différents. Voir `02_content_factory/triggers_cron.md` |
| C-06 | Content poller log dans container Docker | MEDIUM | Log perdu si container recréé. Voir `02_content_factory/triggers_cron.md` |
| C-07 | KILL_SWITCH_GUARDIAN défaillant (27k erreurs) | CRITICAL | Agent de sécurité critique avec 115% taux d'erreur. Kill switch jamais trippé malgré des conditions potentielles. Voir `03_trading_factory/risks.md` R-01 |
| C-08 | Double cleanup bus_cleanup_trading.js | LOW | Même script exécuté 2× par jour (02:00 + 03:30). Idempotent mais confusant. Voir `03_trading_factory/triggers_cron.md` |
| C-09 | Human approval gate non fonctionnel | HIGH | 95 ordres HUMAN_APPROVAL_REQUIRED → tous EXPIRED (TTL 600s). Aucun mécanisme d'approbation. Voir `03_trading_factory/risks.md` R-03 |

---

## Inconnues majeures

| # | Inconnu | Impact |
|---|---------|--------|
| U-01 | Credentials Polymarket (API key/secret) : validité non vérifiable | TYPE_1 — blocage du trading live |
| U-02 | `WALLET_PRIVATE_KEY` absent du `.env` POLY_FACTORY | TYPE_1 — `place_order()` crash si appelé |
| U-03 | Monitoring/alerting externe : aucun système détecté | TYPE_2 — pannes silencieuses |
| U-04 | Backup strategy : aucune politique visible | TYPE_2 — risque de perte de données |
| U-05 | Content poller : pas de supervision PM2, crash silencieux possible | TYPE_2 — pipeline publication bloqué |
| U-06 | Token tracking LLM content : coûts invisibles | TYPE_2 — budget non monitoré |
| U-07 | youtube_analyzer.js : déclencheur exact inconnu | TYPE_3 — pas dans le crontab |
| U-08 | SYSTEM_WATCHDOG : monitore-t-il le content poller ? | TYPE_2 — détection panne incertaine |
| U-09 | Cause exacte des 27 399 erreurs KILL_SWITCH_GUARDIAN | TYPE_1 — sécurité capitale non fonctionnelle |
| U-10 | PREDICTOR : consommateur prévu ? Fonctionnalité intentionnellement orpheline ? | TYPE_3 — gaspillage ressources si orphelin |
| U-11 | Transition testnet → mainnet : plan de migration ? | TYPE_2 — pas d'executor mainnet, pas de plan documenté |

---

## Fichiers créés

### Phase 0
- `AUDITS/README.md`
- `AUDITS/CHANGELOG.md`
- `AUDITS/2026-03-15_full-platform-audit/00_index.md` (ce fichier)

### Phase 1 — `01_global_environment/`
- `env_inventory.md` — inventaire des composants
- `process_map.md` — carte des processus avec conflits
- `integrations_externes.md` — services externes
- `filesystem_map.md` — carte du filesystem
- `unknowns_and_gaps.md` — inconnues et lacunes

### Phase 2 — `02_content_factory/`
- `summary.md` — mission, statut, points de fragilité
- `agents.md` — inventaire des 16 agents (6 content actifs, 5 trading dormants, 5 infra)
- `pipeline_flows.md` — flux horaire + quotidien, ordre d'exécution, points de blocage
- `triggers_cron.md` — 3 cron jobs, scripts, logs, conflits
- `risks.md` — 11 risques identifiés (0 critique, 2 élevé, 6 moyen, 3 faible)
- `recommendations.md` — 11 recommandations (2 P1, 3 P2, 4 P3, 2 P4)

### Phase 3 — `03_trading_factory/`
- `summary.md` — mission, statut, kill switch, capital, LLM costs, top 5 fragilités
- `agents.md` — inventaire des 24 agents (4 data, 3 signal, 2 intel, 3 risk, 3 exec, 3 pub, 4 learning, 2 monitoring)
- `bus_events.md` — 18 topics JSONL, flux ASCII, topics orphelins, analyse résilience
- `pipeline_flows.md` — pipeline prix→exécution, latences, conditions, modes d'échec
- `triggers_cron.md` — poller, conflit C-02, 5 cron jobs, agents sur/sous-schedulés
- `risks.md` — 21 risques (1 critique, 4 élevé, 7 moyen, 6 faible) en 4 sections
- `recommendations.md` — 17 recommandations (3 P0, 4 P1, 4 P2, 3 P3, 3 P4)
- `trading_system_map.md` — diagramme global, composants CORE, checklist troubleshooting

### Appendices — `99_appendices/`
- `pm2_status.txt`
- `crontab.txt`
- `docker_ps.txt`
- `processes.txt`
- `md_files.txt`
- `json_files.txt`
- `ports.txt`
