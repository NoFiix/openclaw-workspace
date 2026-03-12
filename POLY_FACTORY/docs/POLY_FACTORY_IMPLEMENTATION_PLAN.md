# POLY_FACTORY — Plan d'Implémentation

> **Version 3.0 — 12 mars 2026**
> Feuille de route pour construire POLY_FACTORY étape par étape dans l'environnement OpenClaw.
> Basé sur POLY_FACTORY_ARCHITECTURE v4.0 et POLY_FACTORY_PIPELINE v4.0.

---

## CORRECTIONS v3

| # | Correction | Impact |
|---|---|---|
| 1 | **Gate = décision, Capital Manager = exécution** — `POLY_STRATEGY_PROMOTION_GATE` approuve ou refuse. `POLY_CAPITAL_MANAGER` crée le compte live. Séparation propre décision/action. | Sections 1.6 et 1.7 |
| 2 | **Naming uniformisé** — `POLY_BROWNIAN` corrigé en `POLY_BROWNIAN_SNIPER` partout (skills, bus, tables). | Skills, bus |
| 3 | **Bus concret avec payloads** — Chaque event a un format JSON exact avec tous les champs. Enveloppe commune (`event_id`, `topic`, `timestamp`, `producer`, `priority`, `retry_count`, `payload`). 15 payloads détaillés champ par champ. Les contrats sont figés, prêts à coder. | Section 7 |

---

## CORRECTIONS v2

| # | Correction | Impact |
|---|---|---|
| 1 | **Séparation Paper / Live** — `POLY_EXECUTION_ENGINE` remplacé par `POLY_EXECUTION_ROUTER` + `POLY_PAPER_EXECUTION_ENGINE` + `POLY_LIVE_EXECUTION_ENGINE`. Élimine le risque qu'un mauvais flag envoie un ordre réel. | Couche exécution |
| 2 | **`POLY_STRATEGY_PROMOTION_GATE`** — Point de passage unique et auditable pour la transition paper → live. Centralise toutes les vérifications de promotion. | Nouveau composant |
| 3 | **Démarcation RISK_GUARDIAN vs GLOBAL_RISK_GUARD** — Périmètres explicitement distincts avec tableau de responsabilités sans ambiguïté. | Clarification |
| 4 | **Bus de communication** — Section dédiée : événements, topics, fichiers state, synchrone vs async, idempotence. | Nouvelle section |
| 5 | **Timeline indicative** — Les phases sont un ordre recommandé, pas un calendrier ferme. Estimations en effort, pas en semaines fixes. | Section 8 |
| 6 | **Doctrine backtest** — Le backtest est un outil de tri rapide, jamais une validation. Seule la combinaison backtest + paper + tradabilité réelle compte. | Renforcé |
| 7 | **`POLY_STRATEGY_REGISTRY`** — Registre central de la vie logique des stratégies (version, paramètres, plateforme, historique). Complémentaire au POLY_STRATEGY_ACCOUNT qui suit le capital. | Nouveau composant |

---

## 1. LISTE DES AGENTS À IMPLÉMENTER

### 1.1 — Orchestration

**`POLY_FACTORY_ORCHESTRATOR`**

| Attribut | Détail |
|---|---|
| Rôle | Chef d'orchestre. Coordonne les cycles (recherche, test, live, nightly, hebdo). Gère la state machine des stratégies. Route les événements entre agents via le bus de communication. |
| Inputs | Événements de tous les agents via le bus (signaux, milestones, alertes, décisions humaines) |
| Outputs | Commandes vers tous les agents, mise à jour `strategy_lifecycle.json`, rapports |
| Dépendances | Bus de communication, `POLY_DATA_STORE`, `POLY_AUDIT_LOG`, `POLY_STRATEGY_REGISTRY` |
| Fréquence | Continu (boucle principale) + nightly (03:00-04:00 UTC) + hebdomadaire |
| LLM | Non |

---

### 1.2 — Data Ingestion (Couche 1)

**`POLY_MARKET_CONNECTOR`**

| Attribut | Détail |
|---|---|
| Rôle | Abstraction multi-plateformes. Interface unifiée pour Polymarket (et Kalshi/sportsbooks futur). |
| Inputs | WebSocket Polymarket CLOB API, Gamma API. Futur : Kalshi REST, sportsbook APIs. |
| Outputs | `state/feeds/polymarket_prices.json` via bus event `feed:price_update` |
| Dépendances | py-clob-client, websockets, POLYMARKET_API_KEY/SECRET |
| Fréquence | Continu (WebSocket persistent) |
| LLM | Non |

**`POLY_BINANCE_FEED`**

| Attribut | Détail |
|---|---|
| Rôle | Flux WebSocket Binance pour prix BTC/ETH + orderbook depth20 |
| Inputs | Binance WebSocket (`aggTrade` + `depth20@100ms`) |
| Outputs | `state/feeds/binance_raw.json` via bus event `feed:binance_update` |
| Dépendances | websockets, BINANCE_API_KEY (lecture seule) |
| Fréquence | Continu (WebSocket persistent) |
| LLM | Non |

**`POLY_NOAA_FEED`**

| Attribut | Détail |
|---|---|
| Rôle | Fetch prévisions NWS pour 6 stations aéroport US |
| Inputs | NWS REST API |
| Outputs | `state/feeds/noaa_forecasts.json` via bus event `feed:noaa_update` |
| Fréquence | Toutes les 2 minutes |
| LLM | Non |

**`POLY_WALLET_FEED`**

| Attribut | Détail |
|---|---|
| Rôle | Fetch positions brutes des wallets Polymarket surveillés |
| Inputs | Polymarket API publique + Polygon RPC |
| Outputs | `state/feeds/wallet_raw_positions.json` via bus event `feed:wallet_update` |
| Fréquence | Toutes les 60 secondes |
| LLM | Non |

---

### 1.3 — Signal Agents (Couche 2)

**`POLY_DATA_VALIDATOR`**

| Attribut | Détail |
|---|---|
| Rôle | Vérifier qualité et cohérence de TOUTES les données entrantes. Filtre 0 dans la chaîne. Marque les données "SUSPECT" pour qu'elles soient ignorées par les stratégies. |
| Inputs | Bus events `feed:*` (toutes les données brutes) |
| Outputs | Données marquées VALID/SUSPECT dans state. Bus event `data:validation_failed` si problème. |
| Dépendances | Tous les feeds C1, `POLY_AUDIT_LOG` |
| Fréquence | À chaque donnée reçue (continu) |
| LLM | Non |

**`POLY_BINANCE_SIGNALS`**

| Attribut | Détail |
|---|---|
| Rôle | Transformer données brutes Binance en OBI, CVD, VWAP, Momentum, score composite [-1, +1] |
| Inputs | Bus event `feed:binance_update` (données validées) |
| Outputs | `state/feeds/binance_signals.json` via bus event `signal:binance_score` |
| Fréquence | Continu (< 100ms) |
| LLM | Non |

**`POLY_MARKET_ANALYST`**

| Attribut | Détail |
|---|---|
| Rôle | Parser critères de résolution via Sonnet. Résultat caché (1 seul appel par marché). |
| Inputs | Bus event `market:new_detected`. Texte via Gamma API. |
| Outputs | `state/research/resolutions_cache.json`. Bus event `signal:resolution_parsed`. |
| Fréquence | À la demande |
| LLM | Sonnet (~500 tokens/marché, résultat caché) |

