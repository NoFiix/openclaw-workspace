# pipeline_flows.md — Flux du pipeline POLY_FACTORY

**Date** : 2026-03-15
**Scope** : Pipeline complet feeds → signaux → stratégies → 7 filtres → exécution paper

---

## Pipeline principal — Signal to Execution

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     DONNÉES BRUTES (30–600s)                           │
│                                                                         │
│  ┌──────────────────┐ ┌──────────────┐ ┌────────────┐ ┌────────────┐ │
│  │ connector        │ │ binance_feed │ │ noaa_feed  │ │ wallet_feed│ │
│  │ 300s             │ │ 30s          │ │ 120s       │ │ 600s       │ │
│  │ [Polymarket]     │ │ [Binance]    │ │ [NWS/NOAA] │ │ [Gamma]    │ │
│  │ → price_update   │ │ → binance_up │ │ → noaa_up  │ │ → wallet_up│ │
│  │ ✅ ACTIF         │ │ ❌ DISABLED  │ │ ✅ ACTIF   │ │ ❌ DISABLED│ │
│  └────────┬─────────┘ └──────┬───────┘ └─────┬──────┘ └─────┬──────┘ │
│           │                   │                │              │         │
├───────────┼───────────────────┼────────────────┼──────────────┼─────────┤
│           ▼                   ▼                │              ▼         │
│     SIGNAUX (10–60s)                           │                        │
│                                                │                        │
│  ┌──────────────────┐ ┌──────────────┐        │ ┌────────────────────┐│
│  │ msa              │ │ binance_sig  │        │ │ wallet_tracker     ││
│  │ 30s ❌ DISABLED  │ │ 10s ❌ DIS.  │        │ │ 60s ❌ DISABLED    ││
│  │ → market_struct  │ │ → binance_sc │        │ │ → wallet_converg   ││
│  └────────┬─────────┘ └──────┬───────┘        │ └────────┬───────────┘│
│           │                   │                │          │             │
│  ┌──────────────────┐        │                │          │             │
│  │ market_analyst   │        │                │          │             │
│  │ [Sonnet LLM]     │        │                │          │             │
│  │ → resolution     │        │                │          │             │
│  └────────┬─────────┘        │                │          │             │
│           │                   │                │          │             │
├───────────┼───────────────────┼────────────────┼──────────┼─────────────┤
│           ▼                   ▼                ▼          ▼             │
│     STRATÉGIES (5–60s)                                                  │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                                                                    ││
│  │  arb_scanner ❌    weather_arb ✅    latency_arb ❌    brownian ❌ ││
│  │  pair_cost ❌      opp_scorer ✅     no_scanner ✅                 ││
│  │  convergence ✅    news_strat ✅                                   ││
│  │                                                                    ││
│  │  5 actives / 4 disabled ──→ trade:signal                          ││
│  │  ⚠️ 0 signaux émis en 1.5 jours                                   ││
│  └────────────────────────────────┬───────────────────────────────────┘│
│                                    │                                    │
├────────────────────────────────────┼────────────────────────────────────┤
│                                    ▼                                    │
│     ORCHESTRATEUR — 7 FILTRES SÉQUENTIELS                              │
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Filtre 1: DATA QUALITY                                         │    │
│  │   executability ≥ 40 (MSA score)                               │    │
│  │   slippage estimé ≤ 2%                                         │    │
│  │   ⚠️ MSA DISABLED → filtre non alimenté                        │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 2: MICROSTRUCTURE                                       │    │
│  │   ambiguity_score ≤ 3 (résolution parsée)                     │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 3: RESOLUTION                                           │    │
│  │   résolution parsée et non ambiguë                             │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 4: KELLY SIZING                                         │    │
│  │   f* = (p·b - q) / b > 0 (half-Kelly)                         │    │
│  │   max 3% du capital du compte (30€ sur 1 000€)                │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 5: KILL SWITCH                                          │    │
│  │   kill_switch_status != PAUSE_SESSION/STOP_STRATEGY            │    │
│  │   daily drawdown < -5%                                         │    │
│  │   total drawdown < -30%                                        │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 6: RISK GUARDIAN                                        │    │
│  │   positions < 5 (all strategies)                               │    │
│  │   exposure < 80% total capital                                 │    │
│  │   category exposure < 40%                                      │    │
│  ├────────────────────────────────────────────────────────────────┤    │
│  │ Filtre 7: CAPITAL MANAGER                                      │    │
│  │   proposed_size ≤ available_capital dans le compte              │    │
│  └────────────────────────────────────┬───────────────────────────┘    │
│                                        │                                │
│                                        ▼ trade:validated                │
├────────────────────────────────────────┼────────────────────────────────┤
│                                        ▼                                │
│     EXÉCUTION (2s polling)                                              │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────┐      │
│  │ exec_router ❌ DISABLED                                       │      │
│  │   registry.status → paper_testing → execute:paper             │      │
│  │   registry.status → active → execute:live                     │      │
│  └───────────────────────┬──────────────────────────────────────┘      │
│                           ▼                                             │
│  ┌────────────────────────────────┐ ┌──────────────────────────────┐  │
│  │ paper_engine ✅ ACTIF          │ │ live_engine 💤 DORMANT        │  │
│  │ Slippage + fees 0.2%          │ │ py-clob-client (lazy load)   │  │
│  │ Débit compte stratégie        │ │ Credentials .env required    │  │
│  │ → paper_trades_log.jsonl      │ │ → live_trades_log.jsonl      │  │
│  │ → trade:paper_executed        │ │ → trade:live_executed        │  │
│  └────────────────────────────────┘ └──────────────────────────────┘  │
│                                                                         │
│  ⚠️ exec_router DISABLED → même si un signal passait les 7 filtres,    │
│     il ne serait PAS routé vers le paper_engine                         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Latence estimée par étape

