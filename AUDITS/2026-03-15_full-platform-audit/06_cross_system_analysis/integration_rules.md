# integration_rules.md — Règles d'intégration pour nouveaux systèmes

**Date** : 2026-03-15
**Scope** : Checklist, retour d'expérience POLY_FACTORY, conventions de nommage

---

## Résumé exécutif

Ce document est le référentiel pour intégrer un nouveau système dans l'environnement OpenClaw. Il codifie les leçons tirées de l'ajout de POLY_FACTORY et les patterns observés sur les 3 systèmes existants. Chaque section est une checklist actionnable. [DÉDUIT]

---

## Section A — Checklist d'intégration

### 1. Infrastructure

- [ ] **Process management** : Ajouter le process dans PM2 (long-running) ou documenter le mécanisme de démarrage (cron, Docker exec) [OBSERVÉ — poly-orchestrator dans PM2, trading dans Docker]
- [ ] **Auto-restart** : Vérifier que le process redémarre automatiquement après crash (PM2 autorestart, Docker restart policy) [OBSERVÉ — PM2 pour POLY, @reboot sans restart pour Content]
- [ ] **Reboot survival** : Vérifier que le process redémarre après reboot VPS (PM2 startup, @reboot cron, ou Docker restart: unless-stopped) [OBSERVÉ — PM2 startup configuré, @reboot cron pour daemons Docker]
- [ ] **Ports** : Ne pas utiliser les ports déjà occupés (22, 80, 443, 3001, 18789, 18790) — vérifier avec `ss -tlnp` [OBSERVÉ]
- [ ] **Firewall** : Si nouveau port exposé, ajouter règle UFW (quand activé) [DÉDUIT]
- [ ] **Permissions .env** : chmod 600 sur tout fichier .env contenant des secrets [OBSERVÉ — dashboard 600 OK, POLY 664 CRITIQUE]

### 2. Surveillance

- [ ] **SYSTEM_WATCHDOG** : Ajouter dans `SYSTEM_WATCHDOG/config.json` les seuils de monitoring du nouveau système [OBSERVÉ — POLY ajouté via poly_factory block]
- [ ] **Heartbeat file** : Si process long-running, créer un heartbeat file écrit périodiquement et vérifié par le watchdog ou un cron externe [OBSERVÉ — fix récent pour watchdog lui-même]
- [ ] **Alertes Telegram** : Définir quel bot et quel canal. **NE PAS réutiliser le canal existant** sans vérification — actuellement les 4 canaux sont le même chat [OBSERVÉ]
- [ ] **Rapport quotidien 08h** : Ajouter une section dans le rapport SYSTEM_WATCHDOG pour le nouveau système [OBSERVÉ — sections TRADING, CONTENT, POLYMARKET dans le rapport]
- [ ] **Stale detection** : Définir les seuils "stale" pour les agents du nouveau système (WARN à 10× interval, CRIT à 30× interval) [OBSERVÉ — convention existante]

### 3. Variables d'environnement

- [ ] **Lister** toutes les variables requises dans un fichier doc [DÉDUIT]
- [ ] **Vérifier collision** avec les variables existantes — utiliser un préfixe unique (POLY_, BUILDER_, TRADER_, etc.) [OBSERVÉ — POLY utilise POLY_TELEGRAM_*, POLYMARKET_*]
- [ ] **Fichier .env** : Créer un fichier .env dédié dans le dossier du système, permissions 600 [OBSERVÉ — POLY_FACTORY/.env existe]
- [ ] **Documenter** dans CONTEXT_BUNDLE correspondant toutes les variables et leur rôle [DÉDUIT]
- [ ] **Ne jamais partager** une clé API sans documenter le partage (risque révocation cross-system) [DÉDUIT — ANTHROPIC_API_KEY partagée non documentée]

### 4. State files