**`POLY_WALLET_TRACKER`**

| Attribut | Détail |
|---|---|
| Rôle | Signaux enrichis : scoring EV, spécialisation, convergence, alertes comportement |
| Inputs | Bus event `feed:wallet_update` |
| Outputs | `state/feeds/wallet_signals.json`. Bus event `signal:wallet_convergence` si 3+ wallets convergent. |
| Fréquence | Toutes les 60 secondes |
| LLM | Non |

**`POLY_MARKET_STRUCTURE_ANALYZER`**

| Attribut | Détail |
|---|---|
| Rôle | Microstructure : liquidité, spread, profondeur, slippage. Score exécutabilité 0-100. Filtre pré-trade obligatoire. |
| Inputs | Bus event `feed:price_update` |
| Outputs | `state/feeds/market_structure.json`. Bus event `market:illiquid` si score chute. |
| Fréquence | Toutes les 30 secondes |
| LLM | Non |

---

### 1.4 — Strategy Agents (Couche 3)

Chaque STRATEGY_AGENT a son propre `POLY_STRATEGY_ACCOUNT` (1 000€) et une entrée dans le `POLY_STRATEGY_REGISTRY`. Tous émettent des signaux sur le bus, jamais directement vers l'exécution.

| Agent | Inputs (bus events) | Output (bus event) | Fréquence | LLM |
|---|---|---|---|---|
| `POLY_ARB_SCANNER` | `feed:price_update` + `signal:market_structure` | `trade:signal` | 1-5s | Non |
| `POLY_PAIR_COST` | `feed:price_update` + `signal:market_structure` | `trade:signal` | 2-5s | Non |
| `POLY_LATENCY_ARB` | `signal:binance_score` + `feed:price_update` | `trade:signal` | < 1s | Non |
| `POLY_BROWNIAN_SNIPER` | `signal:binance_score` + `feed:price_update` | `trade:signal` | < 1s (fin cycle) | Non |
| `POLY_WEATHER_ARB` | `feed:noaa_update` + `feed:price_update` | `trade:signal` | 2 min | Non |
| `POLY_OPP_SCORER` | `feed:price_update` + `signal:resolution_parsed` | `trade:signal` | 4h | Sonnet (cache) |
| `POLY_NO_SCANNER` | `feed:price_update` + `signal:resolution_parsed` | `trade:signal` | Hebdomadaire | Haiku (1x) |
| `POLY_CONVERGENCE_STRAT` | `signal:wallet_convergence` + `signal:resolution_parsed` | `trade:signal` | 60s | Non |
| `POLY_NEWS_STRAT` | `news:high_impact` + `feed:price_update` | `trade:signal` | Event-driven | Haiku/Sonnet |

---

### 1.5 — Exécution (Couche 4) — CORRIGÉ v2

L'exécution paper et l'exécution live sont **deux modules séparés** derrière un routeur commun.

**`POLY_EXECUTION_ROUTER`**

| Attribut | Détail |
|---|---|
| Rôle | Recevoir les signaux validés par les 7 filtres et les router vers le bon moteur d'exécution (paper ou live) selon le statut de la stratégie dans le `POLY_STRATEGY_REGISTRY`. Ne contient AUCUNE logique d'exécution. |
| Inputs | Bus event `trade:validated` (signal ayant passé tous les filtres) |
| Outputs | Bus event `execute:paper` OU `execute:live` vers le moteur approprié |
| Dépendances | `POLY_STRATEGY_REGISTRY` (vérifie le mode de la stratégie) |
| Fréquence | À chaque signal validé |
| LLM | Non |

Le routeur est un composant trivial (< 50 lignes). Sa seule responsabilité est de lire le statut dans le Registry et de router. Il n'a aucune logique conditionnelle complexe, ce qui élimine le risque qu'un bug envoie un signal paper vers le moteur live.

**`POLY_PAPER_EXECUTION_ENGINE`**

| Attribut | Détail |
|---|---|
| Rôle | Simuler l'exécution de tous les ordres paper. Prix réels, slippage réaliste basé sur `POLY_MARKET_STRUCTURE_ANALYZER`, gas estimé. Aucune interaction avec une API externe. Aucun risque de capital réel. |
| Inputs | Bus event `execute:paper` |
| Outputs | Trade simulé dans `paper_trades_log.jsonl`. Mise à jour du `POLY_STRATEGY_ACCOUNT`. Bus event `trade:paper_executed`. |
| Dépendances | `POLY_MARKET_CONNECTOR` (lecture prix seulement), `POLY_DATA_STORE`, `POLY_AUDIT_LOG` |
| Fréquence | À chaque signal routé en paper |
| LLM | Non |

**`POLY_LIVE_EXECUTION_ENGINE`**

| Attribut | Détail |
|---|---|
| Rôle | Exécuter les ordres réels sur le CLOB Polymarket via py-clob-client. Gestion des fills, retries, slippage réel, gas réel. Interagit avec l'API Polymarket et la blockchain Polygon. |
| Inputs | Bus event `execute:live` |
| Outputs | Trade réel dans `live_trades_log.jsonl`. Mise à jour du `POLY_STRATEGY_ACCOUNT`. Bus event `trade:live_executed` avec tx_hash. |
| Dépendances | `POLY_MARKET_CONNECTOR` (ordres via py-clob-client), `POLY_ORDER_SPLITTER`, wallet Polygon, `POLY_AUDIT_LOG` |
| Fréquence | À chaque signal routé en live (si activé) |
| LLM | Non |
| Retries | 3 tentatives backoff 1s/3s/10s. Réduction taille 50% au retry 3. Kill Switch notifié après 5 échecs. |
| Pré-conditions | `POLY_STRATEGY_PROMOTION_GATE` a validé la stratégie. Approbation JSON non expirée. Wallet balance suffisante. |

**Pourquoi cette séparation est critique :**

- Le live a des contraintes de sécurité très différentes du paper (approbation, wallet, retries, gas).
- Le paper et le live divergent dans la logique au fil du temps (le live gère les fills partiels, les timeouts, les reconnexions API).
- Deux modules séparés réduisent structurellement le risque qu'un mauvais flag envoie un ordre réel.
- C'est plus simple à auditer : le code du `POLY_LIVE_EXECUTION_ENGINE` peut être reviewé isolément.
- Le `POLY_PAPER_EXECUTION_ENGINE` ne contient aucune dépendance vers py-clob-client ou le wallet — il est physiquement incapable d'envoyer un ordre réel.

**`POLY_ORDER_SPLITTER`**

| Attribut | Détail |
|---|---|
| Rôle | Découper ordres en micro-tranches calibrées par depth_usd |
| Inputs | Taille d'ordre + depth_usd du marché cible |
| Outputs | Liste de tranches |
| Fréquence | À la demande (appelé par le LIVE_EXECUTION_ENGINE) |
| LLM | Non |

---

### 1.6 — Promotion (Couche 4.5) — NOUVEAU v2

**`POLY_STRATEGY_PROMOTION_GATE`**

