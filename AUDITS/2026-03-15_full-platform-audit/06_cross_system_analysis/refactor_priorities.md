# refactor_priorities.md — Plan de refactoring priorisé

**Date** : 2026-03-15
**Scope** : Toutes les corrections et améliorations identifiées, classées par priorité

---

## Résumé exécutif

L'audit complet a identifié **16 conflits** (C-01 à C-16), **18 inconnues** (U-01 à U-18), et **~80 recommandations** dans les 5 phases. Ce plan les consolide en **5 niveaux de priorité**. Les corrections P0 concernent la sécurité du capital et des secrets (3 items). Les P1 sont des quick wins à fort impact (8 items). [DÉDUIT]

---

## P0 — Corrections immédiates (risque système ou capital)

| # | Action | Source | Effort | Statut | Tag |
|---|--------|--------|--------|--------|-----|
| P0-1 | **chmod 600 POLY_FACTORY/.env** — wallet private key world-readable | C-13 | 1 min | ⚠️ À faire | [OBSERVÉ] |
| P0-2 | **Activer UFW** — ports Docker exposés sur Internet | C-14, infra R-03/R-04 | 15 min (sudo) | ⚠️ Script prêt, nécessite sudo | [OBSERVÉ] |
| P0-3 | **Bind Docker ports 127.0.0.1** — UFW bypassé par Docker | infra R-03 | 5 min (sudo) | ⚠️ Commandes prêtes, nécessite sudo | [OBSERVÉ] |

**Note** : C-10 (agents disabled), C-11 (bus saturé) et U-13 (0 signaux) ont été **corrigés** lors de la session du 2026-03-15. [OBSERVÉ]

---

## P1 — Cette semaine (quick wins < 1h chacun)

| # | Action | Source | Effort | Statut | Tag |
|---|--------|--------|--------|--------|-----|
| P1-1 | **HTTPS via Let's Encrypt** sur nginx | C-14, dashboard R-01 | 30 min | À faire | [OBSERVÉ] |
| P1-2 | **Backup automatique quotidien** + offsite (rsync/S3) | C-16, infra R-05 | 2h | À faire | [OBSERVÉ] |
| P1-3 | **logTokens() dans Content Factory** (hourly_scraper, scraper, poller) | token R-04, content CC-01 | 2-3h | À faire | [OBSERVÉ] |
| P1-4 | **Diagnostiquer KILL_SWITCH_GUARDIAN** (27k erreurs, 115%) | C-07 | 1-3h | À faire | [OBSERVÉ] |
| P1-5 | **Scheduler cleanup.js** (cron hebdomadaire) | scripts R-01 | 15 min | À faire | [OBSERVÉ] |
| P1-6 | **Content poller dans PM2** (au lieu de @reboot) | content QW-01 | 15 min | À faire | [OBSERVÉ] |
| P1-7 | **Supprimer doublon bus_cleanup** (cron 02:00) | C-08 | 2 min | À faire | [OBSERVÉ] |
| P1-8 | **Désactiver ou réduire PREDICTOR** (11k runs orphelins) | trading P1-02 | 2 min | À faire | [OBSERVÉ] |

---

## P2 — Ce mois

| # | Action | Source | Effort | Statut | Tag |
|---|--------|--------|--------|--------|-----|
| P2-1 | **Séparer canaux Telegram** — au minimum 2 (CRIT, reste) | telegram R-01, shared_arch | 30 min | À faire | [OBSERVÉ] |
| P2-2 | **Rate limiting dashboard** (express-rate-limit) | dashboard R-02 | 30 min | À faire | [OBSERVÉ] |
| P2-3 | **Purger trading_intel_market_features.jsonl** (72 Mo) | infra R-07 | 15 min | À faire | [OBSERVÉ] |
| P2-4 | **Interface contract POLY ↔ Trading** (schema JSON pour fichiers lus en cross-system) | trading R-18/R-19 | 1h | À faire | [DÉDUIT] |
| P2-5 | **Bus deduplication JS** (set event_ids dans consumers) | trading R-06 | 2-3h | À faire | [DÉDUIT] |
| P2-6 | **Atomic writes** pour state files critiques (positions, pnl) | trading R-07 | 1-2h | À faire | [DÉDUIT] |
| P2-7 | **Fallback Anthropic API** (try/catch + alerte après 5 failures) | trading R-13 | 2h | À faire | [DÉDUIT] |
| P2-8 | **Implémenter human approval Telegram** (ou désactiver seuil $5k) | C-09 | 4-8h (ou 5 min pour disable) | À faire | [OBSERVÉ] |
| P2-9 | **Bridge news:high_impact** JS→Python | C-12 | 1-2h | À faire | [OBSERVÉ] |
| P2-10 | **Alerte budget token quotidien** (> $5/jour) dans watchdog | token R-05 | 30 min | À faire | [DÉDUIT] |

---

## P3 — Harmonisation architecture

| # | Action | Source | Effort | Statut | Tag |
|---|--------|--------|--------|--------|-----|
| P3-1 | **Documenter conventions** agent/bus/state dans reference partagé | trading P3-01 | 1h | À faire | [DÉDUIT] |
| P3-2 | **Évaluer news partagé** entre 3 systèmes (RSS → scoring unique) | trading R-21 | Investigation 2h | À faire | [DÉDUIT] |
| P3-3 | **Externaliser modèles LLM** dans config (plus de hardcode) | content CC-02 | 1h | À faire | [OBSERVÉ] |
| P3-4 | **Fix SYSTEM_WATCHDOG false positives** (vérifier via state files, pas docker ps) | trading P1-03 | 30 min | À faire | [OBSERVÉ] |
| P3-5 | **Rotation processed_events.jsonl POLY** (croissance illimitée) | file_ownership | 30 min | À faire | [OBSERVÉ] |
| P3-6 | **Health check HTTP pour poly-orchestrator** (endpoint santé) | gaps L-01 | 2h | À faire | [DÉDUIT] |

---

## P4 — Améliorations futures

| # | Action | Source | Effort | Statut | Tag |
|---|--------|--------|--------|--------|-----|
| P4-1 | **Créer MAINNET_EXECUTOR** (JS Trading) | trading P4-01 | 1-2 jours | À planifier | [DÉDUIT] |
| P4-2 | **Coordination cross-system** Trading ↔ POLY (risk partagé) | trading R-20 | 2-3 jours | À planifier | [DÉDUIT] |
| P4-3 | **Multi-process POLY** (asyncio ou multi-worker) pour réduire CPU | poly P0-02 | 4-8h | À planifier | [DÉDUIT] |
| P4-4 | **Secrets manager** (Vault, AWS SSM, ou au minimum gpg) | infra R-08 | 1 jour | À planifier | [DÉDUIT] |
| P4-5 | **Bot Telegram interactif** pour human approval (✅/❌) | trading P4-02 | 1-2 jours | À planifier | [DÉDUIT] |
| P4-6 | **Monitoring externe** (UptimeRobot, Healthchecks.io) pour VPS et services | U-03 | 1h | À planifier | [DÉDUIT] |

---

## Résumé par priorité

| Priorité | Items | Effort total estimé | Impact |
|----------|-------|-------------------|--------|
| **P0** | 3 | 20 min + sudo | Sécurité secrets et réseau |
| **P1** | 8 | ~8h | Stabilité, monitoring, quick wins |
| **P2** | 10 | ~15h | Robustesse, observabilité |
| **P3** | 6 | ~7h | Architecture, conventions |
| **P4** | 6 | ~6 jours | Évolution, production |
| **Total** | **33** | | |
