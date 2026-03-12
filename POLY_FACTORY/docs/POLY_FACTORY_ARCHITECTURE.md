# POLY_FACTORY — Architecture Système Complète

> **Version 4.0 — 12 mars 2026**
> Architecture du système automatisé de découverte, test, optimisation et déploiement de stratégies Polymarket et marchés de prédiction.
> Compatible avec l'environnement OpenClaw existant.

---

## CHANGEMENTS v4

| Ajout | Rôle |
|---|---|
| `POLY_STRATEGY_ACCOUNT` | Chaque stratégie fonctionne comme une unité financière indépendante avec son propre capital, P&L et historique |
| `POLY_GLOBAL_RISK_GUARD` | Surveillance des pertes globales cumulées sur toutes les stratégies, seuil maximum 4 000€, mode sécurité |
| `POLY_MARKET_CONNECTOR` | Abstraction multi-plateformes permettant de connecter Polymarket, Kalshi, sportsbooks et toute nouvelle plateforme |
| Objectifs mis à jour | POLY_FACTORY est un portefeuille de stratégies indépendantes à tester, comparer, arrêter et potentiellement réactiver |

---

## CONVENTION DE NOMMAGE

Tous les agents POLY_FACTORY portent le préfixe **`POLY_`**. Les agents OpenClaw existants réutilisés conservent leur nom d'origine.

---

## TABLE DES MATIÈRES

1. Vision et Objectifs
2. Modèle Financier — POLY_STRATEGY_ACCOUNT
3. Architecture Globale
4. Tous les Agents
5. Tous les Skills
6. Rôle Exact de Chaque Agent
7. Interactions Entre Agents
8. Flux de Données et Couche de Stockage
9. Pipeline Paper Trading
10. Pipeline de Validation — Passage en Réel
11. Supervision Humaine
12. Veille Stratégique
13. Évaluation et Optimisation des Stratégies
14. Tradabilité Réelle — Le Filtre Ultime
15. Connecteurs Multi-Plateformes — POLY_MARKET_CONNECTOR
16. Intégration OpenClaw
17. Ressources et Accès Nécessaires
18. Garde-fous de Sécurité

---

## 1. VISION ET OBJECTIFS

### 1.1 — Mission

POLY_FACTORY est un **portefeuille de stratégies indépendantes** qui tourne sur les marchés de prédiction. Chaque stratégie est une unité autonome avec son propre capital, ses propres métriques et son propre cycle de vie. Le système découvre de nouvelles stratégies, les teste avec de l'argent fictif, les compare entre elles, arrête celles qui perdent, et ne déploie en réel que celles qui ont prouvé leur valeur — sur validation humaine explicite.

Le vrai objectif n'est pas de tester des idées. C'est d'**identifier les stratégies réellement monétisables dans le temps** et de construire un portefeuille diversifié qui résiste à l'usure individuelle de chaque edge.

### 1.2 — Principes Fondamentaux

| Principe | Règle |
|---|---|
| **Humain dans la boucle** | Le passage fictif → réel n'est JAMAIS automatique. |
| **Stratégie = unité indépendante** | Chaque stratégie a son propre compte (POLY_STRATEGY_ACCOUNT) avec capital, P&L et historique isolés. |
| **Perte globale plafonnée** | POLY_GLOBAL_RISK_GUARD coupe tout si les pertes cumulées dépassent 4 000€. |
| **Multi-plateformes natif** | L'architecture supporte nativement Polymarket ET d'autres marchés via POLY_MARKET_CONNECTOR. |
| **Code gère le risque** | Sizing, stop-loss, kill-switch = déterministe, jamais un LLM. |
| **Zéro LLM chemin critique** | Détection → décision → exécution d'arb = zéro appel LLM. |
| **Signals ≠ Strategies** | Agents de signaux séparés des agents de stratégie. |
| **Tradabilité réelle** | Un edge théorique ne vaut rien s'il ne survit pas au marché réel. |
| **Orchestration centralisée** | Un orchestrateur coordonne tous les agents. |
| **Survive first** | On préfère rater 100 trades que perdre du capital. |
| **Compound Learning** | Chaque trade produit une leçon réutilisable. |

### 1.3 — Objectifs Opérationnels

Le système doit être capable de :

1. **Tester simultanément plusieurs stratégies** — chacune avec 1 000€ de capital fictif, isolées les unes des autres.
2. **Comparer leurs performances** — via un classement unifié (POLY_STRATEGY_EVALUATOR) rendu possible par le fait que chaque stratégie démarre avec le même capital.
3. **Arrêter les stratégies perdantes** — automatiquement si les seuils sont atteints, ou sur décision humaine.
4. **Réactiver des stratégies mises en pause** — si les conditions de marché changent et que l'edge semble revenir.
5. **Rechercher en permanence de nouvelles stratégies** — les edges s'usent, le pipeline de découverte ne s'arrête jamais.
6. **Plafonner les pertes globales** — maximum 4 000€ de perte cumulée sur l'ensemble du système avant arrêt total.

### 1.4 — Paramètres Financiers

| Paramètre | Valeur |
|---|---|
| Capital de test par stratégie (paper) | 1 000€ fictifs |
| Capital réel de départ par stratégie | 1 000€ réels |
| Perte maximale globale acceptable | 4 000€ |
| Nombre max de stratégies en test simultané | 8 |
| Nombre max de stratégies en live simultané | 5 |

### 1.5 — Contraintes Opérationnelles Immuables

1. Stratégies testées en argent fictif d'abord. Aucune exception.
2. Passage en réel = validation humaine explicite obligatoire.
3. Compatible avec l'environnement OpenClaw existant.
4. Recherche permanente de nouvelles stratégies.
5. Perte globale > 4 000€ → arrêt total automatique de toutes les stratégies.

---

## 2. MODÈLE FINANCIER — POLY_STRATEGY_ACCOUNT

