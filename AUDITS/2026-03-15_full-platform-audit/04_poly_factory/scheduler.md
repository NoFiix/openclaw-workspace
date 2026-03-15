# scheduler.md — AgentScheduler POLY_FACTORY

**Date** : 2026-03-15
**Scope** : Orchestration et scheduling des 21 agents Python

---

## Architecture du scheduler

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Type | `AgentScheduler` intégré dans `poly_factory_orchestrator.py` | [OBSERVÉ] |
| Boucle principale | `run_orchestrator.py` → `time.sleep(max(0, 2.0 - elapsed))` | [OBSERVÉ] |
| Intervalle polling | 2.0 secondes | [OBSERVÉ] |
| Mode | Single-threaded (tous les agents dans le même thread/process) | [OBSERVÉ] |
| Registre | Dictionnaire `{agent_name: (callable, interval_s, last_run)}` | [DÉDUIT] |
| Gestion erreurs | try/except par agent, `critical: false` pour agents non-critiques | [OBSERVÉ] |

---

## Liste complète des 21 agents avec intervalles

### Ordre d'enregistrement dans run_orchestrator.py

| # | Agent | Catégorie | Intervalle | Critical | Statut heartbeat | Tag |
|---|-------|-----------|-----------|----------|-------------------|-----|
| 1 | connector | C1 Feed | 300s | true | **ACTIF** (0 restarts) | [OBSERVÉ] |
| 2 | binance_feed | C1 Feed | 30s | true | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 3 | noaa_feed | C1 Feed | 120s | true | **ACTIF** (2 restarts) | [OBSERVÉ] |
| 4 | wallet_feed | C1 Feed | 600s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 5 | msa | C2 Signal | 30s | true | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 6 | binance_sig | C2 Signal | 10s | true | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 7 | wallet_track | C2 Signal | 60s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 8 | data_val | C2 Signal | 10s | true | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 9 | arb_scanner | C3 Strategy | 5s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 10 | weather_arb | C3 Strategy | 60s | false | **ACTIF** (2 restarts) | [OBSERVÉ] |
| 11 | latency_arb | C3 Strategy | 5s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 12 | brownian | C3 Strategy | 5s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 13 | pair_cost | C3 Strategy | 5s | false | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 14 | opp_scorer | C3 Strategy | 30s | false | **ACTIF** (2 restarts) | [OBSERVÉ] |
| 15 | no_scanner | C3 Strategy | 30s | false | **ACTIF** (0 restarts) | [OBSERVÉ] |
| 16 | convergence | C3 Strategy | 30s | false | **ACTIF** (0 restarts) | [OBSERVÉ] |
| 17 | news_strat | C3 Strategy | 30s | false | **ACTIF** (0 restarts) | [OBSERVÉ] |
| 18 | exec_router | C4 Exec | 2s | true | **DISABLED** (3 restarts) | [OBSERVÉ] |
| 19 | paper_engine | C4 Exec | 2s | true | **ACTIF** (1 restart) | [OBSERVÉ] |
| 20 | heartbeat | System | 300s | true | N/A (self) | [OBSERVÉ] |
| 21 | sys_monitor | System | 300s | true | N/A (self) | [OBSERVÉ] |

**Résumé** : 8 actifs, 11 disabled, 2 system (toujours actifs). [OBSERVÉ]

---

## Ordre d'exécution dans tick()

Le scheduler exécute séquentiellement dans la boucle 2s :

```
tick() @ t=0 :
  Pour chaque agent dans l'ordre d'enregistrement :
    si elapsed > interval :
      agent.run_once()      ← bloquant, single-threaded
      lastRun[agent] = now()
    sinon :
      skip

  orchestrator.process_signals()   ← poll bus pour trade:signal, applique 7 filtres
  orchestrator.check_nightly()     ← vérifie si 00:00 UTC → run_nightly()
```

**Conséquence** : Si un agent est lent (ex: LLM call 5s), tous les agents suivants sont retardés. [DÉDUIT]

---

## Durée estimée d'un cycle complet

