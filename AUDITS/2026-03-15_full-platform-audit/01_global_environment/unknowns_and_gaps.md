# unknowns_and_gaps.md — Inconnues et lacunes

**Date** : 2026-03-15
**Méthode** : analyse croisée des observations Phase 0 + Phase 1

---

## Inconnues TYPE_1 (Critique)

### U-01 : Validité des credentials Polymarket

**Statut** : [INCONNU]
**Impact** : Blocage total du trading live si les clés sont invalides/expirées.
**Détail** : `POLYMARKET_API_KEY` et `POLYMARKET_API_SECRET` sont présents dans `.env` mais leur validité n'a pas été testée. Le Gamma API (public) fonctionne sans authentification. Le CLOB API (trading) nécessite ces clés.
**Action recommandée** : Test authentifié sur le CLOB API (`get_api_keys` endpoint).

### U-02 : WALLET_PRIVATE_KEY absent

**Statut** : [OBSERVÉ] — absent du `.env` POLY_FACTORY
**Impact** : `connector_polymarket._get_clob_client()` crashera avec `KeyError: 'WALLET_PRIVATE_KEY'` si `place_order()` ou `get_positions()` est appelé.
**Détail** : Le code à la ligne 257 de `connector_polymarket.py` fait `os.environ["WALLET_PRIVATE_KEY"]` (sans default). `METAMASK_PRIVATE_KEY` est présent mais n'est pas la même variable.
**Action recommandée** : Vérifier si `METAMASK_PRIVATE_KEY` devrait être mappé vers `WALLET_PRIVATE_KEY`, ou si c'est une clé distincte.

### U-03 : État réel des trades JS Trading Factory

**Statut** : [INCONNU]
**Impact** : Impossible de savoir si le système JS trade activement (paper ou live) sans analyser `state/trading/exec/` et `state/trading/live/`.
**Action recommandée** : Audit Phase 3 (Trading Factory).

---

## Inconnues TYPE_2 (Important)

### U-04 : Monitoring et alerting externe

**Statut** : [INCONNU] — aucun système d'alerte externe détecté
**Impact** : Les pannes sont silencieuses. Le watchdog (cron */15min) détecte les crashs mais ses alertes vont [INCONNU] (Telegram? log seulement?).
**Détail** : SYSTEM_WATCHDOG écrit dans `runs/` et potentiellement envoie des notifications, mais la destination n'a pas été vérifiée.
**Action recommandée** : Lire `SYSTEM_WATCHDOG/index.js` pour identifier les canaux de notification.

### U-05 : Stratégie de backup

**Statut** : [INCONNU] — aucune politique de backup observée
**Impact** : Perte de données en cas de crash disque. Les fichiers `state/` (comptes, trades, registry) n'ont pas de backup visible.
**Détail** : 81 Go libre sur 97 Go, mais aucun cron de backup, aucun rsync, aucun snapshot automatique détecté.
**Action recommandée** : Mettre en place un backup minimal des fichiers `state/` critiques.

### U-06 : Rôle exact de POLY_TRADING_PUBLISHER

**Statut** : [INCONNU]
**Impact** : Si ce composant JS bridge les deux systèmes de trading, sa panne pourrait désynchroniser les états.
**Action recommandée** : Analyser `skills_custom/trading/POLY_TRADING_PUBLISHER/` en Phase 3.

### U-07 : Contenu de workspace/.env

**Statut** : [INCONNU] — `grep` sur les clés a retourné vide
**Impact** : Mineur si vide, potentiellement important si contient des secrets utilisés par d'autres composants.
**Action recommandée** : Vérifier si le fichier existe et s'il est utilisé par le Docker container ou PM2.

---

## Inconnues TYPE_3 (Support)

### U-08 : Rôle de workspace/agents/ et workspace/intel/

**Statut** : [INCONNU]
**Impact** : Faible — probablement legacy ou documentation.
**Action recommandée** : `ls` rapide en Phase 5.

### U-09 : Version exacte du Python venv

**Statut** : [DÉDUIT] 3.11.x d'après `ps aux` output (le path indique `.venv/bin/python`)
**Impact** : Faible, mais important pour la reproductibilité.
**Action recommandée** : `POLY_FACTORY/.venv/bin/python --version`

---

## Lacunes identifiées

### L-01 : Pas de health check HTTP pour poly-orchestrator

**Observation** [OBSERVÉ] : poly-orchestrator n'expose aucun port HTTP. PM2 ne peut pas faire de health check applicatif, seulement vérifier que le process tourne.
**Impact** : MEDIUM — un orchestrateur bloqué (deadlock, boucle infinie sans crash) ne serait pas détecté.
**Recommandation** : Ajouter un endpoint health ou un fichier heartbeat que PM2/watchdog peut vérifier.

### L-02 : Pas de rotation des logs poly-orchestrator

**Observation** [DÉDUIT] : PM2 gère ses propres logs (`~/.pm2/logs/`) mais aucune rotation logrotate n'a été observée pour les logs PM2.
**Impact** : LOW — accumulation lente de logs sur disque.

### L-03 : Aucun test d'intégration end-to-end automatisé

**Observation** [DÉDUIT] : Les tests pytest existent (1285 passed) mais sont unitaires. Aucun test E2E vérifiant la chaîne complète (signal → filter → execute → log) avec de vraies données.
**Impact** : MEDIUM — les bugs de pipeline (comme ceux corrigés le 2026-03-14) ne sont détectés qu'en production.

### L-04 : Pas de séparation réseau Docker / host

**Observation** [OBSERVÉ] : Les cron jobs font `docker exec` pour exécuter du code dans le container. Le container a accès au filesystem via volumes montés.
**Impact** : LOW — le container n'est pas isolé du host pour les opérations de trading.
