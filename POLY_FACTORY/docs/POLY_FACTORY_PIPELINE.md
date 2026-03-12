# POLY_FACTORY — Pipeline Opérationnel v4

> **Version 4.0 — 12 mars 2026**
> Blueprint détaillé et exploitable du fonctionnement de POLY_FACTORY.
> Document compagnon de POLY_FACTORY_ARCHITECTURE.md (v4.0).

---

## CHANGEMENTS v4

| Ajout | Impact |
|---|---|
| `POLY_STRATEGY_ACCOUNT` | Chaque stratégie = unité financière indépendante (1 000€ test / 1 000€ réel). Comptes isolés, comparaison normalisée. |
| `POLY_GLOBAL_RISK_GUARD` | Plafond de perte globale 4 000€. Arrêt total automatique si seuil atteint. |
| `POLY_MARKET_CONNECTOR` | Abstraction multi-plateformes (Polymarket, Kalshi, sportsbooks). Remplace POLY_PM_FEED. |
| `POLY_SYSTEM_MONITOR` | Surveillance santé du système, APIs, agents, anomalies infrastructure. |
| `POLY_DATA_VALIDATOR` | Vérification qualité et cohérence des données avant consommation par les stratégies. |
| Cycle 10 — Réévaluation | Les stratégies stoppées peuvent être réactivées si les conditions de marché changent. |
| `POLY_CAPITAL_MANAGER` ajusté | Le capital n'est alloué qu'APRÈS validation humaine. Séquence : évaluation → approbation → allocation. |

---

## MODÈLE FINANCIER — POLY_STRATEGY_ACCOUNT

### Concept

Chaque stratégie fonctionne comme une **unité financière indépendante** avec son propre compte, son propre P&L et son propre cycle de vie. Ce modèle s'appelle `POLY_STRATEGY_ACCOUNT`.

| Paramètre | Valeur |
|---|---|
| Capital de test par stratégie (paper) | 1 000€ fictifs |
| Capital réel de départ par stratégie | 1 000€ réels |
| Perte maximale globale (toutes stratégies) | 4 000€ |
| Max stratégies en test simultané | 8 |
| Max stratégies en live simultané | 5 |

### Pourquoi ce Modèle

Sans comptes indépendants, trois problèmes concrets apparaissent. La comparaison est impossible : si deux stratégies partagent un pool, impossible de savoir laquelle génère quel P&L. La contagion des pertes est invisible : une stratégie perdante consomme le capital d'une gagnante sans que personne ne le détecte. Et la décision de scaling est arbitraire : comment doubler le capital d'une stratégie si on ne sait pas combien elle a gagné isolément ?

Avec `POLY_STRATEGY_ACCOUNT`, chaque stratégie démarre avec 1 000€. La comparaison est triviale : un P&L de +87€ = +8.7% de rendement, directement comparable au +3.1% d'une autre stratégie.

### Structure d'un Account

```json
{
  "account_id": "ACC_POLY_ARB_SCANNER",
  "strategy": "POLY_ARB_SCANNER",
  "status": "active",
  "platform": "polymarket",
  "capital": {
    "initial": 1000.00,
    "current": 1087.45,
    "currency": "EUR",
    "high_water_mark": 1120.30
  },
  "pnl": {
    "total": 87.45,
    "realized": 72.30,
    "unrealized": 15.15,
    "today": 3.20,
    "this_week": 28.50
  },
  "drawdown": {
    "current_pct": -2.93,
    "max_historical_pct": -3.48,
    "max_allowed_pct": -30.0
  },
  "performance": {
    "trades_total": 342,
    "win_rate": 0.847,
    "sharpe_ratio": 2.34,
    "profit_factor": 3.12,
    "evaluator_score": 78
  },
  "status_history": [
    {"status": "paper_testing", "from": "2026-04-01", "to": "2026-04-15"},
    {"status": "active", "from": "2026-04-16", "to": null}
  ]
}
```

### Statuts

| Statut | Signification | Capital | Transition possible |
|---|---|---|---|
| `paper_testing` | Test argent fictif (1 000€) | Fictif | → `awaiting_human` |
| `awaiting_human` | En attente validation humaine | Aucun | → `active` / `paused` / `stopped` |
| `active` | Live trading (1 000€ réels) | Réel | → `paused` / `stopped` |
| `paused` | Suspendu temporairement | Gelé | → `paper_testing` / `active` / `stopped` |
| `stopped` | Arrêté | Récupéré | → `paper_testing` (réactivation, voir Cycle 10) |

Chaque transition est enregistrée dans `POLY_AUDIT_LOG` et met à jour le `POLY_STRATEGY_ACCOUNT`.

---

## POLY_GLOBAL_RISK_GUARD — Plafond de Perte Global

### Pourquoi

Le `POLY_KILL_SWITCH` protège par stratégie. Le `POLY_RISK_GUARDIAN` protège par portefeuille. Mais aucun ne répond à : **combien avons-nous perdu AU TOTAL depuis le début ?** Scénario dangereux : cinq stratégies actives perdent chacune 800€ avant que leur kill-switch individuel les stoppe. Perte totale : 4 000€. Personne n'avait validé un tel risque.

### Fonctionnement

```
Tick : toutes les 60 secondes + après chaque trade résolu

CALCUL :
  perte_globale = Σ(max(0, account.capital.initial - account.capital.current))
                  pour chaque POLY_STRATEGY_ACCOUNT en status != "stopped"

RÉPONSES :

  < 2 000€ (< 50%) → NORMAL
    Aucune action.

  ≥ 2 000€ (50-75%) → ALERTE
    Notification humain. Aucun nouveau passage paper → live autorisé.

  ≥ 3 000€ (75-100%) → CRITIQUE
    Notification URGENTE. Tout le live → paper automatiquement.

  ≥ 4 000€ (100%) → ARRÊT TOTAL
    TOUT stoppé (paper + live). MODE SÉCURITÉ.
    Humain doit réinitialiser manuellement après audit.
```

### State

```json
{
  "status": "NORMAL",
  "total_loss": 847.30,
  "max_loss_allowed": 4000.00,
  "pct_used": 0.212,
  "accounts_contributing": {
    "POLY_LATENCY_ARB": -120.50,
    "POLY_CONVERGENCE_STRAT": -681.80,
    "POLY_WEATHER_ARB": -45.00
  },
  "last_check": "2026-04-20T14:23:00Z"
}
```

### Position dans la Hiérarchie de Risque

| Agent | Scope | Tick |
|---|---|---|
| `POLY_KELLY_SIZER` | Par trade | Chaque signal |
| `POLY_KILL_SWITCH` | Par stratégie / session | 5s + pré-trade |
| `POLY_RISK_GUARDIAN` | Portefeuille | Pré-trade |
| `POLY_CAPITAL_MANAGER` | Allocations entre stratégies | 60s + nightly |
| **`POLY_GLOBAL_RISK_GUARD`** | **Système entier** | **60s + post-trade** |

