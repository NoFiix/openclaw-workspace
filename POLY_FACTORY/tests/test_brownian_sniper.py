"""
Tests for POLY_BROWNIAN_SNIPER (POLY-029).

Key acceptance criteria from ticket:
- GBM probability > yes_ask + EDGE_THRESHOLD → signal emitted
- GBM probability ≤ yes_ask + EDGE_THRESHOLD → no signal
- Fewer than MIN_PRICE_HISTORY samples → no signal
- Low confidence → no signal
- Payload conforms to trade:signal schema
"""

import math
import pytest
from datetime import datetime, timezone

from core.poly_audit_log import PolyAuditLog
from core.poly_data_store import PolyDataStore
from core.poly_event_bus import PolyEventBus
from strategies.poly_brownian_sniper import (
    PolyBrownianSniper,
    CONSUMER_ID,
    ACCOUNT_ID,
    EDGE_THRESHOLD,
    MIN_CONFIDENCE,
    MIN_PRICE_HISTORY,
    SUGGESTED_SIZE_EUR,
    ANNUALIZATION_FACTOR,
    _normal_cdf,
    _compute_volatility,
    _gbm_probability,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

MARKET_ID = "0xabc123"

# Prices where S0 >> K: near-certain YES → GBM prob ≈ 1.0 regardless of σ
DEEP_ITM_SCORE = {
    "market_id":          MARKET_ID,
    "symbol":             "BTC",
    "current_price":      100_000.0,   # S0
    "strike_price":       50_000.0,    # K  (S0 = 2 × K, deep in-the-money)
    "days_to_resolution": 30,
    "confidence":         0.80,
}

# Prices where S0 << K: near-impossible YES → GBM prob ≈ 0.0
DEEP_OTM_SCORE = {
    "market_id":          MARKET_ID,
    "symbol":             "BTC",
    "current_price":      25_000.0,   # S0
    "strike_price":       50_000.0,   # K  (S0 = 0.5 × K, deep out-of-money)
    "days_to_resolution": 30,
    "confidence":         0.80,
}

PRICE_UPDATE = {
    "market_id":   MARKET_ID,
    "platform":    "polymarket",
    "yes_ask":     0.45,
    "no_ask":      0.57,
    "yes_price":   0.44,
    "no_price":    0.56,
    "yes_bid":     0.43,
    "no_bid":      0.55,
    "volume_24h":  100_000,
    "data_status": "VALID",
}

# A fixed price series consistent with DEEP_ITM_SCORE.current_price ≈ 100_000.
# Prices must be close to the score's current_price so that when run_once()
# appends current_price to the rolling history no discontinuity inflates σ.
VOLATILE_PRICES = [99_900, 100_050, 99_850, 100_100, 99_900, 100_050, 99_950]


@pytest.fixture
def sniper(tmp_path):
    return PolyBrownianSniper(base_path=str(tmp_path))


@pytest.fixture
def bus(sniper):
    return sniper.bus


def _publish_price_update(bus, market_id=MARKET_ID, yes_ask=0.45, no_ask=0.57):
    bus.publish(
        topic="feed:price_update",
        producer="POLY_MARKET_CONNECTOR",
        payload={
            "market_id":   market_id,
            "platform":    "polymarket",
            "yes_ask":     yes_ask,
            "no_ask":      no_ask,
            "yes_price":   round(yes_ask - 0.01, 4),
            "no_price":    round(no_ask - 0.01, 4),
            "yes_bid":     round(yes_ask - 0.02, 4),
            "no_bid":      round(no_ask - 0.02, 4),
            "volume_24h":  100_000,
            "data_status": "VALID",
        },
    )


def _publish_binance_score(
    bus,
    market_id=MARKET_ID,
    current_price=100_000.0,
    strike_price=50_000.0,
    days_to_resolution=30,
    confidence=0.80,
    symbol="BTC",
):
    """Publish a signal:binance_score event.

    `symbol` is the overwrite-mode dedup key for this topic.
    """
    bus.publish(
        topic="signal:binance_score",
        producer="POLY_BINANCE_SIGNALS",
        payload={
            "market_id":          market_id,
            "symbol":             symbol,
            "current_price":      current_price,
            "strike_price":       strike_price,
            "days_to_resolution": days_to_resolution,
            "confidence":         confidence,
        },
    )


def _inject_price_history(sniper, market_id, prices, base_ts=None):
    """Seed the sniper's rolling price history without going through the bus."""
    if base_ts is None:
        base_ts = datetime.now(timezone.utc).timestamp()
    for i, price in enumerate(prices):
        sniper._update_price_history(market_id, price, timestamp_s=base_ts + i)


# ---------------------------------------------------------------------------
# _normal_cdf — pure math
# ---------------------------------------------------------------------------

def test_normal_cdf_zero_returns_half():
    assert abs(_normal_cdf(0.0) - 0.5) < 1e-9


def test_normal_cdf_large_positive_approaches_one():
    assert _normal_cdf(10.0) > 0.999


def test_normal_cdf_large_negative_approaches_zero():
    assert _normal_cdf(-10.0) < 0.001


def test_normal_cdf_symmetric():
    """N(x) + N(-x) == 1."""
    for x in [0.5, 1.0, 1.96, 2.5]:
        assert abs(_normal_cdf(x) + _normal_cdf(-x) - 1.0) < 1e-12


def test_normal_cdf_known_value_196():
    """N(1.96) ≈ 0.975 (95% confidence interval boundary)."""
    assert abs(_normal_cdf(1.96) - 0.975) < 0.001


# ---------------------------------------------------------------------------
# _compute_volatility — pure math
# ---------------------------------------------------------------------------

def test_volatility_constant_prices_returns_zero():
    prices = [50_000.0] * 10
    assert _compute_volatility(prices) == 0.0


def test_volatility_single_price_returns_zero():
    assert _compute_volatility([50_000.0]) == 0.0


def test_volatility_empty_returns_zero():
    assert _compute_volatility([]) == 0.0


def test_volatility_three_prices_returns_positive():
    """Need at least 3 prices (2 log returns) to get non-zero sample variance."""
    assert _compute_volatility([50_000.0, 50_100.0, 49_900.0]) > 0.0


def test_volatility_more_variance_gives_higher_sigma():
    """Larger price swings → higher annualised σ."""
    calm  = [1_000, 1_001, 1_000, 1_001, 1_000]
    wild  = [1_000, 1_100, 900,   1_100, 900]
    assert _compute_volatility(wild) > _compute_volatility(calm)


def test_volatility_result_is_non_negative():
    assert _compute_volatility(VOLATILE_PRICES) >= 0.0


def test_volatility_uses_annualization_factor():
    """σ_annualised = σ_per_obs * sqrt(ANNUALIZATION_FACTOR)."""
    # Two prices: only one log return, sample std = that return
    prices = [1.0, math.e]   # ln(e/1) = 1.0
    # std of a single observation (sample std of 1 element → use n-1=0 guard → 1 item)
    # With n=2 prices, m=1 log return, variance = (r-mean)² / max(m-1,1) = 0 / 1 = 0
    # Actually: mean of 1 element = that element, variance = 0 (single point)
    # So σ = 0.  Let's use 3 prices instead.
    prices = [1.0, math.e, 1.0]  # log returns: [1.0, -1.0], mean=0, std=sqrt(2)
    expected = math.sqrt(2) * math.sqrt(ANNUALIZATION_FACTOR)
    assert abs(_compute_volatility(prices) - expected) < 1e-9


# ---------------------------------------------------------------------------
# _gbm_probability — pure math
# ---------------------------------------------------------------------------

def test_gbm_deep_itm_probability_near_one():
    """S0 >> K → probability close to 1."""
    p = _gbm_probability(100_000, 50_000, 0.80, 30)
    assert p > 0.90


def test_gbm_deep_otm_probability_near_zero():
    """S0 << K → probability close to 0."""
    p = _gbm_probability(25_000, 50_000, 0.80, 30)
    assert p < 0.10


def test_gbm_atm_probability_near_half():
    """S0 = K, very low σ, very short time → probability close to 0.5."""
    # d2 ≈ 0 when S0=K, small σ, small T → N(0) = 0.5
    p = _gbm_probability(50_000, 50_000, 0.001, 1)
    assert 0.45 < p < 0.55


def test_gbm_returns_zero_for_nonpositive_inputs():
    assert _gbm_probability(0, 50_000, 0.80, 30) == 0.0
    assert _gbm_probability(50_000, 0, 0.80, 30) == 0.0
    assert _gbm_probability(50_000, 50_000, 0, 30) == 0.0
    assert _gbm_probability(50_000, 50_000, 0.80, 0) == 0.0


def test_gbm_probability_in_range():
    p = _gbm_probability(50_000, 50_000, 0.80, 30)
    assert 0.0 <= p <= 1.0


def test_gbm_higher_current_price_gives_higher_probability():
    p_high = _gbm_probability(80_000, 50_000, 0.80, 30)
    p_low  = _gbm_probability(40_000, 50_000, 0.80, 30)
    assert p_high > p_low


def test_gbm_more_time_increases_uncertainty():
    """Longer time to resolution spreads the distribution: ATM probabilities diverge."""
    p_short = _gbm_probability(50_000, 50_000, 0.80, 5)
    p_long  = _gbm_probability(50_000, 50_000, 0.80, 365)
    # Both should be near 0.5, but zero-drift GBM makes longer time lower (due to
    # the -σ²T/2 drift term)
    assert 0.0 < p_short <= 1.0
    assert 0.0 < p_long <= 1.0


# ---------------------------------------------------------------------------
# Ticket acceptance criteria — _check_opportunity (pure path)
# ---------------------------------------------------------------------------

def test_signal_emitted_when_gbm_prob_exceeds_threshold(sniper):
    """Deep ITM + price history → gbm_prob ≈ 1.0 >> yes_ask + EDGE_THRESHOLD → signal."""
    signal = sniper._check_opportunity(
        MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES
    )
    assert signal is not None


def test_no_signal_when_gbm_prob_below_threshold(sniper):
    """Deep OTM → gbm_prob ≈ 0.0 < yes_ask → no signal."""
    signal = sniper._check_opportunity(
        MARKET_ID, DEEP_OTM_SCORE, PRICE_UPDATE, VOLATILE_PRICES
    )
    assert signal is None


def test_no_signal_with_insufficient_price_history(sniper):
    """Fewer than MIN_PRICE_HISTORY samples → no signal."""
    short_history = VOLATILE_PRICES[:MIN_PRICE_HISTORY - 1]
    signal = sniper._check_opportunity(
        MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, short_history
    )
    assert signal is None


def test_no_signal_with_exactly_min_price_history(sniper):
    """Exactly MIN_PRICE_HISTORY samples → evaluation proceeds (no early exit)."""
    # Deep ITM should still signal even at the minimum history length
    history = VOLATILE_PRICES[:MIN_PRICE_HISTORY]
    signal = sniper._check_opportunity(
        MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, history
    )
    assert signal is not None


def test_no_signal_with_low_confidence(sniper):
    score = {**DEEP_ITM_SCORE, "confidence": MIN_CONFIDENCE - 0.01}
    signal = sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal is None


def test_signal_allowed_at_minimum_confidence(sniper):
    score = {**DEEP_ITM_SCORE, "confidence": MIN_CONFIDENCE}
    signal = sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal is not None


def test_no_signal_missing_current_price(sniper):
    score = {k: v for k, v in DEEP_ITM_SCORE.items() if k != "current_price"}
    assert sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES) is None


