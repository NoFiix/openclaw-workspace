# CLAUDE.md — POLY_FACTORY

POLY_FACTORY is an automated system that discovers, tests, optimizes and deploys strategies on prediction markets (Polymarket, future: Kalshi, sportsbooks). It is part of the OpenClaw environment. Objective: maximize long-term profit under strict risk control.

---

## Reference Documents

Read the right document BEFORE coding:

| When | Read |
|---|---|
| Starting any ticket | `docs/POLY_FACTORY_DEV_BACKLOG.md` → find the ticket, read its artifacts |
| Ticket touches risk or execution | `docs/POLY_FACTORY_IMPLEMENTATION_PLAN.md` section 9 (guards) |
| Ticket touches the bus or inter-agent communication | `docs/POLY_FACTORY_IMPLEMENTATION_PLAN.md` section 7 (bus contracts + payloads) |
| Architecture question or doubt on agent responsibility | `docs/POLY_FACTORY_ARCHITECTURE.md` |
| Pipeline flow question (which cycle, which order) | `docs/POLY_FACTORY_PIPELINE.md` |
| Repo structure or file placement question | `docs/POLY_FACTORY_REPO_STRUCTURE.md` |
| Touching paper or live execution | Re-read the "Separation Paper / Live" section below — EVERY TIME |

---

## Repo Structure

```
POLY_FACTORY/
├── CLAUDE.md              ← this file
├── docs/                  ← architecture, pipeline, plan, backlog (read-only reference)
├── core/                  ← bus, data store, audit log, orchestrator, account, registry
├── agents/                ← data feeds, signal agents, validators, monitors
├── strategies/            ← strategy agents ONLY (emit signals, no execution logic)
├── execution/             ← paper engine, live engine, router, order splitter
├── risk/                  ← kill switch, risk guardian, global risk guard, promotion gate
├── evaluation/            ← evaluator, decay detector, tuner, scout, backtest, compounder
├── connectors/            ← platform connectors (polymarket, kalshi, sportsbook)
├── schemas/               ← JSON schemas for bus events and state files
├── tests/                 ← one test file per agent/component
├── references/            ← static config (station mapping, wallets, weights, rules)
├── state/                 ← runtime data (VPS only, never in Git)
├── tasks/                 ← todo.md + lessons.md
└── .env                   ← secrets (never committed)
```

When creating a file, check the structure above. If uncertain → read `docs/POLY_FACTORY_REPO_STRUCTURE.md`.

---

## Naming Conventions

```
Core         : core/poly_{name}.py                  (ex: core/poly_event_bus.py)
Agents       : agents/poly_{name}.py                (ex: agents/poly_binance_feed.py)
Strategies   : strategies/poly_{name}.py            (ex: strategies/poly_arb_scanner.py)
Execution    : execution/poly_{name}.py             (ex: execution/poly_paper_execution_engine.py)
Risk         : risk/poly_{name}.py                  (ex: risk/poly_kill_switch.py)
Evaluation   : evaluation/poly_{name}.py            (ex: evaluation/poly_strategy_evaluator.py)
Connectors   : connectors/connector_{platform}.py   (ex: connectors/connector_polymarket.py)
Schemas      : schemas/{event_or_model}.json        (ex: schemas/trade_signal.json)
Tests        : tests/test_{name}.py                 (ex: tests/test_kill_switch.py)
State files  : state/{category}/{file}.json         (ex: state/feeds/binance_raw.json)
Bus events   : {category}:{action}                  (ex: trade:signal, feed:price_update)
Accounts     : ACC_POLY_{STRATEGY_NAME}             (ex: ACC_POLY_ARB_SCANNER)
Prefix       : ALL agents use the POLY_ prefix
```

---

## Mandatory Rules

**Paper/Live separation** — `execution/poly_paper_execution_engine.py` and `execution/poly_live_execution_engine.py` are two separate modules in two separate files. Paper CANNOT import py-clob-client, access wallets, or send transactions. The `POLY_EXECUTION_ROUTER` routes signals based on the strategy status in `POLY_STRATEGY_REGISTRY`. Never use a boolean flag to switch paper/live.

**Capital model** — Each strategy gets its own isolated 1 000€ account (`POLY_STRATEGY_ACCOUNT`). Kelly sizing is based on the ACCOUNT capital, never the global capital. Kill switch drawdown is per-account: -5% daily, -30% total.

**Global risk** — If cumulative losses across ALL strategies reach 4 000€, `POLY_GLOBAL_RISK_GUARD` halts everything. This rule cannot be bypassed.

**Promotion flow** — paper → evaluation (score ≥ 60) → `POLY_STRATEGY_PROMOTION_GATE` (10 checks) → human approval (JSON signed, expires 7 days) → `POLY_CAPITAL_MANAGER` creates live account. Gate DECIDES. Capital Manager EXECUTES. Live deployment is NEVER automatic.

**Backtest doctrine** — A positive backtest is NEVER sufficient to promote a strategy. Only the combination backtest + paper trading (≥ 50 trades, ≥ 14 days) + tradability confirmed justifies proposing a strategy for live.

**Strategy separation** — Strategies MUST live in `strategies/`. Strategies must not contain execution logic. Strategies emit signals only (`trade:signal` on the bus). Execution is handled exclusively by `execution/poly_paper_execution_engine.py` or `execution/poly_live_execution_engine.py` via the `POLY_EXECUTION_ROUTER`.

**Event bus** — File-based (`state/bus/pending_events.jsonl`), polling 1-5s. Envelope: `{event_id, topic, timestamp, producer, priority, retry_count, payload}`. Consumers MUST implement idempotence (set of last 10 000 event_ids). Dead letter after 3 retries. Modes: overwrite (feeds), queue (trades, promotions), cache (resolutions), sync (pre-trade risk checks), priority (kill switch, news). Payloads MUST conform to the JSON schemas in `schemas/`.