---

## POLY_MARKET_CONNECTOR — Abstraction Multi-Plateformes

### Pourquoi

Plusieurs stratégies reposent sur l'arbitrage cross-plateforme (Polymarket vs Kalshi, Polymarket vs sportsbooks). Sans abstraction, chaque STRATEGY_AGENT doit implémenter la logique de connexion de chaque plateforme. Ajouter Kalshi signifierait modifier POLY_ARB_SCANNER et tout agent qui pourrait en bénéficier.

`POLY_MARKET_CONNECTOR` fournit une interface unifiée. Ajouter une nouvelle plateforme = écrire un connecteur. Les STRATEGY_AGENTS ne changent pas.

### Interface Commune

```
get_markets(platform?) → [{market_id, platform, title, prices, volume}]
get_orderbook(market_id) → {bids, asks, mid_price, spread}
place_order(market_id, side, size, price) → {order_id, status, tx_hash?}
get_positions() → [{market_id, side, size, entry_price, pnl}]
get_settlement(market_id) → {result, settlement_price}
```

### Connecteurs

| Plateforme | Connecteur | Statut | Stratégies concernées |
|---|---|---|---|
| Polymarket | `connector_polymarket` | Actif | Toutes |
| Kalshi | `connector_kalshi` | Futur (Phase 2) | Cross-platform arb |
| Sportsbooks | `connector_sportsbook` | Futur (Phase 3) | Sports betting edge |

Le `POLY_DATA_VALIDATOR` (voir ci-dessous) vérifie les données de chaque connecteur avant qu'elles atteignent les STRATEGY_AGENTS.

---

## POLY_SYSTEM_MONITOR — Surveillance Infrastructure

### Pourquoi

Un système automatisé de trading ne peut pas fonctionner de manière fiable sans surveillance active de son infrastructure. Les bugs, les pannes d'API, les agents qui tombent silencieusement, les déconnexions WebSocket, la mémoire saturée ou le CPU à 100% sont des problèmes courants qui, s'ils ne sont pas détectés, produisent des données incorrectes ou des trades ratés. Le `POLY_HEARTBEAT` existant vérifie si un agent est vivant, mais il ne vérifie pas si l'agent fonctionne CORRECTEMENT.

`POLY_SYSTEM_MONITOR` va au-delà du heartbeat : il vérifie que le système dans son ensemble est dans un état sain et cohérent.

### Fonctionnement

```
POLY_SYSTEM_MONITOR
│
├── SURVEILLANCE DES AGENTS (tick 60s)
│   │  Pour chaque agent :
│   │    ✓ Processus vivant (PM2 status)
│   │    ✓ Dernière activité < 2× fréquence attendue
│   │    ✓ Mémoire consommée < seuil (500 MB par agent)
│   │    ✓ Pas de boucle infinie (CPU < 90% pendant > 60s)
│   │    ✓ Pas d'erreurs en série dans les logs (> 10 erreurs/min)
│   │  SI problème → alerte + tentative restart automatique
│   │  SI restart échoue 3× → alerte humain, agent désactivé
│
├── SURVEILLANCE DES APIs (tick 30s)
│   │  Pour chaque API externe :
│   │    ✓ Polymarket CLOB : WebSocket connecté, latence < 1s
│   │    ✓ Binance : WebSocket connecté, latence < 500ms
│   │    ✓ NWS/NOAA : dernière réponse HTTP 200 < 5min
│   │    ✓ Polygon RPC : block number progresse (pas stuck)
│   │  SI API down → POLY_KILL_SWITCH notifié pour suspendre les stratégies dépendantes
│   │  SI API dégradée (latence > 3× normale) → alerte WARNING
│
├── SURVEILLANCE INFRASTRUCTURE (tick 5 min)
│   │  ✓ Espace disque VPS > 1 GB libre
│   │  ✓ RAM VPS < 90%
│   │  ✓ CPU VPS < 85% (moyenne 5 min)
│   │  ✓ SQLite historical/*.db accessible et non corrompue
│   │  ✓ Wallet Polygon : balance gas > 0.01 MATIC
│   │  SI infra critique → POLY_KILL_SWITCH NIVEAU 4 (stop session)
│
└── SURVEILLANCE COHÉRENCE (nightly 02:50 UTC)
    │  ✓ Nombre de POLY_STRATEGY_ACCOUNT == nombre de stratégies dans lifecycle
    │  ✓ Σ(account.capital.current) cohérent avec wallet réel (live)
    │  ✓ Pas de trades orphelins (trades dans log mais pas dans account)
    │  ✓ POLY_GLOBAL_RISK_GUARD.total_loss == Σ(pertes accounts)
    │  SI incohérence → alerte humain + rapport détaillé
```

### Différence avec POLY_HEARTBEAT

| | POLY_HEARTBEAT | POLY_SYSTEM_MONITOR |
|---|---|---|
| Question | "L'agent est-il vivant ?" | "Le système fonctionne-t-il correctement ?" |
| Scope | Agents individuels | Infrastructure complète + cohérence |
| Action | Restart agent | Alerte + corrélation + diagnostic |
| Fréquence | 30 min | 30s à 5 min selon le sous-système |

`POLY_HEARTBEAT` reste en place pour les restarts automatiques. `POLY_SYSTEM_MONITOR` supervise l'ensemble et fournit un diagnostic de plus haut niveau.

### Audit Log

`POLY_SYSTEM_MONITOR` écrit dans `POLY_AUDIT_LOG` : catégorie SYSTEM, event_types `system:health_check`, `system:api_degraded`, `system:infra_warning`, `system:coherence_error`.

---

## POLY_DATA_VALIDATOR — Vérification de la Qualité des Données

### Pourquoi

Un système automatisé prend des décisions basées sur les données qu'il reçoit. Si ces données sont incorrectes, manquantes ou corrompues, les stratégies prennent des décisions sur des fondations fausses. Les conséquences sont directes : un prix aberrant déclenche un faux signal d'arb, un forecast NOAA manquant fait rater un trade weather, un orderbook stale fait surestimer la liquidité.

Le problème est que les APIs externes ne sont pas fiables à 100%. Polymarket peut retourner un prix de 0 pendant une maintenance. Binance peut envoyer un tick dupliqué. NWS peut retourner un forecast daté de 6 heures parce que la station météo est en panne. Sans validation, ces données corrompues se propagent directement dans les STRATEGY_AGENTS.

`POLY_DATA_VALIDATOR` est le dernier rempart entre les données brutes et les décisions de trading.

### Fonctionnement