- [ ] **Dossier dédié** : Créer `{SYSTEM}/state/` ou `state/{system}/` — ne JAMAIS écrire dans le state d'un autre système [OBSERVÉ — POLY_FACTORY/state/ séparé, state/trading/ séparé]
- [ ] **Documenter** dans `file_ownership.md` chaque sous-dossier, son owner, ses writers/readers [DÉDUIT]
- [ ] **Rotation/nettoyage** : Prévoir la rotation des fichiers JSONL (bus, logs, trades) AVANT le déploiement [OBSERVÉ — POLY bus avait besoin de compaction fix]
- [ ] **Taille maximale** : Définir un seuil d'alerte dans SYSTEM_WATCHDOG pour les dossiers state du nouveau système [OBSERVÉ — thresholds dans config.json]

### 5. Bus d'événements

- [ ] **Topics uniques** : Vérifier que les topics ne collisionnent pas avec les bus existants (JS: `trading.*`, Python: `feed:`, `signal:`, `trade:`, `risk:`, `system:`) [OBSERVÉ — bus JS et Python physiquement séparés]
- [ ] **Documenter** tous les topics dans `schemas/` avec le format d'enveloppe [OBSERVÉ — POLY_FACTORY/schemas/ contient les JSON schemas]
- [ ] **Compaction** : Implémenter un mécanisme de compaction/purge du bus dès le départ [OBSERVÉ — POLY a dû être fixé a posteriori (C-11)]
- [ ] **Idempotence** : Chaque consommateur DOIT implémenter l'idempotence (set des derniers N event_ids) [OBSERVÉ — POLY_FACTORY/CLAUDE.md l'exige]
- [ ] **Dead letter** : Prévoir une file dead letter pour les événements en échec après N retries [OBSERVÉ — POLY a dead_letter_queue.jsonl]

### 6. Dashboard

- [ ] **Route API** : Créer un fichier de routes dédié dans `dashboard/api/routes/` [OBSERVÉ — polymarket.js ajouté pour POLY]
- [ ] **Page frontend** : Créer une page dédiée dans `dashboard/web/src/pages/` [OBSERVÉ — Polymarket.jsx existe]
- [ ] **Navigation** : Ajouter dans `App.jsx` la nouvelle route et le lien de navigation [OBSERVÉ]
- [ ] **Client API** : Ajouter les fonctions fetch dans `client.js` [OBSERVÉ]
- [ ] **Cache TTL** : Définir un TTL approprié pour chaque endpoint (15s-60s pour données live, 5-15min pour historiques) [OBSERVÉ]

### 7. Telegram

- [ ] **Bot dédié** : Utiliser un bot token dédié (préfixé par le nom du système) [OBSERVÉ — POLY_TELEGRAM_BOT_TOKEN existe]
- [ ] **Canal séparé** : Idéalement utiliser un canal Telegram distinct — NE PAS envoyer dans le canal commun sans vérification (actuellement 14 émetteurs → 1 chat) [OBSERVÉ]
- [ ] **Pas de doublon** : Vérifier que les alertes ne dupliquent pas celles d'un autre système [DÉDUIT]
- [ ] **Documenter** dans `telegram_bots.md` quel bot envoie quoi et à quelle fréquence [DÉDUIT]

### 8. Token tracking LLM

- [ ] **Intégrer** `logTokens.js` (JS) ou `poly_log_tokens.py` (Python) dans chaque appel LLM [OBSERVÉ — Trading ✅, POLY ✅ (vide), Content ❌]
- [ ] **system=** : Utiliser un identifiant unique (`system="nom_du_systeme"`) pour distinguer dans les agrégats [OBSERVÉ — POLY utilise `system="polymarket"`]
- [ ] **Vérifier** que GLOBAL_TOKEN_TRACKER lit le fichier token_costs.jsonl du nouveau système [OBSERVÉ — Tracker lit Trading + POLY]

### 9. Documentation

