"""DexPairData model — typed representation of a DexScreener trading pair."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(slots=True)
class DexPairData:
    """Parsed pair data from DexScreener."""

    # Identity
    chain_id: str = ""
    dex_id: str = ""
    pair_address: str = ""
    base_token_address: str = ""
    base_token_symbol: str = ""
    base_token_name: str = ""
    quote_token_address: str = ""
    quote_token_symbol: str = ""

    # Price
    price_usd: Decimal = Decimal("0")
    price_native: Decimal = Decimal("0")

    # Market data
    market_cap: Decimal = Decimal("0")
    fdv: Decimal = Decimal("0")
    liquidity_usd: Decimal = Decimal("0")
    liquidity_base: Decimal = Decimal("0")
    liquidity_quote: Decimal = Decimal("0")

    # Volume (USD)
    volume_5m: Decimal = Decimal("0")
    volume_1h: Decimal = Decimal("0")
    volume_6h: Decimal = Decimal("0")
    volume_24h: Decimal = Decimal("0")

    # Price changes (percentage)
    price_change_5m: Decimal = Decimal("0")
    price_change_1h: Decimal = Decimal("0")
    price_change_6h: Decimal = Decimal("0")
    price_change_24h: Decimal = Decimal("0")

    # Transactions
    buys_5m: int = 0
    sells_5m: int = 0
    buys_1h: int = 0
    sells_1h: int = 0
    buys_24h: int = 0
    sells_24h: int = 0

    # Age
    pair_created_at: int = 0  # Unix timestamp ms

    # Metadata
    is_boosted: bool = False
    url: str = ""

    # Raw response
    raw: dict = field(default_factory=dict)

    @property
    def buy_sell_ratio_5m(self) -> float:
        """Buy/sell ratio over 5 minutes. >1 = more buying."""
        total = self.buys_5m + self.sells_5m
        if total == 0:
            return 1.0
        return self.buys_5m / max(self.sells_5m, 1)

    @property
    def buy_sell_ratio_1h(self) -> float:
        """Buy/sell ratio over 1 hour."""
        total = self.buys_1h + self.sells_1h
        if total == 0:
            return 1.0
        return self.buys_1h / max(self.sells_1h, 1)

    @property
    def has_liquidity(self) -> bool:
        """Token has meaningful liquidity (>$1000)."""
        return self.liquidity_usd > Decimal("1000")

    @property
    def pair_age_seconds(self) -> int:
        """How old the pair is in seconds."""
        if self.pair_created_at <= 0:
            return 0
        return max(0, int(time.time()) - (self.pair_created_at // 1000))