```
POLY_DATA_VALIDATOR
│
├── VALIDATION DES PRIX (à chaque mise à jour de POLY_MARKET_CONNECTOR)
│   │
│   │  Pour chaque prix reçu :
│   │    ✓ Prix dans [0.01, 0.99] (un prix de 0.00 ou 1.00 = donnée suspecte)
│   │    ✓ YES_price + NO_price dans [0.95, 1.05] (sinon marché incohérent)
│   │    ✓ Variation < 30% par rapport au dernier prix connu (sinon flash crash ou erreur)
│   │    ✓ Timestamp < 30s (sinon donnée stale)
│   │    ✓ Pas de doublon exact (même prix, même timestamp = tick dupliqué)
│   │
│   │  SI validation échoue :
│   │    → Donnée marquée "SUSPECT" dans le fichier state
│   │    → STRATEGY_AGENTS ne consomment PAS les données suspectes
│   │    → POLY_AUDIT_LOG : "data:validation_failed" {source, market, reason}
│   │    → SI 5+ échecs consécutifs sur la même source → alerte POLY_SYSTEM_MONITOR
│
├── VALIDATION DES SIGNAUX BINANCE (à chaque mise à jour de POLY_BINANCE_SIGNALS)
│   │
│   │    ✓ OBI dans [-1, +1]
│   │    ✓ CVD variation cohérente avec volume
│   │    ✓ Prix BTC variation < 5% par rapport au dernier tick (sinon flash crash)
│   │    ✓ Pas de gap > 5s entre deux ticks (sinon feed déconnecté)
│
├── VALIDATION NOAA (à chaque mise à jour de POLY_NOAA_FEED)
│   │
│   │    ✓ Température forecast dans [-50°F, +140°F] (plage réaliste)
│   │    ✓ Timestamp forecast < 6h (sinon prévision trop ancienne)
│   │    ✓ 6 stations présentes (sinon station manquante)
│   │    ✓ Pas de variation > 15°F par rapport au dernier forecast (sinon erreur probable)
│
├── VALIDATION WALLETS (à chaque mise à jour de POLY_WALLET_TRACKER)
│   │
│   │    ✓ Positions non négatives
│   │    ✓ Pas de wallet avec > 100 nouvelles positions en 1 min (sinon bot de spam)
│   │    ✓ Montants cohérents (pas de position de $10M sur un marché à $50K de volume)
│
└── VALIDATION CROSS-SOURCE (tick 60s)
    │
    │  ✓ Prix Polymarket cohérent avec prix Kalshi sur le même événement (si disponible)
    │    (delta > 15% = signal d'arb OU erreur de donnée — flag pour investigation)
    │  ✓ Prix BTC Binance cohérent avec prix implicite sur marchés BTC Polymarket
    │    (delta > 10% = lag OU erreur)
```

### Position dans le Flux

```
API externe → POLY_MARKET_CONNECTOR / FEEDS → POLY_DATA_VALIDATOR → state/feeds/*.json
                                                      │
                                                 SI données valides → consommées par STRATEGY_AGENTS
                                                 SI données suspectes → marquées, non consommées, logguées
```

Le `POLY_DATA_VALIDATOR` s'insère entre les feeds bruts et les fichiers state consommés par les agents. Il ne bloque pas les feeds (les données continuent d'arriver) mais il marque les données invalides pour qu'elles soient ignorées par les STRATEGY_AGENTS.

### Audit Log

Catégorie DATA : event_types `data:validation_passed`, `data:validation_failed`, `data:source_degraded`, `data:stale_detected`.

---

## POLY_CAPITAL_MANAGER — Rôle Ajusté v4

### Changement Fondamental

Dans la v3, le Capital Manager allouait le capital en continu, y compris avant la validation humaine. En v4, le flux est corrigé :

```
v3 (ancien) : Évaluation → Capital Manager alloue → Humain valide → Live
v4 (nouveau) : Évaluation → Humain valide → PUIS Capital Manager alloue → Live
```

Le capital n'est JAMAIS alloué à une stratégie tant qu'elle n'a pas été approuvée par l'humain. Avant approbation, la stratégie fonctionne exclusivement sur son `POLY_STRATEGY_ACCOUNT` paper (1 000€ fictifs). Après approbation, le Capital Manager crée le `POLY_STRATEGY_ACCOUNT` live (1 000€ réels) et gère l'allocation à partir de ce moment.

### Fonctionnement Ajusté

```
POLY_CAPITAL_MANAGER
│
├── CRÉATION D'ACCOUNT LIVE (sur événement : humain signe GO)
│   │  Vérifie : POLY_GLOBAL_RISK_GUARD permet un nouveau compte live
│   │  Crée : POLY_STRATEGY_ACCOUNT live avec 1 000€ réels
│   │  Vérifie : wallet Polygon contient assez de USDC.e
│   │  → AUDIT_LOG : "account:live_created" {strategy, initial_capital}
│
├── CONTRÔLE PRÉ-TRADE (à chaque trade, paper ou live)
│   │  Vérifie sur le POLY_STRATEGY_ACCOUNT de la stratégie :
│   │    ✓ account.status == "paper_testing" ou "active"
│   │    ✓ account.capital.current ≥ taille demandée
│   │    ✓ Trade < 3% du capital du compte (pas du capital global)
│   │    ✓ Exposure sur ce marché (cette stratégie) < max_per_market
│   │  Vérifie au niveau global :
│   │    ✓ POLY_GLOBAL_RISK_GUARD.status != "ARRÊT TOTAL"
│   │    ✓ Exposure totale toutes stratégies sur ce marché < max_global_per_market
│   │  SI échec → trade bloqué, raison logguée
│
├── REBALANCING NIGHTLY (03:20 UTC, live uniquement)
│   │  Ne réalloue PAS le capital entre stratégies (chaque stratégie a son propre compte).
│   │  Vérifie plutôt :
│   │    ✓ Aucun account live en drawdown > -30% (sinon → suspend, retour paper)
│   │    ✓ Somme des accounts live cohérente avec wallet réel
│   │    ✓ Dry powder suffisant pour le gas
│
└── RÉCUPÉRATION DE CAPITAL (sur événement : stratégie stoppée)
    │  Quand une stratégie passe en "stopped" :
    │    → Capital restant du POLY_STRATEGY_ACCOUNT récupéré
    │    → Revient dans le pool disponible pour de futurs accounts live
    │    → AUDIT_LOG : "account:capital_recovered" {strategy, amount}
```

### Différence Clé vs v3

En v3, le Capital Manager décidait quelle part du capital total chaque stratégie méritait (allocation proportionnelle au score). En v4, avec des comptes indépendants à 1 000€, cette allocation proportionnelle n'est plus nécessaire. Le Capital Manager gère plutôt les limites de risque par compte et la cohérence globale. La "récompense" d'une bonne stratégie n'est plus une allocation plus grande, mais une augmentation du capital de son account lors du scaling (décidée par l'humain).

---

## GRILLE DES FRÉQUENCES v4

### Continu

