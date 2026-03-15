# risks.md — Risques POLY_FACTORY

**Date** : 2026-03-15
**Scope** : Risques identifiés dans le système POLY_FACTORY (Python)

---

## Section A — Risques internes

### R-01 : 11 agents disabled sur 19 — pipeline majoritairement inopérant

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **CRITIQUE** |
| Probabilité | Confirmée (heartbeat_state.json) |
| Impact | exec_router disabled → aucun trade ne peut être exécuté. binance_feed disabled → latency_arb et brownian starvés. msa disabled → filtre 1 orchestrateur sans données. Le système est fonctionnellement mort. |
| Cause | 3 restarts atteints → heartbeat désactive l'agent. Cause racine des erreurs non diagnostiquée. |
| Détection | poly_heartbeat publie `system:agent_disabled` mais pas d'alerte externe (pas de Telegram POLY direct) |
| Tag | [OBSERVÉ] |

### R-02 : poly-orchestrator à 98% CPU (C-01)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée (PM2 status) |
| Impact | Consomme un core entier. `pending_events.jsonl` (70k events, 19 Mo) lu à chaque poll (2s) = goulot I/O. Dégrade les performances des autres processes (trading-poller, dashboard-api). |
| Cause | Architecture single-threaded + bus single-file + polling 2s + 70k events accumulés |
| Tag | [OBSERVÉ] |

### R-03 : Bus backlog (70k events pending)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée |
| Impact | 70k events pending vs 22k processed. Les agents disabled ne consomment plus → events s'accumulent. Le fichier grandit (~10 Mo/jour). La compaction (toutes les 100 polls) ne suffit pas car les events non-ackés restent. |
| Tag | [OBSERVÉ] |

### R-04 : 0 trades en 1.5 jours — pipeline stérile

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée |
| Impact | Aucune stratégie n'a émis de `trade:signal`. Les 5 actives (weather_arb, opp_scorer, no_scanner, convergence, news_strat) n'ont trouvé aucun edge suffisant. Impossible d'évaluer le système sans trades. Le pipeline de promotion (50 trades, 14 jours) est inaccessible à ce rythme. |
| Causes possibles | Seuils trop stricts, marchés inadaptés, données incomplètes (11 agents disabled), `news:high_impact` sans producteur |
| Tag | [OBSERVÉ] |

### R-05 : `news:high_impact` sans producteur — poly_news_strat starved

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Confirmée |
| Impact | poly_news_strat consomme `news:high_impact` mais aucun agent POLY ne produit ce topic. Prévu pour bridge avec NEWS_SCORING JS mais non implémenté. La stratégie sera zombie indéfiniment. |
| Tag | [DÉDUIT] |

### R-06 : MAX_RESTARTS=3 trop agressif — cascade de désactivation

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Confirmée (11 agents disabled) |
| Impact | 3 restarts suffisent pour désactiver un agent définitivement (pas de reset automatique). Si la cause est un bug transitoire (ex: API timeout), l'agent reste mort même après résolution du problème. Reset manuel requis. |
| Tag | [DÉDUIT] |

### R-07 : Pas de timeout natif pour les agents

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Possible |
| Impact | Un appel LLM bloqué (Anthropic API lent) ou un HTTP call qui hang bloque tout le scheduler (single-threaded). Pas de watchdog timer pour tuer un agent qui prend trop de temps. |
| Tag | [DÉDUIT] |

### R-08 : Cache résolution permanent — stale data

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Active |
| Impact | `resolutions_cache.json` cache les résolutions parsées de manière permanente. Si les conditions d'un marché changent (ex: amendement, date repoussée), le cache ne sera jamais invalidé. |
| Tag | [DÉDUIT] |

---

## Section B — Risques APIs externes

### R-09 : Polymarket Gamma API — erreurs 403/422 connues

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée (bug corrigé le 2026-03-14) |
| Impact | `get_positions()` retournait 403 (auth required pour certains endpoints). `get_markets()` utilisait path param au lieu de query param → 422. Corrigé, mais Gamma API est non documentée et instable. |
| Fallback | wallet_feed retourne positions vides si 403 | [OBSERVÉ] |
| Tag | [OBSERVÉ] |

