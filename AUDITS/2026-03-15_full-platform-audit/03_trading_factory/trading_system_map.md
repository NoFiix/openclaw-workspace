# trading_system_map.md — Quick Reference Trading Factory

**Date** : 2026-03-15
**Usage** : Référence rapide pour comprendre le système en < 5 minutes

---

## Diagramme global simplifié

```
                         ┌─────────────────────────────┐
                         │     APIS EXTERNES            │
                         │  Binance · Etherscan · RSS   │
                         │  CryptoPanic · Anthropic     │
                         └─────────┬───────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    ▼              ▼              ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │  PRIX    │  │  NEWS    │  │  WHALE   │
              │ FEED+EYE │  │ FEED     │  │ FEED     │
              │ 10-15s   │  │ 300s     │  │ 300s     │
              └────┬─────┘  └────┬─────┘  └────┬─────┘
                   │             │             │
                   ▼             ▼             ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │ REGIME   │  │ NEWS     │  │ WHALE    │
              │ DETECTOR │  │ SCORING  │  │ ANALYZER │
              │ 60s      │  │ Haiku    │  │ 300s     │
              └────┬─────┘  └────┬─────┘  └──────────┘
                   │             │
                   └──────┬──────┘
                          ▼
                   ┌──────────────┐
                   │ TRADE        │
                   │ GENERATOR    │  ← Haiku LLM ($0.49/j)
                   │ 300s         │
                   └──────┬───────┘
                          │ proposals
                          ▼
                   ┌──────────────┐
                   │ RISK         │  ← 7 filtres
                   │ MANAGER      │  ← Kelly sizing
                   │ 60s          │  ← 1% max/trade
                   └──────┬───────┘
                          │ order plans
                          ▼
                   ┌──────────────┐
                   │ POLICY       │  ← whitelist, time window
                   │ ENGINE       │  ← $5k human gate (⚠️ non fonctionnel)
                   │ 30s          │
                   └──────┬───────┘
                          │ decisions
                          ▼
                   ┌──────────────┐
                   │ ORCHESTRATOR │  ← corrèle plan + policy
                   │ 10s          │  ← TTL 10min
                   └──────┬───────┘
                          │ order submit
                          ▼
                   ┌──────────────┐
                   │ TESTNET      │  ← Binance Testnet
                   │ EXECUTOR     │  ← MARKET + OCO
                   │ 30s          │
                   └──────┬───────┘
                          │ trades
               ┌──────────┼──────────┐
               ▼          ▼          ▼
         ┌──────────┐ ┌────────┐ ┌────────────┐
         │PUBLISHER │ │PERF    │ │KILL SWITCH │
         │ Telegram │ │ANALYST │ │ GUARDIAN   │
         └──────────┘ └────────┘ │⚠️ 27k errs │
                                 └────────────┘
```

---

## Composants CORE

| Composant | Rôle | Cycle | Sans lui... |
|-----------|------|-------|-------------|
| BINANCE_PRICE_FEED | Prix spot BTC/ETH/BNB | 10s | Pipeline mort (aucune donnée) |
| MARKET_EYE | RSI/BB/MACD/ATR/Volume | 15s | Pas d'indicateurs techniques |
| TRADE_GENERATOR | Signaux de trade (Haiku LLM) | 300s | Pas de propositions de trade |
| RISK_MANAGER | 7 filtres + Kelly sizing | 60s | Pas de validation risque |
| POLICY_ENGINE | Règles système + approval gate | 30s | Pas d'autorisation de trade |
| TRADING_ORCHESTRATOR | Corrélation plan/policy → submit | 10s | Ordres jamais soumis |
| TESTNET_EXECUTOR | Exécution Binance Testnet | 30s | Ordres jamais exécutés |
| KILL_SWITCH_GUARDIAN | Coupe tout si perte >3% | 60s | Pas de protection capital |

---

## Dépendances critiques

```
Binance REST API ──────→ PRICE_FEED + MARKET_EYE ──→ tout le pipeline
                         (SPOF — pas de fallback)

Anthropic API (Haiku) ──→ NEWS_SCORING + TRADE_GENERATOR
                          (SPOF — pas de fallback, 99% des signaux)

Binance Testnet ────────→ TESTNET_EXECUTOR
                          (SPOF — unique point d'exécution)

poller.js ──────────────→ 23 agents (scheduling + spawning)
                          (SPOF — PM2 auto-restart seul mitigation)
```