| Étape | Agent | Latence pire cas | Tag |
|-------|-------|------------------|-----|
| 1 | Connector → price_update | 300s (cycle connector) | [OBSERVÉ] |
| 2 | MSA → market_structure | +30s | [OBSERVÉ] |
| 3 | Market analyst → resolution | +variable (LLM ~2-5s, cache souvent) | [OBSERVÉ] |
| 4 | Stratégie → trade:signal | +5-60s (selon stratégie) | [OBSERVÉ] |
| 5 | Orchestrateur → 7 filtres → trade:validated | ~instantané (sync dans tick) | [DÉDUIT] |
| 6 | Exec router → execute:paper | +2s (cycle polling) | [OBSERVÉ] |
| 7 | Paper engine → exécution | +2s (cycle polling) | [OBSERVÉ] |
| **TOTAL pire cas** | — | **~6-7 min** (si tous actifs) | [DÉDUIT] |
| **TOTAL typique** | — | **~30s-2 min** (cache chaud) | [DÉDUIT] |

---

## Points de blocage actuels [OBSERVÉ en production]

| # | Blocage | Impact | Tag |
|---|---------|--------|-----|
| **1** | **exec_router DISABLED** | Même si un signal validé est émis, il ne sera **jamais routé** vers le paper_engine | [OBSERVÉ] |
| **2** | **MSA DISABLED** | Filtre 1 (data_quality) n'a pas de données microstructure → impossible de calculer executability | [OBSERVÉ] |
| **3** | **binance_feed + binance_signals DISABLED** | latency_arb et brownian_sniper ne reçoivent aucun signal Binance | [OBSERVÉ] |
| **4** | **wallet_feed + wallet_tracker DISABLED** | convergence_strat ne reçoit jamais de `signal:wallet_convergence` | [OBSERVÉ] |
| **5** | **news:high_impact sans producteur** | news_strat ne recevra jamais d'event même si tous les agents sont actifs | [DÉDUIT] |
| **6** | **0 trade:signal en 1.5 jours** | Aucune stratégie active n'a trouvé d'edge suffisant (seuils trop stricts ou marchés inadaptés) | [OBSERVÉ] |

---

## Différences paper vs live

| Aspect | Paper (actuel) | Live (futur) | Tag |
|--------|----------------|--------------|-----|
| Routage | exec_router → `execute:paper` | exec_router → `execute:live` | [OBSERVÉ] |
| Exécution | paper_engine (simulation locale) | live_engine (py-clob-client, Polygon) | [OBSERVÉ] |
| Slippage | Estimé via MSA ou fallback | Réel (orderbook on-chain) | [OBSERVÉ] |
| Fees | 0.2% simulés | Réels (Polymarket + gas MATIC) | [OBSERVÉ] |
| Capital | Fictif (1 000€ / stratégie) | Réel (1 000€ / stratégie) | [OBSERVÉ] |
| Kill switch daily | -5% → pause (pas de perte réelle) | -5% → pause (perte réelle) | [OBSERVÉ] |
| Kill switch total | -30% → stop | -30% → stop | [OBSERVÉ] |
| Global risk | -4 000€ → arrêt total | -4 000€ → arrêt total | [OBSERVÉ] |
| Credentials | Non requis | POLY_API_KEY, POLY_SECRET, WALLET_PRIVATE_KEY requis | [OBSERVÉ] |

---

## État actuel : trades générés ?

| Métrique | Valeur | Tag |
|----------|--------|-----|
| `paper_trades_log.jsonl` | **Fichier inexistant ou vide** (0 trades) | [OBSERVÉ] |
| `trade:signal` dans le bus | **0 signaux** détectés dans les events récents | [OBSERVÉ] |
| `trade:validated` dans le bus | 0 | [OBSERVÉ] |
| `execute:paper` dans le bus | 0 | [OBSERVÉ] |
| Dernière activité bus | `system:heartbeat` events (monitoring uniquement) | [OBSERVÉ] |

**Conclusion** : Le pipeline est **entièrement stérile**. Aucun signal de trade n'a été émis par aucune stratégie en 1.5 jours de fonctionnement. [OBSERVÉ]

---

## Cohérence temporelle

### Risque de stale data

| Source | Fraîcheur | Risque | Tag |
|--------|-----------|--------|-----|
| feed:price_update | Toutes les 300s | MOYEN — prix Polymarket peuvent bouger significativement en 5 min | [DÉDUIT] |
| feed:binance_update | 30s (quand actif) | FAIBLE — actuellement DISABLED | [OBSERVÉ] |
| feed:noaa_update | 120s | FAIBLE — météo change lentement | [OBSERVÉ] |
| signal:resolution_parsed | Cache permanent | **ÉLEVÉ** — résolution jamais re-parsée, même si conditions changent | [DÉDUIT] |
| signal:market_structure | 30s (quand actif) | MOYEN — actuellement DISABLED, données stale | [OBSERVÉ] |

### Timestamps et ordonnancement

| Aspect | Observation | Tag |
|--------|-------------|-----|
| Format timestamp | ISO 8601 UTC (ex: `2026-03-15T20:38:28.562Z`) | [OBSERVÉ] |
| Cohérence producteur/consommateur | Tous les events ont un `timestamp` du producteur | [OBSERVÉ] |
| Ordonnancement | Le bus est FIFO (append), pas de réordonnancement | [OBSERVÉ] |
| Events dans le désordre | Possible si un agent traite un event avec retard (ex: LLM call 5s) et qu'un autre event arrive entre-temps | [DÉDUIT] |
| Risque de stale consumption | Un consumer qui reprend après un arrêt voit les vieux events d'abord (FIFO) → peut agir sur données périmées | [DÉDUIT] |
