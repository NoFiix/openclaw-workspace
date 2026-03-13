# POLY_FACTORY — Final Dev Spec

**Target:** page `Polymarket` inside the existing dashboard  
**Goal:** provide a precise implementation brief that a frontend developer or coding AI can use directly to build the page with minimal ambiguity.

---

## 1) Purpose

Create a new dashboard section called **Polymarket** for **POLY_FACTORY**, an automated multi-strategy trading system for prediction markets.

This page must allow a user to understand in less than **5 seconds**:

1. whether the system is profitable
2. whether the system is currently at risk
3. which strategies are performing best or worst
4. what positions/trades are currently active
5. whether the infrastructure and signals are healthy

This is **not** a simple stats page.  
It must feel like a **control center for an automated portfolio**.

---

## 2) Product context

### POLY_FACTORY summary

POLY_FACTORY is a fully automated system trading on Polymarket.

It operates with **9 independent strategies**:

- `ARB_SCANNER`
- `WEATHER_ARB`
- `LATENCY_ARB`
- `BROWNIAN_SNIPER`
- `PAIR_COST`
- `OPP_SCORER`
- `NO_SCANNER`
- `CONVERGENCE`
- `NEWS_STRAT`

Each strategy:
- has its own capital allocation
- starts with `1000€` in paper trading
- has independent performance metrics
- can be promoted to live independently
- can be paused/stopped independently

### Current operating mode

For now, the system is primarily in **paper trading** mode.

Validation period:
- minimum target period: **14 days**
- promotion conditions include:
  - `win rate > 52.6%`
  - `Sharpe > 2.5`
  - `drawdown < 5%`
  - plus other gate checks

### Risk protection rules

- **strategy kill switch**: stop a strategy if:
  - daily loss exceeds `-5%`
  - or total loss exceeds `-30%`
- **global kill switch**:
  - stop everything if cumulative losses exceed `4000€`
- **Risk Guardian**:
  - maximum `6` simultaneous open positions
- **Order Splitter**:
  - split large orders to reduce market impact

---

## 3) Design objective

The page must follow the existing dashboard style:

- dark theme
- same colors / spacing / visual language as existing sections
- clean, elegant, premium look
- immediate readability
- low clutter
- professional trading desk feel

### UX principles

The page should follow this information hierarchy:

1. **Summary** → how the system is doing overall
2. **Action** → what the system is doing right now
3. **Diagnosis** → why it performs well or poorly

### Important UX rule

Do **not** overload the UI with too many numbers.  
Each block must have:

- 1 dominant metric
- 3–5 secondary metrics maximum
- details available in tables / detail pages / tooltips / drawers

---

## 4) Route and navigation

### Main route

`/dashboard/polymarket`

### Recommended sub-routes

- `/dashboard/polymarket`
- `/dashboard/polymarket/strategies`
- `/dashboard/polymarket/strategy/:name`
- `/dashboard/polymarket/trades`
- `/dashboard/polymarket/risk`
- `/dashboard/polymarket/system`

### Detail route

Each strategy card must open:

`/dashboard/polymarket/strategy/:name`

Example:

`/dashboard/polymarket/strategy/arb_scanner`

---

## 5) Page layout

The page must be built in the following vertical order:

1. `Header`
2. `Global KPI Strip`
3. `Performance Charts`
4. `Strategy Cards Grid`
5. `Strategy Analysis`
6. `Execution`
7. `Risk Management`
8. `System Health / Infra`

This order is intentional and should be respected.

---

## 6) Page structure in detail

### 6.1 Header

#### Component name

`PolymarketHeader`

#### Purpose

Give immediate context and top-level status.

#### Content

**Left side**
- Title: `Polymarket`
- Subtitle: `Automated Prediction Market Trading`

**Right side**
Display status badges:

- `SYSTEM STATUS`
- `GLOBAL RISK`
- `MODE SPLIT`

Example:
- `RUNNING`
- `RISK: NORMAL`
- `PAPER 7 / LIVE 2`

#### Required data