| Composant | Tick | Justification |
|---|---|---|
| `POLY_MARKET_CONNECTOR` | WebSocket persistent | Remplace PM_FEED, supporte multi-plateformes |
| `POLY_BINANCE_FEED` | WebSocket persistent | BTC temps réel |
| `POLY_BINANCE_SIGNALS` | < 100ms | Edge de latence |
| `POLY_DATA_VALIDATOR` | À chaque donnée reçue | Validation avant consommation |
| `POLY_MARKET_STRUCTURE_ANALYZER` | 30s | Profondeur carnet |
| Tous les STRATEGY_AGENTS | 1s à 2 min selon stratégie | Voir architecture v4 |
| `POLY_EXECUTION_ENGINE` | À chaque signal validé | Exécution immédiate |
| `POLY_KILL_SWITCH` | Tick 5s + pré-trade | Surveillance permanente |
| `POLY_GLOBAL_RISK_GUARD` | Tick 60s + post-trade | Perte globale |
| `POLY_CAPITAL_MANAGER` | Pré-trade + tick 60s | Vérification comptes |
| `POLY_AUDIT_LOG` | À chaque événement | Journalisation immuable |
| `POLY_DATA_STORE` | À chaque écriture | Persistance |

### Minutaire

| Composant | Tick | Justification |
|---|---|---|
| `POLY_NOAA_FEED` | 2 min | Updates NWS |
| `POLY_WALLET_FEED` + `POLY_WALLET_TRACKER` | 60s | Positions on-chain |
| `POLY_SYSTEM_MONITOR` (agents + APIs) | 30-60s | Santé infrastructure |

### Journalier

| Composant | Tick | Justification |
|---|---|---|
| `POLY_SYSTEM_MONITOR` (cohérence) | 02:50 UTC | Avant le cycle nightly |
| `POLY_COMPOUNDER` | 03:00 UTC | Leçons |
| `POLY_STRATEGY_EVALUATOR` | 03:15 UTC | Scores + verdicts |
| `POLY_CAPITAL_MANAGER` (checks nightly) | 03:20 UTC | Vérification accounts |
| `POLY_DECAY_DETECTOR` | 03:30 UTC | Usure |
| `POLY_FACTORY_ORCHESTRATOR` (rapport) | 03:45 UTC | Rapport quotidien |

### Hebdomadaire

| Composant | Tick |
|---|---|
| `POLY_AUDIT_LOG` (rotation) | Dimanche 01:00 UTC |
| `POLY_DATA_STORE` (backup) | Dimanche 02:00 UTC |
| `POLY_STRATEGY_SCOUT` | Dimanche 08:00 UTC |
| Cycle 10 — Réévaluation stratégies stoppées | Dimanche 10:30 UTC |

---

## CYCLE 1 — DÉCOUVERTE DE NOUVELLES STRATÉGIES

> **Fréquence : Hebdomadaire** (dimanche 08:00 UTC)

| | |
|---|---|
| **Déclencheur** | Cron hebdomadaire par `POLY_FACTORY_ORCHESTRATOR` |
| **Input** | Sources publiques + historique `POLY_DATA_STORE` + plateformes `POLY_MARKET_CONNECTOR` |
| **Output** | Fiches stratégies + scores + notification humain |
| **Condition de passage** | Score ≥ 40 + humain approuve → Cycle 3 |
| **Garde-fous** | Max 5 stratégies/semaine, scout ne peut jamais activer, humain décide |
| **Audit Log** | `scout:new_strategy_found`, `strategy_evaluated_preliminary` |

### Ajouts v4

Le `POLY_STRATEGY_SCOUT` prend en compte les connecteurs disponibles dans `POLY_MARKET_CONNECTOR`. Si `connector_kalshi` est actif, le scout peut proposer des stratégies cross-platform. Si seul `connector_polymarket` est actif, les stratégies cross-platform sont filtrées (notées comme "requiert Kalshi, connecteur non disponible").

Le scout consulte aussi les stratégies en statut `stopped` dans le `POLY_DATA_STORE` : si les conditions de marché semblent avoir changé pour une stratégie stoppée, il peut la signaler pour réévaluation (voir Cycle 10).

### Déroulement

```
1.1 — ORCHESTRATOR déclenche SCOUT
     → Passe : blacklist + connecteurs actifs + stratégies stoppées
1.2 — SCOUT scrape et filtre
     → Filtre selon plateformes disponibles (POLY_MARKET_CONNECTOR)
1.3 — Persistance dans DATA_STORE
1.4 — EVALUATOR score préliminaire
1.5 — SI score ≥ 40 → notification humain
     → SI stratégie stoppée détectée pour réévaluation → flag pour Cycle 10
```

---

## CYCLE 2 — COLLECTE DE DONNÉES ET GÉNÉRATION DE SIGNAUX

> **Fréquence : Continu**

