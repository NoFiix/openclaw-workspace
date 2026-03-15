# target_architecture.md — Architecture cible recommandée

**Date** : 2026-03-15
**Scope** : Architecture cible après audit — isolation, mutualisation, conventions

---

## Résumé exécutif

L'architecture actuelle est **80% conforme** à une architecture cible propre. Les systèmes sont déjà isolés (state séparés, bus séparés, agents séparés). Les recommandations portent sur : renforcer l'isolation des secrets, formaliser les conventions de nommage, améliorer la mutualisation du monitoring, et définir des règles strictes pour les ajouts futurs. [DÉDUIT]

---

## Ce qui doit être isolé par système

| Aspect | Isolation actuelle | Recommandation | Tag |
|--------|-------------------|---------------|-----|
| **State files** | ✅ Chaque système a son dossier | Maintenir — jamais d'écriture cross-system | [OBSERVÉ] |
| **Bus d'événements** | ✅ Bus JS et Python physiquement séparés | Maintenir — jamais de topic identique | [OBSERVÉ] |
| **Fichier .env** | ⚠️ POLY a son .env, Container a le sien | Chaque système DOIT avoir son .env dédié, chmod 600 | [OBSERVÉ] |
| **Agents** | ✅ Chaque système dans son dossier | Maintenir — agents/ (Content), skills_custom/trading/ (Trading), POLY_FACTORY/agents/ (POLY) | [OBSERVÉ] |
| **Processus** | ⚠️ Trading et Content partagent le container Docker | Acceptable tant que le container est stable — PM2 pour long-running Python | [OBSERVÉ] |
| **API keys** | ⚠️ ANTHROPIC_API_KEY probablement partagée | Documenter les clés partagées, envisager des clés séparées par système | [DÉDUIT] |

---

## Ce qui peut rester mutualisé

| Composant | Justification | Condition | Tag |
|-----------|-------------|-----------|-----|
| **SYSTEM_WATCHDOG** | Monitoring transverse par nature | Doit couvrir tous les systèmes + s'auto-monitorer (heartbeat) | [OBSERVÉ] |
| **Dashboard** | Vue unifiée de tous les systèmes | Routes API séparées par système, pages dédiées | [OBSERVÉ] |
| **Token Tracker** | Agrégation coûts LLM transverse | Doit couvrir les 3 systèmes (Content manquant) | [OBSERVÉ] |
| **Telegram bots** | Notifications transverses | Séparer les canaux par type (CRIT vs reports vs content) | [DÉDUIT] |
| **Container Docker** | Infrastructure partagée Content + Trading | Acceptable tant que stable | [OBSERVÉ] |
| **Crontab host** | Scheduler unifié | Documenter clairement quel job appartient à quel système | [OBSERVÉ] |
| **nginx** | Reverse proxy unique | OK pour un seul VPS | [OBSERVÉ] |

---

## Namespace bus recommandé

### Bus Trading (JS) — `state/trading/bus/`

| Domaine | Pattern | Exemples | Tag |
|---------|---------|----------|-----|
| Prix | `trading.prices.*` | `trading.prices.btc_usdt` | [OBSERVÉ] |
| Signaux | `trading.signals.*` | `trading.signals.proposal` | [OBSERVÉ] |
| Exécution | `trading.exec.*` | `trading.exec.order`, `trading.exec.fill` | [OBSERVÉ] |
| Risque | `trading.risk.*` | `trading.risk.kill_switch` | [OBSERVÉ] |
| Intel | `trading.intel.*` | `trading.intel.news`, `trading.intel.whale` | [OBSERVÉ] |
| Ops | `trading.ops.*` | `trading.ops.alert`, `trading.ops.health` | [DÉDUIT] |

### Bus POLY (Python) — `POLY_FACTORY/state/bus/`

| Domaine | Pattern | Exemples | Tag |
|---------|---------|----------|-----|
| Feeds | `feed:*` | `feed:binance_update`, `feed:price_update` | [OBSERVÉ] |
| Signaux | `signal:*` | `signal:technical`, `signal:opportunity` | [OBSERVÉ] |
| Trades | `trade:*` | `trade:signal`, `trade:paper_executed` | [OBSERVÉ] |
| Exécution | `execute:*` | `execute:paper`, `execute:live` | [OBSERVÉ] |
| Risque | `risk:*` | `risk:kill_switch`, `risk:drawdown` | [OBSERVÉ] |
| Système | `system:*` | `system:heartbeat`, `system:agent_disabled` | [OBSERVÉ] |
| Évaluation | `eval:*` | `eval:score`, `eval:promotion` | [OBSERVÉ] |