- `system.status`
- `risk.global_state`
- `strategies.paper_count`
- `strategies.live_count`

#### Suggested values

##### `system.status`
- `RUNNING`
- `PAUSED`
- `DEGRADED`
- `HALTED`

##### `risk.global_state`
- `NORMAL`
- `ELEVATED`
- `WARNING`
- `KILL_SWITCH`
- `HALTED`

---

### 6.2 Global KPI Strip

#### Component name

`PolymarketKPIStrip`

#### Purpose

This is the most important row on the page.  
It should answer: **“Is everything under control?”**

#### Layout

Horizontal row of **6 KPI cards**.

#### KPIs to display

1. `System Health`
2. `Total P&L`
3. `Max Drawdown`
4. `Sharpe Ratio`
5. `Open Positions`
6. `Active Strategies`

#### KPI 1 — System Health

##### Component
`SystemHealthCard`

##### Purpose
Primary synthetic score summarizing the system state.

##### Display
- main value: `86 / 100`
- label: `Healthy`

##### Color logic
- `80–100` → green
- `60–79` → yellow
- `40–59` → orange
- `<40` → red

##### Inputs
- `global.pnl`
- `risk.max_drawdown`
- `risk.alert_count`
- `agents.health_score`
- `queue.backlog_score`
- `system.activity_score`
- `risk.global_kill_switch`

##### Implementation note
If exact formula is not available yet, build the component to accept a backend-provided value:

- `system.health_score`
- `system.health_label`

Do **not** hardcode a frontend-only formula unless required.

#### KPI 2 — Total P&L

##### Component
`TotalPnLCard`

##### Display
- total P&L in `€`
- total P&L in `%`
- today’s P&L

Example:
- `+1240 €`
- `+13.8%`
- `Today: +182 €`

##### Inputs
- `pnl.total_eur`
- `pnl.total_percent`
- `pnl.today_eur`

##### Color logic
- positive → green
- negative → red
- neutral → gray

#### KPI 3 — Max Drawdown

##### Component
`DrawdownCard`

##### Display
- `Max Drawdown`
- value in `%`

Example:
- `-2.4%`

##### Inputs
- `risk.max_drawdown_percent`

##### Color logic
- safe → green
- warning threshold near limit → yellow/orange
- breach / critical → red

#### KPI 4 — Sharpe Ratio

##### Component
`SharpeCard`

##### Display
- `Sharpe`
- numeric value

Example:
- `3.1`

##### Inputs
- `metrics.global_sharpe`

##### Color hints
Optional:
- `>2.5` green
- `1.5–2.5` yellow
- `<1.5` red/orange

#### KPI 5 — Open Positions

##### Component
`OpenPositionsCard`

##### Display
- current open positions
- max allowed positions

Example:
- `4 / 6`

##### Inputs
- `risk.open_positions_count`
- `risk.max_open_positions`

##### Color logic
- if close to limit, highlight warning

#### KPI 6 — Active Strategies

##### Component
`ActiveStrategiesCard`

##### Display
- active/running strategies count
- total strategies count

Example:
- `7 / 9`

##### Inputs
- `strategies.running_count`
- `strategies.total_count`

---

### 6.3 Performance Charts

#### Component group
`PolymarketPerformanceSection`

#### Purpose
Show the portfolio-level behavior over time.

#### Charts required
1. `Equity Curve`
2. `Drawdown Curve`

#### Time range filters
Provide a top-right range selector:
- `24h`
- `7d`
- `14d`
- `All`

Default:
- `14d`

This matters because the paper-trading validation cycle is 14 days.

#### Chart 1 — Equity Curve

##### Component
`EquityCurveChart`

##### Type
Line chart

##### Purpose
Show cumulative performance over time.

##### Inputs
Array of points:

```ts
{
  timestamp: string
  pnl_eur: number
}
```

##### Data key
- `timeseries.equity_curve[]`

##### Requirements
- smooth, highly readable
- tooltip on hover
- responsive width
- no visual clutter

#### Chart 2 — Drawdown Curve