| Attribut | Détail |
|---|---|
| Rôle | Point de passage unique et auditable pour la DÉCISION de promotion paper → live. Centralise TOUTES les vérifications. Approuve ou refuse. Ne crée PAS le compte live (c'est `POLY_CAPITAL_MANAGER` qui exécute). Gate = décision. Capital Manager = exécution comptable. |
| Inputs | Bus event `promotion:request` (émis par l'Orchestrator quand l'humain signe GO) |
| Outputs | Bus event `promotion:approved` ou `promotion:denied` avec raison |
| Dépendances | `POLY_STRATEGY_REGISTRY`, `POLY_STRATEGY_ACCOUNT`, `POLY_GLOBAL_RISK_GUARD`, `state/human/approvals.json` |
| Fréquence | Sur événement uniquement |
| LLM | Non |

**Vérifications effectuées par le Promotion Gate :**

```
POLY_STRATEGY_PROMOTION_GATE vérifie (dans cet ordre) :

  1. REGISTRY : la stratégie existe et est en status "awaiting_human"
  2. ACCOUNT : paper_testing a produit ≥ 50 trades + ≥ 14 jours
  3. EVALUATOR : score ≥ 60
  4. DECAY : aucune alerte SERIOUS ou CRITICAL active
  5. APPROVAL : JSON d'approbation humaine existe dans state/human/approvals.json
  6. APPROVAL : le JSON n'est pas expiré (< 7 jours)
  7. APPROVAL : le JSON contient les limites requises (capital max, max/trade, kill-switch)
  8. GLOBAL_RISK_GUARD : statut NORMAL (pas ALERTE ni CRITIQUE)
  9. GLOBAL_RISK_GUARD : la perte globale + 1 000€ (worst case) < 4 000€
  10. WALLET : balance USDC.e suffisante pour le capital initial du compte

  SI les 10 checks passent :
    → AUDIT_LOG : "promotion:approved"
    → Bus event : "promotion:approved" {strategy, approval_json, checks_passed}
    → Le POLY_CAPITAL_MANAGER reçoit l'event et EXÉCUTE :
        - Création du POLY_STRATEGY_ACCOUNT live (1 000€ réels)
        - Mise à jour du REGISTRY : status → "active"
        - AUDIT_LOG : "account:live_created" {strategy, capital}

  SI un seul check échoue :
    → AUDIT_LOG : "promotion:denied" {check_failed, reason}
    → Bus event : "promotion:denied" {strategy, check_failed, reason}
    → La stratégie reste en "awaiting_human"
    → Aucune action du CAPITAL_MANAGER
```

**Pourquoi ce composant est nécessaire :**

Sans `POLY_STRATEGY_PROMOTION_GATE`, la logique de promotion est dispersée entre l'Orchestrator (qui déclenche), l'Evaluator (qui score), le Capital Manager (qui crée le compte), et le Kill Switch (qui vérifie). Chaque agent interprète les conditions à sa manière. Si un agent est mis à jour et qu'un check est oublié, une stratégie peut passer en live sans validation complète.

Le Promotion Gate centralise la DÉCISION. Le Capital Manager exécute l'action comptable. C'est le seul endroit dans le code qui contient la logique "autoriser le passage en live". Si on veut ajouter un check (par exemple "pas de promotion le week-end"), c'est un seul fichier à modifier. Si on veut changer la taille initiale du compte live, c'est le Capital Manager — pas le Gate.

---

### 1.7 — Gestion du Risque (Couche 5)

**`POLY_KILL_SWITCH`**

| Attribut | Détail |
|---|---|
| Rôle | Protection par stratégie et par session. Override total. 5 niveaux de réponse. |
| Scope | **Une stratégie à la fois** (drawdown de son POLY_STRATEGY_ACCOUNT) + **une session** (drawdown daily, pertes consécutives) |
| Inputs | `POLY_STRATEGY_ACCOUNT` par stratégie, compteurs pertes, état feeds, NEWS_SCORING |
| Outputs | Go/No-Go pré-trade, commandes pause/stop via bus event `risk:kill_switch` |
| Fréquence | Tick 5s + pré-trade + health check horaire |
| LLM | Non |

**`POLY_RISK_GUARDIAN`**

| Attribut | Détail |
|---|---|
| Rôle | Protection au niveau portefeuille. Vérifie les limites inter-stratégies. |
| Scope | **Le portefeuille global** (toutes les stratégies actives prises ensemble) |
| Inputs | Toutes les positions ouvertes de tous les `POLY_STRATEGY_ACCOUNT` |
| Outputs | Go/No-Go pré-trade via bus event `risk:portfolio_check` |
| Fréquence | Pré-trade |
| LLM | Non |

**`POLY_GLOBAL_RISK_GUARD`**

| Attribut | Détail |
|---|---|
| Rôle | Plafond de perte cumulée totale sur le système entier. Arrêt total si seuil atteint. |
| Scope | **Le système tout entier** (somme des pertes de tous les comptes depuis le début) |
| Inputs | Tous les `POLY_STRATEGY_ACCOUNT` (somme des pertes) |
| Outputs | Statut global (NORMAL/ALERTE/CRITIQUE/ARRÊT TOTAL) via bus event `risk:global_status` |
| Fréquence | Tick 60s + post-trade |
| LLM | Non |

**Démarcation explicite des 3 agents de risque :**

| Question | POLY_KILL_SWITCH | POLY_RISK_GUARDIAN | POLY_GLOBAL_RISK_GUARD |
|---|---|---|---|
| "Cette stratégie a trop perdu aujourd'hui ?" | **OUI** — drawdown daily du compte | Non | Non |
| "3 pertes consécutives sur cette stratégie ?" | **OUI** — compteur par stratégie | Non | Non |
| "Le portefeuille est trop exposé ?" | Non | **OUI** — exposure totale < 80% | Non |
| "Trop de positions simultanées ?" | Non | **OUI** — max 5 positions | Non |
| "3 positions corrélées sur le même thème ?" | Non | **OUI** — anti-corrélation | Non |
| "Combien avons-nous perdu AU TOTAL depuis le début ?" | Non | Non | **OUI** — somme pertes cumulées |
| "Faut-il tout arrêter ?" | Non | Non | **OUI** — ARRÊT TOTAL si ≥ 4K€ |

Aucun chevauchement. Chaque question a un seul agent responsable.

**`POLY_KELLY_SIZER`**

| Attribut | Détail |
|---|---|
| Rôle | Taille de chaque position. Half-Kelly défaut, Quarter-Kelly haute variance. Basé sur le capital du POLY_STRATEGY_ACCOUNT. |
| Fréquence | À la demande (chaque signal) |

**`POLY_CAPITAL_MANAGER`**

| Attribut | Détail |
|---|---|
| Rôle | Gestion des POLY_STRATEGY_ACCOUNT. **Crée les comptes live** quand `POLY_STRATEGY_PROMOTION_GATE` approuve (bus event `promotion:approved`). Vérification pré-trade que le compte a assez de capital. Limites d'exposition par marché. Récupération de capital quand stratégie stoppée. Gate décide → Capital Manager exécute. |
| Fréquence | Pré-trade + tick 60s + nightly 03:20 UTC |

---

### 1.8 — Stockage + Registre (Couche 6)

**`POLY_DATA_STORE`**

| Attribut | Détail |
|---|---|
| Rôle | Point d'accès unique pour toutes les données persistées. |
| Fréquence | Continu |

**`POLY_AUDIT_LOG`**

| Attribut | Détail |
|---|---|
| Rôle | Journalisation transversale immuable. Source de vérité unique. |
| Catégories | SIGNAL, DECISION, TRADE, RISK, HUMAN, SYSTEM, EVALUATION, DATA, ACCOUNT, PROMOTION |
| Fréquence | À chaque événement |

**`POLY_STRATEGY_REGISTRY`** — NOUVEAU v2

| Attribut | Détail |
|---|---|
| Rôle | Registre central de la vie logique de chaque stratégie. Complémentaire au POLY_STRATEGY_ACCOUNT qui suit le capital. Le Registry suit l'identité, la version, les paramètres et le cycle de vie. |
| Inputs | Tous les agents qui modifient l'état d'une stratégie (Orchestrator, Promotion Gate, Tuner, Scout) |
| Outputs | `state/registry/strategy_registry.json` |
| Fréquence | Sur événement (chaque changement de statut ou de paramètres) |
| LLM | Non |

**Différence ACCOUNT vs REGISTRY :**

| | POLY_STRATEGY_ACCOUNT | POLY_STRATEGY_REGISTRY |
|---|---|---|
| Suit quoi | Le capital, le P&L, le drawdown | L'identité, la version, les paramètres, la plateforme |
| Créé quand | Au lancement du paper testing | Au moment du scouting (bien avant le trading) |
| Modifié par | Chaque trade (P&L), Kill Switch (status) | Tuner (paramètres), Scout (version), Orchestrator (status) |
| Archivé quand | Stratégie stoppée (account gelé) | Jamais (le registry garde tout l'historique) |
| Question clé | "Combien cette stratégie a-t-elle gagné/perdu ?" | "Quels paramètres tournent actuellement ? Quelle version ? Quelle plateforme ?" |

**Structure du Registry :**

```json
{
  "POLY_ARB_SCANNER": {
    "strategy_id": "STRAT_001",
    "status": "active",
    "version": "1.2",
    "category": "arbitrage",
    "platform": "polymarket",
    "parameters": {
      "sum_threshold": 0.97,
      "min_executability": 60,
      "gas_threshold": 0.01
    },
    "parameter_history": [
      {"version": "1.0", "date": "2026-04-01", "params": {"sum_threshold": 0.98}},
      {"version": "1.1", "date": "2026-04-10", "params": {"sum_threshold": 0.97}},
      {"version": "1.2", "date": "2026-04-18", "params": {"sum_threshold": 0.97, "min_executability": 60}}
    ],
    "lifecycle": {
      "scouted": "2026-03-15",
      "backtested": "2026-03-16",
      "paper_started": "2026-04-01",
      "paper_evaluated": "2026-04-15",
      "promoted_live": "2026-04-16",
      "paused": null,
      "stopped": null,
      "reactivated": null
    },
    "backtest_ids": ["BT_001", "BT_003"],
    "account_ids": ["ACC_POLY_ARB_SCANNER_v1"],
    "notes": "Première stratégie promue en live. Version 1.2 ajuste min_executability après tuning."
  }
}
```

Le Registry permet de répondre à des questions que l'Account ne couvre pas : "Quels paramètres cette stratégie utilisait-elle quand elle a été stoppée il y a 3 mois ? Ont-ils changé depuis ? Sur quelle plateforme tournait-elle ?"

---

### 1.9 — Évaluation & Recherche (Couche 7)

**`POLY_STRATEGY_EVALUATOR`**

| Attribut | Détail |
|---|---|
| Rôle | Comparer, classer, juger. Score 8 axes. Verdicts STAR / SOLID / FRAGILE / DECLINING / RETIRE. |
| Inputs | `POLY_STRATEGY_ACCOUNT` + `POLY_STRATEGY_REGISTRY` + métriques + alertes decay |
| Outputs | `strategy_scores.json`, `strategy_rankings.json`, bus event `eval:score_updated` |
| Fréquence | Nightly 03:15 UTC + milestones (50 trades) |
| LLM | Sonnet |

**`POLY_BACKTEST_ENGINE`**

| Attribut | Détail |
|---|---|
| Rôle | Replay de marchés historiques. Outil de TRI RAPIDE, pas de validation. |
| Outputs | `backtest_results/{strategy}_{date}.json` |
| Fréquence | Sur événement |
| LLM | Non |

**DOCTRINE BACKTEST (renforcée v2) :**

Le backtest est un filtre de rejet, pas un filtre d'acceptation. Concrètement :
- Un backtest NÉGATIF est une raison suffisante pour REJETER une stratégie. Si elle ne marche pas sur le passé, elle ne marchera probablement pas en live.
- Un backtest POSITIF n'est JAMAIS une raison suffisante pour ACCEPTER une stratégie. Il ne simule ni le slippage, ni la concurrence, ni les conditions réelles de marché. Son résultat est structurellement optimiste.
- Seule la combinaison **backtest positif + paper trading positif + tradabilité réelle confirmée** justifie de proposer une stratégie au live.
- Le malus -15 sur l'axe tradabilité de l'Evaluator existe pour matérialiser cet optimisme structurel dans le score.
- Le `POLY_STRATEGY_PROMOTION_GATE` vérifie explicitement que le paper trading a été complété (≥ 50 trades + 14 jours) avant toute promotion, ce qui empêche structurellement de promouvoir sur la base d'un backtest seul.

Les autres agents d'évaluation et recherche (STRATEGY_TUNER, DECAY_DETECTOR, COMPOUNDER, STRATEGY_SCOUT) sont inchangés vs v1.

---

### 1.10 — Infrastructure

**`POLY_SYSTEM_MONITOR`**

| Attribut | Détail |
|---|---|
| Rôle | Surveillance infrastructure : agents (PM2, mémoire, CPU), APIs (latence, connectivité), VPS (disque, RAM), cohérence nightly |
| Outputs | Bus events `system:*`, alertes vers `POLY_KILL_SWITCH` si API down |
| Fréquence | Agents 60s, APIs 30s, infra 5min, cohérence nightly 02:50 UTC |

**`POLY_HEARTBEAT`** et **`POLY_PERFORMANCE_LOGGER`** — inchangés vs v1.

---

## 2. SKILLS OPENCLAW NÉCESSAIRES

| Skill | Agents | Rôle | Coût |
|---|---|---|---|
| `polymarket-market-connector` | POLY_MARKET_CONNECTOR | Interface multi-plateformes, WS management | 0 |
| `polymarket-data-validation` | POLY_DATA_VALIDATOR | Règles validation par source, marquage SUSPECT | 0 |
| `polymarket-arb-detection` | POLY_ARB_SCANNER | Bundle arb YES+NO + Dutch book | 0 |
| `polymarket-latency-arb` | POLY_LATENCY_ARB, POLY_BROWNIAN_SNIPER | Signal Engine + Brownian Motion | 0 |
| `polymarket-weather` | POLY_WEATHER_ARB | Mapping stations, parsing buckets | 0 |
| `polymarket-resolution-parser` | POLY_MARKET_ANALYST | Prompt Sonnet → phrase booléenne | ~500 tok |
| `polymarket-wallet-scoring` | POLY_WALLET_TRACKER | EV composite, spécialisation | 0 |
| `polymarket-microstructure` | POLY_MARKET_STRUCTURE_ANALYZER | Liquidité, spread, slippage, score | 0 |
| `polymarket-kelly-sizing` | POLY_KELLY_SIZER | Half/Quarter Kelly + VaR | 0 |
| `polymarket-paper-execution` | POLY_PAPER_EXECUTION_ENGINE | Simulation ordres, slippage réaliste | 0 |
| `polymarket-live-execution` | POLY_LIVE_EXECUTION_ENGINE | py-clob-client, fills, retries, gas | 0 |
| `polymarket-promotion-gate` | POLY_STRATEGY_PROMOTION_GATE | 10 checks de promotion paper→live | 0 |
| `polymarket-strategy-eval` | POLY_STRATEGY_EVALUATOR | Scoring 8 axes, verdicts | ~1000 tok |
| `polymarket-decay-detection` | POLY_DECAY_DETECTOR | Rolling 7j vs 30j, sévérités | 0 |
| `polymarket-scout-research` | POLY_STRATEGY_SCOUT | Scraping, évaluation viabilité | ~2000 tok |
| `polymarket-backtest` | POLY_BACKTEST_ENGINE | Replay historique (outil de tri) | 0 |
| `polymarket-system-monitor` | POLY_SYSTEM_MONITOR | Surveillance agents, APIs, infra | 0 |
| `polymarket-capital-management` | POLY_CAPITAL_MANAGER | Gestion accounts, vérification pré-trade | 0 |

Skills OpenClaw réutilisés : `news-scoring`, `kill-switch`, `compound-learning`, `token-optimization`, `heartbeat-monitoring`.

---

## 3. APIs ET SOURCES DE DONNÉES

| API | Usage | Fréquence | Coût | Auth |
|---|---|---|---|---|
| Polymarket CLOB API | Prix, orderbook, ordres (live) | Continu (WS) | Gratuit | API key + secret |
| Polymarket Gamma API | Listing marchés, résolutions | À la demande | Gratuit | Sans auth |
| Binance WebSocket | Prix BTC/ETH, depth20 | Continu (WS) | Gratuit | API key (lecture) |
| NWS / NOAA API | Prévisions température 6 villes | 2 min | Gratuit | Sans auth |
| Polygon RPC | Positions on-chain wallets | 60s | Gratuit (QuickNode free) | Endpoint URL |
| Kalshi REST API | Prix, marchés (futur Phase 2) | Continu quand activé | Gratuit | API key (futur) |
| Anthropic API | LLM agents hybrides | Variable | ~$15-30/mois | API key existante |
| NEWS_FEED (OpenClaw) | Flux news | Continu | $0 additionnel | Existant |

Coût total données : $0/mois. Alternatives : Alchemy (Polygon), Kraken (Binance), Open-Meteo (NOAA).

---

## 4. CONNECTEURS DE MARCHÉ

Architecture `POLY_MARKET_CONNECTOR` inchangée vs v1 : interface commune (get_markets, get_orderbook, place_order, get_positions, get_settlement), `connector_polymarket` actif, `connector_kalshi` et `connector_sportsbook` futurs.

Ajout v2 : les ordres live sont routés par le `POLY_EXECUTION_ROUTER` vers le `POLY_LIVE_EXECUTION_ENGINE` qui utilise le connecteur approprié via le champ `platform` du signal. Le `POLY_PAPER_EXECUTION_ENGINE` n'utilise PAS les connecteurs pour l'envoi d'ordres (simulation pure).

---

## 5. STRUCTURE DE STOCKAGE DES DONNÉES

Ajout v2 : dossier `state/registry/` pour le `POLY_STRATEGY_REGISTRY`.

```
state/
├── orchestrator/           ← Cycles, state machine
├── registry/               ← NOUVEAU v2 : POLY_STRATEGY_REGISTRY
│   └── strategy_registry.json
├── accounts/               ← POLY_STRATEGY_ACCOUNT (capital)
├── risk/                   ← Kill Switch + Global Risk Guard
├── feeds/                  ← Données temps réel (validées)
├── trading/                ← Logs paper + live (séparés)
├── evaluation/             ← Scores, rankings, decay, tuning
├── research/               ← Scouted, backtests, résolutions
├── human/                  ← Approvals, décisions
├── audit/                  ← POLY_AUDIT_LOG (immuable)
├── bus/                    ← NOUVEAU v2 : Event bus state
│   └── pending_events.jsonl
└── historical/             ← SQLite (marchés, signaux)
```

---

## 6. GESTION DU CAPITAL

### 6.1 — POLY_STRATEGY_ACCOUNT (suit le capital)

Inchangé vs v1. Capital initial 1 000€. Statuts : paper_testing, awaiting_human, active, paused, stopped.

### 6.2 — POLY_STRATEGY_REGISTRY (suit la vie logique) — NOUVEAU v2

Version, paramètres actifs, historique de promotion/pause/retrait, plateforme cible, catégorie, notes. Complémentaire à l'Account.

### 6.3 — POLY_GLOBAL_RISK_GUARD

Inchangé vs v1. NORMAL < 2K€, ALERTE 2-3K€, CRITIQUE 3-4K€, ARRÊT TOTAL ≥ 4K€.

---

## 7. BUS DE COMMUNICATION

### Mécanisme

Event bus via fichiers JSON Lines + polling, cohérent avec l'architecture OpenClaw (ctx.state, PM2, Node.js poller).

```
PRODUCTEUR → écrit un événement dans state/bus/pending_events.jsonl (append-only)
ORCHESTRATOR → lit pending_events.jsonl toutes les 1-5s (polling)
ORCHESTRATOR → route l'événement vers le consommateur approprié
CONSOMMATEUR → traite l'événement, vérifie idempotence via event_id
ORCHESTRATOR → marque l'événement comme traité (processed_events.jsonl)
```

### Format Commun de Tout Événement

Chaque événement, quel que soit le topic, contient cette enveloppe :

```json
{
  "event_id": "EVT_20260420_143245_001",
  "topic": "trade:signal",
  "timestamp": "2026-04-20T14:32:45.123Z",
  "producer": "POLY_ARB_SCANNER",
  "priority": "normal",
  "retry_count": 0,
  "payload": { }
}
```

Règle d'idempotence : chaque consommateur maintient un set `processed_event_ids` (dernier 10 000 IDs). Si `event_id` est déjà dans le set → l'événement est ignoré. Cela garantit qu'un replay accidentel (crash + restart) ne produit pas de trades dupliqués.

Retry : si un consommateur échoue, l'Orchestrator remet l'événement en queue avec `retry_count + 1`. Après 3 échecs → `state/bus/dead_letter.jsonl` + alerte `POLY_SYSTEM_MONITOR`.

### Contrats d'Événements — Payloads Exacts

#### Feeds (mode : écrasement — seule la dernière valeur compte)

**`feed:price_update`** — Publié par `POLY_MARKET_CONNECTOR`, consommé par `POLY_DATA_VALIDATOR` puis tous les STRATEGY_AGENTS.

```json
{
  "payload": {
    "market_id": "0xabc...",
    "platform": "polymarket",
    "yes_price": 0.62,
    "no_price": 0.39,
    "yes_ask": 0.63,
    "yes_bid": 0.61,
    "no_ask": 0.40,
    "no_bid": 0.38,
    "volume_24h": 125000,
    "data_status": "VALID"
  }
}
```

**`feed:binance_update`** — Publié par `POLY_BINANCE_FEED`, consommé par `POLY_DATA_VALIDATOR` puis `POLY_BINANCE_SIGNALS`.

```json
{
  "payload": {
    "symbol": "BTCUSDT",
    "price": 98432.50,
    "bids_top5": [[98430, 1.2], [98428, 0.8]],
    "asks_top5": [[98435, 0.9], [98437, 1.1]],
    "last_trade_qty": 0.15,
    "data_status": "VALID"
  }
}
```

**`feed:noaa_update`** — Publié par `POLY_NOAA_FEED`, consommé par `POLY_DATA_VALIDATOR` puis `POLY_WEATHER_ARB`.

```json
{
  "payload": {
    "station": "KLGA",
    "city": "New York",
    "daily_max_forecast_f": 82,
    "confidence": 0.92,
    "forecast_timestamp": "2026-04-20T12:00:00Z",
    "data_status": "VALID"
  }
}
```

**`feed:wallet_update`** — Publié par `POLY_WALLET_FEED`, consommé par `POLY_DATA_VALIDATOR` puis `POLY_WALLET_TRACKER`.

```json
{
  "payload": {
    "wallet": "0x1234...",
    "positions": [
      {"market_id": "0xabc...", "side": "YES", "size": 500, "avg_price": 0.45}
    ],
    "data_status": "VALID"
  }
}
```

#### Signaux (mode : écrasement pour les scores, queue pour les événements ponctuels)

**`signal:binance_score`** — Publié par `POLY_BINANCE_SIGNALS`, consommé par `POLY_LATENCY_ARB` et `POLY_BROWNIAN_SNIPER`. Mode écrasement.

```json
{
  "payload": {
    "symbol": "BTCUSDT",
    "price": 98432.50,
    "obi": 0.35,
    "cvd": 12450.5,
    "vwap_position": 0.62,
    "momentum": 0.78,
    "composite_score": 0.54
  }
}
```

**`signal:wallet_convergence`** — Publié par `POLY_WALLET_TRACKER`, consommé par `POLY_CONVERGENCE_STRAT`. Mode queue.

```json
{
  "payload": {
    "market_id": "0xabc...",
    "direction": "YES",
    "convergent_wallets": ["0x1234...", "0x5678...", "0x9abc..."],
    "wallet_count": 3,
    "avg_ev_score": 0.82,
    "detection_timestamp": "2026-04-20T14:32:00Z"
  }
}
```

**`signal:resolution_parsed`** — Publié par `POLY_MARKET_ANALYST`, consommé par `POLY_OPP_SCORER`, `POLY_NO_SCANNER`, `POLY_CONVERGENCE_STRAT`. Mode cache (1x par marché).

```json
{
  "payload": {
    "market_id": "0xabc...",
    "boolean_condition": "BTC price > 100000 USD on 2026-06-01 00:00 UTC per CoinGecko",
    "ambiguity_score": 2,
    "unexpected_risk_score": 1,
    "source_url": "https://polymarket.com/event/..."
  }
}
```

#### Trading (mode : queue — chaque événement traité exactement une fois)

**`trade:signal`** — Publié par tout STRATEGY_AGENT, consommé par `POLY_FACTORY_ORCHESTRATOR`.

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "account_id": "ACC_POLY_ARB_SCANNER",
    "market_id": "0xabc...",
    "platform": "polymarket",
    "direction": "BUY_YES_AND_NO",
    "confidence": 0.95,
    "suggested_size_eur": 30,
    "signal_type": "bundle_arb",
    "signal_detail": {"yes_ask": 0.47, "no_ask": 0.49, "spread": 0.04}
  }
}
```

**`trade:validated`** — Publié par l'Orchestrator (après passage des 7 filtres), consommé par `POLY_EXECUTION_ROUTER`.

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "account_id": "ACC_POLY_ARB_SCANNER",
    "market_id": "0xabc...",
    "platform": "polymarket",
    "direction": "BUY_YES_AND_NO",
    "validated_size_eur": 28.5,
    "tranches": [{"size": 14.25, "price_limit": 0.48}, {"size": 14.25, "price_limit": 0.50}],
    "filters_passed": ["data_quality", "microstructure", "resolution", "sizing", "kill_switch", "risk_guardian", "capital_manager"],
    "executability_score": 72,
    "slippage_estimated": 0.003
  }
}
```