- [ ] **CONTEXT_BUNDLE** : Créer `CONTEXT_BUNDLE_{NOM}.md` décrivant l'architecture, les composants, les flux [OBSERVÉ — CONTEXT_BUNDLE_TRADING.md existe]
- [ ] **MEMORY.md** : Mettre à jour si pertinent pour les sessions futures [DÉDUIT]
- [ ] **AUDITS/CHANGELOG.md** : Documenter l'ajout dans le changelog des audits [DÉDUIT]
- [ ] **README système** : CLAUDE.md ou README.md dans le dossier racine du système [OBSERVÉ — POLY_FACTORY/CLAUDE.md]

### 10. Tests

- [ ] **Tests unitaires** : Écrire les tests AVANT de déployer (`tests/test_{agent}.py`) [OBSERVÉ — POLY a un test par agent]
- [ ] **Tests existants** : Vérifier que tous les tests existants passent toujours après l'intégration [DÉDUIT]
- [ ] **Test de non-régression** : Vérifier que le nouveau système ne casse pas les systèmes existants (ports, fichiers, variables) [DÉDUIT]

### 11. Rollback

- [ ] **Désactivation** : Documenter comment désactiver le système sans casser le reste (PM2 stop, cron comment, scheduler disable) [DÉDUIT]
- [ ] **Triggers** : Retirer ou désactiver ses triggers (cron entries, PM2 process, scheduler agents) [DÉDUIT]
- [ ] **Dashboard** : Retirer ses routes et pages si le système est retiré définitivement [DÉDUIT]
- [ ] **Telegram** : Désactiver ses alertes pour ne pas polluer le canal [DÉDUIT]
- [ ] **State files** : Documenter quels fichiers state sont laissés derrière et s'ils peuvent être supprimés [DÉDUIT]
- [ ] **Dépendances** : Vérifier qu'aucun autre système ne lit les fichiers du système retiré (POLY_TRADING_PUBLISHER lit POLY state → ne pas retirer POLY sans adapter le publisher) [OBSERVÉ]

---

## Section B — Retour d'expérience POLY_FACTORY

### Ce qui a cassé lors de l'ajout

| # | Problème | Cause racine | Comment l'éviter | Tag |
|---|----------|-------------|-----------------|-----|
| 1 | **11 agents disabled (C-10)** | `MAX_RESTARTS=3` trop agressif + `ping()` refusait de reviver les agents disabled | Fixer MAX_RESTARTS à 10+, permettre la récupération via ping() — tester les scénarios de restart AVANT le déploiement | [OBSERVÉ] |
| 2 | **Bus saturé 70k events (C-11)** | `_acked_ids` deque capped à 10k, old acked IDs tombaient hors scope → events jamais nettoyés | Lire TOUS les acked IDs depuis le disque lors de la compaction, pas seulement le cache mémoire — ajouter purge par âge | [OBSERVÉ] |
| 3 | **98% CPU (C-01)** | Boucle polling 2s relisant un fichier de 19 Mo à chaque tick | Implémenter la compaction AVANT de mettre en production — monitorer la taille du bus dès le jour 1 | [OBSERVÉ] |
| 4 | **0 trade:signal (U-13)** | Seuils de stratégies trop stricts (edge_threshold=0.15, min_llm_probability=0.85) | Calibrer les seuils sur des données réelles AVANT le déploiement — commencer avec des seuils permissifs et resserrer progressivement | [OBSERVÉ] |
| 5 | **news:high_impact sans producteur (C-12)** | Bridge JS→Python non implémenté — stratégie déployée sans vérifier ses dépendances | Vérifier que TOUS les topics consommés ont un producteur AVANT de déployer une stratégie | [OBSERVÉ] |
| 6 | **POLY_FACTORY/.env world-readable (C-13)** | Fichier créé avec umask par défaut (664) | Toujours `chmod 600` immédiatement après création d'un .env | [OBSERVÉ] |
| 7 | **Token tracking vide** | Agents LLM (opp_scorer, no_scanner) disabled → poly_log_tokens.py jamais appelé | Tester le tracking LLM manuellement avant de dépendre du flux normal | [OBSERVÉ] |

### Leçons clés

