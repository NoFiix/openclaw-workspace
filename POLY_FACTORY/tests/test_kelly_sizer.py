"""
Tests for POLY_KELLY_SIZER (POLY-016).

Ticket acceptance: calculs vérifiés, max 3% du compte.
"""

import pytest

from risk.poly_kelly_sizer import KELLY_MODES, MAX_POSITION_PCT, PolyKellySizer


@pytest.fixture
def sizer():
    return PolyKellySizer()


# ---------------------------------------------------------------------------
# Kelly fraction tests
# ---------------------------------------------------------------------------

def test_kelly_fraction_positive_edge(sizer):
    # confidence=0.6, price=0.5 → (0.6-0.5)/(1-0.5) = 0.1/0.5 = 0.2
    result = sizer.kelly_fraction(0.6, 0.5)
    assert abs(result - 0.2) < 1e-9


def test_kelly_fraction_zero_edge(sizer):
    # confidence == price → no edge
    assert sizer.kelly_fraction(0.5, 0.5) == 0.0


def test_kelly_fraction_negative_edge(sizer):
    # confidence < price → no edge (would be negative Kelly → don't bet)
    assert sizer.kelly_fraction(0.4, 0.6) == 0.0


def test_kelly_fraction_price_zero(sizer):
    assert sizer.kelly_fraction(0.6, 0.0) == 0.0


def test_kelly_fraction_price_one(sizer):
    assert sizer.kelly_fraction(0.6, 1.0) == 0.0


def test_kelly_fraction_confidence_zero(sizer):
    assert sizer.kelly_fraction(0.0, 0.5) == 0.0


def test_kelly_fraction_confidence_one(sizer):
    # confidence=1.0 is valid → f* = (1.0 - 0.5) / (1 - 0.5) = 1.0
    assert sizer.kelly_fraction(1.0, 0.5) == 1.0


def test_kelly_fraction_high_edge(sizer):
    # confidence=0.8, price=0.4 → (0.8-0.4)/(1-0.4) = 0.4/0.6 ≈ 0.667
    result = sizer.kelly_fraction(0.8, 0.4)
    assert abs(result - (0.4 / 0.6)) < 1e-9


def test_kelly_fraction_small_edge(sizer):
    # confidence=0.51, price=0.50 → (0.01)/(0.50) = 0.02
    result = sizer.kelly_fraction(0.51, 0.50)
    assert abs(result - 0.02) < 1e-9


# ---------------------------------------------------------------------------
# Compute tests
# ---------------------------------------------------------------------------

def test_compute_half_kelly_default(sizer):
    # Default mode is "half"
    # fraction = (0.6-0.5)/(0.5) = 0.2; half = 0.1; 0.1*1000=100; cap=30 → 30
    # Let's use small edge to stay under cap
    # fraction=0.02, half=0.01, size=0.01*1000=10 (< 30) → 10
    result = sizer.compute(0.51, 0.50, 1000.0)
    expected = sizer.kelly_fraction(0.51, 0.50) * 0.5 * 1000.0
    assert abs(result - expected) < 1e-6
    assert result > 0


def test_compute_half_kelly_explicit(sizer):
    result_default = sizer.compute(0.51, 0.50, 1000.0)
    result_half = sizer.compute(0.51, 0.50, 1000.0, mode="half")
    assert abs(result_default - result_half) < 1e-9


def test_compute_quarter_kelly(sizer):
    # quarter = half / 2 (when below cap)
    result = sizer.compute(0.51, 0.50, 1000.0, mode="quarter")
    expected = sizer.kelly_fraction(0.51, 0.50) * 0.25 * 1000.0
    assert abs(result - expected) < 1e-6


def test_compute_full_kelly(sizer):
    result = sizer.compute(0.51, 0.50, 1000.0, mode="full")
    expected = sizer.kelly_fraction(0.51, 0.50) * 1.0 * 1000.0
    # May be capped
    assert abs(result - min(expected, 1000.0 * MAX_POSITION_PCT)) < 1e-6


def test_compute_capped_at_3pct(sizer):
    # Large edge: confidence=0.9, price=0.1 → fraction very high → raw_size >> cap
    result = sizer.compute(0.9, 0.1, 1000.0, mode="full")
    assert abs(result - 1000.0 * MAX_POSITION_PCT) < 1e-9
    assert abs(result - 30.0) < 1e-9


def test_compute_zero_capital(sizer):
    assert sizer.compute(0.6, 0.5, 0.0) == 0.0


def test_compute_negative_capital(sizer):
    assert sizer.compute(0.6, 0.5, -100.0) == 0.0


def test_compute_no_edge(sizer):
    assert sizer.compute(0.5, 0.5, 1000.0) == 0.0


def test_compute_negative_edge(sizer):
    assert sizer.compute(0.4, 0.6, 1000.0) == 0.0


def test_compute_invalid_confidence_low(sizer):
    assert sizer.compute(0.0, 0.5, 1000.0) == 0.0


def test_compute_confidence_one_valid(sizer):
    # confidence=1.0 is now valid → should produce a positive size, capped at 3%
    result = sizer.compute(1.0, 0.5, 1000.0)
    assert result > 0
    assert result <= 1000.0 * 0.03  # 3% hard cap


def test_compute_invalid_price_zero(sizer):
    assert sizer.compute(0.6, 0.0, 1000.0) == 0.0


def test_compute_invalid_price_one(sizer):
    assert sizer.compute(0.6, 1.0, 1000.0) == 0.0


def test_compute_invalid_mode_raises(sizer):
    with pytest.raises(ValueError, match="Unknown Kelly mode"):
        sizer.compute(0.6, 0.5, 1000.0, mode="full_turbo")


def test_compute_half_equals_full_divided_by_two(sizer):
    # Use a small edge to stay well below the 3% cap
    confidence, price, capital = 0.51, 0.50, 1000.0
    full = sizer.compute(confidence, price, capital, mode="full")
    half = sizer.compute(confidence, price, capital, mode="half")
    # Both should be well below cap, so ratio holds exactly
    assert abs(half - full / 2) < 1e-9


def test_compute_quarter_equals_full_divided_by_four(sizer):
    confidence, price, capital = 0.51, 0.50, 1000.0
    full = sizer.compute(confidence, price, capital, mode="full")
    quarter = sizer.compute(confidence, price, capital, mode="quarter")
    assert abs(quarter - full / 4) < 1e-9


def test_compute_result_non_negative(sizer):
    for confidence in [0.3, 0.5, 0.6, 0.8]:
        for price in [0.3, 0.5, 0.7]:
            result = sizer.compute(confidence, price, 1000.0)
            assert result >= 0.0, f"Negative result for confidence={confidence}, price={price}"


def test_compute_cap_equals_3pct_of_capital(sizer):
    # Verify cap scales with capital
    result_1000 = sizer.compute(0.9, 0.1, 1000.0, mode="full")
    result_2000 = sizer.compute(0.9, 0.1, 2000.0, mode="full")
    assert abs(result_1000 - 30.0) < 1e-9
    assert abs(result_2000 - 60.0) < 1e-9
