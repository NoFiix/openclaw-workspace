# process_map.md — Carte des processus

**Date** : 2026-03-15
**Méthode** : `pm2 jlist`, `ps aux`, `crontab -l`, `docker ps`, `ss -tlnp`

---

## Processus PM2

| Nom | PID | CPU | RAM | Uptime | Restarts | Rôle | Tag |
|-----|-----|-----|-----|--------|----------|------|-----|
| dashboard-api | 2148812 | 0.2% | 93 MB | 40.8h | 2 | API dashboard (port 3001) | [OBSERVÉ] |
| trading-poller | 2140125 | 0.3% | 72 MB | 41.5h | 1 | Poller JS Trading Factory | [OBSERVÉ] |
| poly-orchestrator | 2249094 | **98.4%** | 164 MB | 31.9h | 2 | Orchestrateur POLY_FACTORY | [OBSERVÉ] |

### Anomalie : poly-orchestrator à 98% CPU

**Cause probable** [DÉDUIT] : la boucle principale dans `run_orchestrator.py` tourne à `POLL_INTERVAL_S = 2.0s`. Cependant, quand `orchestrator.run_once()` + `scheduler.tick()` prennent ~0ms (pas d'événements), le `time.sleep(max(0, 2.0 - elapsed))` devrait dormir ~2s. Le CPU à 98% suggère soit :
1. Des agents qui font du busy-wait interne
2. La lecture/écriture intensive de JSONL à chaque tick (21 agents, certains à 2s/5s)
3. Un problème de I/O thrashing sur `pending_events.jsonl` (lu par chaque poll)

**Impact** : HIGH — consomme la quasi-totalité d'un core, laisse peu de marge pour les autres processus.

---

## Processus Docker

| Container | Image | Status | Ports | Tag |
|-----------|-------|--------|-------|-----|
| openclaw-openclaw-gateway-1 | ghcr.io/openclaw/openclaw:2026.3.2 | Up 43h (healthy) | 18789-18790→18789-18790 | [OBSERVÉ] |

Le container exécute les cron jobs via `docker exec` (scrapers, bus maintenance, watchdog).

---

## Jobs Cron

| Schedule | Commande | Contexte | Tag |
|----------|----------|----------|-----|
| `0 7-23 * * *` | hourly_scraper.js | Docker exec → Content Factory | [OBSERVÉ] |
| `15 19 * * *` | scraper.js (daily) | Docker exec → Content Factory | [OBSERVÉ] |
| `0 3 * * *` | bus_rotation.js | Docker exec → Trading bus | [OBSERVÉ] |
| `30 3 * * *` | bus_cleanup_trading.js | Docker exec → Trading bus | [OBSERVÉ] |
| `0 2 * * *` | bus_cleanup_trading.js (dimanche) | Docker exec → Trading bus | [OBSERVÉ] |
| `@reboot +30s` | trading/poller.js | Docker exec -d | [OBSERVÉ] |
| `@reboot +35s` | poller.js (content) | Docker exec -d | [OBSERVÉ] |
| `*/15 * * * *` | run_watchdog.sh → SYSTEM_WATCHDOG | Docker exec | [OBSERVÉ] |

---

## Analyse des conflits

### CONFLIT C-02 : Double lancement trading/poller.js

**Observation** [OBSERVÉ] :
- `@reboot` cron lance `trading/poller.js` via `docker exec -d` dans le container
- PM2 `trading-poller` (pid 2140125) lance aussi un poller Node.js

**Analyse** [DÉDUIT] :
- Le `@reboot` cron lance `poller.js` DANS le container Docker
- Le PM2 `trading-poller` tourne HORS du container (sur l'hôte)
- Si les deux exécutent les mêmes schedules, il y a duplication des appels agents

**Sévérité** : MEDIUM — duplication possible de données/actions

**Vérification nécessaire** [INCONNU] : confirmer si PM2 trading-poller et cron poller.js exécutent les mêmes agents ou des agents différents.

---

## Ports réseau

| Port | Processus | Usage | Tag |
|------|-----------|-------|-----|
| 22 | sshd | SSH | [OBSERVÉ] |
| 80 | nginx | Reverse proxy web | [OBSERVÉ] |
| 3001 | dashboard-api (PM2) | API dashboard (localhost only) | [OBSERVÉ] |
| 18789 | Docker gateway | OpenClaw Gateway | [OBSERVÉ] |
| 18790 | Docker gateway | OpenClaw Gateway (2nd port) | [OBSERVÉ] |

**Note** : port 3001 écoute uniquement sur 127.0.0.1 → non exposé à l'extérieur. [OBSERVÉ]

---

## Chaîne de dépendances

```
                     ┌─────────────────────────────────────────────┐
                     │            Docker Container                  │
                     │  ┌─ hourly_scraper.js (cron)                │
                     │  ├─ daily_scraper.js (cron)                 │
                     │  ├─ bus_rotation.js (cron)                  │
                     │  ├─ bus_cleanup_trading.js (cron)           │
  crontab ──────────►│  ├─ trading/poller.js (@reboot)            │
                     │  ├─ content/poller.js (@reboot)            │
                     │  └─ SYSTEM_WATCHDOG/index.js (cron */15)   │
                     └─────────────────────────────────────────────┘

                     ┌─────────────────────────────────────────────┐
                     │            PM2 (Host)                        │
  pm2 ──────────────►│  ├─ dashboard-api (Node, port 3001)        │
                     │  ├─ trading-poller (Node)                   │
                     │  └─ poly-orchestrator (Python, 98% CPU)     │
                     └─────────────────────────────────────────────┘
```

Les deux systèmes (Docker cron + PM2 host) n'ont PAS de mécanisme de coordination partagé. [OBSERVÉ]