1. **Tester les scénarios de dégradation** : restart agents, bus saturation, API timeout — pas seulement le happy path [DÉDUIT]
2. **Monitorer dès le jour 1** : ajouter dans SYSTEM_WATCHDOG AVANT de mettre en production, pas après les incidents [DÉDUIT]
3. **Calibrer sur données réelles** : les seuils théoriques (backtest) ne fonctionnent pas en production [OBSERVÉ]
4. **Vérifier les dépendances de bout en bout** : topic → producteur → consommateur → action. Pas de maillon manquant. [OBSERVÉ]
5. **Permissions .env immédiatement** : chmod 600 à la création, pas "plus tard" [OBSERVÉ]

---

## Section C — Conventions de nommage

### Variables d'environnement

| Système | Préfixe | Exemples | Tag |
|---------|---------|----------|-----|
| Content Factory | `BUILDER_` | `BUILDER_TELEGRAM_BOT_TOKEN`, `BUILDER_TELEGRAM_CHAT_ID` | [OBSERVÉ] |
| Trading Factory | `TRADER_` | `TRADER_TELEGRAM_BOT_TOKEN`, `TRADER_TELEGRAM_CHAT_ID` | [OBSERVÉ] |
| POLY_FACTORY | `POLY_` / `POLYMARKET_` | `POLY_TELEGRAM_BOT_TOKEN`, `POLYMARKET_API_KEY` | [OBSERVÉ] |
| System (watchdog) | `TELEGRAM_` (sans préfixe) | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | [OBSERVÉ] |
| Dashboard | `DASHBOARD_` | `DASHBOARD_API_KEY` | [OBSERVÉ] |
| Nouveau système | `{SYSTEM}_` | Ex: `KALSHI_API_KEY`, `KALSHI_TELEGRAM_BOT_TOKEN` | [DÉDUIT] |

### Fichiers state

| Système | Dossier | Convention | Tag |
|---------|---------|-----------|-----|
| Trading Factory | `state/trading/` | Exclusif au système JS | [OBSERVÉ] |
| POLY_FACTORY | `POLY_FACTORY/state/` | Exclusif au système Python | [OBSERVÉ] |
| Content Factory | `state/` (racine) | drafts.json, logs, seen_articles.json | [OBSERVÉ] |
| Nouveau système | `{SYSTEM}/state/` ou `state/{system}/` | Dossier dédié obligatoire | [DÉDUIT] |

### Topics bus

| Bus | Préfixe | Exemples | Tag |
|-----|---------|----------|-----|
| Trading (JS) | `trading.{domain}.*` | `trading.prices.btc`, `trading.signals.proposal` | [OBSERVÉ] |
| POLY (Python) | `{domain}:{action}` | `feed:binance_update`, `trade:signal`, `risk:kill_switch` | [OBSERVÉ] |
| **Règle** | Jamais de topic identique dans les deux bus | — | [DÉDUIT] |

### Agents

| Système | Convention | Exemples | Tag |
|---------|-----------|----------|-----|
| Trading (JS) | MAJUSCULES_UNDERSCORE | `KILL_SWITCH_GUARDIAN`, `BINANCE_PRICE_FEED` | [OBSERVÉ] |
| POLY (Python) | Poly + PascalCase (class), poly_ + snake_case (file) | `PolyBinanceFeed` / `poly_binance_feed.py` | [OBSERVÉ] |
| Content (JS) | snake_case | `hourly_scraper.js`, `poller.js` | [OBSERVÉ] |
| Nouveau système | Choisir une convention et la documenter dans CLAUDE.md | — | [DÉDUIT] |

### Comptes (POLY_FACTORY spécifique)

| Convention | Pattern | Exemple | Tag |
|-----------|---------|---------|-----|
| Account name | `ACC_POLY_{STRATEGY_NAME}` | `ACC_POLY_ARB_SCANNER` | [OBSERVÉ] |
| Strategy name | `POLY_{NAME}` | `POLY_ARB_SCANNER` | [OBSERVÉ] |