| | |
|---|---|
| **Déclencheur** | Démarrage du système |
| **Input** | APIs via POLY_MARKET_CONNECTOR + Binance + NWS + Polygon + NEWS_FEED |
| **Output** | state/feeds/*.json (données validées) + historical/*.db |
| **Condition de passage** | Alimente Cycles 4 et 7 en permanence |
| **Garde-fous** | POLY_DATA_VALIDATOR filtre les données corrompues, POLY_SYSTEM_MONITOR surveille les APIs |
| **Audit Log** | `feed_connected`, `data:validation_failed`, `system:api_degraded` |

### Flux Ajusté v4

```
APIs externes
  │
  ▼
POLY_MARKET_CONNECTOR (Polymarket + Kalshi futur)
POLY_BINANCE_FEED
POLY_NOAA_FEED
POLY_WALLET_FEED
NEWS_FEED (existant)
  │
  ▼ POLY_DATA_VALIDATOR ← NOUVEAU v4
  │  Vérifie prix, timestamps, cohérence, doublons, plages
  │  Marque "SUSPECT" si échec → non consommé par STRATEGY_AGENTS
  │
  ▼ state/feeds/*.json (données validées uniquement)
  │
  ▼ POLY_BINANCE_SIGNALS, POLY_WALLET_TRACKER, POLY_MARKET_STRUCTURE_ANALYZER
  │  (enrichissent les données validées)
  │
  ▼ STRATEGY_AGENTS consomment
```

### POLY_SYSTEM_MONITOR dans ce cycle

Le `POLY_SYSTEM_MONITOR` surveille en continu l'état des APIs et des feeds. Si une API est dégradée (latence > 3× normale), il notifie le `POLY_KILL_SWITCH` qui suspend les stratégies dépendantes. Si une API est totalement down, c'est un NIVEAU 3 (stop trading sur les stratégies concernées).

---

## CYCLE 3 — BACKTEST

> **Fréquence : Sur événement**

| | |
|---|---|
| **Déclencheur** | Scout + humain OK / Tuner / Humain manuellement |
| **Input** | historical/*.db + paramètres stratégie + plateformes ciblées |
| **Output** | backtest_results/ + score Evaluator post-malus |
| **Condition de passage** | Score (post-malus -15) ≥ 40 + humain → Cycle 4 |
| **Garde-fous** | Malus -15 tradabilité, max 3 simultanés, paper obligatoire après |
| **Audit Log** | `backtest_started`, `backtest_completed` |

### Ajout v4 : Multi-plateformes

Si la stratégie cible plusieurs plateformes (ex: arb Polymarket vs Kalshi), le backtest utilise les données historiques des deux plateformes via `POLY_MARKET_CONNECTOR`. Si les données historiques d'une plateforme sont insuffisantes, le backtest le signale explicitement et le malus de tradabilité est augmenté à -25 (au lieu de -15).

### Ajout v4 : Validation des données historiques

Avant de lancer le replay, `POLY_DATA_VALIDATOR` vérifie la qualité des données historiques : pas de trous > 1h, pas de prix aberrants, couverture temporelle suffisante. Si les données sont de mauvaise qualité, le backtest est annulé avec raison "data_quality_insufficient".

---

## CYCLE 4 — PAPER TRADING

> **Fréquence : Continu** (chaque stratégie sur son propre POLY_STRATEGY_ACCOUNT)

| | |
|---|---|
| **Déclencheur** | Humain approuve passage en paper |
| **Input** | Signaux validés (Cycle 2) + POLY_STRATEGY_ACCOUNT paper (1 000€ fictifs) |
| **Output** | paper_trades_log.jsonl + account mis à jour + métriques |
| **Condition de passage** | ≥ 50 trades + ≥ 14j + score ≥ 60 → Cycle 6 |
| **Garde-fous** | 7 filtres (v4), Kill Switch, Global Risk Guard, Data Validator, capital 1 000€ isolé |
| **Audit Log** | Chaque signal, rejet, trade, résolution + contexte account |

### Stratégies Indépendantes en Parallèle

Chaque stratégie en paper testing a son propre `POLY_STRATEGY_ACCOUNT` avec 1 000€ fictifs. Jusqu'à 8 stratégies peuvent tourner en parallèle en paper. Elles partagent les mêmes données (Cycle 2) mais chacune a son propre capital, son propre P&L et son propre compteur de trades. La chaîne de filtres vérifie les limites du COMPTE de la stratégie, pas d'un pool global.

### Chaîne de Filtres v4 (7 filtres)

```
Signal brut du STRATEGY_AGENT
  │ → AUDIT_LOG : "signal_generated" {strategy, account_id, market, platform}
  │
  ▼ FILTRE 0 — DATA QUALITY (POLY_DATA_VALIDATOR) ← NOUVEAU v4
  │  Vérifie : données du marché ciblé pas marquées "SUSPECT"
  │  SI données suspectes → signal rejeté, raison "data_quality"
  │
  ▼ FILTRE 1 — MICROSTRUCTURE (POLY_MARKET_STRUCTURE_ANALYZER)
  │  Vérifie : executability >= 40, slippage_1k < 2%, depth > $500/côté
  │
  ▼ FILTRE 2 — RÉSOLUTION (POLY_MARKET_ANALYST, si non-arb)
  │  Vérifie : ambiguity < 3, unexpected_risk < 5
  │
  ▼ FILTRE 3 — SIZING (POLY_KELLY_SIZER + POLY_ORDER_SPLITTER)
  │  Calcule : Kelly basé sur le capital du POLY_STRATEGY_ACCOUNT (1 000€), PAS sur le capital global
  │  Vérifie : taille < 3% du capital du compte
  │
  ▼ FILTRE 4 — KILL SWITCH (POLY_KILL_SWITCH)
  │  Vérifie : drawdown du POLY_STRATEGY_ACCOUNT, pertes consécutives, feeds actifs
  │
  ▼ FILTRE 5 — RISQUE GLOBAL (POLY_RISK_GUARDIAN)
  │  Vérifie : exposure globale < 80%, positions < 5 toutes stratégies
  │
  ▼ FILTRE 6 — CAPITAL ACCOUNT (POLY_CAPITAL_MANAGER)
  │  Vérifie : account.capital.current ≥ trade_size
  │  Vérifie : POLY_GLOBAL_RISK_GUARD.status != "ARRÊT TOTAL"
  │
  ▼ EXÉCUTION — POLY_EXECUTION_ENGINE (mode paper)
     Met à jour le POLY_STRATEGY_ACCOUNT de cette stratégie
     → AUDIT_LOG : "order_simulated" {account_id, fill_price, slippage, pnl_account}
```

### Comparaison entre Stratégies

Puisque chaque stratégie part de 1 000€, l'Evaluator (Cycle 5) peut produire un classement normalisé à tout moment :

```
PAPER TESTING — Classement Live (jour 10)
#1 POLY_ARB_SCANNER    1 042€ (+4.2%)  32 trades  WR 87%
#2 POLY_WEATHER_ARB    1 018€ (+1.8%)  15 trades  WR 80%
#3 POLY_LATENCY_ARB      993€ (-0.7%)  28 trades  WR 57%
#4 POLY_CONVERGENCE       971€ (-2.9%)   8 trades  WR 50%
```

---

## CYCLE 5 — ÉVALUATION DES PERFORMANCES

> **Fréquence : Journalier** (03:15 UTC) **+ milestone 50 trades**

| | |
|---|---|
| **Déclencheur** | Cron nightly 03:15 / milestone 50 trades |
| **Input** | POLY_STRATEGY_ACCOUNT de chaque stratégie + métriques + alertes decay |
| **Output** | Scores 8 axes + verdicts + classement normalisé + recommendation |
| **Condition de passage** | Score ≥ 60 paper → Cycle 6. Score < 40 live → Cycle 9. Score < 20 → RETIRE |
| **Garde-fous** | Ne peut jamais approuver le live seul, scores historisés |
| **Audit Log** | `"strategy_evaluated"` avec score, verdict, capital account, comparaison |

### Évaluation Basée sur les Comptes

L'Evaluator lit chaque `POLY_STRATEGY_ACCOUNT` directement. Le rendement est calculé sur le capital du compte (1 000€), ce qui normalise la comparaison. Le classement global est envoyé à l'humain dans le rapport nightly.

### Ajout v4 : Vérification POLY_GLOBAL_RISK_GUARD

Avant de proposer une stratégie au passage live (Cycle 6), l'Evaluator vérifie que `POLY_GLOBAL_RISK_GUARD` est en statut NORMAL. Si le système est en ALERTE ou au-delà, aucune nouvelle stratégie ne peut être proposée au live.

---

## CYCLE 6 — VALIDATION HUMAINE

> **Fréquence : Sur événement**

| | |
|---|---|
| **Déclencheur** | Score ≥ 60 + ≥ 50 trades paper + ≥ 14j + GLOBAL_RISK_GUARD NORMAL |
| **Input** | Dossier complet + POLY_STRATEGY_ACCOUNT paper + comparaison avec les autres stratégies |
| **Output** | Approbation JSON signée (expire 7j) → création account live |
| **Condition de passage** | GO → Cycle 7 (Capital Manager crée account live). CONTINUE → Cycle 4. REJECT → archivé |
| **Garde-fous** | Approbation expire 7j, capital alloué APRÈS validation, GLOBAL_RISK_GUARD vérifié |
| **Audit Log** | `"approval_granted"`, `"account:live_created"`, `"strategy_rejected_by_human"` |

### Séquence v4 : Évaluation → Approbation → PUIS Allocation

```
POLY_STRATEGY_EVALUATOR produit le score (Cycle 5)
  │
  ▼ Score ≥ 60 + critères paper remplis
  │
  ▼ POLY_GLOBAL_RISK_GUARD vérifie : perte globale permet un nouveau compte live ?
  │  SI non → stratégie reste en paper, humain notifié "global risk too high"
  │
  ▼ ORCHESTRATOR prépare le dossier pour l'humain
  │
  ▼ HUMAIN décide : GO / CONTINUE / REJECT
  │
  ▼ SI GO :
  │  → POLY_CAPITAL_MANAGER crée le POLY_STRATEGY_ACCOUNT live (1 000€ réels) ← v4
  │  → L'allocation n'existe qu'à partir de ce moment
  │  → AUDIT_LOG : "account:live_created" + "approval_granted"
  │
  ▼ SI CONTINUE :
  │  → Stratégie reste sur son account paper
  │  → Humain peut demander seuil plus élevé (100 trades au lieu de 50)
  │
  ▼ SI REJECT :
     → POLY_STRATEGY_ACCOUNT paper archivé
     → Stratégie → "stopped" (disponible pour Cycle 10 réactivation)
```

### Dossier Humain v4

```
DOSSIER DE VALIDATION — {stratégie}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION 1 — PERFORMANCE (via POLY_STRATEGY_ACCOUNT)
  Capital initial : 1 000€ fictifs
  Capital actuel : 1 042€ (+4.2%)
  Trades : 67 / Win Rate : 87% / Sharpe : 2.34 / MDD : -3.1%

SECTION 2 — TRADABILITÉ + COMPARAISON
  Tradability rate : 72% / Slippage moyen : 0.3%
  Classement : #1 sur 4 stratégies en test

SECTION 3 — ÉTAT DU SYSTÈME
  POLY_GLOBAL_RISK_GUARD : NORMAL (847€ / 4 000€ utilisés)
  Nombre de stratégies live actives : 2 / 5 max
  Capital live déployé : 2 000€ / capacité restante : 3 000€

SECTION 4 — PLATEFORME
  Marché cible : Polymarket (connector_polymarket actif)
  Cross-platform requis : Non

SECTION 5 — PROPOSITION
  Capital live recommandé : 1 000€
  Kill-switch du compte : -30% max
```

---

## CYCLE 7 — LIVE TRADING

> **Fréquence : Continu** (quand activé)

| | |
|---|---|
| **Déclencheur** | Approbation humaine + POLY_STRATEGY_ACCOUNT live créé + flag `--live` |
| **Input** | Signaux validés + POLY_STRATEGY_ACCOUNT live + POLY_MARKET_CONNECTOR |
| **Output** | live_trades_log.jsonl + account live mis à jour + comparaison paper/live |
| **Condition de passage** | Nightly → Cycle 5. Decay → Cycle 8. Score < 40 → Cycle 9 |
| **Garde-fous** | Kill Switch strict, Global Risk Guard, Data Validator, account isolé, wallet isolé |
| **Audit Log** | Chaque ordre, fill, retry, settlement avec account_id et tx_hash |

### Stratégies Indépendantes en Live

Chaque stratégie live a son propre `POLY_STRATEGY_ACCOUNT` avec 1 000€ réels. Max 5 stratégies live simultanées. Les trades de chaque stratégie n'impactent QUE son propre compte. Si POLY_ARB_SCANNER perd 100€, seul le compte de ARB_SCANNER est affecté — les 1 000€ de POLY_WEATHER_ARB restent intacts.

### Vérifications Pré-Trade v4

```
✓ flag --live actif
✓ approbation JSON existe + non expirée (< 7j)
✓ POLY_STRATEGY_ACCOUNT.status == "active"
✓ POLY_STRATEGY_ACCOUNT.capital.current ≥ trade_size
✓ POLY_STRATEGY_ACCOUNT.drawdown.current_pct > max_allowed_pct (-30%)
✓ POLY_GLOBAL_RISK_GUARD.status != "ARRÊT TOTAL" et != "CRITIQUE"
✓ POLY_DATA_VALIDATOR : données du marché ciblé pas "SUSPECT"
✓ POLY_SYSTEM_MONITOR : API plateforme cible opérationnelle
✓ POLY_EXECUTION_ENGINE.api_health.status == "connected"
✓ POLY_KILL_SWITCH.global_status == "active"
✓ POLY_MARKET_CONNECTOR : connecteur plateforme cible actif

SI une seule échoue → trade bloqué → AUDIT_LOG : "order_rejected_live" {account_id, reason}
```

### Multi-Plateformes en Live

Si une stratégie cible plusieurs plateformes (arb Polymarket vs Kalshi), le `POLY_EXECUTION_ENGINE` soumet les ordres à chaque plateforme via `POLY_MARKET_CONNECTOR`. Chaque leg de l'arb est loggué séparément dans l'audit log avec la plateforme source.

---

## CYCLE 8 — DÉTECTION D'USURE / DECAY

> **Fréquence : Journalier** (03:30 UTC) **+ intra-day** (Kill Switch tick 5s)

| | |
|---|---|
| **Déclencheur** | Cron nightly 03:30 / Kill Switch anomalie intra-day |
| **Input** | POLY_STRATEGY_ACCOUNT (30j historique) + métriques rolling |
| **Output** | decay_alerts.json + actions auto sur accounts + notifications |
| **Condition de passage** | WARNING → rien. SERIOUS → Cycle 9. CRITICAL → suspension |
| **Garde-fous** | Ne peut pas RETIRER, seulement SUSPENDRE (passe account en "paused") |
| **Audit Log** | `"decay_alert"` avec sévérité, métriques, account_id, action prise |

### Impact sur les POLY_STRATEGY_ACCOUNT

| Sévérité | Action sur le compte |
|---|---|
| HEALTHY | Aucune |
| WARNING | Log. Aucune action sur le compte. |
| SERIOUS | account.status → "paused" si live. Capital gelé. Tuner déclenché. |
| CRITICAL | account.status → "paused". Si live → retour paper automatique. Notification URGENTE. |

Un account en "paused" conserve son capital mais n'émet plus de trades. Il peut être réactivé (retour en paper_testing pour re-validation) ou stoppé.

---

## CYCLE 9 — OPTIMISATION OU RETRAIT

> **Fréquence : Sur événement**

| | |
|---|---|
| **Déclencheur** | Decay SERIOUS/CRITICAL / Evaluator < 60 / Milestone 50 trades |
| **Input** | POLY_STRATEGY_ACCOUNT + 50+ trades + decay + audit log |
| **Output** | Paramètres optimisés OU account → "stopped" + leçons Compounder |
| **Condition de passage** | Score post-tuning ≥ 60 → retour Cycle 4/7. Score < 20 ou 3 échecs → STOPPED |
| **Garde-fous** | Tuner jamais avant 50 trades, changements live soumis humain |
| **Audit Log** | `"tuning_recommendation"`, `"account:status_changed"`, `"strategy_stopped"` |

### Branche Retrait v4

Quand une stratégie est stoppée :

```
9.6 — Account → "stopped"
  → Capital restant récupéré par POLY_CAPITAL_MANAGER
  → POLY_STRATEGY_ACCOUNT archivé (jamais supprimé)
  → Toutes les données conservées pour référence future
  → AUDIT_LOG : "strategy_stopped" {account_id, reason, final_capital, total_pnl, lifetime}

9.7 — La stratégie N'EST PAS supprimée
  → Elle reste dans le POLY_DATA_STORE avec statut "stopped"
  → Le Cycle 10 peut la réévaluer plus tard
```

---

## CYCLE 10 — RÉÉVALUATION DES STRATÉGIES STOPPÉES

> **Fréquence : Hebdomadaire** (dimanche 10:30 UTC) **+ sur événement**

| | |
|---|---|
| **Déclencheur** | (1) Cron hebdomadaire 10:30 UTC (2) POLY_STRATEGY_SCOUT signale un changement de conditions (3) Nouveau connecteur POLY_MARKET_CONNECTOR activé (4) Humain demande manuellement |
| **Input** | POLY_STRATEGY_ACCOUNT archivés (status "stopped") + conditions de marché actuelles + données POLY_MARKET_CONNECTOR |
| **Output** | Recommandation de réactivation OU confirmation du retrait |
| **Condition de passage** | Réactivation approuvée par humain → NOUVEAU account paper → Cycle 4 |
| **Garde-fous** | Réactivation = NOUVEAU account paper (jamais réactivation directe en live), humain obligatoire |
| **Audit Log** | `"strategy:reeval_started"`, `"strategy:reactivation_proposed"`, `"account:paper_created_reactivation"` |

### Pourquoi ce Cycle est Nécessaire

Les edges Polymarket sont cycliques. Une stratégie d'arb qui ne marchait plus en janvier (trop de concurrence) peut redevenir profitable en juin (concurrents partis, nouvelle liquidité). Un connector Kalshi qui n'existait pas rend soudainement viable une stratégie cross-platform qui avait été rejetée.

Sans Cycle 10, les stratégies stoppées sont des connaissances perdues. Le système a investi du temps et des tokens LLM pour les tester — les recycler quand les conditions changent a un coût marginal quasi nul.

### Déroulement

```
ÉTAPE 10.1 — ORCHESTRATOR compile la liste des stratégies "stopped"
  Input  : POLY_DATA_STORE → tous les POLY_STRATEGY_ACCOUNT en status "stopped"
  Output : liste avec raison du retrait, date, métriques finales

ÉTAPE 10.2 — Analyse des conditions actuelles
  Pour chaque stratégie stoppée :
    → Quelle était la raison du retrait ?
    → Cette raison est-elle toujours valide ?

  Exemples de changements détectables :
    - "competition_pressure > 80%" → Vérifier: le competition_pressure actuel sur
      le même type de marchés a-t-il baissé ?
    - "executability_score < 40" → Vérifier: la liquidité a-t-elle augmenté ?
    - "connector_kalshi required" → Vérifier: connector_kalshi est-il maintenant actif ?
    - "win_rate < breakeven" → Vérifier: les conditions qui causaient les pertes
      ont-elles changé (nouveau market maker, volume accru) ?

ÉTAPE 10.3 — Score de réévaluation
  SI les conditions semblent avoir changé :
    → POLY_BACKTEST_ENGINE relance un backtest sur les données récentes (30 derniers jours)
    → POLY_STRATEGY_EVALUATOR score le résultat
    → SI score ≥ 40 → proposer la réactivation à l'humain

ÉTAPE 10.4 — Décision humaine
  L'humain reçoit :
    - Rappel : pourquoi la stratégie avait été stoppée
    - Ce qui a changé depuis
    - Résultat du backtest récent
    - Score Evaluator

  Décisions :
    GO RÉACTIVATION → NOUVEAU POLY_STRATEGY_ACCOUNT paper créé (1 000€ fictifs, compteurs à zéro)
                    → L'ancien account reste archivé
                    → La stratégie repasse en "paper_testing" → tout le pipeline recommence
    MAINTENIR STOPPED → Rien ne change, réévalué à nouveau la semaine suivante
```

### Ce que la Réactivation NE FAIT PAS

La réactivation ne remet JAMAIS une stratégie directement en live. Elle crée un NOUVEAU compte paper et la stratégie doit re-prouver sa valeur en passant par tous les cycles : paper (50 trades, 14j) → évaluation → validation humaine → micro-live. L'ancien compte reste archivé pour référence — on peut comparer les performances v1 (avant retrait) vs v2 (après réactivation).

---

## MÉCANISMES TRANSVERSAUX (rappel, inchangés vs v3 sauf ajouts)

### POLY_KILL_SWITCH

5 niveaux de réponse inchangés. Ajout v4 : vérifie le drawdown du `POLY_STRATEGY_ACCOUNT` de chaque stratégie (pas un drawdown global). Si `account.drawdown.current_pct > account.drawdown.max_allowed_pct (-30%)` → stratégie stoppée.

### POLY_EXECUTION_ENGINE

Architecture bi-mode inchangée. Ajout v4 : soumet les ordres via `POLY_MARKET_CONNECTOR` (pas directement via py-clob-client). Cela permet l'exécution sur n'importe quelle plateforme connectée. Le P&L de chaque trade met à jour le `POLY_STRATEGY_ACCOUNT` correspondant.

### POLY_AUDIT_LOG

Types d'événements inchangés. Ajouts v4 : catégorie DATA (`data:validation_failed`, `data:stale_detected`), catégorie SYSTEM étendue (`system:api_degraded`, `system:coherence_error`), catégorie ACCOUNT (`account:live_created`, `account:capital_recovered`, `account:paper_created_reactivation`).

---

## SYNTHÈSE — CHRONOLOGIE D'UNE JOURNÉE TYPE

### 00:00 UTC — Reset

```
POLY_KILL_SWITCH       : reset compteurs daily par POLY_STRATEGY_ACCOUNT
POLY_AUDIT_LOG         : rotation fichier
POLY_DATA_VALIDATOR    : reset compteurs d'anomalies
```

### 00:00-02:50 UTC — Trading Actif

```
CONTINU  : Cycles 2, 4, 7 — collecte → validation → signaux → paper/live
CONTINU  : POLY_DATA_VALIDATOR — vérifie chaque donnée entrante
CONTINU  : POLY_SYSTEM_MONITOR — surveille agents + APIs (30-60s)
CONTINU  : POLY_KILL_SWITCH + POLY_GLOBAL_RISK_GUARD — protection
CONTINU  : POLY_EXECUTION_ENGINE via POLY_MARKET_CONNECTOR — exécute
CONTINU  : POLY_AUDIT_LOG — journalise tout
```

### 02:50-04:00 UTC — Cycle Nightly

```
02:50  POLY_SYSTEM_MONITOR         → Vérification cohérence pré-nightly
03:00  POLY_COMPOUNDER             → Leçons (utilise AUDIT_LOG)
03:15  POLY_STRATEGY_EVALUATOR     → Scores basés sur POLY_STRATEGY_ACCOUNT
03:20  POLY_CAPITAL_MANAGER        → Vérification accounts + cohérence wallet
03:30  POLY_DECAY_DETECTOR         → Usure par account
03:35  POLY_STRATEGY_TUNER         → Si déclenché
03:45  POLY_FACTORY_ORCHESTRATOR   → Rapport + actions auto (downgrade, suspend)
04:00  Notification humain          → Résumé avec classement des comptes
```

### 08:00 UTC (dimanche) — Cycles Hebdomadaires

```
01:00  POLY_AUDIT_LOG              → Rotation archives
02:00  POLY_DATA_STORE             → Backup SQLite
08:00  POLY_STRATEGY_SCOUT         → Découverte (Cycle 1)
10:30  POLY_FACTORY_ORCHESTRATOR   → Réévaluation stratégies stoppées (Cycle 10)
```

---

## SYNTHÈSE — MATRICE COMPLÈTE I/O v4

| Cycle | Agents principaux | Input | Output | Fréquence |
|---|---|---|---|---|
| **1 Découverte** | SCOUT + EVALUATOR | Sources + connecteurs actifs | Fiches + scores | Hebdo |
| **2 Collecte** | MARKET_CONNECTOR + FEEDS + DATA_VALIDATOR | APIs multi-plateformes | feeds/*.json validés | Continu |
| **3 Backtest** | BACKTEST + EVALUATOR | historical/*.db + params | Résultats + score | Événement |
| **4 Paper** | STRAT + 7 FILTRES + EXEC_ENGINE | Signaux validés + account paper | Trades + account MAJ | Continu |
| **5 Évaluation** | EVALUATOR | STRATEGY_ACCOUNTS + métriques | Scores + classement normalisé | Nightly |
| **6 Validation** | ORCHESTRATOR + humain | Dossier + état GLOBAL_RISK | Approbation → account live créé | Événement |
| **7 Live** | STRAT + 7 FILTRES + EXEC_ENGINE | Signaux + account live | Trades réels + account MAJ | Continu |
| **8 Decay** | DECAY_DETECTOR | Accounts (30j) + rolling | Alertes + account → paused | Nightly |
| **9 Optimisation** | TUNER + BACKTEST + COMPOUNDER | Account + trades + audit | Params optimisés OU stopped | Événement |
| **10 Réévaluation** | ORCHESTRATOR + BACKTEST + EVALUATOR | Accounts stoppés + conditions | Réactivation proposée | Hebdo |

**Couches transversales :**

| Couche | Rôle | Nouveau v4 |
|---|---|---|
| `POLY_KILL_SWITCH` | Protection par stratégie/session | Vérifie drawdown par account |
| `POLY_GLOBAL_RISK_GUARD` | Perte globale max 4 000€ | **Nouveau** |
| `POLY_CAPITAL_MANAGER` | Gestion accounts, allocation post-validation | **Ajusté** |
| `POLY_MARKET_CONNECTOR` | Multi-plateformes | **Nouveau** |
| `POLY_SYSTEM_MONITOR` | Santé infrastructure | **Nouveau** |
| `POLY_DATA_VALIDATOR` | Qualité des données | **Nouveau** |
| `POLY_EXECUTION_ENGINE` | Exécution via connecteurs | Ajusté |
| `POLY_AUDIT_LOG` | Journalisation immuable | Étendu |
| `POLY_DATA_STORE` | Persistance + accounts | Étendu |

---

## SYNTHÈSE — VUE COMPLÈTE DES TRANSITIONS v4

```
 [SCOUTED] ──► [EVALUATED] ──► [BACKTESTED] ──► [PAPER_TESTING]
                                                   (account 1 000€ fictifs)
                                                        │
                                                   ≥ 50 trades + 14j
                                                        ▼
                                                   [PAPER_EVALUATED]
                                                        │
                                                   score ≥ 60 + GLOBAL_RISK OK
                                                        ▼
                                                   [AWAITING_HUMAN_GO]
                                                        │
                            ┌── GO ─────────────────────┤
                            │                           ├── CONTINUE → [PAPER_TESTING]
                            │                           └── REJECT → [STOPPED]
                            ▼
                    [MICRO_LIVE]
                    (account 1 000€ réels créé)
                            │
                       7j + humain
                            ▼
                    [SCALING] ──► [ACTIVE]
                                    │
                               decay / score < 40
                                    ▼
                               [PAUSED] ──► retour [PAPER_TESTING] ou [STOPPED]
                                    │
                               score < 20 / 3 échecs / humain
                                    ▼
                               [STOPPED]
                                    │
                               Cycle 10 (hebdomadaire)
                               conditions changées ?
                                    │
                               humain approuve réactivation
                                    ▼
                               NOUVEAU [PAPER_TESTING]
                               (nouvel account 1 000€ fictifs)

À tout moment :
  POLY_KILL_SWITCH       → suspend par account
  POLY_GLOBAL_RISK_GUARD → arrêt total si perte ≥ 4 000€
  POLY_DATA_VALIDATOR    → bloque si données corrompues
  POLY_SYSTEM_MONITOR    → alerte si infrastructure défaillante
  POLY_AUDIT_LOG         → enregistre chaque transition
```

---

*Version 4.0. Changements vs v3 : POLY_STRATEGY_ACCOUNT (1 000€ indépendant par stratégie), POLY_GLOBAL_RISK_GUARD (plafond 4 000€), POLY_MARKET_CONNECTOR (multi-plateformes), POLY_SYSTEM_MONITOR (santé infrastructure), POLY_DATA_VALIDATOR (qualité données, filtre 0 dans la chaîne), Cycle 10 réévaluation (réactivation stratégies stoppées), POLY_CAPITAL_MANAGER ajusté (allocation APRÈS validation humaine), chaîne à 7 filtres.*