##### Component
`DrawdownChart`

##### Type
Area chart or line+area chart

##### Purpose
Show drawdown evolution over time.

##### Inputs
Array of points:

```ts
{
  timestamp: string
  drawdown_percent: number
}
```

##### Data key
- `timeseries.drawdown_curve[]`

##### Requirements
- drawdown should be visually obvious
- negative values easy to interpret

---

### 6.4 Strategy Cards Grid

#### Component group
`StrategyGrid`

#### Layout
3 columns × 3 rows on desktop  
Responsive collapse on smaller screens

#### Purpose
This is the main multi-strategy supervision view.  
Cards are for **quick scanning**.

Each strategy must have one card.

#### Strategies
- `ARB_SCANNER`
- `WEATHER_ARB`
- `LATENCY_ARB`
- `BROWNIAN_SNIPER`
- `PAIR_COST`
- `OPP_SCORER`
- `NO_SCANNER`
- `CONVERGENCE`
- `NEWS_STRAT`

#### Strategy Card

##### Component
`StrategyCard`

##### Purpose
Provide a high-signal summary of one strategy.

##### Card structure

**Header**
- strategy name
- mode badge
- status badge

Example:
- `ARB_SCANNER`
- `PAPER`
- `RUNNING`

**Main metrics**
- capital
- P&L in €
- P&L in %
- win rate
- Sharpe

**Risk metrics**
- drawdown
- total trades
- open trades

**Visual element**
- small sparkline of recent P&L evolution

**Footer**
- last activity timestamp / relative time

**CTA**
- `View Details`

##### Required data

```ts
{
  name: string
  mode: "PAPER" | "LIVE"
  status: "RUNNING" | "PAUSED" | "STOPPED" | "IDLE"
  capital_eur: number
  pnl_eur: number
  pnl_percent: number
  win_rate_percent: number
  sharpe: number
  drawdown_percent: number
  trades_total: number
  trades_open: number
  last_activity_at: string
  sparkline: Array<{ timestamp: string; pnl_eur: number }>
}
```

##### Visual states

**Mode colors**
- `PAPER` → blue
- `LIVE` → green

**Status colors**
- `RUNNING` → green
- `PAUSED` → yellow
- `STOPPED` → red
- `IDLE` → gray

**Risk hint**
If drawdown is elevated or kill-switch threshold is near, show a warning badge or border state.

##### Extra note
Cards should prioritize readability.  
Do **not** pack too many metrics into a single card.

---

### 6.5 Strategy Analysis

#### Component group
`StrategyAnalysisSection`

#### Purpose
Allow direct comparison between strategies.

This block must contain:
1. `Strategy Leaderboard`
2. `Strategy Comparison Table`

#### Strategy Leaderboard

##### Component
`StrategyLeaderboard`

##### Type
Horizontal bar chart

##### Purpose
Rank strategies from best to worst.

##### Default metric
`P&L %`

##### Required inputs

```ts
Array<{
  strategy: string
  pnl_percent: number
}>
```

##### Optional enhancement
Later allow switching metric:
- `P&L %`
- `Sharpe`
- `Win Rate`
- `Drawdown`

#### Strategy Comparison Table

##### Component
`StrategyTable`

##### Purpose
Precise cross-strategy comparison.

##### Columns
- `Strategy`
- `Mode`
- `Status`
- `Capital`
- `Open Positions`
- `Trades`
- `P&L €`
- `P&L %`
- `Win Rate`
- `Sharpe`
- `Drawdown`
- `Promotion Status`
- `Last Activity`

##### Sorting
Must support sort on at least:
- `P&L €`
- `P&L %`
- `Sharpe`
- `Drawdown`
- `Win Rate`
- `Last Activity`

##### Filtering
Optional but recommended:
- mode (`PAPER` / `LIVE`)
- status
- promotion status

##### Required data shape

