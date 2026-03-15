# filesystem_map.md — Carte du filesystem

**Date** : 2026-03-15
**Méthode** : `ls`, `du`, observation directe

---

## Arborescence principale

```
/home/openclawadmin/openclaw/
└── workspace/                          ← racine de travail
    ├── AUDITS/                         ← audits (ce dossier)
    ├── POLY_FACTORY/                   ← système Python prediction markets
    │   ├── agents/                     ← feeds + signal agents
    │   ├── connectors/                 ← connecteurs plateforme
    │   ├── core/                       ← bus, store, orchestrator
    │   ├── evaluation/                 ← évaluateur, tuner, scout
    │   ├── execution/                  ← paper + live engines, router
    │   ├── risk/                       ← kill switch, risk guardian
    │   ├── strategies/                 ← 9 stratégies
    │   ├── schemas/                    ← JSON schemas bus events
    │   ├── tests/                      ← pytest test files
    │   ├── references/                 ← config statique
    │   ├── docs/                       ← architecture, pipeline, backlog
    │   ├── state/                      ← runtime data (15 sous-dossiers)
    │   ├── .venv/                      ← virtualenv Python 3.11
    │   └── .env                        ← secrets POLY_FACTORY
    ├── skills_custom/                  ← agents JS OpenClaw
    │   ├── trading/                    ← 25 agents JS trading
    │   │   ├── _shared/               ← utilitaires partagés
    │   │   ├── _deferred/             ← agents inactifs
    │   │   ├── poller.js              ← orchestrateur polling JS
    │   │   ├── bus_rotation.js        ← maintenance bus JS
    │   │   └── bus_cleanup_trading.js ← nettoyage bus JS
    │   ├── hourly_scraper.js          ← scraper horaire
    │   ├── scraper.js                 ← scraper quotidien
    │   └── poller.js                  ← content poller
    ├── dashboard/
    │   ├── api/                       ← API Node.js (PM2)
    │   │   ├── routes/                ← endpoints REST
    │   │   └── .env                   ← config dashboard
    │   └── web/
    │       └── src/                   ← frontend React/Next
    ├── state/
    │   └── trading/                   ← state JS Trading Factory
    │       ├── bus/                   ← bus JS (JSONL)
    │       ├── runs/                  ← logs d'exécution agents JS
    │       ├── schedules/             ← schedules agents JS
    │       ├── configs/               ← config agents JS
    │       ├── audit/                 ← audit logs JS
    │       ├── exec/                  ← exécution JS
    │       ├── learning/              ← ML/learning JS
    │       ├── live/                  ← live trading JS
    │       ├── memory/                ← mémoire agents JS
    │       ├── risk/                  ← risk state JS
    │       ├── context/               ← contexte JS
    │       └── poller.log             ← ~48 Mo log
    ├── agents/                        ← [INCONNU] usage exact
    ├── docs/                          ← documentation globale
    ├── intel/                         ← [INCONNU] contenu
    ├── recipes/                       ← recettes automatisées
    └── .env                           ← secrets globaux (vide?) [INCONNU]
```

---

## Répertoires state — Analyse de risque

### POLY_FACTORY/state/ (Python)

| Sous-dossier | Rôle | Owner | Risque | Tag |
|-------------|------|-------|--------|-----|
| `accounts/` | Comptes stratégie (1000€ chacun) | poly-orchestrator | TYPE_1 — perte = reset capital | [OBSERVÉ] |
| `bus/` | pending_events.jsonl, processed, dead_letter | poly-orchestrator | TYPE_1 — corruption = perte événements | [OBSERVÉ] |
| `trading/` | paper_trades_log.jsonl | poly-orchestrator | TYPE_1 — historique trades | [OBSERVÉ] |
| `feeds/` | prix Polymarket, Binance, NOAA, wallet | poly-orchestrator | TYPE_2 — données régénérables | [OBSERVÉ] |
| `orchestrator/` | heartbeat, lifecycle, system_state | poly-orchestrator | TYPE_2 — état orchestrateur | [OBSERVÉ] |
| `registry/` | strategy_registry.json | poly-orchestrator | TYPE_2 — config stratégies | [OBSERVÉ] |
| `risk/` | kill_switch, risk state | poly-orchestrator | TYPE_1 — sécurité trading | [OBSERVÉ] |
| `evaluation/` | scores, evaluations | poly-orchestrator | TYPE_3 — régénérable | [OBSERVÉ] |
| `audit/` | audit log | poly-orchestrator | TYPE_3 — historique | [OBSERVÉ] |
| `historical/` | données historiques | poly-orchestrator | TYPE_3 | [OBSERVÉ] |
| `human/` | approbations humaines | poly-orchestrator | TYPE_1 — sécurité promotion | [OBSERVÉ] |
| `llm/` | cache LLM | poly-orchestrator | TYPE_4 — jetable | [OBSERVÉ] |
| `memory/` | mémoire agents | poly-orchestrator | TYPE_3 | [OBSERVÉ] |
| `research/` | recherche stratégies | poly-orchestrator | TYPE_3 | [OBSERVÉ] |
| `strategies/` | state stratégies | poly-orchestrator | TYPE_2 | [OBSERVÉ] |

### workspace/state/trading/ (JS)

| Sous-dossier | Rôle | Owner | Tag |
|-------------|------|-------|-----|
| `bus/` | bus JS (JSONL) | trading-poller + cron | [OBSERVÉ] |
| `runs/` | logs exécution agents (~6 Mo) | trading-poller + watchdog | [OBSERVÉ] |
| `schedules/` | 7 schedules agents | trading-poller | [OBSERVÉ] |
| `configs/` | config agents JS | trading-poller | [OBSERVÉ] |
| `audit/` | rotation logs | cron bus_rotation | [OBSERVÉ] |
| `exec/` | exécution JS | trading-poller | [OBSERVÉ] |
| `learning/` | apprentissage ML | trading-poller | [OBSERVÉ] |
| `live/` | trading live JS | trading-poller | [OBSERVÉ] |
| `memory/` | mémoire agents JS | trading-poller | [OBSERVÉ] |
| `risk/` | état risque JS | trading-poller | [OBSERVÉ] |
| `context/` | contexte agents | trading-poller | [OBSERVÉ] |

---

## CONFLIT C-03 : Deux systèmes de state indépendants

**Observation** [OBSERVÉ] :
- `POLY_FACTORY/state/` → géré par Python `poly-orchestrator`
- `workspace/state/trading/` → géré par JS `trading-poller` + cron jobs

**Analyse** [DÉDUIT] :
- Les deux systèmes ont chacun leur propre bus, risk management, exécution
- Aucun mécanisme de coordination entre les deux n'a été observé
- POLY_TRADING_PUBLISHER (JS) semble être un pont entre les deux mais son fonctionnement exact est [INCONNU]

**Sévérité** : MEDIUM — risque de décisions contradictoires si les deux systèmes sont actifs simultanément sur les mêmes marchés.

---

## Fichiers notables

| Fichier | Taille | Remarque | Tag |
|---------|--------|----------|-----|
| `state/trading/poller.log` | ~48 Mo | Log principal du poller JS, croissance continue | [OBSERVÉ] |
| `POLY_FACTORY/state/bus/pending_events.jsonl` | variable | Compacté auto tous les 100 polls si >10k events | [OBSERVÉ] |
| `POLY_FACTORY/.env` | secrets | 9 clés configurées, `WALLET_PRIVATE_KEY` absente | [OBSERVÉ] |