---

## Top 5 risques

| # | Risque | Sévérité | Action immédiate |
|---|--------|----------|------------------|
| 1 | KILL_SWITCH_GUARDIAN défaillant (27k erreurs) | **CRITIQUE** | Diagnostiquer + corriger |
| 2 | Double poller C-02 (PM2 + cron Docker) | **ÉLEVÉ** | Supprimer @reboot cron |
| 3 | Human approval non fonctionnel (95 EXPIRED) | **ÉLEVÉ** | Désactiver ou implémenter |
| 4 | Binance API = SPOF sans fallback | **ÉLEVÉ** | Accepté (uptime >99.9%) |
| 5 | Anthropic API = SPOF pour signaux | **ÉLEVÉ** | Ajouter fallback gracieux |

---

## État actuel

| Métrique | Valeur | Tag |
|----------|--------|-----|
| Mode | Paper / Testnet | [OBSERVÉ] |
| Capital | 10 000 USDT (fictif) | [OBSERVÉ] |
| Trades exécutés | 4 (tous positifs) | [OBSERVÉ] |
| PnL total | +$864.82 (100% win rate) | [OBSERVÉ] |
| Positions ouvertes | 0 | [OBSERVÉ] |
| Kill switch | ARMED (jamais trippé) | [OBSERVÉ] |
| Stratégie active | Momentum uniquement | [OBSERVÉ] |
| Coût LLM | ~$1.30/jour (~$39/mois) | [OBSERVÉ] |
| Agents actifs | 22/24 (PAPER_EXECUTOR disabled, TUNER dormant) | [OBSERVÉ] |
| Bus taille | ~170 Mo (18 topics JSONL) | [OBSERVÉ] |

---

## Checklist troubleshooting

### Pipeline ne produit plus de trades

1. `cat state/trading/exec/killswitch.json` → si `TRIPPED`, le kill switch bloque tout. Reset : supprimer le fichier.
2. `pm2 status trading-poller` → si stopped, `pm2 restart trading-poller`
3. Vérifier Binance API : `curl -s https://api.binance.com/api/v3/ping` → doit retourner `{}`
4. Vérifier les features : `tail -1 state/trading/bus/trading_intel_market_features.jsonl` → doit être récent
5. Vérifier les proposals : `tail -1 state/trading/bus/trading_strategy_trade_proposal.jsonl` → récent ?
6. Vérifier policy : `tail -1 state/trading/bus/trading_strategy_policy_decision.jsonl` → APPROVED ?
7. Vérifier pipeline state : `cat state/trading/memory/pipeline_state.json | python3 -m json.tool | grep status` → y a-t-il des ordres PENDING ?

### Kill switch trippé par erreur

1. `cat state/trading/exec/killswitch.json` → vérifier `reason`
2. Si faux positif : `echo '{"state":"ARMED","tripped_at":null,"reason":null,"trip_count":0}' > state/trading/exec/killswitch.json`
3. Vérifier que KILL_SWITCH_GUARDIAN fonctionne : `ls -la state/trading/runs/KILL_SWITCH_GUARDIAN/` → fichiers récents ?

### Double exécution suspectée (C-02)

1. `ps aux | grep poller.js | grep -v grep` → devrait montrer 1 seul process
2. Si 2 processes : `kill <pid_du_cron_process>` puis supprimer la ligne @reboot du crontab
3. Vérifier les doublons bus : `tail -5 state/trading/bus/trading_raw_market_ticker.jsonl | jq '.timestamp'` → timestamps identiques = doublon

### Coûts LLM anormalement élevés

1. `cat state/trading/audit/token_costs.jsonl | tail -20` → identifier l'agent consommateur
2. Si double coût : vérifier C-02 (double poller)
3. NEWS_SCORING = 61% du budget → normal (7 300 appels Haiku)
4. TRADE_GENERATOR = 38% → normal (1 050 appels Haiku)