**`execute:paper`** / **`execute:live`** — Publié par `POLY_EXECUTION_ROUTER`, consommé par le moteur correspondant.

```json
{
  "payload": {
    "execution_mode": "paper",
    "strategy": "POLY_ARB_SCANNER",
    "account_id": "ACC_POLY_ARB_SCANNER",
    "market_id": "0xabc...",
    "platform": "polymarket",
    "direction": "BUY_YES_AND_NO",
    "size_eur": 28.5,
    "tranches": [{"size": 14.25, "price_limit": 0.48}],
    "expected_fill_price": 0.471,
    "slippage_estimated": 0.003
  }
}
```

**`trade:paper_executed`** / **`trade:live_executed`** — Publié par le moteur d'exécution, consommé par `POLY_DATA_STORE`, `POLY_PERFORMANCE_LOGGER`, `POLY_AUDIT_LOG`.

```json
{
  "payload": {
    "trade_id": "TRD_20260420_001",
    "execution_mode": "live",
    "strategy": "POLY_ARB_SCANNER",
    "account_id": "ACC_POLY_ARB_SCANNER",
    "market_id": "0xabc...",
    "platform": "polymarket",
    "direction": "BUY_YES_AND_NO",
    "fill_price": 0.473,
    "slippage_actual": 0.004,
    "size_eur": 28.5,
    "fees": 0.02,
    "gas_cost": 0.005,
    "tx_hash": "0xdef...",
    "execution_time_ms": 340
  }
}
```

