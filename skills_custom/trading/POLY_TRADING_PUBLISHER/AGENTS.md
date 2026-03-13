# POLY_TRADING_PUBLISHER

Agent Node.js de notification Telegram pour le système POLY_FACTORY (marchés prédictifs).

## Rôle

Publie sur un canal Telegram Polymarket dédié :
- Alertes en temps réel (trades LIVE, kill switches, promotions)
- Alertes sélectives PAPER (premier trade du jour, kill switch, proche éligibilité)
- Rapport quotidien à 20h00 Paris
- Rapport hebdomadaire le dimanche à 20h00 Paris

## Ce que cet agent NE fait PAS

- Ne surveille PAS l'infrastructure ni les agents (c'est SYSTEM_WATCHDOG)
- Ne publie PAS d'alertes OpenClaw crypto trading (c'est TRADING_PUBLISHER)
- Ne prend PAS de décisions de trading
- N'accède PAS au bus OpenClaw pour les données POLY (lecture directe fichiers POLY_FACTORY)

## Sources de données

```
POLY_BASE = /home/openclawadmin/openclaw/workspace/POLY_FACTORY/state/

trading/paper_trades_log.jsonl   → trades PAPER
trading/live_trades_log.jsonl    → trades LIVE
accounts/ACC_POLY_*.json         → capital et P&L par stratégie
risk/kill_switch_status.json     → kill switch par stratégie
risk/global_risk_state.json      → statut global (NORMAL/ALERTE/CRITIQUE/ARRET_TOTAL)
evaluation/strategy_scores.json  → scores d'évaluation (axe, total, verdict)
orchestrator/system_state.json   → état orchestrateur
```

## Variables d'environnement requises

```
POLY_TELEGRAM_BOT_TOKEN   — token du bot Telegram Polymarket
POLY_TELEGRAM_CHAT_ID     — ID du canal de notification
POLY_BASE_PATH            — (optionnel) override du chemin POLY_FACTORY/state
```

## Types de messages (13)

### Priorité 1 — Alertes LIVE
| Fonction             | Déclencheur                                        |
|----------------------|----------------------------------------------------|
| `msgLiveTradeOpened` | Nouveau trade `live_trades_log.jsonl`              |
| `msgLiveTradeClosed` | Trade LIVE avec outcome (résolu)                   |
| `msgLiveKillSwitch`  | KS `STOP_STRATEGY` ou `PAUSE_DAILY` (LIVE)         |
| `msgGlobalKillSwitch`| `risk/global_risk_state.json` → ARRET_TOTAL        |
| `msgPromotion`       | `account.status` passe à `live`                    |
| `msgLiveStrategyPaused` | KS PAUSE → stratégie live                       |
| `msgLiveStrategyResumed`| KS → retour OK (stratégie live)                 |
| `msgLiveDrawdownWarning`| KS `WARNING` (cooldown 4h)                      |

### Priorité 2 — Alertes PAPER (sélectives)
| Fonction                  | Déclencheur                                    |
|---------------------------|------------------------------------------------|
| `msgPaperTradeOpened`     | 1er trade PAPER ouvert du jour par stratégie   |
| `msgPaperTradeClosed`     | Trade PAPER résolu (avec outcome)              |
| `msgPaperNearEligibility` | Stratégie à ≥80% des seuils d'éligibilité live |
| `msgPaperValidationFailed`| (réservé — à connecter au PROMOTION_GATE)      |
| `msgPaperKillSwitch`      | KS `PAUSE_DAILY` sur compte paper              |

### Priorité 3 — Rapports
| Fonction          | Déclencheur                        |
|-------------------|------------------------------------|
| `msgDailyReport`  | 20h00–20h59 Paris, une fois/jour   |
| `msgWeeklyReport` | Dimanche 20h00–20h59 Paris         |

## Déduplication

Toutes les alertes sont protégées par `sent_keys` (timestamp) dans l'état agent :
- `ctx.state.sent_keys` — clés de déduplication (type → timestamp)
- `ctx.state.known_paper_ids` — IDs des trades PAPER déjà connus
- `ctx.state.known_live_ids`  — IDs des trades LIVE déjà connus
- `ctx.state.prev_ks_levels`  — niveaux kill switch précédents par stratégie
- `ctx.state.prev_global`     — dernier statut global risk

Au premier démarrage (`_initialized = false`), tous les trades existants sont
enregistrés dans `known_*_ids` SANS envoyer d'alerte (anti-flood de démarrage).

## Planning

```
schedules/POLY_TRADING_PUBLISHER.schedule.json
every_seconds: 60
```

## Fichiers

```
POLY_TRADING_PUBLISHER/
├── index.js       — launcher (runAgent pattern)
├── handler.js     — logique principale
├── formatters.js  — helpers formatage (purs)
├── messages.js    — templates Telegram
└── AGENTS.md      — cette documentation
```
