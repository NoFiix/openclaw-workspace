# triggers_cron.md — Déclencheurs et cron jobs Trading Factory

**Date** : 2026-03-15
**Scope** : Poller, cron jobs, scheduling, conflit C-02

---

## 1. Le poller — moteur central

### Architecture

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Fichier | `skills_custom/trading/poller.js` | [OBSERVÉ] |
| Mode | Boucle infinie, check toutes les 800ms | [OBSERVÉ] |
| Schedules | Lit `state/trading/schedules/*.schedule.json` | [OBSERVÉ] |
| Exécution agent | `child_process.execFile("node", ["index.js", "--input", payload])` | [OBSERVÉ] |
| Timeout agent | 35s (kill child process si dépassé) | [OBSERVÉ] |
| Jitter | Configurable par agent (2-120s) | [OBSERVÉ] |
| Tracking | `lastRun[agent_id]` en mémoire (non persisté) | [OBSERVÉ] |
| Log | stdout/stderr du child process | [OBSERVÉ] |

### Agents pollés (23 schedules)

| Catégorie | Agents | Intervalle | Critique | Tag |
|-----------|--------|-----------|----------|-----|
| Données temps réel | BINANCE_PRICE_FEED, MARKET_EYE | 10-15s | ✓ | [OBSERVÉ] |
| Intelligence | PREDICTOR, REGIME_DETECTOR | 60s | ✓ | [OBSERVÉ] |
| Données batch | NEWS_FEED, WHALE_FEED, WHALE_ANALYZER, NEWS_SCORING | 300s | ✓ | [OBSERVÉ] |
| Stratégie | TRADE_GENERATOR | 300s | ✓ | [OBSERVÉ] |
| Risk/Policy | RISK_MANAGER (60s), POLICY_ENGINE (30s) | 30-60s | ✓ | [OBSERVÉ] |
| Orchestration | TRADING_ORCHESTRATOR | 10s | ✓ | [OBSERVÉ] |
| Exécution | TESTNET_EXECUTOR (30s), PAPER_EXECUTOR (30s, **disabled**) | 30s | ✓/✗ | [OBSERVÉ] |
| Publication | TRADING_PUBLISHER (60s), POLY_TRADING_PUBLISHER (60s) | 60s | ✓/✗ | [OBSERVÉ] |
| Monitoring | KILL_SWITCH_GUARDIAN | 60s | ✓ | [OBSERVÉ] |
| Évaluation | PERFORMANCE_ANALYST, STRATEGY_GATEKEEPER | 3600s | ✗/✓ | [OBSERVÉ] |
| Recherche | STRATEGY_RESEARCHER (86400s), TRADE_STRATEGY_TUNER (604800s) | 1j-7j | ✗ | [OBSERVÉ] |
| Tokens | GLOBAL_TOKEN_TRACKER (3600s), GLOBAL_TOKEN_ANALYST (3600s) | 3600s | ✗ | [OBSERVÉ] |

**Total** : 23 agents × 800ms polling loop = ~28 checks/seconde. [DÉDUIT]

---

## 2. Conflit C-02 — Double poller

### Contexte

Deux instances du trading poller coexistent :