#### Risque (mode : queue prioritaire pour kill_switch et global_risk)

**`risk:kill_switch`** — Publié par `POLY_KILL_SWITCH`, consommé par `POLY_FACTORY_ORCHESTRATOR` et `POLY_CAPITAL_MANAGER`. Prioritaire.

```json
{
  "priority": "high",
  "payload": {
    "action": "pause_strategy",
    "strategy": "POLY_LATENCY_ARB",
    "account_id": "ACC_POLY_LATENCY_ARB",
    "reason": "daily_drawdown_exceeded",
    "drawdown_pct": -5.2,
    "threshold_pct": -5.0,
    "resume_at": "2026-04-21T00:00:00Z"
  }
}
```

**`risk:global_status`** — Publié par `POLY_GLOBAL_RISK_GUARD`, consommé par `POLY_FACTORY_ORCHESTRATOR` et `POLY_STRATEGY_PROMOTION_GATE`.

```json
{
  "payload": {
    "status": "ALERTE",
    "total_loss_eur": 2150.30,
    "max_loss_eur": 4000.00,
    "pct_used": 0.538,
    "action_taken": "block_new_live_promotions",
    "accounts_contributing": {"POLY_LATENCY_ARB": -820.50, "POLY_CONVERGENCE_STRAT": -1329.80}
  }
}
```

