# pipeline_flows.md — Flux du pipeline Trading Factory

**Date** : 2026-03-15
**Scope** : Pipeline complet prix → exécution, avec latences et conditions

---

## Pipeline principal — Signal to Execution

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DONNÉES BRUTES (10–300s)                            │
│                                                                             │
│  ┌─────────────────────┐  ┌───────────────┐  ┌─────────────────┐          │
│  │ BINANCE_PRICE_FEED  │  │  NEWS_FEED    │  │  WHALE_FEED     │          │
│  │ every 10s           │  │  every 300s   │  │  every 300s     │          │
│  │ → raw.market.ticker │  │  → raw.news   │  │  → raw.whale    │          │
│  │ [Binance REST]      │  │  [RSS+APIs]   │  │  [Etherscan v2] │          │
│  └─────────┬───────────┘  └──────┬────────┘  └───────┬─────────┘          │
│            │                      │                    │                     │
│            ▼                      ▼                    ▼                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                     INTELLIGENCE (15–300s)                                   │
│                                                                             │
│  ┌────────────────────┐  ┌──────────────┐  ┌──────────────────┐           │
│  │ MARKET_EYE         │  │ NEWS_SCORING │  │ WHALE_ANALYZER   │           │
│  │ every 15s          │  │ every 300s   │  │ every 300s       │           │
│  │ [direct Binance]   │  │ [Haiku LLM]  │  │                  │           │
│  │ → intel.features   │  │ → intel.news │  │ → intel.whale    │           │
│  └───┬───────┬────────┘  └──────┬───────┘  └──────┬───────────┘           │
│      │       │                   │                  │                       │
│      │  ┌────┴──────────┐        │         ┌────────┘                       │
│      │  │ PREDICTOR     │        │         │                                │
│      │  │ every 60s     │        │         │                                │
│      │  │ → prediction  │        │         │                                │
│      │  │ ⚠️ ORPHELIN    │        │         │                                │
│      │  └───────────────┘        │         │                                │
│      │                           │         │                                │
│      ▼                           │         ▼                                │
│  ┌──────────────────────────────────────────────────────┐                  │
│  │ REGIME_DETECTOR — every 60s                          │                  │
│  │ inputs: intel.features + intel.whale                  │                  │
│  │ → intel.regime (TREND_UP/DOWN/RANGE/PANIC/EUPHORIA)  │                  │
│  └──────────────────────┬───────────────────────────────┘                  │
│                          │                                                  │
├──────────────────────────┼──────────────────────────────────────────────────┤
│                   STRATÉGIE (300s)                                          │
│                          ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │ TRADE_GENERATOR — every 300s (cooldown 30min/symbol)        │          │
│  │ inputs: intel.features + intel.regime + intel.news            │          │
│  │ flow:  1. Filtre pré-Haiku (hasSignal)                       │          │
│  │        2. Haiku LLM: direction, confidence, TP/SL            │          │
│  │        3. Filtre post-LLM (confidence ≥ threshold)           │          │
│  │ → strategy.trade.proposal                                    │          │
│  │ cost: ~$0.49/jour (38% budget LLM)                          │          │
│  └──────────────────────┬───────────────────────────────────────┘          │
│                          │                                                  │
├──────────────────────────┼──────────────────────────────────────────────────┤
│              RISQUE & POLICY (30–60s)                                       │
│                          ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │ RISK_MANAGER — every 60s                                     │          │
│  │ 7 filtres séquentiels :                                      │          │
│  │   1. kill_switch != TRIPPED                                  │          │
│  │   2. confidence ≥ 0.45                                       │          │
│  │   3. risk/reward ≥ 2.0                                       │          │
│  │   4. stop-loss valide (< 5% du prix)                         │          │
│  │   5. pas d'overlap (< 3 positions ouvertes)                  │          │
│  │   6. daily loss < 3%                                         │          │
│  │   7. Kelly sizing (max 1% capital = $100)                    │          │
│  │ → VALIDÉ: strategy.order.plan                                │          │
│  │ → REJETÉ: strategy.block                                     │          │
│  └──────────────────────┬───────────────────────────────────────┘          │
│                          ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │ POLICY_ENGINE — every 30s                                    │          │
│  │ Règles :                                                     │          │
│  │   • Asset whitelist (BTC, ETH, BNB uniquement)              │          │
│  │   • Notional < $5 000 → APPROVED                            │          │
│  │   • Notional ≥ $5 000 → HUMAN_APPROVAL_REQUIRED             │          │
│  │   • Time window (8h-22h UTC uniquement)                      │          │
│  │   • Strategy doit être "active" dans gatekeeper             │          │
│  │   • env="paper" → mode paper                                │          │
│  │ → strategy.policy.decision                                   │          │
│  │ ⚠️ 95 HUMAN_APPROVAL_REQUIRED → tous EXPIRED (TTL 600s)     │          │
│  └──────────────────────┬───────────────────────────────────────┘          │
│                          │                                                  │
├──────────────────────────┼──────────────────────────────────────────────────┤
│             ORCHESTRATION (10s)                                             │
│                          ▼                                                  │
│  ┌──────────────────────────────────────────────────────────────┐          │
│  │ TRADING_ORCHESTRATOR — every 10s                             │          │
│  │ State machine :                                              │          │
│  │   order.plan + policy.decision → corrélation                 │          │
│  │   PENDING_POLICY → (attend policy) → TTL 10min               │          │
│  │   APPROVED → exec.order.submit                               │          │
│  │   BLOCKED → fin                                              │          │
│  │   HUMAN_APPROVAL_REQUIRED → attend (TTL 600s) → EXPIRED     │          │
│  │ Capacity: 200 active + 100 terminal orders                   │          │
│  └──────────────────────┬───────────────────────────────────────┘          │
│                          │                                                  │
├──────────────────────────┼──────────────────────────────────────────────────┤
│              EXÉCUTION (30s)                                                │
│                          ▼                                                  │
│  ┌────────────────────────────────────────────────┐                        │
│  │ Mode testnet (actuel)                          │                        │
│  │ TESTNET_EXECUTOR — every 30s                   │                        │
│  │   • Binance Testnet REST (HMAC-SHA256)         │                        │
│  │   • MARKET order (entry)                       │                        │
│  │   • OCO order (TP + SL simultanés)             │                        │
│  │   • Gère positions ouvertes (close quand TP/SL)│                        │
│  │ → exec.trade.ledger + exec.position.snapshot   │                        │
│  │ → exec.order.error (si échec)                  │                        │
│  │ → exec.order.fill (si succès)                  │                        │
│  └────────────────────────────────────────────────┘                        │
│  ┌────────────────────────────────────────────────┐                        │
│  │ Mode paper (désactivé en schedule)             │                        │
│  │ PAPER_EXECUTOR — every 30s (schedule disabled) │                        │
│  │   • Simulation locale (slippage 10 bps)        │                        │
│  │   • exec/positions.json + exec/daily_pnl.json  │                        │
│  └────────────────────────────────────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Latence end-to-end

