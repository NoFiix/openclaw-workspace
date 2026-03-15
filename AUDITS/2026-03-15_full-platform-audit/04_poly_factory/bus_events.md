# bus_events.md — Inventaire des topics bus POLY_FACTORY

**Date** : 2026-03-15
**Scope** : Bus événementiel Python file-based (JSONL)

---

## Architecture du bus

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Type | File-based JSONL (1 fichier unique `pending_events.jsonl`) | [OBSERVÉ] |
| Répertoire | `state/bus/` | [OBSERVÉ] |
| Format envelope | `{event_id, topic, timestamp, producer, priority, retry_count, payload}` | [OBSERVÉ] |
| Consommation | Polling avec idempotence (`_acked_ids` deque maxlen=10 000) | [OBSERVÉ] |
| Persistence acks | `bus/processed_events.jsonl` | [OBSERVÉ] |
| Dead letter | `bus/dead_letter.jsonl` (après 3 retries) | [OBSERVÉ] |
| Modes | overwrite (feeds), queue (trades), cache (résolutions), sync (risk checks), priority (kill switch) | [OBSERVÉ] |
| Compaction | Automatique toutes les 100 poll() si >10 000 events | [OBSERVÉ] |
| Validation | `validate_payload(topic, payload)` via JSON schemas (warn-only, non bloquant) | [OBSERVÉ] |

---

## Liste complète des 20 topics bus

### Feeds (overwrite mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `feed:price_update` | connector_polymarket | arb_scanner, weather_arb, latency_arb, brownian, pair_cost, opp_scorer, no_scanner, news_strat, orchestrator | ~300s | **CORE** | [OBSERVÉ] |
| `feed:binance_update` | poly_binance_feed | poly_binance_signals | ~30s | SUPPORT | [OBSERVÉ] |
| `feed:noaa_update` | poly_noaa_feed | poly_weather_arb | ~120s | SUPPORT | [OBSERVÉ] |
| `feed:wallet_update` | poly_wallet_feed | poly_wallet_tracker | ~600s | SUPPORT | [OBSERVÉ] |

### Signals (queue/cache mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `signal:binance_score` | poly_binance_signals | poly_latency_arb, poly_brownian_sniper | ~10s | SUPPORT | [OBSERVÉ] |
| `signal:market_structure` | poly_market_structure_analyzer | poly_arb_scanner, poly_pair_cost, orchestrator (filtre 1) | ~30s | **CORE** | [OBSERVÉ] |
| `signal:wallet_convergence` | poly_wallet_tracker | poly_convergence_strat | ~60s | SUPPORT | [OBSERVÉ] |
| `signal:resolution_parsed` | poly_market_analyst | poly_opp_scorer, poly_no_scanner, poly_convergence_strat | À la demande | SUPPORT | [OBSERVÉ] |

### Strategy (queue mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `trade:signal` | 9 stratégies | poly_factory_orchestrator | Variable (quand edge détecté) | **CORE** | [OBSERVÉ] |
| `trade:validated` | poly_factory_orchestrator | poly_execution_router | Après 7 filtres | **CORE** | [OBSERVÉ] |

### Execution (queue mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `execute:paper` | poly_execution_router | poly_paper_execution_engine | Post-validation | **CORE** | [OBSERVÉ] |
| `execute:live` | poly_execution_router | poly_live_execution_engine | Post-validation (futur) | **CORE** | [OBSERVÉ] |
| `trade:paper_executed` | poly_paper_execution_engine | poly_performance_logger, poly_global_risk_guard | Post-exécution | **CORE** | [OBSERVÉ] |
| `trade:live_executed` | poly_live_execution_engine | poly_performance_logger, poly_global_risk_guard | Post-exécution (futur) | **CORE** | [OBSERVÉ] |

### Risk (priority mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `risk:kill_switch` | poly_kill_switch | poly_factory_orchestrator | Sur trigger | **CORE** | [OBSERVÉ] |
| `risk:global_status` | poly_global_risk_guard | poly_factory_orchestrator | Sur changement état | **CORE** | [OBSERVÉ] |

### System (priority mode)

| Topic | Producteur(s) | Consommateur(s) | Fréquence | Criticité | Tag |
|-------|--------------|-----------------|-----------|-----------|-----|
| `system:heartbeat` | poly_heartbeat | audit_log | ~300s | SUPPORT | [OBSERVÉ] |
| `system:agent_stale` | poly_heartbeat | orchestrateur | Sur détection | SUPPORT | [OBSERVÉ] |
| `system:agent_disabled` | poly_heartbeat | orchestrateur | Sur 3 restarts | **CORE** | [OBSERVÉ] |
| `system:health_check` | poly_system_monitor | audit_log | ~300s | SUPPORT | [OBSERVÉ] |

