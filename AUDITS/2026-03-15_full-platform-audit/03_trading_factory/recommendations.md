# recommendations.md — Recommandations Trading Factory

**Date** : 2026-03-15
**Priorité** : P0 (immédiat/capital) → P1 (quick wins <1h) → P2 (next session) → P3 (harmonisation) → P4 (futur)

---

## P0 — Immédiates (sécurité + capital)

### P0-01 : Supprimer la ligne @reboot cron du trading poller

**Risque** : R-02 — double exécution agents, double ordres possibles, double coût LLM
**Action** : Supprimer la ligne `@reboot sleep 30 && docker exec -d openclaw-gateway-1 sh -c 'node poller.js'` du crontab. PM2 `trading-poller` gère déjà le poller avec auto-restart.
**Vérification** : `crontab -l | grep poller.js` → ne doit plus contenir la ligne trading
**Effort** : 5 min
**Impact** : Élimine le risque de double exécution, double coût LLM, double ordres.
**Priorité** : **P0**

### P0-02 : Diagnostiquer et corriger KILL_SWITCH_GUARDIAN

**Risque** : R-01 — kill switch inopérant (27 399 erreurs, 115% error rate)
**Action** :
1. Lire les 100 dernières lignes de `poller.log` filtrées sur KILL_SWITCH_GUARDIAN pour identifier l'erreur
2. Corriger le bug (probablement un fichier state manquant ou un import cassé)
3. Vérifier que le guardian écrit correctement `killswitch.json`
4. Tester le trip : simuler daily loss >3% → vérifier que TRIPPED
**Effort** : 1-3h
**Impact** : Restaure la dernière ligne de défense du système.
**Priorité** : **P0**

### P0-03 : Implémenter ou désactiver le seuil human approval

**Risque** : R-03 — 95 ordres HUMAN_APPROVAL_REQUIRED → tous EXPIRED
**Action** (choix A ou B) :
- **A** : Implémenter un bot Telegram d'approbation (bouton ✅/❌, TTL 10 min, fallback BLOCK)
- **B** : Temporairement augmenter le seuil à $50 000 (au-dessus du capital fictif $10k) pour ne jamais déclencher le gate non fonctionnel
**Effort** : A = 4-8h, B = 5 min
**Impact** : A = sécurité réelle. B = élimine le blocage factice (95 trades perdus).
**Priorité** : **P0**

---

## P1 — Quick wins (< 1h chacun)

### P1-01 : Supprimer le double cron bus_cleanup

**Risque** : R-09
**Action** : Supprimer la ligne `0 2 * * * ... bus_cleanup_trading.js` du crontab. Garder uniquement le run de 03:30.
**Effort** : 2 min
**Impact** : Clarté des logs, plus de confusion sur 2 runs.
**Priorité** : **P1**

### P1-02 : Désactiver ou réduire PREDICTOR

**Risque** : R-04
**Action** : Soit `enabled: false` dans le schedule, soit `every_seconds: 300` pour réduire le gaspillage. Output non consommé.
**Effort** : 2 min
**Impact** : Élimine 11k runs inutiles.
**Priorité** : **P1**

### P1-03 : Corriger les faux positifs SYSTEM_WATCHDOG

**Risque** : R-05
**Action** : Modifier `SYSTEM_WATCHDOG/handler.js` pour vérifier les agents via les fichiers state (mtime des `runs/*.json`) plutôt que via `docker ps` pour les processes PM2.
**Effort** : 30 min
**Impact** : Élimine 3 faux CRIT, restaure la confiance dans les alertes.
**Priorité** : **P1**

### P1-04 : Ajouter surveillance santé KILL_SWITCH_GUARDIAN dans watchdog

**Risque** : R-01 (détection)
**Action** : Dans SYSTEM_WATCHDOG, ajouter un check : si `runs/KILL_SWITCH_GUARDIAN/*.json` contient `"success": false` dans les 5 derniers runs → CRIT alert.
**Effort** : 30 min
**Impact** : Le watchdog détecte que le guardian est cassé, au lieu de ne vérifier que l'état du kill switch.
**Priorité** : **P1**

---

## P2 — Prochaine session (1-4h chacun)

### P2-01 : Ajouter déduplication bus (event_id)

**Risque** : R-06
**Action** : Chaque consommateur bus doit maintenir un set des derniers N event_ids traités (similaire au mécanisme POLY_FACTORY). Si event_id déjà vu → skip.
**Effort** : 2-3h (patch dans `_shared/busRead.js`)
**Impact** : Protection contre les events dupliqués, même avec C-02 résolu.
**Priorité** : **P2**

### P2-02 : Ajouter lock file pour écritures state critiques