| Étape | Agent | Latence pire cas | Explication | Tag |
|-------|-------|-------------------|-------------|-----|
| 1 | MARKET_EYE → features | 15s | Cycle 15s, timeout 25s | [OBSERVÉ] |
| 2 | REGIME_DETECTOR → regime | +60s | Attend cycle 60s | [OBSERVÉ] |
| 3 | TRADE_GENERATOR → proposal | +300s | Cycle 300s + LLM call (~2-5s) + cooldown 30min/symbol | [OBSERVÉ] |
| 4 | RISK_MANAGER → order.plan | +60s | Cycle 60s | [OBSERVÉ] |
| 5 | POLICY_ENGINE → decision | +30s | Cycle 30s | [OBSERVÉ] |
| 6 | ORCHESTRATOR → order.submit | +10s | Cycle 10s | [OBSERVÉ] |
| 7 | TESTNET_EXECUTOR → fill | +30s | Cycle 30s + Binance API (~1-3s) | [OBSERVÉ] |
| **TOTAL** | — | **~8 min (worst case)** | Somme pire cas sans cooldown | [DÉDUIT] |
| **TOTAL avec cooldown** | — | **~38 min** | Cooldown 30min/symbol active | [DÉDUIT] |

**Latence typique observée** : ~3-5 minutes (la plupart des cycles ne tombent pas au pire cas). [DÉDUIT]

---

## Conditions et gates