---

## Topics orphelins identifiés

| Topic | Producteur | Problème | Tag |
|-------|------------|----------|-----|
| `news:high_impact` | [INCONNU] | Consommé par poly_news_strat mais **aucun producteur identifié** dans POLY_FACTORY. Probablement prévu pour NEWS_SCORING (JS Trading Factory) mais pas de bridge. | [DÉDUIT] |
| `data:validation_failed` | poly_data_validator | Publié mais **aucun consommateur** identifié (audit trail seulement) | [DÉDUIT] |
| `market:illiquid` | poly_market_structure_analyzer | Publié mais **aucun consommateur** identifié | [DÉDUIT] |
| `system:api_degraded` | poly_system_monitor | Publié mais **pas de réaction automatique** configurée | [DÉDUIT] |
| `eval:decay_alert` | poly_decay_detector | Publié mais **pas de réaction automatique** (alerte seulement) | [DÉDUIT] |
| `capital:reallocation` | poly_compounder | Publié mais **pas de consommateur** (compounder non intégré au flux) | [DÉDUIT] |

**Impact** : `news:high_impact` est le plus impactant — poly_news_strat ne recevra jamais de signal et restera zombie. [DÉDUIT]

---

## Schéma ASCII du flux d'événements

```
┌──────────────────── EXTERNAL APIS ──────────────────────────────────┐
│  Polymarket Gamma    Binance REST    NWS/NOAA    Wallet Gamma       │
└────────┬────────────────┬──────────────┬──────────────┬─────────────┘
         │                │              │              │
         ▼                ▼              ▼              ▼
┌─ FEEDS ─────────────────────────────────────────────────────────────┐
│ connector ──→ feed:price_update (overwrite)                         │
│ binance_feed ──→ feed:binance_update (overwrite)         [DISABLED] │
│ noaa_feed ──→ feed:noaa_update (overwrite)                          │
│ wallet_feed ──→ feed:wallet_update (overwrite)           [DISABLED] │
└────────────────────────┬────────────────────────────────────────────┘
                         ▼
┌─ SIGNALS ───────────────────────────────────────────────────────────┐
│ market_structure_analyzer ──→ signal:market_structure     [DISABLED] │
│ binance_signals ──→ signal:binance_score                 [DISABLED] │
│ wallet_tracker ──→ signal:wallet_convergence             [DISABLED] │
│ market_analyst ──→ signal:resolution_parsed (LLM Sonnet)            │
│                                                                      │
│ ⚠️ news:high_impact ──→ AUCUN PRODUCTEUR                            │
└────────────────────────┬────────────────────────────────────────────┘
                         ▼
┌─ STRATEGIES ────────────────────────────────────────────────────────┐
│ arb_scanner ────┐                                        [DISABLED] │
│ weather_arb ────┤                                                    │
│ latency_arb ────┤                                        [DISABLED] │
│ brownian ───────┤                                        [DISABLED] │
│ pair_cost ──────┤──→ trade:signal (queue)                [DISABLED] │
│ opp_scorer ─────┤                                                    │
│ no_scanner ─────┤                                                    │
│ convergence ────┤                                                    │
│ news_strat ─────┘                                                    │
└────────────────────────┬────────────────────────────────────────────┘
                         ▼
┌─ ORCHESTRATOR (7 filtres) ──────────────────────────────────────────┐
│ Filtre 1: data_quality (executability ≥40, slippage ≤2%)            │
│ Filtre 2: microstructure (ambiguity ≤3)                             │
│ Filtre 3: resolution (parsed, non ambigu)                           │
│ Filtre 4: sizing (Kelly > 0)                                        │
│ Filtre 5: kill_switch (OK ou WARNING)                               │
│ Filtre 6: risk_guardian (positions < 5, exposure < 80%)             │
│ Filtre 7: capital_manager (available ≥ proposed)                    │
│                                                                      │
│ ──→ trade:validated (queue)                                          │
└────────────────────────┬────────────────────────────────────────────┘
                         ▼
┌─ EXECUTION ─────────────────────────────────────────────────────────┐
│ exec_router ──→ execute:paper OU execute:live            [DISABLED] │
│ paper_engine ──→ trade:paper_executed (queue)                        │
│ live_engine ──→ trade:live_executed (queue)              [DORMANT]  │
└────────────────────────┬────────────────────────────────────────────┘
                         ▼
┌─ RISK & EVALUATION ────────────────────────────────────────────────┐
│ performance_logger ← trade:paper_executed                           │
│ global_risk_guard ← trade:paper_executed ──→ risk:global_status     │
│ kill_switch ──→ risk:kill_switch (priority)                          │
│                                                                      │
│ strategy_evaluator ──→ eval:score_updated (nightly)                  │
│ decay_detector ──→ eval:decay_alert (nightly)                        │
│ heartbeat ──→ system:heartbeat, system:agent_disabled (priority)     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Saturation et backlog

| Métrique | Valeur | Tag |
|----------|--------|-----|
| Taille `pending_events.jsonl` | **69 976 lignes** (19 Mo) | [OBSERVÉ] |
| Taille `processed_events.jsonl` | 21 646 lignes (2.5 Mo) | [OBSERVÉ] |
| Ratio pending / processed | **3.2×** — le bus accumule plus vite qu'il ne consomme | [DÉDUIT] |
| Events estimés par tick (2s) | ~15-20 (heartbeat + feeds + strategies scanning) | [DÉDUIT] |
| Events par heure | ~30 000 | [DÉDUIT] |
| Compaction | Toutes les 100 poll() si >10k events | [OBSERVÉ] |

**Anomalie** : 70k events pending après 1.5 jours. La compaction ne suffit pas car elle ne supprime que les events déjà ackés. Le backlog vient de **11 agents disabled qui ne poll plus** → leurs events s'accumulent indéfiniment. [DÉDUIT]

**Risque de saturation** : À ce rythme (~30k events/heure, compaction ~10k), le fichier grandit de ~10 Mo/jour. Projection 30 jours : ~300 Mo. L'I/O sur ce fichier unique contribue aux 98% CPU de l'orchestrateur. [DÉDUIT]

---

## Résilience

### Topic perdu (fichier supprimé)

| Scénario | Impact | Récupération | Tag |
|----------|--------|-------------|-----|
| `pending_events.jsonl` supprimé | **TOUT LE BUS PERDU** — tous les events non ackés disparaissent | Recréé vide au prochain poll(), mais historique perdu | [DÉDUIT] |
| `processed_events.jsonl` supprimé | Replay d'events déjà traités au prochain restart | Les agents idempotents survivent, les autres peuvent doubler des actions | [DÉDUIT] |

### Duplication d'events

| Mécanisme | Efficacité | Tag |
|-----------|-----------|-----|
| `_acked_ids` (deque maxlen=10 000) | **BON** — filtre les doublons pour les 10k derniers events | [OBSERVÉ] |
| Overwrite mode (feeds) | **BON** — les feeds écrasent le dernier event, pas d'accumulation | [OBSERVÉ] |
| Queue mode (trades) | Dépend de l'idempotence du consumer | [DÉDUIT] |

### Agent bloqué

| Scénario | Impact | Détection | Tag |
|----------|--------|-----------|-----|
| Agent stale (ne poll plus) | Events s'accumulent dans pending_events.jsonl | poly_heartbeat (2× expected_freq → stale) | [OBSERVÉ] |
| Agent crash loop (3 restarts) | Agent désactivé, events non consommés | poly_heartbeat → `system:agent_disabled` | [OBSERVÉ] |
| Agent disabled en chaîne | Cascade : binance_feed disabled → binance_signals disabled → latency_arb disabled | **Observé en production** : 11 agents disabled en cascade | [OBSERVÉ] |

---

## Comparaison bus JS vs bus Python

| Aspect | Bus JS (Trading Factory) | Bus Python (POLY_FACTORY) | Tag |
|--------|------------------------|---------------------------|-----|
| **Format** | 1 fichier JSONL par topic (18 fichiers) | 1 fichier JSONL unique (`pending_events.jsonl`) | [OBSERVÉ] |
| **Taille totale** | ~170 Mo | ~22 Mo (pending + processed) | [OBSERVÉ] |
| **Consommation** | Cursor-based (`readSince`) | Polling avec ack (idempotence) | [OBSERVÉ] |
| **Idempotence** | Non (pas de dédup) | Oui (`_acked_ids` deque 10k) | [OBSERVÉ] |
| **Dead letter** | Non | Oui (après 3 retries) | [OBSERVÉ] |
| **Compaction** | Rotation externe (`bus_rotation.js`) | Intégrée (toutes les 100 polls) | [OBSERVÉ] |
| **Validation** | Non | JSON schema (warn-only) | [OBSERVÉ] |
| **Modes** | Append seulement | overwrite/queue/cache/sync/priority | [OBSERVÉ] |
| **Performance I/O** | Distribué (1 fichier/topic = parallélisme) | **Goulot** (1 fichier unique = sérialisé) | [DÉDUIT] |
| **Scalabilité** | Meilleure (topics indépendants) | Limitée (tout dans 1 fichier) | [DÉDUIT] |

**Avantage Python** : Idempotence, dead letter, validation, modes riches.
**Avantage JS** : Performance I/O (fichiers distribués), pas de goulot d'étranglement single-file.
**Conclusion** : Le bus Python est plus sophistiqué mais le choix single-file est un goulot. [DÉDUIT]