**Risque** : R-07
**Action** : Implémenter un simple `fs.writeFileSync` avec `.tmp` + `rename` atomique pour `exec/positions.json`, `memory/pipeline_state.json`, `exec/daily_pnl.json`.
**Effort** : 1-2h
**Impact** : Élimine le risque de corruption par écritures concurrentes.
**Priorité** : **P2**

### P2-03 : Définir contrat d'interface POLY_FACTORY ↔ Trading Factory

**Risque** : R-18, R-19
**Action** : Documenter les fichiers state de POLY_FACTORY lus par POLY_TRADING_PUBLISHER et GLOBAL_TOKEN_TRACKER dans un fichier `references/poly_factory_interface.json` avec version + schema.
**Effort** : 1h
**Impact** : Détection précoce des breaking changes.
**Priorité** : **P2**

### P2-04 : Ajouter fallback pour l'API Anthropic

**Risque** : R-13
**Action** : Dans NEWS_SCORING et TRADE_GENERATOR, ajouter un try/catch qui :
1. Log l'erreur
2. Skip le cycle (pas de signal)
3. Publie une alerte `trading.ops.alert` (type: "llm_api_down")
4. Après 5 échecs consécutifs → signal dégradé au KILL_SWITCH_GUARDIAN
**Effort** : 2h
**Impact** : Détection explicite de la panne LLM au lieu du silence.
**Priorité** : **P2**

---

## P3 — Harmonisation

### P3-01 : Unifier les conventions agent entre les 3 factories

**Risque** : R-20, R-21
**Contexte** : Content Factory (lowercase, AGENTS.md + SOUL.md), Trading Factory (UPPERCASE, handler.js), POLY_FACTORY (Python, poly_*.py) — 3 conventions différentes.
**Action** : Documenter les conventions dans `references/agent_conventions.md`. Ne pas migrer (trop risqué), clarifier la frontière.
**Effort** : 1h
**Impact** : Clarté pour les futurs développeurs.
**Priorité** : **P3**

### P3-02 : Évaluer le partage news entre les 3 systèmes

**Risque** : R-21
**Action** : Évaluer la faisabilité d'un flux partagé : RSS → scoring unique → consumers (content, trading, POLY). Risque de couplage excessif.
**Effort** : Investigation 2h
**Impact** : Réduction coûts API et LLM.
**Priorité** : **P3**

### P3-03 : Optimiser les schedules agents

**Action** : Aligner les cycles producer/consumer pour réduire les polls inutiles :
- POLICY_ENGINE : 30s → 60s (aligné sur RISK_MANAGER)
- PREDICTOR : désactiver ou intégrer dans REGIME_DETECTOR
- TRADING_ORCHESTRATOR : 10s OK (doit être rapide)
**Effort** : 30 min
**Impact** : Réduction charge CPU/IO du poller.
**Priorité** : **P3**

---

## P4 — Futur (pré-requis mainnet)

### P4-01 : Créer un MAINNET_EXECUTOR

**Risque** : R-17
**Action** : Nouveau module `MAINNET_EXECUTOR/handler.js` basé sur TESTNET_EXECUTOR, avec :
- Clés API mainnet (dans .env)
- Vérification balances réelles
- Confirmation fill + reconciliation
- Rate limiting plus strict
- Alertes Telegram sur chaque trade
**Effort** : 1-2 jours
**Priorité** : **P4** (pré-requis passage mainnet)

### P4-02 : Implémenter un bot Telegram d'approbation interactive

**Risque** : R-03
**Action** : Bot Telegram avec inline keyboard (✅ Approve / ❌ Reject), correlated avec les ordres HUMAN_APPROVAL_REQUIRED, TTL configurable, fallback BLOCK.
**Effort** : 1-2 jours
**Priorité** : **P4** (pré-requis passage mainnet avec gros ordres)

### P4-03 : Ajouter coordination cross-system Trading Factory ↔ POLY_FACTORY

**Risque** : R-20
**Action** : Shared risk state : total exposure, global drawdown, circuit breaker cross-système.
**Effort** : 2-3 jours
**Priorité** : **P4** (quand les deux systèmes sont en production)

---

## Résumé des priorités

| Priorité | # | Actions | Effort total |
|----------|---|---------|-------------|
| **P0** | 3 | Kill C-02, fix guardian, fix human approval | 1-4h |
| **P1** | 4 | Double cleanup, PREDICTOR, watchdog faux positifs, surveillance guardian | ~1h |
| **P2** | 4 | Dedup bus, lock files, contrat POLY, fallback Anthropic | 6-8h |
| **P3** | 3 | Conventions docs, news partagé, schedules optimisés | 3-4h |
| **P4** | 3 | Mainnet executor, bot approval, coordination cross-system | 4-7 jours |
| **Total** | **17** | | |
