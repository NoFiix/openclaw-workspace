# summary.md — Trading Factory (JS)

**Date** : 2026-03-15
**Scope** : Système de trading automatisé multi-agents JavaScript (Binance spot)

---

## Mission du système

Système de trading automatisé multi-agents sur Binance (testnet puis mainnet). Pipeline complet : collecte de données (prix, news, whale) → indicateurs techniques → prédiction → génération de signaux → gestion du risque → exécution → publication. Objectif : trading algorithmique crypto spot (BTC/ETH/BNB) avec risque contrôlé.

---

## Entrée / Sortie principales

| Direction | Description | Tag |
|-----------|-------------|-----|
| **Entrée** | Binance REST API (tickers + klines 5m/1h/4h) | [OBSERVÉ] |
| **Entrée** | 6 RSS feeds crypto + CryptoPanic + SEC EDGAR + Fear&Greed | [OBSERVÉ] |
| **Entrée** | Etherscan v2 (whale transfers ETH + ERC20) | [OBSERVÉ] |
| **Sortie** | Ordres MARKET + OCO sur Binance Testnet | [OBSERVÉ] |
| **Sortie** | Publications Telegram (@CryptoRizonTrader_bot) | [OBSERVÉ] |

---

## Fréquence d'exécution globale

| Couche | Agents | Intervalle | Tag |
|--------|--------|-----------|-----|
| Données brutes | BINANCE_PRICE_FEED, MARKET_EYE | 10-15s | [OBSERVÉ] |
| Intelligence | PREDICTOR, REGIME_DETECTOR, NEWS_SCORING | 60-300s | [OBSERVÉ] |
| Stratégie | TRADE_GENERATOR | 300s | [OBSERVÉ] |
| Risque + Policy | RISK_MANAGER, POLICY_ENGINE | 30-60s | [OBSERVÉ] |
| Orchestration | TRADING_ORCHESTRATOR | 10s | [OBSERVÉ] |
| Exécution | TESTNET_EXECUTOR, PAPER_EXECUTOR | 30s | [OBSERVÉ] |
| Monitoring | KILL_SWITCH_GUARDIAN | 60s | [OBSERVÉ] |
| Évaluation | PERFORMANCE_ANALYST, STRATEGY_GATEKEEPER | 3600s | [OBSERVÉ] |

---

## Statut actuel

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| Mode | **Paper / Testnet** (env="paper" dans POLICY_ENGINE config) | [OBSERVÉ] |
| Capital fictif | 10 000 USDT | [OBSERVÉ] |
| Trades exécutés | 4 (tous profits, +$864.82, 100% win rate) | [OBSERVÉ] |
| Stratégie active | Momentum uniquement | [OBSERVÉ] |
| Dernière trade | 2026-03-09T22:14Z | [OBSERVÉ] |
| Positions ouvertes | 0 | [OBSERVÉ] |

---

## Kill Switch

| Propriété | Valeur | Tag |
|-----------|--------|-----|
| État | **ARMED** (non déclenché) | [OBSERVÉ] |
| trip_count | 0 | [OBSERVÉ] |
| Conditions de déclenchement | Daily loss >3%, 3+ erreurs consécutives executor, data quality degraded >15min, exchange down >5min | [OBSERVÉ] |
| Reset | Manuel uniquement | [OBSERVÉ] |