### 2.1 — Concept

Chaque stratégie dans POLY_FACTORY fonctionne comme une **unité financière indépendante** avec son propre compte isolé. Ce modèle s'appelle `POLY_STRATEGY_ACCOUNT`.

C'est la brique qui transforme POLY_FACTORY d'un "système qui teste des idées" en un "portefeuille de stratégies comparables et pilotables".

### 2.2 — Pourquoi ce Modèle

Sans comptes indépendants par stratégie, trois problèmes concrets apparaissent :

1. **Comparaison impossible** — Si POLY_ARB_SCANNER et POLY_WEATHER_ARB partagent un même pool de capital, impossible de savoir laquelle génère quel P&L. Les métriques sont mélangées, le Sharpe ratio est celui du pool, pas de la stratégie.

2. **Contagion des pertes** — Une stratégie perdante consomme le capital d'une stratégie gagnante. La perdante devrait être arrêtée, mais comme le pool global est encore positif, personne ne la détecte à temps.

3. **Décision de scaling impossible** — Comment décider de doubler le capital d'une stratégie si on ne sait pas exactement combien elle a gagné ou perdu, isolément ?

Avec `POLY_STRATEGY_ACCOUNT`, chaque stratégie est une boîte noire financière : on injecte 1 000€, on mesure ce qui en sort. La comparaison est triviale.

### 2.3 — Structure d'un POLY_STRATEGY_ACCOUNT

```json
{
  "account_id": "ACC_POLY_ARB_SCANNER",
  "strategy": "POLY_ARB_SCANNER",
  "mode": "live",
  "created_at": "2026-04-01T00:00:00Z",

  "capital": {
    "initial": 1000.00,
    "current": 1087.45,
    "currency": "EUR",
    "high_water_mark": 1120.30,
    "low_water_mark": 965.20
  },

  "pnl": {
    "total": 87.45,
    "realized": 72.30,
    "unrealized": 15.15,
    "today": 3.20,
    "this_week": 28.50,
    "this_month": 87.45
  },

  "drawdown": {
    "current": -2.93,
    "max_historical": -3.48,
    "max_allowed": -30.0
  },

  "status": "active",
  "status_history": [
    {"status": "paper_testing", "from": "2026-04-01", "to": "2026-04-15"},
    {"status": "awaiting_human", "from": "2026-04-15", "to": "2026-04-16"},
    {"status": "active", "from": "2026-04-16", "to": null}
  ],

  "performance": {
    "trades_total": 342,
    "win_rate": 0.847,
    "sharpe_ratio": 2.34,
    "profit_factor": 3.12,
    "max_drawdown_pct": -3.48,
    "tradability_rate": 0.72,
    "avg_trade_pnl": 0.26,
    "evaluator_score": 78
  },

  "limits": {
    "max_position_pct": 0.03,
    "max_per_trade": 50.00,
    "kill_switch_daily_pct": -0.05,
    "kill_switch_strategy_pct": -0.30
  }
}
```

### 2.4 — Statuts Possibles d'un Account

| Statut | Signification | Capital utilisé | Transition |
|---|---|---|---|
| `paper_testing` | Test en argent fictif (1 000€ simulés) | Fictif | → `awaiting_human` après 50 trades + 14j + score ≥ 60 |
| `awaiting_human` | En attente de validation humaine | Aucun | → `active` (GO) ou `paused` (CONTINUE) ou `stopped` (REJECT) |
| `active` | Live trading avec capital réel | 1 000€ réels | → `paused` (decay) ou `stopped` (retrait) |
| `paused` | Temporairement suspendu | Capital gelé, pas de trades | → `paper_testing` (réactivation) ou `active` (reprise) ou `stopped` |
| `stopped` | Arrêt définitif | Capital récupéré | → `paper_testing` (réactivation si conditions changent) |

### 2.5 — Réactivation de Stratégies

Une stratégie en statut `stopped` n'est pas forcément morte pour toujours. Si les conditions de marché changent (nouvelle liquidité, concurrence réduite, nouvelle plateforme ajoutée), elle peut être réactivée :

```
RÉACTIVATION :
  1. L'humain OU POLY_STRATEGY_SCOUT détecte que les conditions ont changé
  2. Humain approuve la réactivation
  3. La stratégie repasse en status "paper_testing" avec un NOUVEAU POLY_STRATEGY_ACCOUNT
     (capital fictif 1 000€, compteurs remis à zéro)
  4. Elle doit REPASSER tout le pipeline : 50 trades paper → évaluation → humain → micro-live
  5. L'ancien account reste archivé pour référence (on ne le modifie jamais)
```

Ce mécanisme est essentiel car les edges Polymarket sont cycliques : un arb qui ne marchait plus en janvier peut redevenir profitable en juin si la concurrence a diminué.

### 2.6 — Comment ce Modèle Facilite la Comparaison

Puisque chaque stratégie démarre avec le même capital (1 000€), la comparaison est directe :

```
CLASSEMENT DES STRATÉGIES — Semaine du 14 avril 2026
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

#1  POLY_ARB_SCANNER       1 087€  (+8.7%)  Sharpe 2.34  Score 78  STAR
#2  POLY_LATENCY_ARB       1 052€  (+5.2%)  Sharpe 1.89  Score 71  SOLID
#3  POLY_WEATHER_ARB       1 031€  (+3.1%)  Sharpe 1.45  Score 64  SOLID
#4  POLY_OPP_SCORER        1 012€  (+1.2%)  Sharpe 1.10  Score 55  FRAGILE
#5  POLY_CONVERGENCE_STRAT   988€  (-1.2%)  Sharpe 0.60  Score 42  FRAGILE
#6  POLY_NO_SCANNER          995€  (-0.5%)  Sharpe 0.80  Score 48  FRAGILE
—
    P&L GLOBAL             +165€            Perte globale restante avant arrêt : 3 835€
```

