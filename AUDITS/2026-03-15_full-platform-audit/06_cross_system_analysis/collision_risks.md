# collision_risks.md — Risques de collisions inter-systèmes

**Date** : 2026-03-15
**Scope** : Collisions fichiers, variables, réseau, temporelles

---

## Résumé exécutif

L'environnement OpenClaw présente **peu de collisions critiques** grâce à une séparation physique des systèmes (dossiers state distincts, bus distincts). Les collisions identifiées sont principalement **temporelles** (double cleanup, boot race condition) et **environnementales** (même canal Telegram, même clé Anthropic). Le risque le plus élevé est la **dépendance commune au container Docker** qui héberge 2 systèmes + le monitoring. [OBSERVÉ/DÉDUIT]

---

## Section A — Collisions fichiers state

| Fichier | Writers | Type collision | Risque | Mitigation | Tag |
|---------|---------|---------------|--------|-----------|-----|
| `state/drafts.json` | hourly_scraper.js, poller.js | 2 writers JS (Content) | MOYEN — pas de lock, écriture atomique non garantie | hourly_scraper écrit 1×/h, poller modifie unitairement → collision improbable | [DÉDUIT] |
| `state/trading/poller.log` | Trading poller (Docker), watchdog (tail) | 1 writer + 1 reader concurrent | FAIBLE — reader peut lire un état partiel mais watchdog lit seulement mtime | — | [OBSERVÉ] |
| `POLY_FACTORY/state/bus/pending_events.jsonl` | Tous agents POLY (append), compact() (rewrite) | N writers append + 1 rewrite compaction | FAIBLE — compaction dans la même boucle single-threaded | Single-threaded Python → pas de concurrence | [OBSERVÉ] |

**Conclusion** : Aucune collision critique de fichiers state. Le seul risque réel (`state/drafts.json`) est atténué par la nature séquentielle des accès. [DÉDUIT]

---

## Section B — Collisions variables d'environnement

### Même nom, valeurs potentiellement différentes

| Variable | Fichier 1 | Fichier 2 | Même valeur ? | Risque | Tag |
|----------|-----------|-----------|---------------|--------|-----|
| `ANTHROPIC_API_KEY` | Container .env | POLY_FACTORY/.env | Très probablement oui | Révocation = 3 systèmes down simultanément | [DÉDUIT] |
| `BINANCE_API_KEY` | Container .env | POLY_FACTORY/.env | Possiblement oui | Rate limiting partagé si même clé | [DÉDUIT] |
| `BINANCE_API_SECRET` | Container .env | POLY_FACTORY/.env | Possiblement oui | Idem | [DÉDUIT] |

### Même variable, scopes différents (pas de collision)

| Variable | Scope | Isolation | Tag |
|----------|-------|-----------|-----|
| `TELEGRAM_BOT_TOKEN` | Container (watchdog) | Isolé dans Docker env | [OBSERVÉ] |
| `BUILDER_TELEGRAM_BOT_TOKEN` | Container (content) | Isolé dans Docker env | [OBSERVÉ] |
| `TRADER_TELEGRAM_BOT_TOKEN` | Container (trading) | Isolé dans Docker env | [OBSERVÉ] |
| `POLY_TELEGRAM_BOT_TOKEN` | POLY_FACTORY/.env | Isolé dans POLY env | [OBSERVÉ] |

### Chat IDs — collision confirmée

| Variable | Valeur | Impact | Tag |
|----------|--------|--------|-----|
| `TELEGRAM_CHAT_ID` | 1066147184 | Même canal | [OBSERVÉ] |
| `BUILDER_TELEGRAM_CHAT_ID` | 1066147184 | Même canal | [OBSERVÉ] |
| `TRADER_TELEGRAM_CHAT_ID` | 1066147184 | Même canal | [OBSERVÉ] |
| `POLY_TELEGRAM_CHAT_ID` | 1066147184 | Même canal | [OBSERVÉ] |

**Impact** : 4 bots × 14 émetteurs → 1 seul canal. Alerte CRIT noyée parmi les drafts hourly et rapports quotidiens. Risque d'ignorer une alerte critique. [OBSERVÉ]

---

## Section C — Collisions réseau/ports

### État actuel