#### Promotion (mode : queue)

**`promotion:request`** — Publié par `POLY_FACTORY_ORCHESTRATOR`, consommé par `POLY_STRATEGY_PROMOTION_GATE`.

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "approval_id": "POLY_LIVE_003",
    "evaluator_score": 78,
    "paper_trades": 127,
    "paper_days": 21
  }
}
```

**`promotion:approved`** — Publié par `POLY_STRATEGY_PROMOTION_GATE`, consommé par `POLY_CAPITAL_MANAGER` (crée le compte live), `POLY_FACTORY_ORCHESTRATOR` (met à jour le cycle), `POLY_STRATEGY_REGISTRY` (met à jour le lifecycle).

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "approval_id": "POLY_LIVE_003",
    "checks_passed": 10,
    "initial_capital_eur": 1000,
    "max_per_trade_eur": 50,
    "kill_switch_daily_pct": -0.03
  }
}
```

**`promotion:denied`** — Publié par `POLY_STRATEGY_PROMOTION_GATE`, consommé par `POLY_FACTORY_ORCHESTRATOR` et `POLY_AUDIT_LOG`.

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "check_failed": "global_risk_guard",
    "check_number": 8,
    "reason": "Global risk status is ALERTE, no new live promotions allowed",
    "global_loss_eur": 2150.30
  }
}
```

#### Évaluation et système (mode : queue)

**`eval:score_updated`** — Publié par `POLY_STRATEGY_EVALUATOR`, consommé par `POLY_FACTORY_ORCHESTRATOR` et `POLY_CAPITAL_MANAGER`.

```json
{
  "payload": {
    "strategy": "POLY_ARB_SCANNER",
    "account_id": "ACC_POLY_ARB_SCANNER",
    "score_total": 78,
    "verdict": "STAR",
    "previous_score": 72,
    "previous_verdict": "SOLID",
    "axes": {"profitability": 75, "stability": 90, "tradability": 85, "resilience": 88}
  }
}
```

**`data:validation_failed`** — Publié par `POLY_DATA_VALIDATOR`, consommé par `POLY_SYSTEM_MONITOR` et `POLY_AUDIT_LOG`.

```json
{
  "payload": {
    "source": "POLY_MARKET_CONNECTOR",
    "platform": "polymarket",
    "market_id": "0xabc...",
    "check_failed": "price_range",
    "reason": "yes_price = 0.00 (outside [0.01, 0.99])",
    "raw_value": 0.00,
    "consecutive_failures": 3
  }
}
```

### Modes de Livraison

| Mode | Comportement | Topics concernés |
|---|---|---|
| **Écrasement** | Seule la dernière valeur compte | `feed:*`, `signal:binance_score` |
| **Queue** | Traité exactement une fois, dans l'ordre | `trade:*`, `promotion:*`, `eval:*`, `data:*` |
| **Cache** | Stocké et réutilisé, un seul calcul par clé | `signal:resolution_parsed` |
| **Sync** | L'appelant attend la réponse | `risk:portfolio_check` (pré-trade) |
| **Prioritaire** | Traité avant les événements normaux | `risk:kill_switch`, `news:high_impact` |

---

## 8. ORDRE D'IMPLÉMENTATION

Les phases ci-dessous sont un **ordre recommandé**, pas un calendrier ferme. L'effort estimé est indicatif et dépend de la familiarité avec les APIs, de la quantité de données historiques disponibles, et des imprévus inévitables dans un système qui interagit avec des APIs externes.

### Phase 1 — Fondations : Data + Connecteurs + Bus

**Effort estimé** : 1-3 semaines selon expérience API
**Prérequis** : VPS Hostinger opérationnel, clés API Polymarket et Binance

```
1. POLY_DATA_STORE         ← Structure fichiers, ctx.state
2. POLY_AUDIT_LOG          ← Append JSON Lines
3. Bus de communication    ← pending_events.jsonl + polling Orchestrator (version minimale)
4. POLY_MARKET_CONNECTOR   ← connector_polymarket (WebSocket CLOB + Gamma)
5. POLY_BINANCE_FEED       ← WebSocket Binance
6. POLY_NOAA_FEED          ← REST NWS
7. POLY_WALLET_FEED        ← REST Polymarket + Polygon RPC
```

**Livrable** : données affluent dans state/feeds/ en continu. Audit log et bus fonctionnent.

**Critère de validation** : fichiers state se mettent à jour 24h sans interruption. Événements transitent via le bus.

---

### Phase 2 — Signaux + Validation

**Effort estimé** : 1-2 semaines
**Prérequis** : Phase 1 complète

```
8.  POLY_DATA_VALIDATOR       ← Règles validation par source
9.  POLY_BINANCE_SIGNALS      ← OBI, CVD, VWAP, Momentum, score
10. POLY_MARKET_STRUCTURE_ANALYZER ← Liquidité, spread, profondeur, score
11. POLY_WALLET_TRACKER       ← EV scoring, spécialisation, convergence
12. POLY_MARKET_ANALYST       ← Parser résolution via Sonnet (cache)
```

**Livrable** : signaux enrichis et validés dans state/feeds/. Données invalides marquées SUSPECT.

---

### Phase 3 — Backtest Engine

**Effort estimé** : 1 semaine
**Prérequis** : Phase 1 (Data Store) + Phase 2 (signaux archivés dans historical/)

```
13. POLY_BACKTEST_ENGINE     ← Replay historique, métriques (outil de tri, PAS de validation)
```

**Livrable** : on peut soumettre des paramètres et obtenir WR, Sharpe, MDD, PF en minutes.

---

### Phase 4 — Paper Trading + Registry

**Effort estimé** : 2-3 semaines
**Prérequis** : Phase 2 (signaux) + Phase 3 (backtest pour pré-calibrer)

```
14. POLY_STRATEGY_REGISTRY      ← Registre central des stratégies
15. POLY_STRATEGY_ACCOUNT       ← Modèle de données capital
16. POLY_KELLY_SIZER            ← Sizing basé sur le compte
17. POLY_PAPER_EXECUTION_ENGINE ← Simulation (AUCUNE dépendance py-clob-client)
18. POLY_ORDER_SPLITTER         ← Découpage ordres (simulé)
19. POLY_ARB_SCANNER            ← Première stratégie
20. POLY_WEATHER_ARB            ← Deuxième stratégie
```

**Livrable** : deux stratégies en paper, 1 000€ fictifs chacune, accounts et registry mis à jour.

---

### Phase 5 — Évaluation + Risque

**Effort estimé** : 2-3 semaines
**Prérequis** : Phase 4 (stratégies en paper qui produisent des trades)

```
21. POLY_KILL_SWITCH             ← Protection par compte
22. POLY_RISK_GUARDIAN           ← Protection portefeuille (positions, exposure, corrélation)
23. POLY_GLOBAL_RISK_GUARD       ← Plafond 4 000€ (perte cumulée totale)
24. POLY_CAPITAL_MANAGER         ← Gestion accounts, vérification pré-trade
25. POLY_PERFORMANCE_LOGGER      ← Agrégation métriques
26. POLY_STRATEGY_EVALUATOR      ← Score 8 axes, verdicts, classement
27. POLY_DECAY_DETECTOR          ← Rolling 7j vs 30j
```

**Livrable** : évaluation nightly fonctionne. Kill Switch et Global Risk Guard opérationnels.

---

### Phase 6 — Stratégies Complémentaires

**Effort estimé** : 2-3 semaines
**Prérequis** : Phase 5 (risque opérationnel pour protéger les nouveaux accounts)

```
28-34. POLY_LATENCY_ARB, POLY_BROWNIAN_SNIPER, POLY_PAIR_COST,
       POLY_OPP_SCORER, POLY_NO_SCANNER, POLY_CONVERGENCE_STRAT, POLY_NEWS_STRAT