Ce tableau est impossible à produire sans comptes isolés.

### 2.7 — Stockage des Accounts

```
state/accounts/
├── ACC_POLY_ARB_SCANNER.json
├── ACC_POLY_LATENCY_ARB.json
├── ACC_POLY_WEATHER_ARB.json
├── ACC_POLY_OPP_SCORER.json
├── ACC_POLY_CONVERGENCE_STRAT.json
├── ACC_POLY_NO_SCANNER.json
├── ACC_POLY_PAIR_COST.json
├── ACC_POLY_BROWNIAN_SNIPER.json
├── ACC_POLY_NEWS_STRAT.json
└── archive/                         ← Accounts de stratégies stopped
    ├── ACC_POLY_CONVERGENCE_STRAT_v1.json
    └── ...
```

Chaque account est mis à jour par `POLY_DATA_STORE` à chaque trade résolu. Le `POLY_STRATEGY_EVALUATOR` lit les accounts pour produire le classement. Le `POLY_GLOBAL_RISK_GUARD` lit la somme des P&L pour surveiller le seuil global.

---

## 3. ARCHITECTURE GLOBALE

### 3.1 — Vue d'Ensemble en 9 Couches

```
┌────────────────────────────────────────────────────────────────────────┐
│                           POLY_FACTORY                                 │
│                                                                        │
│  C9 — SUPERVISION HUMAINE                                             │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ Dashboard │ Alertes │ Rapports │ Go/No-Go Valve                │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                              ▲                                         │
│  C8 — ORCHESTRATION CENTRALE                                          │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │                  POLY_FACTORY_ORCHESTRATOR                      │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                           ▲ ▼                                          │
│  C7 — ÉVALUATION & AMÉLIORATION                                       │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_STRATEGY_EVALUATOR │ POLY_STRATEGY_TUNER                  │   │
│  │ POLY_DECAY_DETECTOR     │ POLY_COMPOUNDER                      │   │
│  │ POLY_STRATEGY_SCOUT     │ POLY_BACKTEST_ENGINE                  │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                           ▲ ▼                                          │
│  C6 — STOCKAGE + COMPTES                                              │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_DATA_STORE │ POLY_STRATEGY_ACCOUNT (×N, un par stratégie) │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                           ▲ ▼                                          │
│  C5 — GESTION DU RISQUE                                               │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_KILL_SWITCH │ POLY_KELLY_SIZER │ POLY_RISK_GUARDIAN       │   │
│  │ POLY_GLOBAL_RISK_GUARD  ← NOUVEAU v4                          │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                           ▲ ▼                                          │
│  C4 — EXÉCUTION                                                        │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_PAPER_ENGINE │ POLY_LIVE_ENGINE │ POLY_ORDER_SPLITTER     │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                            ▲                                           │
│  C3 — STRATEGY_AGENTS                                                  │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_ARB_SCANNER    │ POLY_LATENCY_ARB  │ POLY_WEATHER_ARB    │   │
│  │ POLY_PAIR_COST      │ POLY_OPP_SCORER   │ POLY_NO_SCANNER     │   │
│  │ POLY_CONVERGENCE    │ POLY_NEWS_STRAT   │ POLY_BROWNIAN       │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                            ▲                                           │
│  C2 — SIGNAL_AGENTS                                                    │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_WALLET_TRACKER │ POLY_MARKET_STRUCTURE_ANALYZER           │   │
│  │ POLY_MARKET_ANALYST │ POLY_BINANCE_SIGNALS                     │   │
│  └────────────────────────────────────────────────────────────────┘   │
│                            ▲                                           │
│  C1 — DATA INGESTION + CONNECTEURS                                     │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ POLY_MARKET_CONNECTOR  ← NOUVEAU v4 (abstraction multi-marché)│   │
│  │  ├── connector_polymarket (CLOB API)                           │   │
│  │  ├── connector_kalshi (REST API) — futur                       │   │
│  │  └── connector_sportsbook — futur                              │   │
│  │ POLY_BINANCE_FEED │ POLY_NOAA_FEED │ POLY_WALLET_FEED         │   │
│  │ NEWS_FEED (existant OpenClaw)                                  │   │
│  └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 — Séparation Paper / Live

```
STRATEGY_AGENT ──► ORCHESTRATOR ──► POLY_STRATEGY_ACCOUNT (vérifie capital)
                                ──► POLY_GLOBAL_RISK_GUARD (vérifie perte globale)
                                ──► MODE SWITCH (défaut = paper)
                                         │            │
                                  POLY_PAPER      POLY_LIVE
                                  _ENGINE         _ENGINE
