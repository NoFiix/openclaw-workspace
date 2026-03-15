# watchdog.md — SYSTEM_WATCHDOG

**Date** : 2026-03-15
**Scope** : Analyse complète du SYSTEM_WATCHDOG et de sa couverture de monitoring

---

## Résumé exécutif

Le SYSTEM_WATCHDOG est le seul composant de monitoring transverse d'OpenClaw. Il surveille 3 systèmes (Trading Factory, Content Factory, POLY_FACTORY), 21+ agents trading, les processus critiques (pollers, orchestrateur), et l'infrastructure (disque, logs). Il envoie des alertes Telegram et un rapport quotidien à 08h UTC.

**Constat principal** : Le watchdog couvre 80% du système mais n'est **pas lui-même supervisé**. S'il tombe, personne n'est alerté. [OBSERVÉ]

---

## Rôle exact

Le SYSTEM_WATCHDOG est un agent de santé globale qui :
1. Vérifie la fraîcheur de tous les agents trading (stale detection)
2. Surveille les processus critiques (trading poller, content poller, Docker container, poly-orchestrator)
3. Contrôle l'état des kill switches (Trading + POLY)
4. Monitore l'infrastructure (disque, taille logs, taille bus)
5. Publie des alertes Telegram graduées (CRIT/WARN) avec déduplication
6. Envoie un rapport quotidien consolidé à 08h UTC

**Fréquence** : toutes les 15 minutes (configurable via `config.json`)

---

## Ce qu'il surveille actuellement [OBSERVÉ]

### Processus

| Process | Méthode de détection | Seuils | Tag |
|---------|---------------------|--------|-----|
| Trading poller | Recherche PID + `poller.log` mtime | Stale si log > 30 min | [OBSERVÉ] |
| Content poller | Recherche PID dans container Docker | PID absent = CRIT | [OBSERVÉ] |
| Docker container (openclaw-gateway) | `docker inspect` status | Non running = CRIT | [OBSERVÉ] |
| poly-orchestrator | `pgrep -f run_orchestrator.py` | PID absent = CRIT | [OBSERVÉ] |

### Agents Trading (21 agents)

| Catégorie | Agents | Méthode | Seuils stale |
|-----------|--------|---------|-------------|
| Data | BINANCE_PRICE_FEED, MARKET_DATA_AGGREGATOR, etc. | `last_run_ts` dans state.json | WARN: 10× interval, CRIT: 30× interval | [OBSERVÉ] |
| Signal | SIGNAL_GENERATOR, REGIME_DETECTOR, etc. | idem | idem |
| Risk | KILL_SWITCH_GUARDIAN, STRATEGY_GATEKEEPER | idem | idem |
| Exec | TRADING_ORCHESTRATOR, PAPER_EXECUTOR | idem | idem |
| Learning | STRATEGY_RESEARCHER, etc. | idem | idem |

Les agents sont chargés dynamiquement depuis `state/trading/schedules/*.schedule.json`. [OBSERVÉ]

### Content Factory

| Composant | Méthode | Seuils | Tag |
|-----------|---------|--------|-----|
| hourly_scraper | `hourly_scraper.log` mtime | > 2h = WARN | [OBSERVÉ] |
| daily_scraper | `daily_scraper.log` mtime | > 48h = WARN | [OBSERVÉ] |
| bus_rotation | Log mtime | > 48h = WARN | [OBSERVÉ] |
| performance_analyst | Memory file mtime | > 7 jours inactif = WARN | [OBSERVÉ] |
| news_scoring | Memory file mtime | > 7 jours inactif = WARN | [OBSERVÉ] |

### POLY_FACTORY

| Composant | Méthode | Données lues | Tag |
|-----------|---------|-------------|-----|
| Processus orchestrator | `pgrep -f run_orchestrator.py` | PID | [OBSERVÉ] |
| Global risk status | `global_risk_state.json` | status (NORMAL/ALERTE/CRITIQUE/ARRET_TOTAL) | [OBSERVÉ] |
| Agents disabled count | `heartbeat_state.json` | Nombre d'agents status=disabled | [OBSERVÉ] |
| Paper trades (24h) | `paper_trades_log.jsonl` | Count récent | [OBSERVÉ] |
| Daily P&L | Agrégation accounts | Somme daily_pnl_eur | [OBSERVÉ] |

### Infrastructure

| Métrique | Seuil WARN | Seuil CRIT | Tag |
|----------|-----------|-----------|-----|
| Disque libre | < 20% | < 10% | [OBSERVÉ] |
| poller.log taille | > 50 Mo | — | [OBSERVÉ] |
| Bus trading dir | > 400 Mo | — | [OBSERVÉ] |
| State trading dir | > 800 Mo | — | [OBSERVÉ] |
| Erreurs récentes poller | > 3 dans 300 lignes | — | [OBSERVÉ] |

---

## Ce qu'il ne surveille PAS [OBSERVÉ/DÉDUIT]