```ts
Array<{
  name: string
  mode: "PAPER" | "LIVE"
  status: "RUNNING" | "PAUSED" | "STOPPED" | "IDLE"
  capital_eur: number
  open_positions: number
  trades_total: number
  pnl_eur: number
  pnl_percent: number
  win_rate_percent: number
  sharpe: number
  drawdown_percent: number
  promotion_status: "NOT_ELIGIBLE" | "NEAR_ELIGIBLE" | "ELIGIBLE" | "PROMOTED" | "REJECTED"
  last_activity_at: string
}>
```

---

### 6.6 Execution

#### Component group
`ExecutionSection`

#### Purpose
Show what the system is doing **right now**.

This block must contain:
1. `Live Trade Feed`
2. `Open Positions Table`

Optional later:
3. `Trade History`

#### Live Trade Feed

##### Component
`TradeFeed`

##### Purpose
Provide a real-time terminal-like feed of events.

##### Display per event
- timestamp
- strategy
- market
- side (`YES` / `NO`)
- event type (`OPEN`, `CLOSE`, `PARTIAL`, `STOP`, `RISK_ACTION`)
- size
- entry/exit price
- realized P&L if applicable

##### Example

```text
[12:03:14] NEWS_STRAT
OPEN YES
BTC above 90k before April 1st
Price: 0.63
Size: 120€
```

##### Color logic
- `OPEN` → blue
- `CLOSE_WIN` → green
- `CLOSE_LOSS` → red
- `RISK_ACTION` / `STOP` → orange

##### Required data shape

```ts
Array<{
  id: string
  timestamp: string
  strategy: string
  market: string
  side: "YES" | "NO"
  event_type: "OPEN" | "CLOSE" | "PARTIAL" | "STOP" | "RISK_ACTION"
  price: number
  size_eur: number
  realized_pnl_eur?: number
}>
```

##### UX note
This should feel alive, but should not be visually noisy.

#### Open Positions Table

##### Component
`OpenPositionsTable`

##### Purpose
Show current exposure.

##### Columns
- `Strategy`
- `Market`
- `Side`
- `Entry Price`
- `Current Price`
- `Size €`
- `Unrealized P&L`
- `Duration`
- `Mode`
- `Risk State` (optional but recommended)

##### Required data shape

```ts
Array<{
  id: string
  strategy: string
  market: string
  side: "YES" | "NO"
  entry_price: number
  current_price: number
  size_eur: number
  unrealized_pnl_eur: number
  duration_seconds: number
  mode: "PAPER" | "LIVE"
  risk_state?: "NORMAL" | "WARNING" | "DANGER"
}>
```

##### Sorting
Recommended:
- unrealized P&L
- duration
- size
- strategy

#### Optional later — Trade History

##### Component
`TradeHistoryTable`

##### Purpose
Historical analysis.

##### Columns
- `Time`
- `Strategy`
- `Market`
- `Side`
- `Entry`
- `Exit`
- `P&L`
- `Duration`
- `Mode`

##### Filters
- strategy
- mode
- open/closed
- date range
- winning/losing

This can be phase 2 if needed.

---

### 6.7 Risk Management

#### Component group
`RiskManagementSection`

#### Purpose
Make risk visible and decision-ready.

This block must contain:
1. `Risk Overview`
2. `Promotion Gate`

Recommended later:
3. `Strategy Risk Heatmap`

#### Risk Overview

##### Component
`RiskPanel`

##### Display key metrics
- global drawdown
- worst strategy drawdown
- active warnings count
- global kill switch state
- open exposure
- open positions usage (`current / max`)

##### Required data shape

```ts
{
  global_drawdown_percent: number
  worst_strategy_drawdown_percent: number
  active_warnings_count: number
  global_kill_switch_state: "NORMAL" | "ARMED" | "TRIGGERED"
  open_exposure_eur: number
  open_positions_count: number
  max_open_positions: number
}
```

#### Promotion Gate

##### Component
`PromotionGateTable`

##### Purpose
Show which strategies are close to moving from paper to live.

##### Per-strategy metrics to show
- `Win Rate`
- `Sharpe`
- `Drawdown`
- `Trades Sample Size`
- `Paper Duration`
- `Risk Events`
- `Promotion Status`