---

## NEVER

- Import `py-clob-client` in any paper module
- Bypass the Promotion Gate for live deployment
- Use a boolean flag to switch paper/live (use `POLY_EXECUTION_ROUTER`)
- Create a strategy without a `POLY_STRATEGY_ACCOUNT` and `POLY_STRATEGY_REGISTRY` entry
- Promote a strategy to live based on backtest alone (paper trading required)
- Modify the event bus envelope format without updating ALL consumers AND `schemas/`
- Commit wallet private keys or API secrets to Git — secrets must only be read from `.env`, never hardcoded
- Share capital between strategies (accounts are isolated)
- Let `POLY_STRATEGY_PROMOTION_GATE` create accounts (that is `POLY_CAPITAL_MANAGER`'s job)
- Skip risk checks — the 7-filter chain applies to EVERY trade, no exception
- Put execution logic inside a strategy file — strategies emit signals only, execution engines execute
- Place a file in the wrong directory — check the repo structure above before creating any file

---

## Development Workflow

**Ticket-based** — The official backlog is `docs/POLY_FACTORY_DEV_BACKLOG.md`. One ticket at a time unless explicitly told otherwise. Each ticket has: objective, artifacts (Python + state + config + test files), dependencies, acceptance criteria.

**Plan mode** — For any task involving 3+ steps, architecture decisions, or multiple files: (1) enter plan mode, (2) write the plan in `tasks/todo.md` referencing the POLY-XXX ticket ID, (3) validate, (4) execute. If something fails → stop and re-plan.

**Task tracking** — `tasks/todo.md` tracks the current sprint only. Each task MUST reference a POLY-XXX ticket ID from the backlog. Do not create tasks outside the backlog without discussion.

**Lessons** — Maintain `tasks/lessons.md`. On every correction: capture the mistake pattern, write a prevention rule, review lessons at session start.

---

## Verification

A task is NOT complete until:

- Tests pass (`tests/test_{agent}.py`)
- Code runs without errors
- Behavior matches the ticket's acceptance criteria
- For paper modules: `grep -r "py_clob_client\|py-clob-client" execution/poly_paper_execution_engine.py` returns 0 results
- Bus payloads match the JSON schemas in `schemas/` and the contracts in `docs/POLY_FACTORY_IMPLEMENTATION_PLAN.md` section 7
- File is in the correct directory per the repo structure
- Ask: "Would a senior engineer approve this change?"

---

## Code Quality

- Prefer simple solutions over clever ones
- Fix root causes, not symptoms
- **1 agent = 1 file = 1 responsibility** — agents must not implement multiple unrelated roles. If a file does two things, split it.
- No hacky fixes — if a workaround is needed, document WHY
- Keep state files as the single source of truth (no in-memory-only state)

---

## When Uncertain

1. Read the architecture documents (see Reference Documents above)
2. Check the repo structure (`docs/POLY_FACTORY_REPO_STRUCTURE.md`)
3. Follow the backlog order
4. Prioritize safety over speed
5. Prefer robust solutions over clever ones
6. Ask rather than assume

---

## DÉCISION PROMPT NO_SCANNER / OPP_SCORER — 2026-03-30

### Contexte
Le prompt LLM original estimait prob_no sans ancrage au prix du marché.
Résultat : biais systématique +3.3 points → 12/12 trades perdants.

Un premier correctif "calibré" a été testé mais rejeté :
il neutralisait le modèle (LLM copiait le marché, edge=0).
Avoir biais=0 n'est pas suffisant — il faut edge > 0.

### Décision déployée
Nouveau prompt : LLM = adversaire du marché (détecteur de mismatch).
Le LLM ne prédit plus une probabilité — il cherche activement
si le marché se trompe et pourquoi.

Gate activé : signal émis UNIQUEMENT si :
- has_edge = true
- edge_strength >= "moderate"
- confidence >= "medium"

### À vérifier impérativement le 2026-04-13 (dans 2 semaines)

QUESTION CLEF :
Le nouveau prompt génère-t-il des signaux has_edge=true ?
Si oui : sont-ils profitables (PnL positif sur ces trades) ?
Si non : le LLM n'a pas d'edge structurel sur ces marchés
         → désactiver NO_SCANNER ou changer de type de marché.

MÉTRIQUES À REGARDER :
1. Nombre de signaux has_edge=true générés en 2 semaines
   grep "LLM_DECISION.*has_edge=True" logs/pm2-out.log | wc -l
2. Ratio has_edge=true / total décisions LLM
   grep "LLM_DECISION" logs/pm2-out.log | wc -l
3. Distribution edge_strength
   grep "LLM_DECISION" logs/pm2-out.log | grep -o "edge_strength=[a-z]*"
4. PnL des trades exécutés
   cat state/accounts/ACC_POLY_NO_SCANNER.json → pnl.total
   cat state/accounts/ACC_POLY_OPP_SCORER.json → pnl.total
5. Si 0 signal has_edge=true en 2 semaines →
   le LLM confirme qu'il n'a pas d'information supérieure au marché
   sur ces marchés sportifs/politiques bien suivis
   → décision : désactiver NO_SCANNER, explorer marchés de niche

FICHIERS À CONSULTER :
- logs/pm2-out.log (grep "LLM_DECISION")
- state/trading/paper_trades_log.jsonl
- state/accounts/ACC_POLY_NO_SCANNER.json
- state/accounts/ACC_POLY_OPP_SCORER.json