### R-10 : Binance API — feed disabled

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Confirmée (binance_feed disabled) |
| Impact | Pas de données Binance → latency_arb et brownian_sniper privées de signaux. L'API Binance elle-même est stable (>99.9%), le problème est interne. |
| Fallback | Aucun — les stratégies Binance-dépendantes sont mortes |
| Tag | [OBSERVÉ] |

### R-11 : NOAA Weather API — rate limit et disponibilité

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Faible |
| Impact | Si NOAA down → weather_arb sans données. API gratuite, pas de SLA. |
| Fallback | Aucun |
| Tag | [DÉDUIT] |

### R-12 : Polygon RPC — stub non implémenté

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Structurelle |
| Impact | Le fallback RPC de wallet_feed est un stub. Si Gamma API change son endpoint positions, pas de plan B. |
| Tag | [OBSERVÉ] |

### R-13 : Anthropic API — LLM bloquant

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Faible |
| Impact | opp_scorer (Sonnet) et no_scanner (Haiku) dépendent d'Anthropic. Si API down → ces 2 stratégies ne scorent plus. Les 7 autres stratégies non-LLM continuent. L'appel LLM est dans le thread principal → timeout = potentiel hang du scheduler entier. |
| Fallback | Cache (4h opp_scorer, permanent no_scanner) |
| Tag | [DÉDUIT] |

---

## Section C — Risques capital

### R-14 : Mécanismes de protection capital — état actuel

| Mécanisme | Statut | Tag |
|-----------|--------|-----|
| Kill switch par stratégie | OK — non déclenché (0 trades) | [OBSERVÉ] |
| Kill switch global | OK — NORMAL (perte 0€ sur 4 000€) | [OBSERVÉ] |
| Risk guardian | OK — 0 positions (max 5) | [OBSERVÉ] |
| Kelly sizer | Non testé (0 trades) | [OBSERVÉ] |
| Capital manager | Non testé (0 trades) | [OBSERVÉ] |
| Promotion gate | Non testé (0 évaluations) | [OBSERVÉ] |

**Risque** : 5 mécanismes sur 6 n'ont **jamais été testés en conditions réelles**. La robustesse théorique ne garantit pas le fonctionnement en production. [DÉDUIT]

### R-15 : WALLET_PRIVATE_KEY absent — live impossible

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** (bloquant pour live) |
| Probabilité | Confirmée (U-02) |
| Impact | `poly_live_execution_engine` fait `os.environ["WALLET_PRIVATE_KEY"]` → `KeyError` crash si mode live activé. Le passage paper → live est **structurellement bloqué**. |
| Tag | [OBSERVÉ] |

### R-16 : Credentials Polymarket non vérifiés

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Inconnue (U-01) |
| Impact | `POLY_API_KEY` et `POLY_SECRET` présents dans `.env` mais jamais testés sur le CLOB API réel. Possiblement expirés ou invalides. |
| Tag | [INCONNU] |

### R-17 : Scénario de perte en live

| Scénario | Perte maximale | Protection | Tag |
|----------|---------------|------------|-----|
| 1 stratégie lose tout | -1 000€ | Kill switch total -30% → stop à -300€ | [DÉDUIT] |
| 5 stratégies lose daily | -250€ (5 × -5%) | Kill switch daily -5% par stratégie | [DÉDUIT] |
| Toutes stratégies lose | -4 000€ → ARRÊT TOTAL | Global risk guard | [DÉDUIT] |
| Bug kill switch | Illimité (capital total) | **Pas de backup** si kill switch bugué | [DÉDUIT] |

---

## Section D — Risques inter-systèmes

### R-18 : POLY_TRADING_PUBLISHER (JS) lit les fichiers state POLY_FACTORY

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Active |
| Impact | Agent JS Trading Factory qui lit `POLY_FACTORY/state/trading/paper_trades_log.jsonl` et `state/orchestrator/system_state.json`. Couplage implicite. Si POLY_FACTORY change le format → publisher casse silencieusement. |
| Tag | [OBSERVÉ] |

### R-19 : GLOBAL_TOKEN_TRACKER (JS) lit token_costs.jsonl

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Active |
| Impact | Le fichier est actuellement vide (0 bytes). Si le format change quand il sera rempli, le tracker JS cassera. |
| Tag | [OBSERVÉ] |