**Anomalie** : KILL_SWITCH_GUARDIAN a **27 399 erreurs** sur 23 645 runs (taux d'erreur 115%). Malgré ces erreurs, le kill switch n'a jamais été déclenché. [OBSERVÉ]

---

## Capital et règles de risque

| Règle | Valeur | Tag |
|-------|--------|-----|
| Capital initial | 10 000 USDT (fictif testnet) | [OBSERVÉ] |
| Risque par trade | 1% ($100) | [OBSERVÉ] |
| Max positions simultanées | 3 | [OBSERVÉ] |
| Max perte daily | -3% → kill switch | [OBSERVÉ] |
| Confidence minimum | 0.45 (RISK_MANAGER) | [OBSERVÉ] |
| Ratio R/R minimum | 2.0 | [OBSERVÉ] |
| Seuil human approval | $5 000 notional | [OBSERVÉ] |
| Kelly sizing | Implémenté dans RISK_MANAGER | [OBSERVÉ] |

---

## Coût LLM

| Métrique | Valeur | Tag |
|----------|--------|-----|
| Total sur 6 jours | $7.80 USD | [OBSERVÉ] |
| Moyenne journalière | $1.30 USD | [OBSERVÉ] |
| Projection mensuelle | ~$39 USD | [OBSERVÉ] |

| Agent | Appels | Coût | % total | Tag |
|-------|--------|------|---------|-----|
| NEWS_SCORING (Haiku) | 7 303 | $4.81 | 61% | [OBSERVÉ] |
| TRADE_GENERATOR (Haiku) | 1 051 | $2.96 | 38% | [OBSERVÉ] |
| STRATEGY_RESEARCHER (Sonnet) | 12 | $0.03 | <1% | [OBSERVÉ] |

---

## APIs externes — criticité

| API | Usage | Criticité | Si indisponible | Tag |
|-----|-------|-----------|-----------------|-----|
| Binance REST (mainnet) | Prix, klines, tickers | **BLOQUANT** | Aucun indicateur, aucun trade possible | [OBSERVÉ] |
| Binance Testnet | Exécution ordres MARKET+OCO | **BLOQUANT** | Exécution impossible (paper fonctionne encore) | [OBSERVÉ] |
| Etherscan v2 | Whale transfers | DÉGRADÉ | Perte du whale_context, TRADE_GENERATOR continue sans whale data | [OBSERVÉ] |
| CryptoPanic | News crypto | OPTIONNEL | RSS feeds compensent partiellement | [OBSERVÉ] |
| SEC EDGAR | News réglementaire | OPTIONNEL | Pas de détection early de news SEC | [OBSERVÉ] |
| Fear & Greed Index | Sentiment | OPTIONNEL | Sentiment non disponible | [OBSERVÉ] |
| RSS feeds (6) | Articles crypto | DÉGRADÉ | NEWS_SCORING n'a plus de matière | [OBSERVÉ] |
| Anthropic API | Haiku + Sonnet | **BLOQUANT** | NEWS_SCORING et TRADE_GENERATOR ne produisent plus de signaux | [OBSERVÉ] |
| CoinGecko | Prix ETH/BTC (pour whale USD) | DÉGRADÉ | Whale amounts non convertis en USD | [OBSERVÉ] |
| Telegram | Alertes + publications | OPTIONNEL | Alertes silencieuses | [OBSERVÉ] |

---

## Top 5 points de fragilité

| # | Fragilité | Sévérité | Tag |
|---|-----------|----------|-----|
| **1** | KILL_SWITCH_GUARDIAN en erreur continue (27k erreurs) — l'agent de sécurité critique est lui-même défaillant | CRITIQUE | [OBSERVÉ] |
| **2** | Conflit C-02 : double poller (PM2 host + cron Docker) — duplication potentielle d'exécution d'agents | ÉLEVÉ | [OBSERVÉ] |
| **3** | Tous les ordres HUMAN_APPROVAL_REQUIRED expirent (TTL 600s) — aucun mécanisme d'approbation en place | ÉLEVÉ | [OBSERVÉ] |
| **4** | SYSTEM_WATCHDOG rapporte 3 services critiques down (orchestrator + pollers) — les process PM2 sont en fait online mais le watchdog les voit via Docker | ÉLEVÉ | [OBSERVÉ] |
| **5** | Un seul point d'exécution (TESTNET_EXECUTOR) sans fallback — crash = plus aucune exécution | MOYEN | [DÉDUIT] |