##### Promotion status values
- `NOT_ELIGIBLE`
- `NEAR_ELIGIBLE`
- `ELIGIBLE`
- `PROMOTED`
- `REJECTED`

##### Required data shape

```ts
Array<{
  strategy: string
  win_rate_percent: number
  sharpe: number
  drawdown_percent: number
  trade_sample_size: number
  paper_days_completed: number
  paper_days_target: number
  risk_events_count: number
  promotion_status: "NOT_ELIGIBLE" | "NEAR_ELIGIBLE" | "ELIGIBLE" | "PROMOTED" | "REJECTED"
}>
```

##### UX note
This section is important because it turns the page into a **decision dashboard**, not just a monitoring dashboard.

#### Recommended later — Strategy Risk Heatmap

##### Component
`StrategyRiskHeatmap`

##### Purpose
High-level risk scanning across all strategies.

##### Matrix dimensions
Strategies × risk criteria

##### Example risk criteria
- daily loss
- total drawdown
- open exposure
- inactivity
- unusual loss streak
- signal staleness
- agent stale
- confidence drop

##### Cell colors
- green
- yellow
- orange
- red

This is phase 2, not mandatory for the first version.

---

### 6.8 System Health / Infra

#### Component group
`SystemHealthSection`

#### Purpose
Confirm whether displayed trading data is trustworthy and up to date.

This block must contain:
1. `Agent Health Panel`
2. `Event Queue Status`
3. `Signal Freshness`

#### Agent Health Panel

##### Component
`AgentHealthPanel`

##### Purpose
Show status of critical components.

##### Items to display
Can include both strategies and infra agents/components.

Suggested list:
- `ARB_SCANNER`
- `WEATHER_ARB`
- `LATENCY_ARB`
- `BROWNIAN_SNIPER`
- `PAIR_COST`
- `OPP_SCORER`
- `NO_SCANNER`
- `CONVERGENCE`
- `NEWS_STRAT`
- `EVENT_BUS`
- `EXECUTION_ENGINE`
- `RISK_GUARDIAN`
- `PROMOTION_GATE`
- `PRICE_FEEDS`
- `NEWS_INGESTION`
- `WALLET_MONITOR`

##### Health states
- `HEALTHY`
- `DELAYED`
- `STALE`
- `ERROR`
- `OFFLINE`

##### Required data shape

```ts
Array<{
  name: string
  type: "STRATEGY" | "AGENT" | "SERVICE"
  status: "HEALTHY" | "DELAYED" | "STALE" | "ERROR" | "OFFLINE"
  last_activity_at?: string
  last_heartbeat_at?: string
}>
```

#### Event Queue Status

##### Component
`EventQueueStatus`

##### Purpose
Monitor processing flow and bottlenecks.

##### Metrics to display
- pending events
- average processing time
- max delay
- dropped events
- retried events

##### Required data shape

```ts
{
  pending_events: number
  avg_processing_ms: number
  max_delay_ms: number
  dropped_events: number
  retried_events: number
}
```

#### Signal Freshness

##### Component
`SignalStatusPanel`

##### Purpose
Verify the freshness of key external/internal signals.

##### Signals to show
- BTC price feed
- ETH price feed
- NOAA forecast
- news ingestion
- wallet convergence

##### Display
For each source:
- name
- freshness status
- last update time

##### Required data shape

```ts
Array<{
  signal_name: string
  status: "FRESH" | "AGING" | "STALE" | "ERROR"
  last_updated_at: string
}>
```

##### UX note
Freshness should be instantly readable.  
A stale data source should be visually obvious.

---

## 7) Detail page specification

### 7.1 Strategy detail page

#### Route
`/dashboard/polymarket/strategy/:name`

#### Purpose
Deep dive into one strategy.

#### Required sections
1. `Strategy Overview`
2. `Equity Curve`
3. `Trade History`
4. `Open Positions`
5. `Risk Diagnostics`
6. `Promotion Gate Status`
7. `Logs / Activity`
8. `Signals Used`