| Port | Service | Bind | Risque résiduel après fix Docker | Tag |
|------|---------|------|--------------------------------|-----|
| 22 | SSH | 0.0.0.0 | Aucun (nécessaire) | [OBSERVÉ] |
| 80 | nginx | IPv6 public | MOYEN — HTTP sans TLS, API key en clair | [OBSERVÉ] |
| 3001 | dashboard-api | 127.0.0.1 | Aucun (localhost only) | [OBSERVÉ] |
| 18789 | Docker gateway | 0.0.0.0 | **ÉLEVÉ** — exposé publiquement, fix Docker compose non appliqué (sudo requis) | [OBSERVÉ] |
| 18790 | Docker gateway | 0.0.0.0 | **ÉLEVÉ** — idem | [OBSERVÉ] |

### Collisions port potentielles

| Risque | Détail | Tag |
|--------|--------|-----|
| Nouveau service sur :3001 | Dashboard-api occupe ce port, PM2 restart le protège | FAIBLE | [DÉDUIT] |
| Nouveau service sur :18789 | Docker occupe ces ports, conflit si autre container lancé | FAIBLE | [DÉDUIT] |
| Pas de port POLY | POLY_FACTORY n'expose aucun port HTTP — pas de health check réseau possible | MOYEN | [OBSERVÉ] |

---

## Section D — Collisions temporelles

### Collisions cron confirmées

| Heure | Job 1 | Job 2 | Collision | Risque | Tag |
|-------|-------|-------|----------|--------|-----|
| 02:00 | bus_cleanup_trading.js | — | — | — | [OBSERVÉ] |
| 03:00 | bus_rotation.js | — | — | — | [OBSERVÉ] |
| 03:30 | bus_cleanup_trading.js | — | Doublon du job 02:00 (C-08) | FAIBLE (idempotent) | [OBSERVÉ] |
| 08:00 | SYSTEM_WATCHDOG rapport | GLOBAL_TOKEN_ANALYST (Lun+Jeu) | Pas de conflit (agents indépendants) | AUCUN | [OBSERVÉ] |
| 20:00 | GLOBAL_TOKEN_TRACKER rapport | POLY_TRADING_PUBLISHER rapport | Deux rapports Telegram simultanés dans le même canal | FAIBLE | [DÉDUIT] |

### Race conditions au boot

| Séquence | Risque | Mitigation | Tag |
|----------|--------|-----------|-----|
| Docker start vs @reboot +30s | Si Docker met > 30s, trading poller échoue silencieusement | `sleep 30` est une estimation, pas une vérification `docker ps` | [DÉDUIT] |
| Docker start vs @reboot +35s | Si Docker met > 35s, content poller échoue silencieusement | Idem | [DÉDUIT] |
| PM2 auto-restart vs cron @reboot | PM2 poly-orchestrator et dashboard-api redémarrent automatiquement, les pollers Docker non | Asymétrie de supervision | [OBSERVÉ] |

### Collisions implicites (même ressource, fenêtres proches)

| Ressource | Accès 1 | Accès 2 | Fenêtre | Risque | Tag |
|-----------|---------|---------|---------|--------|-----|
| Binance API | Trading BINANCE_PRICE_FEED (60s) | POLY PolyBinanceFeed (30s) | Continu | Rate limiting si même clé (~2 req/s total) | [DÉDUIT] |
| Anthropic API | Content hourly_scraper (1×/h) | Trading NEWS_SCORING (~60s cycle) | Continu | Rate limiting très improbable (faible volume) | [DÉDUIT] |
| Anthropic API | POLY opp_scorer/no_scanner (30s) | Trading NEWS_SCORING | Continu | Rate limiting très improbable | [DÉDUIT] |
| Telegram API | 14 émetteurs | — | Variable | Rate limiting possible en cas de burst (>30 msg/s) | [DÉDUIT] |

### Collisions temporelles watchdog

| Check watchdog | Resource vérifiée | Conflit avec | Tag |
|---------------|-------------------|-------------|-----|
| */15 min | poller.log mtime | rotate_poller_log.sh (04:00) — si rotation au moment du check, mtime reset → fausse alerte "log not updated" | [DÉDUIT] |
| */15 min | Docker container | docker compose restart — container transitoirement absent | [DÉDUIT] |

**Risque rotation/watchdog** : Si le watchdog check tombe pendant la rotation quotidienne (04:00), le log fraîchement truncaté peut déclencher un faux positif. Fenêtre de collision : ~1 seconde. Risque quasi nul. [SUPPOSÉ]
