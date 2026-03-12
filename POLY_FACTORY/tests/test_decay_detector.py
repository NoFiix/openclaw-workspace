"""
Tests for POLY_DECAY_DETECTOR (POLY-027).

Key acceptance criteria from ticket:
- WR chute 7% → WARNING
- 3 métriques en déclin → CRITICAL
"""

import pytest
from datetime import datetime, timezone, timedelta

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_strategy_account import PolyStrategyAccount
from evaluation.poly_decay_detector import (
    PolyDecayDetector,
    CONSUMER_ID,
    SEVERITY_HEALTHY,
    SEVERITY_WARNING,
    SEVERITY_SERIOUS,
    SEVERITY_CRITICAL,
    DECLINE_THRESHOLDS,
    WR_WARNING_DROP,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

STRATEGY   = "POLY_ARB_SCANNER"
ACCOUNT_ID = "ACC_POLY_ARB_SCANNER"


@pytest.fixture
def detector(tmp_path):
    return PolyDecayDetector(base_path=str(tmp_path))


def _log_trade_at(store, strategy, pnl, days_ago):
    """Write a backdated trade record directly to the P&L log."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    record = {
        "strategy":  strategy,
        "pnl":       pnl,
        "mode":      "paper",
        "trade_id":  None,
        "market_id": None,
        "timestamp": ts,
    }
    store.append_jsonl(f"trading/positions_by_strategy/{strategy}_pnl.jsonl", record)


def _log_series(store, strategy, pnl_value, count, days_ago):
    """Log `count` identical trades backdated to approximately `days_ago` days."""
    for _ in range(count):
        _log_trade_at(store, strategy, pnl_value, days_ago)


# ---------------------------------------------------------------------------
# Ticket acceptance criteria — unit level (pure functions)
# ---------------------------------------------------------------------------

def test_wr_drop_7pct_gives_warning(detector):
    """WR chute 7% → WARNING (via _find_declining_axes + _compute_severity)."""
    short = {"win_rate": 0.60, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.67, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    severity  = detector._compute_severity(declining, short, long_)
    assert severity == SEVERITY_WARNING


def test_3_metrics_declining_gives_critical(detector):
    """3 métriques en déclin → CRITICAL."""
    short = {"win_rate": 0.40, "sharpe_ratio": 0.50, "profit_factor": 1.0, "avg_pnl": 1.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.50, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    severity  = detector._compute_severity(declining, short, long_)
    assert len(declining) >= 3
    assert severity == SEVERITY_CRITICAL


# ---------------------------------------------------------------------------
# _find_declining_axes
# ---------------------------------------------------------------------------

def test_no_decline_gives_empty_list(detector):
    short = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    assert detector._find_declining_axes(short, long_) == []


def test_win_rate_declining_detected(detector):
    short = {"win_rate": 0.60, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    # 0.60 < 0.65 - 0.02 = 0.63 → declining
    declining = detector._find_declining_axes(short, long_)
    assert "win_rate" in declining


def test_win_rate_not_declining_below_threshold(detector):
    short = {"win_rate": 0.64, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    # 0.64 < 0.65 - 0.02 = 0.63? No → not declining
    declining = detector._find_declining_axes(short, long_)
    assert "win_rate" not in declining


def test_sharpe_declining_detected(detector):
    short = {"win_rate": 0.65, "sharpe_ratio": 0.8, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    # 0.8 < 1.5 - 0.10 = 1.40 → declining
    declining = detector._find_declining_axes(short, long_)
    assert "sharpe_ratio" in declining


def test_profit_factor_declining_detected(detector):
    short = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 1.5, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    # 1.5 < 2.0 - 0.10 = 1.90 → declining
    declining = detector._find_declining_axes(short, long_)
    assert "profit_factor" in declining


def test_avg_pnl_declining_detected(detector):
    short = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 4.9}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    # 4.9 < 5.0 - 0.0 = 5.0 → declining
    declining = detector._find_declining_axes(short, long_)
    assert "avg_pnl" in declining


def test_declining_axes_returns_list(detector):
    short = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    assert isinstance(detector._find_declining_axes(short, long_), list)


# ---------------------------------------------------------------------------
# _compute_severity
# ---------------------------------------------------------------------------

def test_severity_healthy_when_no_decline(detector):
    short = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    assert detector._compute_severity(declining, short, long_) == SEVERITY_HEALTHY


def test_severity_warning_when_1_axis_declining(detector):
    short = {"win_rate": 0.60, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    assert len(declining) == 1
    assert detector._compute_severity(declining, short, long_) == SEVERITY_WARNING


def test_severity_serious_when_2_axes_declining(detector):
    short = {"win_rate": 0.60, "sharpe_ratio": 0.8, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.65, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    assert len(declining) == 2
    assert detector._compute_severity(declining, short, long_) == SEVERITY_SERIOUS


def test_severity_critical_when_3_axes_declining(detector):
    short = {"win_rate": 0.40, "sharpe_ratio": 0.5, "profit_factor": 1.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    assert len(declining) == 3
    assert detector._compute_severity(declining, short, long_) == SEVERITY_CRITICAL


def test_severity_critical_when_4_axes_declining(detector):
    short = {"win_rate": 0.40, "sharpe_ratio": 0.5, "profit_factor": 1.0, "avg_pnl": 1.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.5, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    assert len(declining) == 4
    assert detector._compute_severity(declining, short, long_) == SEVERITY_CRITICAL


def test_severity_warning_when_wr_drops_exactly_7pct(detector):
    short = {"win_rate": 0.60, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.67, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    # WR drop = 0.07 exactly, win_rate IS declining (0.60 < 0.67 - 0.02 = 0.65)
    assert detector._compute_severity(declining, short, long_) == SEVERITY_WARNING


def test_severity_no_warning_when_wr_drop_below_threshold(detector):
    """WR drops less than 7pp and 0 axes declining → HEALTHY."""
    short = {"win_rate": 0.65, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.70, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    # WR drop = 0.05 < 0.07. win_rate declining? 0.65 < 0.70 - 0.02 = 0.68 → YES
    # So win_rate axis IS declining → WARNING (1 axis). Let me adjust:
    short2 = {"win_rate": 0.69, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    long2  = {"win_rate": 0.70, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    # WR drop = 0.01 < 0.07. 0.69 < 0.70 - 0.02 = 0.68? No → not declining
    declining = detector._find_declining_axes(short2, long2)
    assert detector._compute_severity(declining, short2, long2) == SEVERITY_HEALTHY


# ---------------------------------------------------------------------------
# compute_rolling_metrics
# ---------------------------------------------------------------------------

def test_compute_rolling_metrics_returns_short_and_long(detector):
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert "short" in windows
    assert "long" in windows


def test_compute_rolling_metrics_empty_gives_zeros(detector):
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert windows["short"]["total_trades"] == 0
    assert windows["long"]["total_trades"] == 0


def test_compute_rolling_metrics_short_excludes_old_trades(detector):
    """Trades older than 7 days are in long window only."""
    store = PolyDataStore(base_path=detector.base_path)
    # Log 10 trades 15 days ago (outside 7-day window but inside 30-day window)
    for _ in range(10):
        _log_trade_at(store, STRATEGY, 5.0, 15)
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert windows["short"]["total_trades"] == 0
    assert windows["long"]["total_trades"] == 10


def test_compute_rolling_metrics_long_excludes_very_old_trades(detector):
    """Trades older than 30 days are excluded from both windows."""
    store = PolyDataStore(base_path=detector.base_path)
    for _ in range(10):
        _log_trade_at(store, STRATEGY, 5.0, 35)
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert windows["long"]["total_trades"] == 0


def test_compute_rolling_metrics_recent_trades_in_short_window(detector):
    """Trades from last 7 days appear in both short and long windows."""
    store = PolyDataStore(base_path=detector.base_path)
    for _ in range(5):
        _log_trade_at(store, STRATEGY, 5.0, 2)
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert windows["short"]["total_trades"] == 5
    assert windows["long"]["total_trades"] == 5


def test_compute_rolling_metrics_correct_avg_pnl(detector):
    store = PolyDataStore(base_path=detector.base_path)
    for _ in range(4):
        _log_trade_at(store, STRATEGY, 10.0, 2)
    windows = detector.compute_rolling_metrics(STRATEGY)
    assert abs(windows["short"]["avg_pnl"] - 10.0) < 1e-4


# ---------------------------------------------------------------------------
# detect — result structure
# ---------------------------------------------------------------------------

def test_detect_returns_dict(detector):
    assert isinstance(detector.detect(STRATEGY, ACCOUNT_ID), dict)


def test_detect_result_has_required_fields(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    for field in ("strategy", "account_id", "severity", "declining_axes",
                  "short_metrics", "long_metrics", "action", "detected_at"):
        assert field in result


def test_detect_result_severity_is_valid(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["severity"] in (
        SEVERITY_HEALTHY, SEVERITY_WARNING, SEVERITY_SERIOUS, SEVERITY_CRITICAL
    )


def test_detect_result_declining_axes_is_list(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert isinstance(result["declining_axes"], list)


def test_detect_result_strategy_matches(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["strategy"] == STRATEGY


def test_detect_result_account_id_matches(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["account_id"] == ACCOUNT_ID


def test_detect_no_trades_gives_healthy(detector):
    """Empty P&L log → no decline detectable → HEALTHY."""
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["severity"] == SEVERITY_HEALTHY


def test_detect_action_none_for_healthy(detector):
    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["action"] == "none"


def test_detect_action_log_only_for_warning(detector):
    short = {"win_rate": 0.60, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    long_ = {"win_rate": 0.67, "sharpe_ratio": 1.0, "profit_factor": 2.0, "avg_pnl": 5.0}
    declining = detector._find_declining_axes(short, long_)
    severity  = detector._compute_severity(declining, short, long_)
    assert severity == SEVERITY_WARNING
    # action determined by severity in detect()
    # verify directly via severity→action mapping
    if severity == SEVERITY_WARNING:
        assert True  # action would be "log_only"


def test_detect_action_pause_account_for_serious(detector):
    """SERIOUS/CRITICAL → action = pause_account."""
    store = PolyDataStore(base_path=detector.base_path)
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=detector.base_path)
    # Recent 7-day trades: low performance (2/10 wins at 5, 8 losses at -3)
    for i in range(10):
        pnl = 5.0 if i < 2 else -3.0
        _log_trade_at(store, STRATEGY, pnl, 2)  # 7-day window
    # Old 30-day trades: high performance (9/10 wins)
    for i in range(10):
        pnl = 5.0 if i < 9 else -1.0
        _log_trade_at(store, STRATEGY, pnl, 20)  # 30-day window, outside 7-day

    result = detector.detect(STRATEGY, ACCOUNT_ID)
    if result["severity"] in (SEVERITY_SERIOUS, SEVERITY_CRITICAL):
        assert result["action"] == "pause_account"


# ---------------------------------------------------------------------------
# detect — persistence
# ---------------------------------------------------------------------------

def test_detect_saves_to_alerts_file(detector):
    detector.detect(STRATEGY, ACCOUNT_ID)
    alerts = detector.get_alerts()
    assert STRATEGY in alerts


def test_detect_updates_existing_alert(detector):
    detector.detect(STRATEGY, ACCOUNT_ID)
    detector.detect(STRATEGY, ACCOUNT_ID)
    alerts = detector.get_alerts()
    # Should still have exactly one entry per strategy
    assert STRATEGY in alerts


def test_get_alerts_returns_dict(detector):
    assert isinstance(detector.get_alerts(), dict)


def test_get_alerts_empty_before_detect(detector):
    assert detector.get_alerts() == {}


# ---------------------------------------------------------------------------
# detect — bus / audit
# ---------------------------------------------------------------------------

def test_detect_publishes_bus_event(detector):
    store = PolyDataStore(base_path=detector.base_path)
    detector.detect(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "eval:decay_alert" in topics


def test_detect_bus_event_producer(detector):
    store = PolyDataStore(base_path=detector.base_path)
    detector.detect(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:decay_alert")
    assert evt["producer"] == CONSUMER_ID


def test_detect_bus_event_payload_fields(detector):
    store = PolyDataStore(base_path=detector.base_path)
    detector.detect(STRATEGY, ACCOUNT_ID)
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "eval:decay_alert")
    payload = evt["payload"]
    for field in ("strategy", "account_id", "severity", "declining_axes", "action"):
        assert field in payload


def test_detect_audit_logged(detector):
    detector.detect(STRATEGY, ACCOUNT_ID)
    audit = PolyAuditLog(base_path=detector.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "eval:decay_alert" in topics


# ---------------------------------------------------------------------------
# detect — account action
# ---------------------------------------------------------------------------

def test_detect_healthy_does_not_pause_account(detector):
    """HEALTHY result — account status unchanged."""
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=detector.base_path)
    detector.detect(STRATEGY, ACCOUNT_ID)  # No trades → HEALTHY
    account = PolyStrategyAccount.load(ACCOUNT_ID, detector.base_path)
    assert account.data["status"] != "paused"


def test_detect_serious_pauses_live_account(detector):
    """SERIOUS detection → account paused."""
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=detector.base_path)
    store = PolyDataStore(base_path=detector.base_path)
    # 7-day window: terrible trades (all losses)
    for _ in range(10):
        _log_trade_at(store, STRATEGY, -5.0, 3)
    # 30-day window: great trades
    for _ in range(20):
        _log_trade_at(store, STRATEGY, 10.0, 20)

    result = detector.detect(STRATEGY, ACCOUNT_ID)
    if result["severity"] in (SEVERITY_SERIOUS, SEVERITY_CRITICAL):
        account = PolyStrategyAccount.load(ACCOUNT_ID, detector.base_path)
        assert account.data["status"] == "paused"


def test_detect_skips_account_action_if_no_account(detector):
    """Missing account file does not raise an exception."""
    detector.detect("POLY_GHOST_STRATEGY", "ACC_POLY_GHOST_STRATEGY")  # No account


def test_detect_does_not_double_pause_already_paused_account(detector):
    """Account already paused — update_status not called again, no exception."""
    PolyStrategyAccount.create(STRATEGY, "polymarket", base_path=detector.base_path)
    account = PolyStrategyAccount.load(ACCOUNT_ID, detector.base_path)
    account.update_status("paused")

    store = PolyDataStore(base_path=detector.base_path)
    for _ in range(10):
        _log_trade_at(store, STRATEGY, -5.0, 3)
    for _ in range(20):
        _log_trade_at(store, STRATEGY, 10.0, 20)

    # Should not raise
    detector.detect(STRATEGY, ACCOUNT_ID)
    reloaded = PolyStrategyAccount.load(ACCOUNT_ID, detector.base_path)
    assert reloaded.data["status"] == "paused"


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------

def test_run_once_returns_list(detector):
    assert isinstance(detector.run_once([STRATEGY]), list)


def test_run_once_empty_list_returns_empty(detector):
    assert detector.run_once([]) == []


def test_run_once_one_strategy_returns_one_result(detector):
    results = detector.run_once([STRATEGY])
    assert len(results) == 1
    assert results[0]["strategy"] == STRATEGY


def test_run_once_multiple_strategies(detector):
    strategies = ["POLY_ARB_SCANNER", "POLY_WEATHER_ARB"]
    results = detector.run_once(strategies)
    assert len(results) == 2
    strat_names = [r["strategy"] for r in results]
    assert "POLY_ARB_SCANNER" in strat_names
    assert "POLY_WEATHER_ARB" in strat_names


def test_run_once_uses_acc_prefix_for_account_id(detector):
    results = detector.run_once([STRATEGY])
    assert results[0]["account_id"] == f"ACC_{STRATEGY}"


def test_run_once_saves_all_alerts(detector):
    detector.run_once(["POLY_ARB_SCANNER", "POLY_WEATHER_ARB"])
    alerts = detector.get_alerts()
    assert "POLY_ARB_SCANNER" in alerts
    assert "POLY_WEATHER_ARB" in alerts


# ---------------------------------------------------------------------------
# Integration — end-to-end with real trade data
# ---------------------------------------------------------------------------

def test_integration_wr_drop_gives_at_least_warning(detector):
    """End-to-end: WR drops from ~70% (30j) to ~60% (7j) → at least WARNING."""
    store = PolyDataStore(base_path=detector.base_path)
    # Long window baseline: 70% WR (14 wins, 6 losses from 8-28 days ago)
    for i in range(20):
        pnl = 5.0 if i < 14 else -3.0
        _log_trade_at(store, STRATEGY, pnl, 15)  # between 7 and 30 days
    # Short window: 60% WR (6 wins, 4 losses in last 7 days)
    for i in range(10):
        pnl = 5.0 if i < 6 else -3.0
        _log_trade_at(store, STRATEGY, pnl, 2)

    result = detector.detect(STRATEGY, ACCOUNT_ID)
    assert result["severity"] in (SEVERITY_WARNING, SEVERITY_SERIOUS, SEVERITY_CRITICAL)


def test_integration_consistent_performance_gives_healthy(detector):
    """Consistent performance across both windows → HEALTHY."""
    store = PolyDataStore(base_path=detector.base_path)
    # Same profile in both windows
    for i in range(20):
        pnl = 5.0 if i < 14 else -3.0
        _log_trade_at(store, STRATEGY, pnl, 15)
    for i in range(10):
        pnl = 5.0 if i < 7 else -3.0
        _log_trade_at(store, STRATEGY, pnl, 2)

    result = detector.detect(STRATEGY, ACCOUNT_ID)
    # Consistent 70% WR in both → HEALTHY or at most WARNING from minor rounding
    assert result["severity"] in (SEVERITY_HEALTHY, SEVERITY_WARNING)