### R-20 : SYSTEM_WATCHDOG (JS) surveille poly-orchestrator

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Active |
| Impact | Le watchdog JS vérifie `system_state.json` et le heartbeat POLY. Si le format change → faux positifs/négatifs dans les alertes. |
| Tag | [OBSERVÉ] |

### R-21 : Pas de coordination capital entre Trading Factory et POLY_FACTORY

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Structurelle (C-03) |
| Impact | Deux systèmes de trading indépendants. Le JS trade sur Binance crypto, POLY sur Polymarket prediction. Pas de corrélation directe, mais budget LLM partagé (même ANTHROPIC_API_KEY). |
| Tag | [DÉDUIT] |

---

## Section E — Observabilité

### Logs existants

| Log | Emplacement | Contenu | Tag |
|-----|-------------|---------|-----|
| PM2 logs | `~/.pm2/logs/poly-orchestrator-{out,error}.log` | stdout/stderr du process | [OBSERVÉ] |
| Audit log | `state/audit/audit_{date}.jsonl` | 427 events/jour (heartbeat, health checks) | [OBSERVÉ] |
| Paper trades log | `state/trading/paper_trades_log.jsonl` | 0 trades | [OBSERVÉ] |
| Token costs | `state/llm/token_costs.jsonl` | Vide (0 bytes) | [OBSERVÉ] |

### Métriques existantes

| Métrique | Source | Fréquence | Tag |
|----------|--------|-----------|-----|
| Agent liveness | poly_heartbeat → heartbeat_state.json | 300s | [OBSERVÉ] |
| System health | poly_system_monitor → audit log | 300s | [OBSERVÉ] |
| Global risk status | poly_global_risk_guard → global_risk_state.json | Sur event | [OBSERVÉ] |
| Strategy accounts | accounts/ACC_POLY_*.json | Sur trade | [OBSERVÉ] |

### Alertes existantes

| Alerte | Canal | Contenu | Tag |
|--------|-------|---------|-----|
| POLY_TRADING_PUBLISHER | Telegram | Daily report 20h, paper/live trades | [OBSERVÉ] |
| SYSTEM_WATCHDOG | Telegram | CRIT/WARN alerts | [OBSERVÉ] |
| Global risk ALERTE | (interne bus) | Pas de notification Telegram directe | [DÉDUIT] |
| Agent disabled | (interne bus) | Pas de notification Telegram directe | [DÉDUIT] |

### Zones non observées (échec silencieux)

| Zone | Risque | Tag |
|------|--------|-----|
| **Agents disabled** | 11 agents disabled sans alerte Telegram — seul SYSTEM_WATCHDOG (JS, */15 min) peut détecter | [OBSERVÉ] |
| **Bus saturation** | Pas de métrique sur la taille du bus → 70k events non détectés | [DÉDUIT] |
| **LLM coûts** | Token tracking vide → coûts LLM invisibles | [OBSERVÉ] |
| **Stratégies zombie** | Pas de détection "stratégie active mais 0 signaux en N jours" | [DÉDUIT] |
| **CPU orchestrateur** | 98% CPU non alerté (PM2 ne surveille pas le CPU, seulement le process alive) | [OBSERVÉ] |
| **Cause des restarts** | Le heartbeat compte les restarts mais ne log pas la cause des erreurs | [DÉDUIT] |

---

## Résumé des risques par sévérité

| Sévérité | # | Risques |
|----------|---|---------|
| **CRITIQUE** | 1 | R-01 (11 agents disabled) |
| **ÉLEVÉ** | 5 | R-02 (98% CPU), R-03 (bus backlog 70k), R-04 (0 trades), R-09 (Gamma API instable), R-15 (WALLET_KEY absent) |
| **MOYEN** | 6 | R-05 (news_strat starved), R-06 (MAX_RESTARTS trop bas), R-07 (pas de timeout), R-10 (binance disabled), R-13 (Anthropic hang), R-16 (credentials non vérifiés), R-18 (couplage POLY_PUBLISHER) |
| **FAIBLE** | 5 | R-08 (cache stale), R-11 (NOAA), R-12 (Polygon stub), R-19 (token tracker), R-20 (watchdog couplage), R-21 (pas de coordination capital) |
| **Total** | **21** | |