| Instance | Source | PID | Uptime | Tag |
|----------|--------|-----|--------|-----|
| PM2 `trading-poller` | `pm2 start ecosystem.config.cjs` (sur l'hôte) | Variable | 42h+ | [OBSERVÉ] |
| Cron Docker | `@reboot sleep 30 && docker exec -d openclaw-gateway-1 sh -c 'node poller.js'` | Variable | Depuis boot | [OBSERVÉ] |

### Mécanisme

```
┌──── HOST ──────────────────┐      ┌──── DOCKER CONTAINER ──────────────────┐
│                             │      │                                         │
│  PM2 → trading-poller       │      │  @reboot cron → docker exec -d          │
│  node poller.js             │      │  node poller.js                         │
│  (pid: variable)            │      │  (pid: variable)                        │
│  lastRun: {in-memory-A}     │      │  lastRun: {in-memory-B}                │
│                             │      │                                         │
│  ──→ spawns agents ──→      │      │  ──→ spawns agents ──→                 │
│  writes to state/trading/*  │      │  writes to state/trading/*             │
│  (même filesystem via mount)│      │  (même filesystem via volume mount)    │
│                             │      │                                         │
└─────────────────────────────┘      └─────────────────────────────────────────┘
                 ↓                                      ↓
          ┌──────────────────────────────────────────────────────┐
          │     MÊME BUS JSONL (state/trading/bus/*.jsonl)       │
          │     → DOUBLE EVENTS pour chaque cycle agent          │
          └──────────────────────────────────────────────────────┘
```

### Impact mesuré

| Impact | Détail | Sévérité | Tag |
|--------|--------|----------|-----|
| Double exécution agents | Chaque agent tourne 2× par cycle → double events bus | ÉLEVÉ | [DÉDUIT] |
| Double appels API externes | Binance, Etherscan, CryptoPanic, RSS → double rate limit consommé | ÉLEVÉ | [DÉDUIT] |
| Double coût LLM | NEWS_SCORING + TRADE_GENERATOR appelés 2× → $2.60/jour au lieu de $1.30 | MOYEN | [DÉDUIT] |
| Ordres dupliqués | TESTNET_EXECUTOR pourrait soumettre le même ordre 2× sur Binance Testnet | **CRITIQUE** | [DÉDUIT] |
| Fichiers state corrompus | 2 processes écrivent simultanément dans `exec/positions.json`, `memory/pipeline_state.json` | ÉLEVÉ | [DÉDUIT] |
| Confusion monitoring | SYSTEM_WATCHDOG compte les runs des 2 pollers comme un seul → stats faussées | MOYEN | [DÉDUIT] |

### Mitigation existante

| Mécanisme | Efficacité | Tag |
|-----------|-----------|-----|
| `lastRun[agent_id]` dans poller.js | **INEFFICACE** — chaque instance a son propre lastRun en mémoire | [OBSERVÉ] |
| Cooldown 30min/symbol dans TRADE_GENERATOR | **PARTIELLEMENT EFFICACE** — cooldown persisté dans `memory/trade_cooldowns.json`, partagé entre les 2 pollers | [OBSERVÉ] |
| TTL 10min dans ORCHESTRATOR | **PARTIELLEMENT EFFICACE** — les ordres dupliqués auraient des IDs différents → 2 ordres distincts | [DÉDUIT] |

### Recommandation

**Supprimer la ligne `@reboot` du crontab** — PM2 gère déjà le trading-poller avec auto-restart. La ligne cron est redondante et dangereuse. [DÉDUIT]

---

## 3. Cron jobs

### Crontab complet (lignes trading)

```bash
# Bus rotation — archive + truncate vieux events
0 3 * * * docker exec openclaw-gateway-1 node bus_rotation.js >> rotation.log 2>&1

# Bus cleanup — TTL-based pruning (RUN #1)
30 3 * * * docker exec openclaw-gateway-1 node bus_cleanup_trading.js >> cleanup_trading.log 2>&1

# Bus cleanup — TTL-based pruning (RUN #2 ⚠️ doublon probable)
0 2 * * * docker exec openclaw-gateway-1 node bus_cleanup_trading.js >> cleanup.log 2>&1

# Trading poller — ⚠️ C-02: doublon avec PM2
@reboot sleep 30 && docker exec -d openclaw-gateway-1 sh -c 'node poller.js >> poller.log 2>&1'

# System watchdog — health checks + alertes Telegram
*/15 * * * * bash run_watchdog.sh >> watchdog.log 2>&1
```

### Analyse des cron jobs

| Job | Fréquence | Exécution via | Risque | Tag |
|-----|-----------|---------------|--------|-----|
| `bus_rotation.js` | Daily 03:00 | Docker exec | OK — single run, idempotent | [OBSERVÉ] |
| `bus_cleanup_trading.js` #1 | Daily 03:30 | Docker exec | OK | [OBSERVÉ] |
| `bus_cleanup_trading.js` #2 | Daily 02:00 | Docker exec | ⚠️ **Doublon** — même script, log différent | [OBSERVÉ] |
| `poller.js` @reboot | Au boot | Docker exec -d | ⚠️ **C-02** — conflit avec PM2 | [OBSERVÉ] |
| `run_watchdog.sh` | */15 min | Bash direct (hôte) | OK — mais résultats faussés par Docker perspective | [OBSERVÉ] |

### Anomalie : double cleanup

`bus_cleanup_trading.js` est exécuté **deux fois par jour** :
- 02:00 UTC → log dans `state/cleanup.log`
- 03:30 UTC → log dans `logs/cleanup_trading.log`

Le script est idempotent (TTL-based), donc le deuxième run ne fait presque rien. Mais c'est un overhead inutile et une source de confusion dans les logs. [DÉDUIT]

---

## 4. Agents sur-schedulés / sous-schedulés

### Sur-schedulés (CPU/IO gaspillé)

| Agent | Schedule actuel | Recommandé | Raison | Tag |
|-------|----------------|------------|--------|-----|
| PREDICTOR | 60s | **Supprimer ou 300s** | Output non consommé (orphelin) — gaspille 11k runs pour rien | [DÉDUIT] |
| POLICY_ENGINE | 30s | 60s | Poll plus vite que RISK_MANAGER (60s) produit des order.plan | [DÉDUIT] |
| KILL_SWITCH_GUARDIAN | 60s | 30s | Agent de sécurité critique avec 27k erreurs — devrait être plus fréquent pour rattraper les erreurs | [DÉDUIT] |

### Sous-schedulés (risque de retard)

| Agent | Schedule actuel | Recommandé | Raison | Tag |
|-------|----------------|------------|--------|-----|
| KILL_SWITCH_GUARDIAN | 60s | **30s** | En mode live, 60s de délai avant détection = trop lent pour un kill switch | [DÉDUIT] |
| SYSTEM_WATCHDOG | 900s (*/15 min) | 300s | Détecte les pannes avec 15 min de retard | [DÉDUIT] |

### Désynchronisations

| Chaîne | Problème | Tag |
|--------|----------|-----|
| MARKET_EYE (15s) → TRADE_GENERATOR (300s) | TRADE_GENERATOR lit des features potentiellement vieilles de 285s | [DÉDUIT] |
| TRADE_GENERATOR (300s) → RISK_MANAGER (60s) | RISK_MANAGER poll 5× entre 2 proposals. 4 polls sur 5 = no-op | [DÉDUIT] |
| TRADING_ORCHESTRATOR (10s) → TESTNET_EXECUTOR (30s) | Orchestrator submit un ordre, executor le voit 30s plus tard au pire | [OBSERVÉ] |

---

## 5. run_watchdog.sh

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Fichier | `skills_custom/trading/run_watchdog.sh` | [OBSERVÉ] |
| Mode | Exécuté directement sur l'hôte (bash, pas docker exec) | [OBSERVÉ] |
| Cron | `*/15 * * * *` | [OBSERVÉ] |
| Méthode | Appelle `docker exec openclaw-gateway-1 node SYSTEM_WATCHDOG/handler.js` | [DÉDUIT] |
| Log | `/home/openclawadmin/logs/watchdog.log` | [OBSERVÉ] |

**Note** : Le watchdog est le seul agent trading qui n'est PAS géré par le poller. Il a son propre cron */15 min et s'exécute via `docker exec` depuis l'hôte. [OBSERVÉ]
