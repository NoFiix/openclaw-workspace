# recommendations.md — Recommandations POLY_FACTORY

**Date** : 2026-03-15
**Priorité** : P0 (bloquant) → P1 (quick wins <1h) → P2 (corrections importantes) → P3 (harmonisation) → P4 (futur)

---

## P0 — Corrections bloquant le paper trading

### P0-01 : Diagnostiquer et réactiver les 11 agents disabled

**Risque** : R-01 — pipeline majoritairement inopérant
**Action** :
1. Lire les PM2 error logs : `~/.pm2/logs/poly-orchestrator-error.log`
2. Identifier la cause racine des crashes (probablement : API timeout, fichier state manquant, ou import error)
3. Corriger le bug pour chaque agent
4. Reset les restart counters dans `heartbeat_state.json` (mettre `restart_count: 0`, `status: "active"`)
5. Vérifier que les agents restent stables pendant 15+ minutes
**Effort** : 2-4h
**Impact** : Restaure le pipeline complet. Sans cette correction, **0 trade sera jamais possible**.
**Priorité** : **P0**

### P0-02 : Réduire le CPU orchestrateur (98% → <30%)

**Risque** : R-02 — overhead CPU + dégradation performances globales
**Actions possibles** (par ordre de priorité) :
1. **Compaction agressive** : Après chaque nightly, purger tous les events pending ackés. Réduire le fichier de 70k → <1k events.
2. **Augmenter POLL_INTERVAL** : 2s → 5s pour les agents non-critiques. Les feeds (300s) et stratégies (30-60s) n'ont pas besoin d'un tick à 2s.
3. **Séparer bus read** : Ne pas scanner tout le fichier à chaque tick. Maintenir un offset fichier (`seek`) au lieu de relire depuis le début.
**Effort** : 2-4h
**Impact** : CPU de 98% → <30%. Libère des ressources pour les autres processes.
**Priorité** : **P0**

### P0-03 : Implémenter un producteur pour `news:high_impact`

**Risque** : R-05 — poly_news_strat starved
**Action** : Soit créer un bridge JS→Python qui forward les `trading.intel.news.event` (urgency ≥7) du bus JS Trading Factory vers le bus Python POLY_FACTORY, soit implémenter un news feed POLY natif.
**Alternative** : Marquer news_strat comme DORMANT et retirer du scheduler si le bridge est trop complexe.
**Effort** : 1-2h (bridge) ou 5 min (disable)
**Impact** : Débloque la 9ème stratégie ou clarifie qu'elle est dormante.
**Priorité** : **P0**

---

## P1 — Quick wins (< 1h chacun)

### P1-01 : Augmenter MAX_RESTARTS de 3 à 10 avec reset quotidien

**Risque** : R-06 — cascade de désactivation
**Action** : Dans `poly_heartbeat.py`, changer `MAX_RESTARTS = 3` → `MAX_RESTARTS = 10`. Ajouter un `reset_daily()` dans le nightly cycle qui remet les restart_count à 0 pour tous les agents (donnant une nouvelle chance chaque jour).
**Effort** : 15 min
**Impact** : Les agents qui crashent occasionnellement (API timeout) ne seront plus définitivement morts.
**Priorité** : **P1**

### P1-02 : Ajouter alerte Telegram pour agents disabled

**Risque** : R-01 (détection)
**Action** : Dans `poly_heartbeat.py`, quand un agent est désactivé, publier un message vers Telegram via `POLY_TELEGRAM_BOT_TOKEN` (déjà configuré pour POLY_TRADING_PUBLISHER).
**Effort** : 30 min
**Impact** : L'humain est immédiatement notifié quand un agent meurt.
**Priorité** : **P1**

### P1-03 : Ajouter timeout pour les appels agents dans le scheduler

**Risque** : R-07 — LLM hang bloque tout
**Action** : Wrapper chaque `agent.run_once()` dans un `signal.alarm(30)` (timeout 30s) ou utiliser `concurrent.futures.ThreadPoolExecutor` avec `timeout=30`.
**Effort** : 30 min
**Impact** : Un agent lent ne peut plus bloquer le scheduler entier.
**Priorité** : **P1**

### P1-04 : Aligner les intervalles stratégies avec les feeds

**Risque** : Gaspillage CPU/IO
**Action** : Stratégies à 5s (arb_scanner, latency_arb, brownian, pair_cost) → aligner sur 30-60s (le connector ne rafraîchit que toutes les 300s, le binance_feed toutes les 30s). Inutile de scanner à 5s si les données ne changent que toutes les 30-300s.
**Effort** : 10 min (modifier les intervalles dans run_orchestrator.py)
**Impact** : Réduction significative des polls inutiles (~90% de réduction pour ces 4 agents).
**Priorité** : **P1**

---

## P2 — Corrections importantes

### P2-01 : Migrer bus vers multi-fichiers (comme JS)

**Risque** : R-02, R-03 — CPU et backlog
**Action** : Séparer `pending_events.jsonl` en 1 fichier par topic (comme le bus JS). Chaque agent ne lit que le fichier de son topic. Élimine le goulot I/O single-file.
**Effort** : 4-8h (refactoring `poly_event_bus.py` + tous les consumers)
**Impact** : CPU divisé par ~5-10. Scalabilité améliorée.
**Priorité** : **P2**

### P2-02 : Ajouter WALLET_PRIVATE_KEY ou documenter le blocker

