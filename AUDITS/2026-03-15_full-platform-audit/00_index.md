# 00_index.md — Full Platform Audit 2026-03-15

**Status** : `DISCOVERY_DONE` (Phase 0 + Phase 1 complete)
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
| Phase 2 — Content Factory | TODO | `02_content_factory/` |
| Phase 3 — Trading Factory | TODO | `03_trading_factory/` |
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

---

## Inconnues majeures

| # | Inconnu | Impact |
|---|---------|--------|
| U-01 | Credentials Polymarket (API key/secret) : validité non vérifiable | TYPE_1 — blocage du trading live |
| U-02 | `WALLET_PRIVATE_KEY` absent du `.env` POLY_FACTORY | TYPE_1 — `place_order()` crash si appelé |
| U-03 | Monitoring/alerting externe : aucun système détecté | TYPE_2 — pannes silencieuses |
| U-04 | Backup strategy : aucune politique visible | TYPE_2 — risque de perte de données |

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

### Appendices — `99_appendices/`
- `pm2_status.txt`
- `crontab.txt`
- `docker_ps.txt`
- `processes.txt`
- `md_files.txt`
- `json_files.txt`
- `ports.txt`