```

**Livrable** : 9 stratégies en parallèle en paper, chacune sur son propre account.

---

### Phase 7 — Orchestration + Promotion + Live

**Effort estimé** : 3-5 semaines (phase la plus critique)
**Prérequis** : Phases 1-6 complètes, 14+ jours de paper trading réussi

```
35. POLY_FACTORY_ORCHESTRATOR      ← State machine, cycles complets, routing bus
36. POLY_STRATEGY_PROMOTION_GATE   ← 10 checks de promotion paper → live
37. POLY_EXECUTION_ROUTER          ← Routing paper/live basé sur Registry
38. POLY_LIVE_EXECUTION_ENGINE     ← py-clob-client on-chain (MODULE SÉPARÉ du paper)
39. POLY_COMPOUNDER                ← Compound Learning nightly
40. POLY_STRATEGY_TUNER            ← Optimisation post-50 trades
41. POLY_STRATEGY_SCOUT            ← Veille hebdomadaire
```

**Livrable** : pipeline complet. Première stratégie promue en micro-live si score ≥ 60 + validation humaine + Promotion Gate approuve.

---

### Phase 8 — Monitoring + Robustesse

**Effort estimé** : 1-2 semaines
**Prérequis** : Phase 7 (système complet à surveiller)

```
42. POLY_SYSTEM_MONITOR     ← Surveillance infrastructure
43. POLY_HEARTBEAT          ← Pattern existant, adapter
```

---

### Phase 9 — Multi-Plateformes (Futur)

**Effort estimé** : variable par plateforme
**Prérequis** : stratégie cross-platform validée en paper

```
44. connector_kalshi.py      ← Phase 2 du multi-plateforme
45. connector_sportsbook.py  ← Phase 3
```

---

## 9. GARDE-FOUS DU SYSTÈME

### 9.1 — 5 Couches de Protection

```
COUCHE 1 — PAR TRADE (chaîne de 7 filtres)
  POLY_DATA_VALIDATOR          Filtre 0 : données valides
  POLY_MARKET_STRUCTURE_ANALYZER Filtre 1 : executability ≥ 40/60
  POLY_MARKET_ANALYST          Filtre 2 : ambiguity < 3
  POLY_KELLY_SIZER             Filtre 3 : max 3% du COMPTE
  POLY_KILL_SWITCH             Filtre 4 : drawdown, pertes, feeds
  POLY_RISK_GUARDIAN           Filtre 5 : exposure portefeuille
  POLY_CAPITAL_MANAGER         Filtre 6 : capital du compte suffisant

