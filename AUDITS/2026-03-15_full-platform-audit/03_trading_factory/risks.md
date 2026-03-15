# risks.md — Risques Trading Factory

**Date** : 2026-03-15
**Scope** : Risques identifiés dans le système Trading Factory (JS)

---

## Section A — Risques internes

### R-01 : KILL_SWITCH_GUARDIAN défaillant (27 399 erreurs)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **CRITIQUE** |
| Probabilité | Confirmée (115% taux d'erreur) |
| Impact | Le kill switch — la dernière ligne de défense — ne fonctionne pas correctement. En cas de perte >3% daily, le système pourrait ne pas s'arrêter. |
| Détection actuelle | SYSTEM_WATCHDOG vérifie `killswitch.json` mais **pas la santé du guardian lui-même** |
| Tag | [OBSERVÉ] |

### R-02 : Conflit C-02 — double exécution du poller

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée (PM2 host + cron Docker) |
| Impact | Double events bus, double appels API, double coût LLM ($1.30/jour en trop), risque de double ordres Binance, corruption possible des fichiers state partagés |
| Détection actuelle | Non détecté — le watchdog ne distingue pas les 2 instances |
| Tag | [OBSERVÉ] |

### R-03 : Human approval non fonctionnel (95 ordres expirés)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Confirmée (100% des HUMAN_APPROVAL_REQUIRED → EXPIRED) |
| Impact | Aucun mécanisme de validation humaine n'existe réellement. Si un ordre dépasse $5k, il expire systématiquement. Le seuil de sécurité est une illusion. |
| Détection actuelle | Aucune alerte sur les ordres expirés |
| Tag | [OBSERVÉ] |

### R-04 : PREDICTOR orphelin (gaspillage ressources)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Confirmée |
| Impact | 11 093 runs × 60s cycle, 7.7 Mo bus. Pas de consommateur. CPU gaspillé. |
| Détection actuelle | Aucune |
| Tag | [DÉDUIT] |

### R-05 : SYSTEM_WATCHDOG faux positifs (3 CRIT)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Confirmée |
| Impact | Le watchdog rapporte 3 services critiques "down" (orchestrator + pollers) parce qu'il les cherche comme processes Docker alors qu'ils tournent via PM2 sur l'hôte. Faux positifs érodent la confiance dans les alertes. |
| Détection actuelle | Auto-reporté mais faux |
| Tag | [OBSERVÉ] |

### R-06 : Pas de déduplication bus

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Active (via C-02) |
| Impact | Events dupliqués dans le bus → signaux dupliqués dans le pipeline → ordres potentiellement dupliqués. Le seul garde-fou est le cooldown 30min/symbol de TRADE_GENERATOR (persisté en fichier). |
| Détection actuelle | Aucune |
| Tag | [DÉDUIT] |

### R-07 : Corruption fichiers state par accès concurrent

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Possible (2 pollers écrivent simultanément) |
| Impact | `exec/positions.json`, `memory/pipeline_state.json`, `exec/daily_pnl.json` peuvent être corrompus par des écritures concurrentes (pas de lock file). |
| Détection actuelle | Aucune (crash silencieux) |
| Tag | [DÉDUIT] |

### R-08 : Bus files grandissent sans limite (170 Mo actuels)

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Atténuée par cleanup |
| Impact | `intel.market.features` = 72 Mo en 6 jours. Avec cleanup actif, stabilisé à ~170 Mo. Sans cleanup → 500 Mo/mois, risque disque plein. |
| Détection actuelle | SYSTEM_WATCHDOG vérifie la taille disque |
| Tag | [OBSERVÉ] |

### R-09 : Double cleanup quotidien

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Confirmée |
| Impact | `bus_cleanup_trading.js` exécuté 2× (02:00 + 03:30). Idempotent, donc pas de dommage. Overhead inutile + confusion logs. |
| Détection actuelle | Aucune |
| Tag | [OBSERVÉ] |

---

## Section B — Risques API externes

### R-10 : Binance REST API — single point of failure

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Faible (Binance uptime >99.9%) |
| Impact | Si Binance mainnet REST est down : plus de prix, plus d'indicateurs, pipeline entièrement bloqué. Pas de fallback (pas de WebSocket, pas de source secondaire). |
| Condition kill switch | Exchange down >5 min → TRIPPED |
| Tag | [OBSERVÉ] |

### R-11 : Binance Testnet instabilité

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Connue (testnet moins fiable que mainnet) |
| Impact | Ordres rejetés, fills partiels, prix décalés vs mainnet. Les 4 trades exécutés ont fonctionné mais le testnet peut diverger significativement. |
| Tag | [DÉDUIT] |

### R-12 : Etherscan v2 rate limiting

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Confirmée (79 erreurs WHALE_FEED) |
| Impact | Perte temporaire des données whale. TRADE_GENERATOR continue sans whale_context. |
| Mitigation | 250ms delay entre appels ERC20 dans WHALE_FEED |
| Tag | [OBSERVÉ] |

### R-13 : Anthropic API — bloquant pour signaux

| Propriété | Valeur |
|-----------|--------|
| Sévérité | **ÉLEVÉ** |
| Probabilité | Faible (uptime historique Anthropic >99.5%) |
| Impact | NEWS_SCORING (61% budget) et TRADE_GENERATOR (38% budget) dépendent de Haiku. Si API down → plus de scoring news, plus de proposals. Pipeline produit 0 signal. |
| Fallback | Aucun |
| Tag | [DÉDUIT] |

### R-14 : CoinGecko — conversion whale USD

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Faible |
| Impact | Whale amounts non convertis en USD si CoinGecko down. Score whale dégradé mais pas critique. |
| Tag | [DÉDUIT] |

---

## Section C — Risques capital

### R-15 : Capital fictif = pas de validation réelle

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Structurelle |
| Impact | 10 000 USDT fictifs, 4 trades, 100% win rate (+$864.82). Ces résultats ne sont pas transférables au mainnet : slippage réel, liquidité réelle, latence réseau réelle seront différents. Le 100% win rate sur 4 trades est statistiquement non significatif. |
| Tag | [DÉDUIT] |

### R-16 : Seuil human approval non protecteur

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Confirmée |
| Impact | Le seuil de $5 000 existe dans POLICY_ENGINE mais aucun mécanisme d'approbation n'est implémenté. En mode live avec capital réel, un gros ordre serait simplement bloqué (EXPIRED), pas approuvé manuellement. |
| Tag | [OBSERVÉ] |

### R-17 : Pas d'executor mainnet

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Structurelle (transition future) |
| Impact | La transition testnet → mainnet nécessite un nouvel executor. Risque d'introduire des bugs lors de la migration (clés API, signatures, slippage, fees réels). |
| Tag | [DÉDUIT] |

---

## Section D — Risques inter-systèmes

### R-18 : POLY_TRADING_PUBLISHER — couplage POLY_FACTORY

| Propriété | Valeur |
|-----------|--------|
| Sévérité | MOYEN |
| Probabilité | Active |
| Impact | Agent JS Trading Factory qui lit directement les fichiers state de POLY_FACTORY (Python). Dépendance implicite : si POLY_FACTORY change son format de state, le publisher casse silencieusement. Pas de contrat d'interface, pas de versioning. |
| Tag | [OBSERVÉ] |

### R-19 : GLOBAL_TOKEN_TRACKER — couplage POLY_FACTORY

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Active |
| Impact | Lit `POLY_FACTORY/state/llm/token_costs.jsonl`. Même risque que R-18 mais impact limité au reporting des coûts tokens (pas de décision trading). |
| Tag | [OBSERVÉ] |

### R-20 : Absence de coordination Trading Factory ↔ POLY_FACTORY

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Structurelle |
| Impact | Deux systèmes de trading indépendants (conflit C-03). Pas de coordination des positions (un système ne sait pas ce que l'autre fait), pas de budget commun, pas de risk management global. Si les deux systèmes tradent simultanément sur le même marché, exposure non contrôlée. |
| Tag | [DÉDUIT] |

### R-21 : Trois systèmes de collecte news indépendants

| Propriété | Valeur |
|-----------|--------|
| Sévérité | FAIBLE |
| Probabilité | Structurelle |
| Impact | Content Factory (scraper.js), Trading Factory (NEWS_FEED + NEWS_SCORING), et POLY_FACTORY (poly_news_strat) collectent et analysent les news chacun de leur côté. Triple coût API, triple coût LLM. Pas de bénéfice croisé. |
| Tag | [DÉDUIT] |

---

## Résumé des risques par sévérité

| Sévérité | # | Risques |
|----------|---|---------|
| **CRITIQUE** | 1 | R-01 (kill switch guardian défaillant) |
| **ÉLEVÉ** | 4 | R-02 (double poller), R-03 (human approval mort), R-10 (Binance SPOF), R-13 (Anthropic SPOF) |
| **MOYEN** | 7 | R-05 (watchdog faux positifs), R-06 (pas de dedup bus), R-07 (corruption concurrente), R-11 (testnet instable), R-15 (capital fictif), R-16 (seuil $5k mort), R-17 (pas d'executor mainnet), R-18 (couplage POLY) |
| **FAIBLE** | 6 | R-04 (PREDICTOR orphelin), R-08 (bus croissance), R-09 (double cleanup), R-12 (Etherscan rate limit), R-14 (CoinGecko), R-19 (token tracker couplage), R-20 (pas de coordination), R-21 (triple news) |
| **Total** | **21** | |