### Règle stricte

**Jamais de topic identique dans les deux bus.** Le bus JS utilise `trading.*` (dot-separated), le bus Python utilise `domain:action` (colon-separated). Cette différence de format est suffisante pour éviter toute confusion. [DÉDUIT]

### Bridge cross-bus

Si un topic doit transiter d'un bus à l'autre (ex: `news:high_impact`), un agent bridge dédié DOIT être implémenté. Le bridge :
1. Consomme dans le bus source
2. Transforme si nécessaire
3. Publie dans le bus destination avec un topic propre
4. Ne modifie jamais le format natif du bus source

**Bridge identifié mais non implémenté** : NEWS_SCORING (JS) → `news:high_impact` (Python bus) — C-12. [OBSERVÉ]

---

## Namespace state recommandé

| Dossier | Owner exclusif | Règle | Tag |
|---------|---------------|-------|-----|
| `state/trading/` | TRADING_FACTORY (JS agents) | Aucun autre système n'écrit ici | [OBSERVÉ] |
| `POLY_FACTORY/state/` | POLY_FACTORY (Python agents) | Aucun autre système n'écrit ici | [OBSERVÉ] |
| `state/` (racine) | CONTENT_FACTORY + scripts partagés | drafts.json, logs, seen_articles, publish_history | [OBSERVÉ] |
| `dashboard-data/aggregates/` | Dashboard API | Données agrégées pour historiques | [DÉDUIT] |

### Règle stricte

**Un système ne DOIT JAMAIS écrire dans le state d'un autre système.** Les lectures croisées sont autorisées (dashboard, watchdog, publishers). Si un nouveau système est ajouté, il DOIT créer `{SYSTEM}/state/` ou `state/{system}/`. [DÉDUIT]

---

## Convention scheduler recommandée

| Type de process | Scheduler recommandé | Exemples | Tag |
|----------------|---------------------|----------|-----|
| Long-running Python | **PM2** (autorestart, logs, monitoring) | poly-orchestrator | [OBSERVÉ] |
| Long-running JS (dans Docker) | **PM2 ou @reboot daemon** — préférer PM2 | trading poller, content poller | [DÉDUIT] |
| Script ponctuel | **Cron** | hourly_scraper, scraper, bus_rotation, watchdog | [OBSERVÉ] |
| Agents internes | **AgentScheduler** (Python) ou **Poller loop** (JS) | 21 agents POLY (scheduler), 24 agents Trading (poller) | [OBSERVÉ] |

### Règle

Tout process long-running DOIT être supervisé par PM2 ou un mécanisme équivalent avec restart auto. Les daemons `@reboot` SANS supervision (content poller, trading poller) sont un anti-pattern à corriger. [DÉDUIT]

---

## Convention watchdog

| Règle | Détail | Tag |
|-------|--------|-----|
| **SYSTEM_WATCHDOG surveille TOUT** | Chaque nouveau système doit être ajouté dans config.json | [DÉDUIT] |
| **Heartbeat file** | Chaque process long-running DOIT écrire un heartbeat file périodique | [DÉDUIT] |
| **Seuils stale** | WARN à 10× interval, CRIT à 30× interval (convention existante) | [OBSERVÉ] |
| **Meta-watchdog** | Le watchdog DOIT être supervisé par un mécanisme indépendant (cron externe vérifiant heartbeat) | [OBSERVÉ — fix appliqué] |
| **Rapport quotidien** | Chaque système a une section dans le rapport 08h UTC | [OBSERVÉ] |

---

## Convention dashboard

| Règle | Détail | Tag |
|-------|--------|-----|
| **Une route API par système** | `routes/polymarket.js`, `routes/trading.js`, `routes/content.js` | [OBSERVÉ] |
| **Une page par système** | `Polymarket.jsx`, `Trading.jsx`, `Content.jsx` | [OBSERVÉ] |
| **Jamais de données cross-système** dans une même route | La route `/api/polymarket/live` ne lit QUE `POLY_FACTORY/state/` | [OBSERVÉ] |
| **Overview agrège** | La page Overview peut combiner des données de plusieurs systèmes | [OBSERVÉ] |
| **Cache TTL** | 15-30s pour données live, 60s pour trades/perf, 5-15min pour historiques | [OBSERVÉ] |
| **Auth** | Toutes les routes DOIVENT vérifier `x-api-key` | [OBSERVÉ] |