COUCHE 2 — PAR STRATÉGIE (POLY_STRATEGY_ACCOUNT + KILL_SWITCH)
  Capital isolé : 1 000€ / -30% max / -5% daily / 3 pertes → pause

COUCHE 3 — PAR PORTEFEUILLE (POLY_RISK_GUARDIAN seul)
  Max 80% exposé / 5 positions / anti-corrélation / 40% par catégorie

COUCHE 4 — SYSTÈME GLOBAL (POLY_GLOBAL_RISK_GUARD seul)
  Perte cumulée totale < 4 000€. ARRÊT TOTAL si dépassé.

COUCHE 5 — STRUCTURELLE
  Paper → live JAMAIS automatique
  POLY_STRATEGY_PROMOTION_GATE : 10 checks obligatoires
  POLY_PAPER_EXECUTION_ENGINE physiquement incapable d'envoyer un ordre réel
  POLY_LIVE_EXECUTION_ENGINE dans un module séparé, auditable isolément
  Approbation humaine expire 7 jours
  POLY_AUDIT_LOG trace immuable de tout
  POLY_STRATEGY_REGISTRY trace l'identité et les versions
```

### 9.2 — Agents de Sécurité

| Agent | Protège | Scope | Override |
|---|---|---|---|
| `POLY_DATA_VALIDATOR` | Qualité données | Chaque donnée | Marque SUSPECT |
| `POLY_KILL_SWITCH` | Chaque stratégie | 1 account à la fois | Stop stratégie/session |
| `POLY_RISK_GUARDIAN` | Portefeuille | Toutes positions ensemble | Bloque si exposure max |
| `POLY_GLOBAL_RISK_GUARD` | Système entier | Somme pertes cumulées | Arrêt total ≥ 4K€ |
| `POLY_STRATEGY_PROMOTION_GATE` | Transition paper→live | 1 stratégie à la fois | Refuse si 1 check échoue |
| `POLY_CAPITAL_MANAGER` | Comptes | 1 account à la fois | Bloque si capital insuffisant |
| `POLY_SYSTEM_MONITOR` | Infrastructure | VPS + APIs + agents | Alerte + kill switch |
| `POLY_EXECUTION_ROUTER` | Routing paper/live | Chaque signal | Route selon Registry |
| `POLY_AUDIT_LOG` | Traçabilité | Tout le système | Journalise, ne bloque pas |

---

## ANNEXE — RÉSUMÉ EXÉCUTIF

```
POLY_FACTORY = 45 composants en 9 phases

Phase 1 : Data + connecteurs + bus    → les données affluent
Phase 2 : Signaux + validation        → les données sont fiables
Phase 3 : Backtest engine             → on peut filtrer les mauvaises idées
Phase 4 : Paper + registry            → les stratégies tournent en fictif
Phase 5 : Évaluation + risque         → le système se protège et compare
Phase 6 : Stratégies complètes        → 9 stratégies en parallèle
Phase 7 : Orchestration + promotion + live → première stratégie en réel
Phase 8 : Monitoring + robustesse     → le système est surveillé
Phase 9 : Multi-plateformes           → Kalshi, sportsbooks (futur)

Corrections v2 :
  - Paper et live dans des modules SÉPARÉS (pas un flag)
  - Promotion Gate centralise la transition paper → live (10 checks)
  - Registry suit la vie logique, Account suit le capital
  - Bus de communication défini (événements, topics, modes, idempotence)
  - Timeline = ordre recommandé, pas promesse de calendrier
  - Backtest = outil de tri, JAMAIS de validation finale
  - RISK_GUARDIAN (portefeuille) ≠ GLOBAL_RISK_GUARD (système) : démarcation nette

Corrections v3 :
  - Gate DÉCIDE, Capital Manager EXÉCUTE (création compte live)
  - Naming uniformisé (POLY_BROWNIAN_SNIPER partout)
  - Bus figé avec 15 payloads JSON exacts, prêts à coder
```

---

*Document basé sur POLY_FACTORY_ARCHITECTURE v4.0, POLY_FACTORY_PIPELINE v4.0, corrections architecturales v2 et v3.*