#### Strategy Overview content
- strategy name
- mode
- status
- capital
- P&L €
- P&L %
- win rate
- Sharpe
- drawdown
- trade counts
- last activity

#### Trade History content
Same logic as global history but filtered to one strategy.

#### Risk Diagnostics content
- daily loss
- total drawdown
- streak metrics
- warning states
- kill switch proximity

#### Signals Used content
Display the signals relevant to the strategy.

Example:
- `WEATHER_ARB` → NOAA
- `LATENCY_ARB` → Binance BTC/ETH feed
- `CONVERGENCE` → pro wallet clustering
- `NEWS_STRAT` → news impact feed

---

## 8) Visual language and color system

### General theme
Must match the current dashboard.

### Important semantic colors
Use color primarily to communicate:
- risk
- urgency
- operational state

Do **not** rely only on color for P&L.

### Recommended semantics

#### Mode
- `PAPER` → blue
- `LIVE` → green

#### Status
- `RUNNING` → green
- `PAUSED` → yellow
- `STOPPED` → red
- `IDLE` → gray

#### Risk
- `NORMAL` → green
- `WATCH` → yellow
- `WARNING` → orange
- `DANGER` → red

#### Infra
- `HEALTHY` → green
- `DELAYED` → yellow
- `STALE` → orange
- `ERROR` / `OFFLINE` → red

---

## 9) Important implementation rules

### Rule 1 — Separate paper and live clearly
The UI must never make paper and live performance ambiguous.

At minimum:
- badge on each strategy
- mode column in tables
- explicit counts in header

Recommended:
- allow filtering by mode

### Rule 2 — Keep top of page summary-focused
The first screen must answer:
- is system healthy?
- is system profitable?
- is risk acceptable?

### Rule 3 — Do not overbuild version 1
Version 1 should prioritize:
- readability
- structure
- correctness of data mapping

Not every advanced diagnostic needs to ship on day one.

### Rule 4 — Components should be data-driven
The frontend should be built so that components can consume backend payloads cleanly.

Avoid hardcoded strategy assumptions beyond:
- display order
- labels
- route generation

### Rule 5 — Build for future scalability
Current system has 9 strategies, but component design should not assume it will stay at 9 forever.

---

## 10) Recommended data contract

Below is a suggested high-level payload shape for the main page.