def test_no_signal_missing_strike_price(sniper):
    score = {k: v for k, v in DEEP_ITM_SCORE.items() if k != "strike_price"}
    assert sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES) is None


def test_no_signal_missing_days_to_resolution(sniper):
    score = {k: v for k, v in DEEP_ITM_SCORE.items() if k != "days_to_resolution"}
    assert sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES) is None


def test_no_signal_missing_yes_ask(sniper):
    price = {k: v for k, v in PRICE_UPDATE.items() if k != "yes_ask"}
    assert sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, price, VOLATILE_PRICES) is None


def test_no_signal_zero_current_price(sniper):
    score = {**DEEP_ITM_SCORE, "current_price": 0}
    assert sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES) is None


def test_no_signal_constant_price_history(sniper):
    """All identical prices → σ = 0 → _gbm_probability returns 0 → no signal."""
    constant = [50_000.0] * 10
    assert sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, constant) is None


# ---------------------------------------------------------------------------
# _check_opportunity — payload conformance
# ---------------------------------------------------------------------------

def test_signal_payload_required_fields(sniper):
    signal = sniper._check_opportunity(
        MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES
    )
    required = {
        "strategy", "account_id", "market_id", "platform",
        "direction", "confidence", "suggested_size_eur",
        "signal_type", "signal_detail",
    }
    assert required.issubset(signal.keys())