| Lacune | Impact | Tag |
|--------|--------|-----|
| **Bus Python POLY_FACTORY** (pending_events.jsonl taille) | Saturation 70k events non détectée (C-11 pré-fix) | [DÉDUIT] |
| **CPU orchestrateur** | 98% CPU non alerté (PM2 ne le remonte pas) | [DÉDUIT] |
| **Token costs LLM** | Pas d'alerte si coûts explosent | [DÉDUIT] |
| **Stratégies zombie POLY** | Agents actifs mais 0 signaux depuis N jours | [DÉDUIT] |
| **Cause des restarts agents** | Le watchdog voit les agents disabled mais pas pourquoi | [DÉDUIT] |
| **Dashboard API** | Pas de health check du dashboard-api (PM2 monitore le process, pas la santé HTTP) | [DÉDUIT] |
| **Content poller santé interne** | Vérifie si le process tourne, pas s'il traite des messages | [DÉDUIT] |
| **Freshness des feeds POLY** | Pas de check sur binance_raw.json, noaa_forecasts.json mtime | [DÉDUIT] |
| **Backups** | Aucun monitoring de backup (U-04) | [OBSERVÉ] |
| **Lui-même** | Le watchdog ne se monitore pas (voir SPOF ci-dessous) | [OBSERVÉ] |

---

## Canal Telegram

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Bot | `TELEGRAM_BOT_TOKEN` (env var) | [OBSERVÉ] |
| Chat | `TELEGRAM_CHAT_ID` (env var) | [OBSERVÉ] |
| Bot name | `@OppenCllawBot` | [DÉDUIT] |
| Canal distinct ? | Oui — séparé de TRADER et POLY bots | [OBSERVÉ] |

---

## Format des alertes

### Alertes temps réel (toutes les 15 min)

```
🔴 CRIT — Trading poller not found (PID absent)
Détecté: 2026-03-15T14:30:00Z | Ouvert depuis: 45min

⚠️ WARN — BINANCE_PRICE_FEED stale (last run 35 min ago, interval 60s)
```

**Déduplication** : Incident tracking avec cooldown progressif :
- 1ère alerte : immédiate
- 2ème : après 1h
- 3ème : après 6h
- Résolution : message `✅ RESOLVED` [OBSERVÉ]

### Rapport quotidien 08h UTC

```
📊 DAILY HEALTH REPORT — 2026-03-15 08:00 UTC

SYSTEM
  Score: 87/100 | CRIT: 0 | WARN: 2
  Disk: 17% used (81G free)

TRADING
  Kill Switch: ARMED | Trades 48h: 3
  Agents: 21 OK / 0 WARN / 0 ERROR

CONTENT
  Hourly: ✅ (45m ago) | Daily: ✅ (18h ago)
  Poller: RUNNING

POLYMARKET
  Mode: PAPER | Risk: NORMAL
  Agents: 19/19 active | Disabled: 0
  Trades 24h: 0 | PnL today: 0.00€

INCIDENTS: 2 open
  ⚠️ WARN — PREDICTOR stale (7d)
  ⚠️ WARN — bus_dir 354M (threshold 400M)
```

[OBSERVÉ]

---

## Single points of failure

### Le watchdog lui-même n'est pas supervisé [OBSERVÉ]

| Question | Réponse | Tag |
|----------|---------|-----|
| Qui supervise le watchdog ? | **Personne** | [OBSERVÉ] |
| Est-il dans PM2 ? | **Non** — il tourne dans le Docker container, schedulé par le poller trading | [OBSERVÉ] |
| S'il tombe, qui le sait ? | **Personne** — pas d'alerte, pas de health check | [OBSERVÉ] |
| Détection possible ? | Absence de rapport 08h → Daniel le remarque manuellement (best case) | [DÉDUIT] |
| Fréquence du risque | Le poller trading peut mourir ou le schedule peut sauter → watchdog ne tourne plus | [DÉDUIT] |

**Impact** : Si le watchdog tombe, TOUS les systèmes de monitoring tombent simultanément. C'est le single point of failure le plus critique de l'infrastructure. [DÉDUIT]

---

## Recommandations

| # | Action | Priorité | Effort |
|---|--------|----------|--------|
| 1 | **Monitorer le watchdog** : ajouter un cron externe (host) qui vérifie le mtime du dernier rapport ou heartbeat file | P0 | 15 min |
| 2 | Ajouter monitoring bus POLY (taille pending_events.jsonl) | P1 | 30 min |
| 3 | Ajouter monitoring CPU orchestrateur (via `/proc/stat` ou PM2 API) | P1 | 30 min |
| 4 | Ajouter health check HTTP du dashboard-api | P2 | 15 min |
| 5 | Ajouter alerte si token_costs.jsonl > seuil quotidien | P2 | 30 min |
| 6 | Ajouter détection stratégie zombie POLY (active mais 0 signals depuis 24h) | P3 | 1h |