**Risque** : R-15 — live impossible
**Action** : Soit ajouter `WALLET_PRIVATE_KEY` dans `.env` (mapper depuis `METAMASK_PRIVATE_KEY` si c'est la même clé), soit documenter clairement que le passage live est bloqué et les pré-requis.
**Effort** : 15 min (variable mapping) ou 30 min (documentation)
**Impact** : Débloquer le chemin paper → live.
**Priorité** : **P2**

### P2-03 : Valider les credentials Polymarket

**Risque** : R-16 — credentials possiblement invalides
**Action** : Écrire un script de test : `test_polymarket_auth.py` qui fait un `GET /api/keys` authentifié sur le CLOB API.
**Effort** : 30 min
**Impact** : Confirmer ou infirmer U-01 (blocage potential live).
**Priorité** : **P2**

### P2-04 : Investiguer pourquoi 0 trade:signal en 1.5 jours

**Risque** : R-04 — pipeline stérile
**Action** :
1. Ajouter du logging temporaire dans chaque stratégie active pour tracer : "signal potentiel trouvé", "filtré par seuil X", "aucun edge"
2. Vérifier les seuils : `edge_threshold` (0.05-0.15), `min_confidence` (0.70-0.85) — possiblement trop stricts pour les marchés actuels
3. Vérifier que `feed:price_update` contient bien des données exploitables pour les 20 marchés
**Effort** : 2-3h
**Impact** : Comprendre pourquoi le système ne produit aucun signal et ajuster.
**Priorité** : **P2**

### P2-05 : Ajouter métriques bus dans system_monitor

**Risque** : Bus saturation non détectée
**Action** : Ajouter dans `poly_system_monitor.py` un check : taille pending_events.jsonl > 50k events → WARNING, > 100k → CRITICAL.
**Effort** : 30 min
**Impact** : Détection proactive de la saturation bus.
**Priorité** : **P2**

---

## P3 — Harmonisation avec Trading Factory et Content Factory

### P3-01 : Bridge news JS → Python

**Action** : Créer un agent bridge (`POLY_NEWS_BRIDGE`) dans skills_custom/trading/ qui lit `trading.intel.news.event` (bus JS) et écrit `news:high_impact` dans le bus Python.
**Alternative** : Le faire dans POLY_TRADING_PUBLISHER (déjà un bridge JS→POLY).
**Effort** : 2-3h
**Impact** : Débloque poly_news_strat + unifie les flux news.
**Priorité** : **P3**

### P3-02 : Contrat d'interface POLY_FACTORY ↔ Trading Factory

**Action** : Documenter dans `references/poly_factory_interface.json` :
- Fichiers state lus par POLY_TRADING_PUBLISHER et GLOBAL_TOKEN_TRACKER
- Schéma attendu pour chaque fichier
- Versioning (si format change → incrémenter version)
**Effort** : 1h
**Impact** : Détection précoce des breaking changes cross-système.
**Priorité** : **P3**

### P3-03 : Unifier monitoring dans un dashboard Polymarket

**Action** : Le dashboard React Polymarket existe déjà (4 endpoints Express). Ajouter :
- Indicateur bus health (pending events count, backlog ratio)
- Indicateur agents disabled (count + list)
- Indicateur CPU orchestrateur
**Effort** : 2-3h
**Impact** : Visibilité centralisée de la santé POLY_FACTORY.
**Priorité** : **P3**

---

## P4 — Améliorations futures

### P4-01 : Migrer vers architecture multi-process (comme poller.js)

**Action** : Remplacer le scheduler single-threaded par un système multi-process Python (ProcessPoolExecutor ou multiprocessing). Chaque agent dans un process séparé, communication via files ou shared memory.
**Effort** : 2-3 jours
**Impact** : Isolation (crash d'un agent ne tue pas le scheduler), parallélisme (multi-core), timeout natif.
**Priorité** : **P4**

### P4-02 : Ajouter agent POLY_STRATEGY_RESEARCHER (LLM)

**Action** : Équivalent de STRATEGY_RESEARCHER (JS) pour POLY_FACTORY. Scrape forums prediction markets (Manifold, Metaculus), identifie nouvelles stratégies.
**Effort** : 1-2 jours
**Impact** : Pipeline de découverte de nouvelles stratégies.
**Priorité** : **P4**

### P4-03 : Activer connector_kalshi pour arb cross-platform

**Action** : connector_kalshi est implémenté mais non connecté. Obtenir API key Kalshi, tester l'intégration, activer l'arb cross-platform dans arb_scanner.
**Effort** : 1 jour
**Impact** : Nouvelle source d'opportunités d'arbitrage.
**Priorité** : **P4**

### P4-04 : Ajouter compounding automatique

**Action** : poly_compounder existe mais n'est pas dans le scheduler. L'intégrer avec un seuil de profit configurable (100€ par défaut).
**Effort** : 1h
**Impact** : Croissance composée du capital (quand les stratégies seront profitables).
**Priorité** : **P4**

---

## Résumé des priorités

| Priorité | # | Actions | Effort total |
|----------|---|---------|-------------|
| **P0** | 3 | Réactiver agents, réduire CPU, news bridge | 5-10h |
| **P1** | 4 | MAX_RESTARTS, Telegram alerts, timeout, intervalles | ~1h30 |
| **P2** | 5 | Multi-file bus, WALLET_KEY, credentials, debug signals, bus metrics | 7-12h |
| **P3** | 3 | News bridge, contrat interface, dashboard | 5-7h |
| **P4** | 4 | Multi-process, researcher, Kalshi, compounder | 4-6 jours |
| **Total** | **19** | | |
