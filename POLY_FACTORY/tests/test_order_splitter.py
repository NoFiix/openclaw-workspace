"""
Tests for POLY_ORDER_SPLITTER (POLY-018).
"""

import math
import pytest

from core.poly_data_store import PolyDataStore
from execution.poly_order_splitter import (
    PolyOrderSplitter,
    DEFAULT_DEPTH_USD,
    MAX_TRANCHES,
    MIN_TRANCHE_EUR,
    TRANCHE_DEPTH_FRACTION,
)


@pytest.fixture
def splitter(tmp_path):
    return PolyOrderSplitter(base_path=str(tmp_path))


# ---------------------------------------------------------------------------
# split() — core logic
# ---------------------------------------------------------------------------

def test_split_returns_list(splitter):
    result = splitter.split(28.5, 0.48, 10_000.0)
    assert isinstance(result, list)


def test_split_result_fields(splitter):
    tranches = splitter.split(28.5, 0.48, 10_000.0)
    for t in tranches:
        assert "size" in t
        assert "price_limit" in t


def test_split_single_tranche_when_size_fits(splitter):
    # depth = 10_000, max_tranche = 100. size = 50 → 1 tranche
    tranches = splitter.split(50.0, 0.50, 10_000.0)
    assert len(tranches) == 1
    assert abs(tranches[0]["size"] - 50.0) < 1e-6


def test_split_multiple_tranches(splitter):
    # depth = 500, max_tranche = 5.0. size = 28.5 → ceil(28.5/5) = 6 tranches
    tranches = splitter.split(28.5, 0.48, 500.0)
    assert len(tranches) > 1


def test_split_tranche_sizes_sum_to_total(splitter):
    for depth in (200.0, 1_000.0, 50_000.0):
        tranches = splitter.split(100.0, 0.50, depth)
        total = sum(t["size"] for t in tranches)
        assert abs(total - 100.0) < 1e-4, f"depth={depth}: sum={total}"


def test_split_price_limit_propagated(splitter):
    tranches = splitter.split(50.0, 0.63, 1_000.0)
    for t in tranches:
        assert t["price_limit"] == 0.63


def test_split_caps_at_max_tranches(splitter):
    # depth = 1, max_tranche = MIN_TRANCHE_EUR = 1.0. size = 1000 → ceil(1000/1) = 1000 capped to 10
    tranches = splitter.split(1000.0, 0.50, 1.0)
    assert len(tranches) == MAX_TRANCHES


def test_split_always_at_least_one_tranche(splitter):
    tranches = splitter.split(0.5, 0.50, 100_000.0)
    assert len(tranches) >= 1


def test_split_no_tranche_smaller_than_min(splitter):
    # With normal sizes, no tranche should be smaller than MIN_TRANCHE_EUR
    # except when total size itself is below MIN_TRANCHE_EUR
    tranches = splitter.split(50.0, 0.50, 100.0)
    for t in tranches:
        assert t["size"] >= MIN_TRANCHE_EUR - 1e-6


def test_split_zero_depth_uses_default(splitter):
    tranches_zero = splitter.split(50.0, 0.50, 0.0)
    tranches_default = splitter.split(50.0, 0.50, DEFAULT_DEPTH_USD)
    assert len(tranches_zero) == len(tranches_default)


def test_split_negative_depth_uses_default(splitter):
    tranches = splitter.split(50.0, 0.50, -100.0)
    assert len(tranches) >= 1
    total = sum(t["size"] for t in tranches)
    assert abs(total - 50.0) < 1e-4


def test_split_max_tranche_capped_at_500(splitter):
    # depth = 1_000_000, 1% = 10_000 → capped at MAX_TRANCHE_EUR=500
    # size = 400 → ceil(400/500) = 1 tranche
    tranches = splitter.split(400.0, 0.50, 1_000_000.0)
    assert len(tranches) == 1


def test_split_exact_division(splitter):
    # size = 30.0, depth = 1_000, max_tranche = 10 → 3 tranches of 10.0
    tranches = splitter.split(30.0, 0.48, 1_000.0)
    assert len(tranches) == 3
    for t in tranches:
        assert abs(t["size"] - 10.0) < 1e-6


# ---------------------------------------------------------------------------
# split_from_market() — reads depth from market_structure.json
# ---------------------------------------------------------------------------

def test_split_from_market_reads_depth(splitter):
    store = PolyDataStore(base_path=splitter.store.base_path)
    store.write_json("feeds/market_structure.json", {
        "0xabc": {"depth_usd": 1_000.0, "slippage_1k": 0.005}
    })
    # depth=1000, max_tranche=10. size=50 → ceil(50/10)=5 tranches
    tranches = splitter.split_from_market(50.0, 0.48, "0xabc")
    assert len(tranches) == 5
    total = sum(t["size"] for t in tranches)
    assert abs(total - 50.0) < 1e-4


def test_split_from_market_unknown_market_uses_default(splitter):
    store = PolyDataStore(base_path=splitter.store.base_path)
    store.write_json("feeds/market_structure.json", {})
    # Unknown market → DEFAULT_DEPTH_USD = 10_000, max_tranche = 100
    # size = 50 → 1 tranche
    tranches = splitter.split_from_market(50.0, 0.50, "0xunknown")
    assert len(tranches) == 1
    assert abs(tranches[0]["size"] - 50.0) < 1e-6


def test_split_from_market_no_file_uses_default(splitter):
    # market_structure.json doesn't exist → DEFAULT_DEPTH_USD
    tranches = splitter.split_from_market(50.0, 0.50, "0xabc")
    assert len(tranches) >= 1
    total = sum(t["size"] for t in tranches)
    assert abs(total - 50.0) < 1e-4


def test_split_from_market_result_fields(splitter):
    store = PolyDataStore(base_path=splitter.store.base_path)
    store.write_json("feeds/market_structure.json", {
        "0xabc": {"depth_usd": 5_000.0}
    })
    tranches = splitter.split_from_market(28.5, 0.48, "0xabc")
    for t in tranches:
        assert "size" in t
        assert "price_limit" in t


def test_split_from_market_price_limit_propagated(splitter):
    store = PolyDataStore(base_path=splitter.store.base_path)
    store.write_json("feeds/market_structure.json", {
        "0xabc": {"depth_usd": 2_000.0}
    })
    tranches = splitter.split_from_market(30.0, 0.72, "0xabc")
    for t in tranches:
        assert t["price_limit"] == 0.72