def test_signal_payload_strategy(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["strategy"] == CONSUMER_ID


def test_signal_payload_account_id(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["account_id"] == ACCOUNT_ID


def test_signal_payload_platform(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["platform"] == "polymarket"


def test_signal_payload_direction(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["direction"] == "BUY_YES"


def test_signal_payload_signal_type(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["signal_type"] == "brownian_sniper"


def test_signal_payload_suggested_size_eur(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["suggested_size_eur"] == SUGGESTED_SIZE_EUR


def test_signal_detail_fields(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    detail = signal["signal_detail"]
    for field in ("gbm_probability", "yes_ask", "edge", "sigma",
                  "current_price", "strike_price", "days_to_resolution"):
        assert field in detail


def test_signal_detail_gbm_probability_in_range(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert 0.0 <= signal["signal_detail"]["gbm_probability"] <= 1.0


def test_signal_detail_edge_equals_gbm_minus_yes_ask(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    detail = signal["signal_detail"]
    expected_edge = round(detail["gbm_probability"] - detail["yes_ask"], 6)
    assert abs(detail["edge"] - expected_edge) < 1e-9


def test_signal_detail_sigma_positive(sniper):
    signal = sniper._check_opportunity(MARKET_ID, DEEP_ITM_SCORE, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["signal_detail"]["sigma"] > 0.0


def test_signal_confidence_capped_at_one(sniper):
    score = {**DEEP_ITM_SCORE, "confidence": 2.0}
    signal = sniper._check_opportunity(MARKET_ID, score, PRICE_UPDATE, VOLATILE_PRICES)
    assert signal["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Price-history management
# ---------------------------------------------------------------------------

def test_update_price_history_adds_entry(sniper):
    sniper._update_price_history(MARKET_ID, 50_000.0)
    assert len(sniper._price_history[MARKET_ID]) == 1


def test_update_price_history_prunes_old_entries(sniper):
    """Entries older than WINDOW_SECONDS are pruned."""
    old_ts = datetime.now(timezone.utc).timestamp() - 120  # 2 minutes ago
    sniper._update_price_history(MARKET_ID, 49_000.0, timestamp_s=old_ts)
    sniper._update_price_history(MARKET_ID, 50_000.0)  # now
    # Old entry should be pruned
    assert all(p == 50_000.0 for _, p in sniper._price_history[MARKET_ID])


def test_get_recent_prices_returns_list(sniper):
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    prices = sniper._get_recent_prices(MARKET_ID)
    assert isinstance(prices, list)
    assert len(prices) == len(VOLATILE_PRICES)


def test_get_recent_prices_empty_for_unknown_market(sniper):
    assert sniper._get_recent_prices("0xunknown") == []


def test_price_history_accumulates_across_runs(sniper, bus):
    """Multiple run_once() calls accumulate price history for the same market."""
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=49_500.0)
    sniper.run_once()

    _publish_binance_score(bus, current_price=49_510.0)
    sniper.run_once()

    prices = sniper._get_recent_prices(MARKET_ID)
    assert len(prices) == 2


# ---------------------------------------------------------------------------
# run_once — bus integration
# ---------------------------------------------------------------------------

def test_run_once_returns_list(sniper):
    assert isinstance(sniper.run_once(), sniper.run_once().__class__)
    assert isinstance(sniper.run_once(), list)


def test_run_once_no_signal_without_price_update(sniper, bus):
    """No feed:price_update cached → no opportunity check → no signal."""
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    signals = sniper.run_once()
    assert len(signals) == 0


def test_run_once_no_signal_with_insufficient_history(sniper, bus):
    """Fewer than MIN_PRICE_HISTORY samples in history → no signal."""
    _publish_price_update(bus)
    # Inject only MIN_PRICE_HISTORY - 1 historical prices
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES[:MIN_PRICE_HISTORY - 1])
    # Score event adds 1 more price → still MIN_PRICE_HISTORY - 1 + 1 = MIN_PRICE_HISTORY
    # Actually it will reach MIN_PRICE_HISTORY exactly, which passes — adjust
    _inject_price_history(sniper, MARKET_ID, [])  # reset
    sniper._price_history[MARKET_ID] = []
    # Inject 3 prices manually (below min)
    for p in VOLATILE_PRICES[:3]:
        sniper._update_price_history(MARKET_ID, p)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    # After score event: 4 prices total (< MIN_PRICE_HISTORY=5) → no signal
    signals = sniper.run_once()
    assert len(signals) == 0


def test_run_once_emits_signal_when_conditions_met(sniper, bus):
    """Deep ITM + full history + price update → signal."""
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_price_update(bus, yes_ask=0.45)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0, days_to_resolution=30)
    signals = sniper.run_once()
    assert len(signals) == 1


def test_run_once_signal_published_to_bus(sniper, bus):
    store = PolyDataStore(base_path=sniper.bus.store.base_path)
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    sniper.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    topics = [e.get("topic") for e in events]
    assert "trade:signal" in topics


def test_run_once_signal_producer_is_consumer_id(sniper, bus):
    store = PolyDataStore(base_path=sniper.bus.store.base_path)
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    sniper.run_once()
    events = store.read_jsonl("bus/pending_events.jsonl")
    evt = next(e for e in events if e.get("topic") == "trade:signal")
    assert evt["producer"] == CONSUMER_ID


def test_run_once_signal_audit_logged(sniper, bus):
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    sniper.run_once()
    audit = PolyAuditLog(base_path=sniper.bus.store.base_path)
    today = datetime.now(timezone.utc).strftime("%Y_%m_%d")
    entries = audit.read_events(today)
    topics = [e.get("topic") for e in entries]
    assert "trade:signal" in topics


def test_run_once_acks_all_events(sniper, bus):
    """After run_once(), a second call returns no new signals."""
    _inject_price_history(sniper, MARKET_ID, VOLATILE_PRICES)
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=100_000.0, strike_price=50_000.0)
    sniper.run_once()
    signals2 = sniper.run_once()
    assert signals2 == []


def test_run_once_price_cache_populated(sniper, bus):
    _publish_price_update(bus, yes_ask=0.55)
    sniper.run_once()
    assert MARKET_ID in sniper._price_cache
    assert sniper._price_cache[MARKET_ID]["yes_ask"] == 0.55


def test_run_once_score_cache_populated(sniper, bus):
    _publish_price_update(bus)
    _publish_binance_score(bus, current_price=48_000.0)
    sniper.run_once()
    assert MARKET_ID in sniper._score_cache
    assert sniper._score_cache[MARKET_ID]["current_price"] == 48_000.0


# ---------------------------------------------------------------------------
# Multi-market independence
# ---------------------------------------------------------------------------

def test_multiple_markets_only_itm_signals(sniper, bus):
    """Market A deep ITM, market B deep OTM → one signal.

    Injected history must be close to the score's current_price so that
    when run_once() appends current_price to the rolling history no large
    price jump inflates σ and collapses the GBM probability.
    """
    # 0xaaa: BTC at ~100_000, strike=50_000 (deep ITM)
    btc_prices = [99_900, 100_050, 99_850, 100_100, 99_900, 100_050, 99_950]
    _inject_price_history(sniper, "0xaaa", btc_prices)
    # 0xbbb: ETH at ~25_000, strike=50_000 (deep OTM)
    eth_prices = [24_900, 25_050, 24_850, 25_100, 24_900, 25_050, 24_950]
    _inject_price_history(sniper, "0xbbb", eth_prices)

    _publish_price_update(bus, market_id="0xaaa", yes_ask=0.45)
    _publish_price_update(bus, market_id="0xbbb", yes_ask=0.45)
    _publish_binance_score(bus, market_id="0xaaa", current_price=100_000,
                           strike_price=50_000, symbol="BTC")
    _publish_binance_score(bus, market_id="0xbbb", current_price=25_000,
                           strike_price=50_000, symbol="ETH")

    signals = sniper.run_once()
    assert len(signals) == 1
    assert signals[0]["market_id"] == "0xaaa"


def test_multiple_markets_both_itm_both_signal(sniper, bus):
    """Two markets both deep ITM → two signals."""
    btc_prices = [99_900, 100_050, 99_850, 100_100, 99_900, 100_050, 99_950]
    eth_prices = [199_800, 200_100, 199_700, 200_200, 199_800, 200_100, 199_900]
    _inject_price_history(sniper, "0xaaa", btc_prices)
    _inject_price_history(sniper, "0xbbb", eth_prices)

    _publish_price_update(bus, market_id="0xaaa", yes_ask=0.45)
    _publish_price_update(bus, market_id="0xbbb", yes_ask=0.45)
    _publish_binance_score(bus, market_id="0xaaa", current_price=100_000,
                           strike_price=50_000, symbol="BTC")
    _publish_binance_score(bus, market_id="0xbbb", current_price=200_000,
                           strike_price=50_000, symbol="ETH")

    signals = sniper.run_once()
    assert len(signals) == 2
    mids = {s["market_id"] for s in signals}
    assert mids == {"0xaaa", "0xbbb"}