| Phase | Agents concernés | Durée estimée | Tag |
|-------|-----------------|---------------|-----|
| Feeds actifs | connector (HTTP ~1-3s), noaa_feed (HTTP ~1-2s) | ~3-5s | [DÉDUIT] |
| Signals actifs | aucun (msa, binance_sig, wallet_track disabled) | ~0s | [OBSERVÉ] |
| Strategies actives | weather_arb, opp_scorer, no_scanner, convergence, news_strat (pure math/cache) | ~0.1-0.5s | [DÉDUIT] |
| Exécution | paper_engine (pas d'events → no-op) | ~0.01s | [DÉDUIT] |
| System | heartbeat (300s cycle), sys_monitor (300s cycle) | ~0.05s quand exécutés | [DÉDUIT] |
| Bus poll + filtres | orchestrator.process_signals() | ~0.1-1s (scan 70k events) | [DÉDUIT] |
| **Total par tick** | — | **~0.5-6s** | [DÉDUIT] |

**Anomalie** : Le tick dure parfois >2s → le `time.sleep(max(0, 2.0 - elapsed))` retourne 0 → pas de sleep → CPU 98%. [DÉDUIT]

---

## Agents les plus coûteux

### En temps CPU

| Agent | Coût | Raison | Tag |
|-------|------|--------|-----|
| orchestrator.process_signals() | **ÉLEVÉ** | Scan de `pending_events.jsonl` (70k lignes, 19 Mo) à chaque tick | [DÉDUIT] |
| connector (polymarket) | MOYEN | HTTP call vers Gamma API (20 marchés) | [DÉDUIT] |
| noaa_feed | MOYEN | HTTP call vers NWS API (6 stations) | [DÉDUIT] |
| opp_scorer (LLM) | Variable | Claude Sonnet call ~2-5s si cache miss | [DÉDUIT] |

### En temps I/O

| Agent | Coût I/O | Raison | Tag |
|-------|----------|--------|-----|
| Bus poll (chaque agent) | **ÉLEVÉ** | Lecture complète de `pending_events.jsonl` (19 Mo) à chaque poll() | [DÉDUIT] |
| Bus publish | MOYEN | Append to `pending_events.jsonl` | [DÉDUIT] |
| Heartbeat state | FAIBLE | Write `heartbeat_state.json` | [DÉDUIT] |

---

## Risque de dérive

| Scénario | Impact | Probabilité | Tag |
|----------|--------|------------|-----|
| Tick durée > 2s | Sleep = 0 → boucle sans pause → CPU 100% | **CONFIRMÉ** (98% CPU observé) | [OBSERVÉ] |
| Tick durée > 5s | Agents à 5s d'intervalle (arb_scanner, etc.) manquent des cycles | Probable avec disabled agents éliminés | [DÉDUIT] |
| Tick durée > 30s | binance_feed et msa (30s interval) manquent des cycles | Improbable (sauf LLM timeout) | [DÉDUIT] |
| LLM call timeout | opp_scorer bloque le thread pendant 30s | Possible (Anthropic API slowdown) | [DÉDUIT] |

**Mitigation** : Les agents disabled (11/21) réduisent la charge par tick. Paradoxalement, le CPU est à 98% **malgré** les agents disabled. Le goulot est le bus I/O. [DÉDUIT]

---

## Agents mal synchronisés

| Dépendance | Intervalle producteur | Intervalle consommateur | Problème | Tag |
|------------|----------------------|-------------------------|----------|-----|
| binance_feed (30s) → binance_sig (10s) | 30s | 10s | Signal poll 3× par cycle feed → 2 polls sur 3 = no-op | [DÉDUIT] |
| connector (300s) → arb_scanner (5s) | 300s | 5s | Scanner poll 60× par cycle connector → 59 polls sur 60 = données identiques | [DÉDUIT] |
| connector (300s) → opp_scorer (30s) | 300s | 30s | Scorer poll 10× par cycle connector → 9 sur 10 = données identiques | [DÉDUIT] |
| wallet_feed (600s) → wallet_track (60s) | 600s | 60s | Tracker poll 10× par cycle feed → 9 sur 10 inutiles | [DÉDUIT] |

**Conséquence** : Les stratégies à 5s (arb_scanner, latency_arb, brownian, pair_cost) polled 60× entre chaque update du connector (300s). Gaspillage CPU/IO massif. [DÉDUIT]

---

## CPU / Mémoire observés

| Process | CPU | RAM | Uptime | Restarts | Tag |
|---------|-----|-----|--------|----------|-----|
| poly-orchestrator (PM2) | **98%** | 164 Mo | ~32h | 2 | [OBSERVÉ] |

**Décomposition estimée du CPU** :

| Composant | % CPU estimé | Tag |
|-----------|-------------|-----|
| Bus I/O (lecture 19 Mo/tick) | ~60-70% | [DÉDUIT] |
| Agent run_once() calls | ~10-15% | [DÉDUIT] |
| Python overhead (GIL, GC) | ~10-15% | [DÉDUIT] |
| State file JSON read/write | ~5-10% | [DÉDUIT] |

---

## Comparaison AgentScheduler Python vs poller JS

| Aspect | AgentScheduler Python | Poller JS | Tag |
|--------|----------------------|-----------|-----|
| **Architecture** | Single-threaded, in-process | Multi-process (child_process per agent) | [OBSERVÉ] |
| **Parallélisme** | Aucun (séquentiel dans tick) | Naturel (chaque agent = process séparé) | [OBSERVÉ] |
| **Isolation** | Crash d'un agent peut affecter tout le process | Crash d'un agent = child process meurt, poller survit | [OBSERVÉ] |
| **CPU** | 98% (single core, I/O-bound) | 0.3% (distribué) | [OBSERVÉ] |
| **Mémoire** | 164 Mo (tout en un process) | 73 Mo (poller) + children temporaires | [OBSERVÉ] |
| **Timeout** | Pas de timeout natif (LLM peut bloquer) | 35s timeout par child process | [OBSERVÉ] |
| **Gestion erreurs** | try/except + critical flag | Exit code du child process | [OBSERVÉ] |
| **Scheduling** | Interval-based, check chaque tick | Interval-based, lastRun en mémoire | [OBSERVÉ] |
| **Jitter** | Non | Oui (configurable par agent) | [OBSERVÉ] |
| **Scalabilité** | Limitée (single-thread) | Meilleure (multi-process) | [DÉDUIT] |

**Avantage Python** : Simplicité, état partagé facile (même process).
**Avantage JS** : Isolation, parallélisme, timeout natif, 300× moins de CPU.
**Conclusion** : L'architecture single-threaded Python est le principal responsable des 98% CPU. [DÉDUIT]
