"""Tests for DexPairData model."""

import time
from decimal import Decimal

from dexscreener import DexPairData


def test_defaults():
    pair = DexPairData()
    assert pair.price_usd == Decimal("0")
    assert pair.chain_id == ""
    assert pair.pair_address == ""


def test_buy_sell_ratio_5m():
    pair = DexPairData(buys_5m=10, sells_5m=5)
    assert pair.buy_sell_ratio_5m == 2.0


def test_buy_sell_ratio_no_trades():
    pair = DexPairData(buys_5m=0, sells_5m=0)
    assert pair.buy_sell_ratio_5m == 1.0


def test_buy_sell_ratio_1h():
    pair = DexPairData(buys_1h=3, sells_1h=6)
    assert pair.buy_sell_ratio_1h == 0.5


def test_has_liquidity():
    low = DexPairData(liquidity_usd=Decimal("500"))
    high = DexPairData(liquidity_usd=Decimal("5000"))
    assert not low.has_liquidity
    assert high.has_liquidity


def test_pair_age_seconds():
    now_ms = int(time.time() * 1000)
    pair = DexPairData(pair_created_at=now_ms - 3600_000)  # 1 hour ago
    age = pair.pair_age_seconds
    assert 3590 <= age <= 3610  # allow 10s tolerance


def test_pair_age_zero_when_no_created_at():
    pair = DexPairData(pair_created_at=0)
    assert pair.pair_age_seconds == 0