---

## Convention Telegram (cible)

| Canal | Contenu | Émetteurs max | Tag |
|-------|---------|-------------- |-----|
| **ALERTES** (nouveau) | CRIT + WARN (watchdog, kill switch) | 2-3 | [DÉDUIT] |
| **TRADING** | P&L, trades, token costs, strategy tuning | 4-5 | [DÉDUIT] |
| **CONTENT** | Drafts, publications, sélections | 3-4 | [DÉDUIT] |
| **POLY** | Reports POLY, paper trades | 1-2 | [DÉDUIT] |

**État actuel** : 4 bots → 1 canal. **Cible** : 4 bots → 3-4 canaux distincts. [DÉDUIT]

---

## Diagramme architecture cible

```
┌─────────────────────────────────────────────────────────────────────┐
│                    VPS srv1425899 (ou migration future)              │
│                                                                      │
│  ┌═══════════════════════════════════════════════════════════════┐   │
│  ║  DOCKER (Content + Trading JS)                                ║   │
│  ║  ├─ Content: scraper, poller (PM2), hourly_scraper            ║   │
│  ║  ├─ Trading: poller.js (PM2), 24 agents                      ║   │
│  ║  └─ Shared: WATCHDOG, TOKEN_TRACKER, POLY_PUBLISHER           ║   │
│  ╚═══════════════════════════════════════════════════════════════╝   │
│                                                                      │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │  POLY_FACTORY     │  │  DASHBOARD        │  │  FUTURE SYSTEM   │   │
│  │  (PM2, Python)    │  │  (PM2, Express)   │  │  ({SYS}/state/)  │   │
│  │  state/ isolé     │  │  :3001 → nginx    │  │  .env chmod 600  │   │
│  │  bus isolé        │  │  :443 HTTPS ✅     │  │  PM2 supervisé   │   │
│  │  .env chmod 600   │  │  rate-limited     │  │  watchdog config │   │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  INFRA CIBLE                                                  │   │
│  │  ✅ UFW actif (22, 80, 443)                                   │   │
│  │  ✅ HTTPS (Let's Encrypt)                                     │   │
│  │  ✅ Docker ports 127.0.0.1                                    │   │
│  │  ✅ Backup quotidien offsite                                  │   │
│  │  ✅ Log rotation (logrotate + scripts)                        │   │
│  │  ✅ Secrets chmod 600 (pas de vault, acceptable pour 1 VPS)   │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  MONITORING CIBLE                                             │   │
│  │  ✅ SYSTEM_WATCHDOG couvre tout + auto-monitored              │   │
│  │  ✅ TOKEN_TRACKER couvre 3 systèmes (Content ajouté)          │   │
│  │  ✅ Telegram : 3-4 canaux séparés (CRIT, Trading, Content)   │   │
│  │  ✅ Dashboard : HTTPS, rate-limited, health endpoint          │   │
│  │  ✅ Monitoring externe (UptimeRobot) pour VPS + nginx         │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Delta actuel → cible

| Aspect | Actuel | Cible | Effort | Tag |
|--------|--------|-------|--------|-----|
| Permissions .env | 664 (POLY) | 600 | 1 min | [OBSERVÉ] |
| Firewall | Inactif | UFW 22/80/443 | 15 min | [OBSERVÉ] |
| Docker ports | 0.0.0.0 | 127.0.0.1 | 5 min (sudo) | [OBSERVÉ] |
| HTTPS | Non | Let's Encrypt | 30 min | [OBSERVÉ] |
| Backups | Stales 12j, locaux | Quotidien, offsite | 2h | [OBSERVÉ] |
| Token tracking Content | Non | logTokens() dans 3 scripts | 2-3h | [OBSERVÉ] |
| Canaux Telegram | 1 canal | 3-4 canaux | 30 min | [OBSERVÉ] |
| Content poller supervision | @reboot | PM2 | 15 min | [DÉDUIT] |
| KILL_SWITCH_GUARDIAN | Défaillant | Fonctionnel | 1-3h | [OBSERVÉ] |
| Monitoring externe | Non | UptimeRobot/Healthchecks.io | 1h | [DÉDUIT] |
| **Total effort delta** | | | **~10-12h** | [DÉDUIT] |