```ts
type PolymarketDashboardData = {
  header: {
    system_status: "RUNNING" | "PAUSED" | "DEGRADED" | "HALTED"
    global_risk_state: "NORMAL" | "ELEVATED" | "WARNING" | "KILL_SWITCH" | "HALTED"
    paper_count: number
    live_count: number
  }

  global_kpis: {
    health_score: number
    health_label: string
    total_pnl_eur: number
    total_pnl_percent: number
    today_pnl_eur: number
    max_drawdown_percent: number
    global_sharpe: number
    open_positions_count: number
    max_open_positions: number
    active_strategies_count: number
    total_strategies_count: number
  }

  charts: {
    equity_curve: Array<{
      timestamp: string
      pnl_eur: number
    }>
    drawdown_curve: Array<{
      timestamp: string
      drawdown_percent: number
    }>
  }

  strategies: Array<{
    name: string
    mode: "PAPER" | "LIVE"
    status: "RUNNING" | "PAUSED" | "STOPPED" | "IDLE"
    capital_eur: number
    pnl_eur: number
    pnl_percent: number
    win_rate_percent: number
    sharpe: number
    drawdown_percent: number
    trades_total: number
    trades_open: number
    open_positions: number
    promotion_status: "NOT_ELIGIBLE" | "NEAR_ELIGIBLE" | "ELIGIBLE" | "PROMOTED" | "REJECTED"
    last_activity_at: string
    sparkline: Array<{
      timestamp: string
      pnl_eur: number
    }>
  }>

  live_trade_feed: Array<{
    id: string
    timestamp: string
    strategy: string
    market: string
    side: "YES" | "NO"
    event_type: "OPEN" | "CLOSE" | "PARTIAL" | "STOP" | "RISK_ACTION"
    price: number
    size_eur: number
    realized_pnl_eur?: number
  }>

  open_positions: Array<{
    id: string
    strategy: string
    market: string
    side: "YES" | "NO"
    entry_price: number
    current_price: number
    size_eur: number
    unrealized_pnl_eur: number
    duration_seconds: number
    mode: "PAPER" | "LIVE"
    risk_state?: "NORMAL" | "WARNING" | "DANGER"
  }>

  risk: {
    global_drawdown_percent: number
    worst_strategy_drawdown_percent: number
    active_warnings_count: number
    global_kill_switch_state: "NORMAL" | "ARMED" | "TRIGGERED"
    open_exposure_eur: number
    open_positions_count: number
    max_open_positions: number
  }

  promotion_gate: Array<{
    strategy: string
    win_rate_percent: number
    sharpe: number
    drawdown_percent: number
    trade_sample_size: number
    paper_days_completed: number
    paper_days_target: number
    risk_events_count: number
    promotion_status: "NOT_ELIGIBLE" | "NEAR_ELIGIBLE" | "ELIGIBLE" | "PROMOTED" | "REJECTED"
  }>

  agents: Array<{
    name: string
    type: "STRATEGY" | "AGENT" | "SERVICE"
    status: "HEALTHY" | "DELAYED" | "STALE" | "ERROR" | "OFFLINE"
    last_activity_at?: string
    last_heartbeat_at?: string
  }>

  queue: {
    pending_events: number
    avg_processing_ms: number
    max_delay_ms: number
    dropped_events: number
    retried_events: number
  }

  signals: Array<{
    signal_name: string
    status: "FRESH" | "AGING" | "STALE" | "ERROR"
    last_updated_at: string
  }>
}
```

---

## 11) Build priority

If implementation must be phased, use this order.

### Phase 1 — essential
1. `Header`
2. `Global KPI Strip`
3. `Performance Charts`
4. `Strategy Cards Grid`
5. `Open Positions Table`
6. `Live Trade Feed`

### Phase 2 — comparison + decision
7. `Strategy Leaderboard`
8. `Strategy Comparison Table`
9. `Risk Overview`
10. `Promotion Gate`

### Phase 3 — diagnostics / infra
11. `Agent Health Panel`
12. `Event Queue Status`
13. `Signal Freshness`
14. `Strategy Detail Page`

### Phase 4 — advanced
15. `Trade History`
16. `Strategy Risk Heatmap`
17. `Alert Center`
18. `Worst Offender Panel`

---

## 12) Optional premium additions

These are not mandatory for V1 but would significantly improve the product.

### A. Alert Center
Dedicated panel listing current alerts.

Examples:
- `LATENCY_ARB feed stale for 43s`
- `NEWS_STRAT generated 4 losing trades in a row`
- `Global queue above normal threshold`
- `WEATHER_ARB waiting on NOAA refresh`

### B. Worst Offender Panel
A compact block showing:
- worst drawdown strategy
- most inactive strategy
- highest exposure strategy
- most profitable strategy

### C. Readiness State
More explicit state labels per strategy:
- `BUILDING`
- `LEARNING`
- `READY`
- `LIVE`
- `GUARDED`
- `HALTED`

This is more product-friendly than simple paper/live/stopped.

---

## 13) Final implementation intent

The page must tell this story very clearly:

1. **Is the system healthy?**
2. **Is it making money?**
3. **Where is performance coming from?**
4. **Where is the risk?**
5. **What is the system doing right now?**
6. **Which strategies are ready for live trading?**

If the UI makes these answers obvious at a glance, then the page is successful.

---

## 14) Short instruction for coding AI

Use this spec as the source of truth to build the `Polymarket` dashboard page and its related sub-pages.

Priorities:
- clean hierarchy
- componentized architecture
- readable trading-oriented UI
- clear separation between paper and live
- data-driven components
- scalable structure for more strategies in the future

The final result should feel like a **professional automated trading control center**, not a generic admin page.