```

---

## 4. TOUS LES AGENTS

### 4.0 — ORCHESTRATION (C8)

| # | Agent | Type | LLM | Fréquence |
|---|---|---|---|---|
| 0 | `POLY_FACTORY_ORCHESTRATOR` | Python + config | Non | Continu |

### 4.1 — SIGNAL_AGENTS (C1-C2)

| # | Agent | Couche | LLM | Fréquence |
|---|---|---|---|---|
| 1 | `POLY_MARKET_CONNECTOR` | C1 | Non | Continu |
| 2 | `POLY_BINANCE_FEED` | C1 | Non | Continu (WS) |
| 3 | `POLY_NOAA_FEED` | C1 | Non | 2 min |
| 4 | `POLY_WALLET_FEED` | C1 | Non | 60s |
| 5 | `NEWS_FEED` | C1 | **Existant** | — |
| 6 | `POLY_BINANCE_SIGNALS` | C2 | Non | <100ms |
| 7 | `POLY_MARKET_ANALYST` | C2 | Sonnet (1x cache) | À la demande |
| 8 | `POLY_WALLET_TRACKER` | C2 | Non | 60s |
| 9 | `POLY_MARKET_STRUCTURE_ANALYZER` | C2 | Non | 30s |

### 4.2 — STRATEGY_AGENTS (C3)

| # | Agent | LLM | Fréquence |
|---|---|---|---|
| 10 | `POLY_ARB_SCANNER` | Non | 1-5s |
| 11 | `POLY_PAIR_COST` | Non | 2-5s |
| 12 | `POLY_LATENCY_ARB` | Non | <1s |
| 13 | `POLY_BROWNIAN_SNIPER` | Non | Dernières 60s |
| 14 | `POLY_WEATHER_ARB` | Non | 2 min |
| 15 | `POLY_OPP_SCORER` | Sonnet (cache) | Quotidien |
| 16 | `POLY_NO_SCANNER` | Haiku (1x) | Hebdomadaire |
| 17 | `POLY_CONVERGENCE_STRAT` | Non | 60s |
| 18 | `POLY_NEWS_STRAT` | Haiku/Sonnet | Event-driven |

### 4.3 — EXÉCUTION + RISQUE (C4-C5)

| # | Agent | LLM | Fréquence |
|---|---|---|---|
| 19 | `POLY_PAPER_ENGINE` | Non | Continu |
| 20 | `POLY_LIVE_ENGINE` | Non | Si activé |
| 21 | `POLY_ORDER_SPLITTER` | Non | À la demande |
| 22 | `POLY_KILL_SWITCH` | Non | Continu |
| 23 | `POLY_KELLY_SIZER` | Non | À la demande |
| 24 | `POLY_RISK_GUARDIAN` | Non | Continu |
| 25 | `POLY_GLOBAL_RISK_GUARD` | Non | Continu |

### 4.4 — STOCKAGE + COMPTES (C6)

| # | Agent | LLM | Fréquence |
|---|---|---|---|
| 26 | `POLY_DATA_STORE` | Non | Continu |

`POLY_STRATEGY_ACCOUNT` n'est pas un agent mais un modèle de données géré par `POLY_DATA_STORE`. Il y a un account par stratégie active.

### 4.5 — ÉVALUATION & RECHERCHE (C7)

| # | Agent | LLM | Fréquence |
|---|---|---|---|
| 27 | `POLY_STRATEGY_EVALUATOR` | Sonnet (périodique) | Quotidien + events |
| 28 | `POLY_STRATEGY_TUNER` | Sonnet | Post-50 trades |
| 29 | `POLY_DECAY_DETECTOR` | Non | Nightly |
| 30 | `POLY_COMPOUNDER` | Haiku | Nightly |
| 31 | `POLY_STRATEGY_SCOUT` | Sonnet | Hebdomadaire |
| 32 | `POLY_BACKTEST_ENGINE` | Non | À la demande |

### 4.6 — INFRASTRUCTURE

| # | Agent | LLM | Fréquence |
|---|---|---|---|
| 33 | `POLY_HEARTBEAT` | Non | 30 min |
| 34 | `POLY_PERFORMANCE_LOGGER` | Non | Continu |

**Total : 35 agents.** 24 Python pur (zéro LLM). 11 hybrides. `POLY_MARKET_CONNECTOR` remplace `POLY_PM_FEED` en l'englobant. `POLY_GLOBAL_RISK_GUARD` est nouveau.

---

## 5. TOUS LES SKILLS

| Skill | Coût |
|---|---|
| `polymarket-arb-detection` | 0 |
| `polymarket-latency-arb` | 0 |
| `polymarket-weather` | 0 |
| `polymarket-resolution-parser` | ~500 tok/marché |
| `polymarket-wallet-scoring` | 0 |
| `polymarket-kelly-sizing` | 0 |
| `polymarket-paper-trading` | 0 |
| `polymarket-strategy-eval` | ~1000 tok/eval |
| `polymarket-decay-detection` | 0 |
| `polymarket-scout-research` | ~2000 tok/scan |
| `polymarket-microstructure` | 0 |
| `polymarket-backtest` | 0 |
| `polymarket-tradability-check` | 0 |
| `polymarket-market-connector` | 0 |

Skills OpenClaw réutilisés : `news-scoring`, `kill-switch`, `compound-learning`, `token-optimization`, `heartbeat-monitoring`.

---

## 6. RÔLE EXACT DE CHAQUE AGENT

### C8 — POLY_FACTORY_ORCHESTRATOR

**Mission** : Coordonner l'ensemble du système. Déclencher les pipelines dans le bon ordre, router les données, gérer les transitions d'état des stratégies et de leurs POLY_STRATEGY_ACCOUNT, maintenir la cohérence globale. Aucun LLM.

**State Machine des stratégies :**

```
SCOUTED → BACKTESTED → EVALUATED → PAPER_TESTING → PAPER_EVALUATED
→ AWAITING_HUMAN_GO → MICRO_LIVE → SCALING → ACTIVE
→ PAUSED (si decay ou décision humaine)
→ STOPPED (si retrait)
→ PAPER_TESTING (si réactivation approuvée par l'humain)
→ REJECTED (si non viable)
```

Chaque transition met à jour le `status` du `POLY_STRATEGY_ACCOUNT` correspondant.

---

### C5 — POLY_GLOBAL_RISK_GUARD

**Mission** : Surveiller les pertes globales cumulées sur TOUTES les stratégies (paper et live). Si les pertes atteignent le seuil maximum de 4 000€, déclencher un arrêt total du système et entrer en mode sécurité.

**Pourquoi cet agent est nécessaire :**

Le `POLY_KILL_SWITCH` protège au niveau d'une stratégie individuelle (drawdown daily, pertes consécutives). Le `POLY_RISK_GUARDIAN` protège au niveau du portefeuille (exposition, positions simultanées). Mais aucun des deux ne répond à la question : **combien avons-nous perdu AU TOTAL depuis le début, toutes stratégies confondues ?**

Scénario dangereux sans `POLY_GLOBAL_RISK_GUARD` : cinq stratégies sont actives en live avec 1 000€ chacune. Chacune perd 800€ avant que son kill-switch individuel la stoppe (-80%). Perte totale : 4 000€. L'humain n'a rien approuvé de tel — il pensait risquer 1 000€ par stratégie, pas 4 000€ au total.

Le `POLY_GLOBAL_RISK_GUARD` résout ce problème en imposant un plafond absolu sur la perte cumulée.

**Fonctionnement :**

```
Tick : toutes les 60 secondes + après chaque trade résolu

CALCUL :
  Pour chaque POLY_STRATEGY_ACCOUNT (tous statuts sauf "stopped") :
    perte_stratégie = max(0, account.capital.initial - account.capital.current)
  
  perte_globale = Σ(perte_stratégie)

NIVEAUX DE RÉPONSE :

  perte_globale < 2 000€ (50% du seuil) :
    → STATUS : NORMAL
    → Aucune action

  perte_globale ≥ 2 000€ ET < 3 000€ (50-75%) :
    → STATUS : ALERTE
    → Notification humain : "Pertes globales à {perte_globale}€ sur 4 000€ max"
    → Aucun nouveau passage paper → live autorisé sans validation humaine renforcée
    → Les stratégies live existantes continuent

  perte_globale ≥ 3 000€ ET < 4 000€ (75-100%) :
    → STATUS : CRITIQUE
    → Notification Telegram URGENTE
    → Toutes les stratégies live repassent en paper automatiquement
    → Aucune stratégie ne peut passer en live
    → L'humain doit intervenir pour rétablir le trading live

  perte_globale ≥ 4 000€ :
    → STATUS : ARRÊT TOTAL
    → TOUTES les stratégies (paper ET live) sont stoppées
    → Le système entre en MODE SÉCURITÉ
    → Plus aucun trade possible (même paper)
    → L'humain doit manuellement réinitialiser le système
    → Nécessite un audit complet avant reprise
```

**State :**

```json
{
  "status": "NORMAL",
  "total_loss": 847.30,
  "max_loss_allowed": 4000.00,
  "pct_used": 0.212,
  "accounts_contributing": {
    "POLY_ARB_SCANNER": -0.00,
    "POLY_LATENCY_ARB": -120.50,
    "POLY_WEATHER_ARB": -45.00,
    "POLY_CONVERGENCE_STRAT": -681.80
  },
  "last_check": "2026-04-20T14:23:00Z",
  "alerts_sent": []
}
```

**Relation avec les autres agents de risque :**

| Agent | Niveau de protection | Scope |
|---|---|---|
| `POLY_KELLY_SIZER` | Par trade | Taille de position |
| `POLY_KILL_SWITCH` | Par stratégie / par session | Drawdown daily, pertes consécutives |
| `POLY_RISK_GUARDIAN` | Par portefeuille | Exposition, positions, corrélation |
| `POLY_GLOBAL_RISK_GUARD` | **Système entier** | **Perte cumulée totale toutes stratégies** |

---

### C6 — POLY_DATA_STORE (mis à jour v4)

**Mission** : Centraliser toutes les données opérationnelles incluant désormais les `POLY_STRATEGY_ACCOUNT`.

**Structure mise à jour :**

```
state/
├── orchestrator/
│   ├── system_state.json
│   ├── strategy_lifecycle.json
│   └── cycle_log.json
├── accounts/                       ← NOUVEAU v4
│   ├── ACC_POLY_ARB_SCANNER.json
│   ├── ACC_POLY_LATENCY_ARB.json
│   ├── ...
│   └── archive/
│       └── ACC_*_v1.json           ← Accounts de stratégies stopped
├── risk/                           ← NOUVEAU v4
│   ├── global_risk_state.json      ← POLY_GLOBAL_RISK_GUARD
│   └── kill_switch_status.json
├── feeds/
│   ├── polymarket_prices.json
│   ├── kalshi_prices.json          ← NOUVEAU v4 (quand connecteur ajouté)
│   ├── binance_raw.json
│   ├── binance_signals.json
│   ├── noaa_forecasts.json
│   ├── wallet_raw_positions.json
│   ├── wallet_signals.json
│   └── market_structure.json
├── trading/
│   ├── paper_trades_log.jsonl
│   ├── live_trades_log.jsonl
│   └── positions_by_strategy/      ← NOUVEAU v4 (isolé par account)
│       ├── POLY_ARB_SCANNER.json
│       └── ...
├── evaluation/
│   ├── strategy_scores.json
│   ├── strategy_rankings.json      ← Classement basé sur les accounts
│   ├── tradability_reports.json
│   ├── decay_alerts.json
│   └── tuning_recommendations.json
├── research/
│   ├── scouted_strategies.json
│   ├── backtest_results/
│   └── resolutions_cache.json
├── human/
│   ├── approvals.json
│   └── decisions_log.jsonl
└── historical/
    ├── markets.db
    └── signals.db
```

---

### C1 — POLY_MARKET_CONNECTOR

**Mission** : Abstraire l'accès aux marchés de prédiction derrière une interface unifiée, permettant de connecter Polymarket aujourd'hui et d'ajouter Kalshi, des sportsbooks ou toute autre plateforme demain, sans modifier les STRATEGY_AGENTS.

**Pourquoi cette abstraction est nécessaire :**

Plusieurs stratégies du système reposent sur l'arbitrage cross-plateforme (Polymarket vs Kalshi, Polymarket vs sportsbooks). Sans abstraction, chaque STRATEGY_AGENT devrait implémenter la logique de connexion de chaque plateforme. Ajouter Kalshi signifierait modifier POLY_ARB_SCANNER, POLY_PAIR_COST, et tout agent qui pourrait en bénéficier.

Avec `POLY_MARKET_CONNECTOR`, ajouter une nouvelle plateforme = écrire un nouveau connecteur. Les STRATEGY_AGENTS ne changent pas.

**Architecture :**

```
POLY_MARKET_CONNECTOR
│
├── Interface commune (ce que les agents voient)
│   │
│   │  get_markets(platform?) → [{market_id, title, prices, volume, resolution_criteria}]
│   │  get_orderbook(market_id) → {bids, asks, mid_price, spread}
│   │  place_order(market_id, side, size, price) → {order_id, status}
│   │  get_positions() → [{market_id, side, size, entry_price, pnl}]
│   │  get_settlement(market_id) → {result, settlement_price}
│   │
│   │  Chaque méthode retourne le même format quel que soit le connecteur sous-jacent.
│
├── connector_polymarket (ACTIF)
│   │  Implémentation : py-clob-client + WebSocket CLOB + Gamma API
│   │  Auth : POLYMARKET_API_KEY + POLYMARKET_API_SECRET
│   │  Particularités : settlement on-chain Polygon, gas MATIC
│
├── connector_kalshi (FUTUR — Phase 2)
│   │  Implémentation : Kalshi REST API
│   │  Auth : KALSHI_API_KEY
│   │  Particularités : régulé CFTC, marchés US uniquement
│   │  Statut : non implémenté, prévu quand stratégie cross-platform validée en paper
│
└── connector_sportsbook (FUTUR — Phase 3)
    │  Implémentation : à définir selon la plateforme
    │  Statut : non implémenté, prévu si stratégie sports arb validée
```

**Comment ajouter un nouveau marché :**

```
1. Écrire un fichier connector_{platform}.py qui implémente l'interface commune
2. Ajouter la configuration dans POLY_MARKET_CONNECTOR.config.json
3. Les STRATEGY_AGENTS existants peuvent immédiatement consommer les données
4. Les stratégies cross-platform (arb PM vs Kalshi) activent les deux connecteurs
5. Aucun autre agent ne change
```

**Output vers les SIGNAL_AGENTS :**

`POLY_MARKET_CONNECTOR` remplace l'ancien `POLY_PM_FEED` et l'englobe. Il fournit les prix à `POLY_MARKET_STRUCTURE_ANALYZER` et à tous les STRATEGY_AGENTS via les mêmes fichiers state, avec un champ `platform` ajouté :

```json
{
  "market_id": "0xabc...",
  "platform": "polymarket",
  "title": "BTC above 100K by June?",
  "yes_price": 0.62,
  "no_price": 0.39,
  "volume_24h": 125000,
  "timestamp": "2026-04-20T14:23:44Z"
}
```

Quand un deuxième connecteur est actif (ex: Kalshi), le même fichier contient des entrées de DEUX plateformes, ce qui permet à `POLY_ARB_SCANNER` de détecter les arbs cross-platform sans modification.

---

### C5 — Agents de Risque (rappel des rôles)

**`POLY_KILL_SWITCH`** — Override par stratégie et par session. Drawdown daily → stop. 3 pertes → stop. Vérifie le POLY_STRATEGY_ACCOUNT de la stratégie concernée. Lit les limites `kill_switch_daily_pct` et `kill_switch_strategy_pct` du compte.

**`POLY_KELLY_SIZER`** — Half-Kelly par défaut. Taille ajustée au capital disponible dans le POLY_STRATEGY_ACCOUNT (pas le capital global). `max_position = account.capital.current × account.limits.max_position_pct`.

**`POLY_RISK_GUARDIAN`** — Portefeuille global : max 80% du capital total exposé, max 5 positions simultanées toutes stratégies confondues, anti-corrélation.

**`POLY_GLOBAL_RISK_GUARD`** — Perte cumulée totale. Voir section dédiée ci-dessus.

---

### Autres Agents (inchangés vs v3)

Tous les agents des couches C2, C3, C4, C7 et Infrastructure sont identiques à la v3. Se référer aux sections correspondantes du document v3 pour le détail de chaque agent.

Ajustement clé : chaque STRATEGY_AGENT et chaque ENGINE vérifie désormais le `POLY_STRATEGY_ACCOUNT` de la stratégie avant tout trade :

```
Vérification pré-trade ajoutée :
  ✓ account.status == "paper_testing" ou "active"
  ✓ account.capital.current > 0
  ✓ account.drawdown.current > account.drawdown.max_allowed
  ✓ POLY_GLOBAL_RISK_GUARD.status != "ARRÊT TOTAL"
```

---

## 7. INTERACTIONS ENTRE AGENTS

### 7.1 — Flux mis à jour avec comptes et risque global

```
C1 DATA (via POLY_MARKET_CONNECTOR) → C2 SIGNALS → C3 STRATEGIES
     │
     ▼
ORCHESTRATOR vérifie :
  → POLY_STRATEGY_ACCOUNT (capital disponible ?)
  → POLY_GLOBAL_RISK_GUARD (perte globale sous seuil ?)
  → POLY_KILL_SWITCH (pas de blocage ?)
     │
     ▼
C5 RISK → C4 EXECUTION (paper ou live)
     │
     ▼
C6 DATA_STORE (persiste trade + met à jour POLY_STRATEGY_ACCOUNT)
     │
     ▼
C7 EVALUATION (utilise les accounts pour comparer et classer)
     │
     ▼
C9 HUMAIN (voit le classement des comptes, décide GO/NOGO)
```

### 7.2 — Reaction Matrix (ajouts v4)

```json
{
  "reactions_v4": [
    {"source": "POLY_GLOBAL_RISK_GUARD", "event": "global_risk:alert", "target": "POLY_FACTORY_ORCHESTRATOR", "note": "Alerte 50% seuil → notification humain"},
    {"source": "POLY_GLOBAL_RISK_GUARD", "event": "global_risk:critical", "target": "POLY_KILL_SWITCH", "note": "75% seuil → toutes stratégies live → paper"},
    {"source": "POLY_GLOBAL_RISK_GUARD", "event": "global_risk:shutdown", "target": "POLY_FACTORY_ORCHESTRATOR", "note": "100% seuil → arrêt total système"},
    {"source": "POLY_MARKET_CONNECTOR", "event": "connector:new_platform", "target": "POLY_MARKET_STRUCTURE_ANALYZER", "note": "Nouvelle plateforme → analyser sa microstructure"},
    {"source": "POLY_MARKET_CONNECTOR", "event": "connector:disconnected", "target": "POLY_KILL_SWITCH", "note": "Plateforme déconnectée → suspendre stratégies dépendantes"},
    {"source": "POLY_DATA_STORE", "event": "account:trade_settled", "target": "POLY_GLOBAL_RISK_GUARD", "note": "Trade résolu → recalcul perte globale"}
  ]
}
```

Les réactions de la v3 (ARB_SCANNER → ORCHESTRATOR, DECAY → KILL_SWITCH, etc.) restent inchangées.

---

## 8. FLUX DE DONNÉES ET COUCHE DE STOCKAGE

Voir structure `POLY_DATA_STORE` section 6. Les ajouts v4 sont : dossier `state/accounts/`, dossier `state/risk/`, dossier `state/trading/positions_by_strategy/`, fichier `state/feeds/kalshi_prices.json` (quand connecteur ajouté).

---

## 9. PIPELINE PAPER TRADING

```
1. STRATEGY_AGENT émet signal → ORCHESTRATOR
2. Orchestrator vérifie : strategy_account.status == "paper_testing"
3. Orchestrator vérifie : POLY_GLOBAL_RISK_GUARD.status != "ARRÊT TOTAL"
4. POLY_MARKET_STRUCTURE_ANALYZER vérifie executability >= 40
5. POLY_KELLY_SIZER calcule taille (basée sur account.capital.current, pas le capital global)
6. POLY_KILL_SWITCH vérifie drawdown du POLY_STRATEGY_ACCOUNT
7. POLY_RISK_GUARDIAN vérifie exposure portefeuille global
8. POLY_PAPER_ENGINE simule (prix réels + slippage réaliste)
9. POLY_DATA_STORE persiste le trade + met à jour le POLY_STRATEGY_ACCOUNT
10. À résolution : P&L calculé sur le compte de la stratégie
11. POLY_PERFORMANCE_LOGGER agrège
12. À 50 trades : Orchestrator → POLY_STRATEGY_EVALUATOR
```

Capital paper par stratégie : **1 000€ fictifs**. Ce montant identique pour toutes les stratégies permet la comparaison directe.

Critères de sortie : ≥ 50 trades, WR > breakeven, Sharpe > 1.5, PF > 1.3, DD < 10% du compte, tradability > 70%, pas de decay, durée ≥ 14j, score ≥ 60.

---

## 10. PIPELINE DE VALIDATION — PASSAGE EN RÉEL

```
BACKTEST (score ≥ 40 requis)
  → PAPER (50+ trades, 14j, capital fictif 1 000€)
  → POLY_STRATEGY_EVALUATOR (score ≥ 60)
  → POLY_GLOBAL_RISK_GUARD (vérifie que perte globale permet un nouveau compte live)
  → HUMAIN (GO/NOGO, JSON signé expire 7j)
  → Création POLY_STRATEGY_ACCOUNT live (capital réel 1 000€)
  → MICRO-LIVE (7j, kill-switch -3% du compte)
  → HUMAIN (SCALE/KEEP/STOP)
  → SCALING (augmentation progressive du capital du compte)
```

Ajout v4 : avant de proposer le passage en live à l'humain, `POLY_GLOBAL_RISK_GUARD` vérifie que la perte globale permet d'absorber un éventuel échec complet de cette stratégie (= le compte de 1 000€ tombe à 0). Si la marge restante est insuffisante, le passage en live est bloqué.

---

## 11. SUPERVISION HUMAINE

**L'humain ne fait JAMAIS** : sizing, stop-loss, parsing résolution, évaluation liquidité, monitoring temps réel, comparaison des stratégies.

**SEUL l'humain fait** : approuver le live, fixer le capital d'un compte, décider de réactiver une stratégie stoppée, réinitialiser le système après un ARRÊT TOTAL du POLY_GLOBAL_RISK_GUARD, review mensuelle.

---

## 12. ÉVALUATION ET OPTIMISATION DES STRATÉGIES

### 12.1 — POLY_STRATEGY_EVALUATOR (mis à jour v4)

L'Evaluator lit désormais les `POLY_STRATEGY_ACCOUNT` pour produire le classement. Puisque chaque stratégie démarre avec 1 000€, la comparaison est normalisée : un P&L de +87€ sur le compte de POLY_ARB_SCANNER signifie +8.7% de rendement, directement comparable au +3.1% de POLY_WEATHER_ARB.

Le classement hebdomadaire envoyé à l'humain inclut le capital courant, le P&L, le Sharpe, le score Evaluator et le verdict de chaque compte.

### 12.2 — Réactivation de Stratégies

Quand `POLY_STRATEGY_SCOUT` ou `POLY_DECAY_DETECTOR` détecte que les conditions de marché ont changé (nouvelle liquidité, concurrence réduite, nouveau connecteur de plateforme), une stratégie en statut `stopped` peut être proposée à la réactivation.

Le processus : notification humain → humain approuve → création d'un NOUVEAU `POLY_STRATEGY_ACCOUNT` (compteurs à zéro, capital fictif 1 000€) → retour en `paper_testing` → tout le pipeline recommence. L'ancien account reste archivé.

---

## 13. TRADABILITÉ RÉELLE — LE FILTRE ULTIME

*(Inchangé vs v3 — chaîne de 4 filtres, métriques de tradabilité, risque par stratégie.)*

Ajout v4 : le filtre de tradabilité vérifie aussi la plateforme via `POLY_MARKET_CONNECTOR`. Si une stratégie d'arb cross-platform nécessite Kalshi mais que `connector_kalshi` n'est pas actif, le trade est bloqué.

---

## 14. CONNECTEURS MULTI-PLATEFORMES — POLY_MARKET_CONNECTOR

*(Voir section 6 pour le détail complet.)*

**Plateformes prévues :**

| Plateforme | Connecteur | Statut | Stratégies concernées |
|---|---|---|---|
| **Polymarket** | `connector_polymarket` | Actif | Toutes |
| **Kalshi** | `connector_kalshi` | Futur (Phase 2) | Cross-platform arb, marchés politiques US |
| **Sportsbooks** | `connector_sportsbook` | Futur (Phase 3) | Sports betting edge, blessures/lineups |
| **PredictFun** | `connector_predictfun` | Futur | Cross-platform arb additionnel |

**Principe d'extension :** chaque nouveau connecteur implémente la même interface (`get_markets`, `get_orderbook`, `place_order`, `get_positions`, `get_settlement`). Les STRATEGY_AGENTS ne changent pas. Le `POLY_MARKET_STRUCTURE_ANALYZER` analyse automatiquement la microstructure de chaque nouvelle plateforme.

---

## 15. INTÉGRATION OPENCLAW

Réutilise sans duplication : NEWS_FEED, NEWS_SCORING, Compound Learning, Token Optimization, HEARTBEAT, Two-Layer Memory, AGENT.md template, Dashboard Aggregates, PM2, ctx.state.

---

## 16. RESSOURCES ET ACCÈS NÉCESSAIRES

| Ressource | Coût | Note v4 |
|---|---|---|
| Polymarket CLOB API | Gratuit | Via POLY_MARKET_CONNECTOR |
| Polymarket Gamma API | Gratuit, sans auth | Via POLY_MARKET_CONNECTOR |
| Kalshi API | Gratuit (futur) | Phase 2, quand connecteur implémenté |
| Binance WebSocket | Gratuit | |
| NWS / NOAA API | Gratuit, sans auth | |
| Polygon RPC (QuickNode free) | Gratuit | |
| py-clob-client | Open-source | |
| Wallet USDC.e Polygon | Gas minimal | Un wallet par stratégie live possible (optionnel) |
| Anthropic API | ~$15-30/mois | |
| SQLite | Gratuit | |

Capital nécessaire pour déployer N stratégies live : N × 1 000€ + marge pour gas et fees.

---

## 17. GARDE-FOUS DE SÉCURITÉ

```
COUCHE 1 — PAR TRADE
  Filtre tradabilité (POLY_MARKET_STRUCTURE_ANALYZER)
  Taille basée sur le POLY_STRATEGY_ACCOUNT (pas le capital global)
  Max 3% du capital du compte par trade
  POLY_ORDER_SPLITTER calibré sur depth_usd

COUCHE 2 — PAR STRATÉGIE (POLY_STRATEGY_ACCOUNT)
  Capital isolé : 1 000€ par stratégie
  Kill-switch par compte : -30% max → stratégie stoppée automatiquement
  Drawdown daily -5% du compte → pause pour la journée
  3 pertes consécutives → pause pour la journée

COUCHE 3 — PAR PORTEFEUILLE (POLY_RISK_GUARDIAN)
  Max 80% du capital total exposé
  Max 5 positions simultanées toutes stratégies
  Anti-corrélation check
  Max 40% par catégorie de stratégie

COUCHE 4 — SYSTÈME GLOBAL (POLY_GLOBAL_RISK_GUARD)
  Perte cumulée < 2 000€ → NORMAL
  Perte cumulée ≥ 2 000€ → ALERTE (notification humain)
  Perte cumulée ≥ 3 000€ → CRITIQUE (live → paper automatique)
  Perte cumulée ≥ 4 000€ → ARRÊT TOTAL (tout stoppé, audit requis)

COUCHE 5 — STRUCTURELLE
  Paper → live JAMAIS automatique
  Approbation humaine expire 7j
  Wallet isolé du reste d'OpenClaw
  Clé privée jamais dans Git
  POLY_KILL_SWITCH + POLY_GLOBAL_RISK_GUARD override tout
  Défaut = paper, flag --live requis
  POLY_MARKET_CONNECTOR vérifie la connectivité avant tout trade
```

---

## ANNEXE — RÉSUMÉ

```
POLY_FACTORY = portefeuille de stratégies indépendantes

Chaque stratégie :
  → POLY_STRATEGY_ACCOUNT (1 000€ test / 1 000€ réel)
  → Pipeline : SCOUT → BACKTEST → PAPER → EVALUATOR → HUMAIN → LIVE
  → Peut être stoppée, réactivée, comparée aux autres

Protection :
  → POLY_KILL_SWITCH (par stratégie)
  → POLY_GLOBAL_RISK_GUARD (global, max perte 4 000€)

Multi-plateforme :
  → POLY_MARKET_CONNECTOR (Polymarket actif, Kalshi/sportsbooks futurs)

ORCHESTRATOR coordonne. EVALUATOR juge. DATA_STORE mémorise.
GLOBAL_RISK_GUARD protège. HUMAIN décide.
```

**35 agents.** 24 sans LLM. Comptes isolés par stratégie. Perte globale plafonnée à 4 000€. Multi-plateformes natif. Humain obligatoire pour tout passage en réel.

---

*Version 4.0. Changements vs v3 : POLY_STRATEGY_ACCOUNT (capital isolé 1 000€/stratégie, P&L indépendant, réactivation possible), POLY_GLOBAL_RISK_GUARD (perte max 4 000€, 4 niveaux de réponse, arrêt total automatique), POLY_MARKET_CONNECTOR (abstraction multi-plateformes, interface unifiée, connecteurs enfichables), objectifs mis à jour (portefeuille de stratégies, comparaison normalisée, réactivation).*