| Gate | Condition | Si KO | Tag |
|------|-----------|-------|-----|
| Kill switch | `killswitch.json.state != "TRIPPED"` | **Tout le pipeline bloqué** (RISK_MANAGER rejette tout) | [OBSERVÉ] |
| Confidence | proposal.confidence ≥ 0.45 | Rejeté par RISK_MANAGER → `strategy.block` | [OBSERVÉ] |
| Risk/Reward | R/R ≥ 2.0 | Rejeté par RISK_MANAGER | [OBSERVÉ] |
| Max positions | < 3 ouvertes | Rejeté par RISK_MANAGER | [OBSERVÉ] |
| Daily loss | < 3% | Si ≥ 3% → kill switch TRIPPED | [OBSERVÉ] |
| Asset whitelist | BTC, ETH, BNB | Rejeté par POLICY_ENGINE | [OBSERVÉ] |
| Notional | < $5 000 | Si ≥ $5 000 → HUMAN_APPROVAL_REQUIRED (expire TTL 600s) | [OBSERVÉ] |
| Time window | 8h-22h UTC | Hors plage → BLOCKED par POLICY_ENGINE | [OBSERVÉ] |
| Strategy status | "active" dans gatekeeper | Si "testing" ou "rejected" → BLOCKED | [OBSERVÉ] |
| Cooldown | 30 min depuis dernier signal pour ce symbol | Pas de nouveau signal généré par TRADE_GENERATOR | [OBSERVÉ] |

---

## Modes d'échec

### Échec silencieux (pas de signal visible)

| Point d'échec | Symptôme | Détection | Tag |
|---------------|----------|-----------|-----|
| Binance API down | MARKET_EYE produit 0 features | KILL_SWITCH_GUARDIAN (data degraded >15min) | [OBSERVÉ] |
| Haiku API down | TRADE_GENERATOR et NEWS_SCORING ne produisent rien | SYSTEM_WATCHDOG (stale agent) | [DÉDUIT] |
| Poller crash | Aucun agent ne tourne | PM2 auto-restart (host poller), mais Docker poller = crash silencieux | [OBSERVÉ] |
| Kill switch inopérant | KILL_SWITCH_GUARDIAN a 27k erreurs mais ne trippe pas | **NON DÉTECTÉ** — le watchdog vérifie `killswitch.json` mais ne vérifie pas la santé du guardian | [DÉDUIT] |

### Échec bruyant (alerte déclenchée)

| Point d'échec | Alerte | Canal | Tag |
|---------------|--------|-------|-----|
| Daily loss >3% | Kill switch TRIPPED | Telegram @TraderBot | [OBSERVÉ] |
| 3+ erreurs executor | Kill switch TRIPPED | Telegram @TraderBot | [OBSERVÉ] |
| Agent stale >2× cycle | SYSTEM_WATCHDOG CRIT/WARN | Telegram @OppenCllawBot | [OBSERVÉ] |
| Disque <5% | SYSTEM_WATCHDOG CRIT | Telegram @OppenCllawBot | [OBSERVÉ] |

---

## Incompatibilités de schedule

| Agents | Problème | Impact | Tag |
|--------|----------|--------|-----|
| MARKET_EYE (15s) → PREDICTOR (60s) | 4 cycles features par cycle prediction | Prediction basée sur features potentiellement "vieilles" de 45s max | FAIBLE | [DÉDUIT] |
| TRADE_GENERATOR (300s) → RISK_MANAGER (60s) | 5 cycles risk par cycle signal | RISK_MANAGER poll souvent pour rien | FAIBLE | [DÉDUIT] |
| POLICY_ENGINE (30s) → ORCHESTRATOR (10s) | 3 cycles orchestrator par cycle policy | ORCHESTRATOR attend la policy.decision → PENDING_POLICY | OK | [OBSERVÉ] |
| KILL_SWITCH_GUARDIAN (60s) | Détecte une situation 60s trop tard au pire cas | Perte maximale pendant le délai de détection | MOYEN | [DÉDUIT] |

---

## Pipeline paper vs testnet vs live

| Étape | Paper (désactivé) | Testnet (actuel) | Live (futur) | Tag |
|-------|--------------------|------------------|---------------|-----|
| Data feeds | Identiques | Identiques | Identiques | [OBSERVÉ] |
| Intelligence | Identique | Identique | Identique | [OBSERVÉ] |
| TRADE_GENERATOR | Identique | Identique | Identique | [OBSERVÉ] |
| RISK_MANAGER | Identique | Identique | Identique | [OBSERVÉ] |
| POLICY_ENGINE | env="paper" | env="paper" | env="live" (à configurer) | [OBSERVÉ] |
| Executor | PAPER_EXECUTOR (simulation locale) | TESTNET_EXECUTOR (Binance Testnet) | (non implémenté) | [OBSERVÉ] |
| Capital réel | Non | Non (API keys testnet) | Oui | [OBSERVÉ] |

**Écart critique** : Aucun executor mainnet n'existe. La transition paper → testnet → live nécessite un nouvel executor + nouvelles API keys + review sécurité. [DÉDUIT]
