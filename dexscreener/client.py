"""
Async DexScreener API client.

Free public API — no authentication required.
Rate limit: ~300 req/min (~5/s).
API docs: https://docs.dexscreener.com/api/reference
"""

from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any

import httpx

from .models import DexPairData

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.dexscreener.com"

# 429 retry settings
_MAX_429_RETRIES = 3
_429_BASE_BACKOFF = 2.0


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    header = resp.headers.get("Retry-After")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except (TypeError, ValueError):
        return None


def _safe_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def _safe_int(val: Any) -> int:
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0


class DexScreenerClient:
    """Async DexScreener API client with rate limiting and 429 handling.

    Works on any chain DexScreener supports: solana, ethereum, base, bsc,
    arbitrum, polygon, avalanche, etc.

    Example::

        async with DexScreenerClient() as client:
            pairs = await client.get_token_pairs("solana", token_address)
            print(pairs[0].price_usd)
    """

    __slots__ = (
        "_http",
        "_cache",
        "_cache_ttl",
        "_429_cooldown_until",
        "_429_consecutive",
        "_rate_limit",
        "_rate_tokens",
        "_rate_last_refill",
    )

    def __init__(
        self,
        *,
        rate_limit: float = 5.0,
        cache_ttl: float = 8.0,
    ) -> None:
        """
        Args:
            rate_limit: Max requests per second (default 5.0).
            cache_ttl: Default cache TTL in seconds.
        """
        self._http: httpx.AsyncClient | None = None
        self._cache: dict[str, tuple[Any, float]] = {}  # key → (value, expires_at)
        self._cache_ttl = cache_ttl
        self._429_cooldown_until: float = 0.0
        self._429_consecutive: int = 0
        self._rate_limit = max(rate_limit, 0.1)
        self._rate_tokens = rate_limit
        self._rate_last_refill = time.monotonic()

    async def __aenter__(self) -> DexScreenerClient:
        await self.startup()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.shutdown()

    async def startup(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            headers={"Accept": "application/json"},
        )

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # -- Public API ----------------------------------------------------------

    async def get_token_pairs(
        self,
        chain: str,
        token_address: str,
    ) -> list[DexPairData]:
        """Get all trading pairs for a token, sorted by liquidity (highest first).

        Args:
            chain: Chain identifier (e.g., "solana", "ethereum", "base").
            token_address: Token contract/mint address.
        """
        cache_key = f"pairs:{chain}:{token_address}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        data = await self._get_with_retry(
            f"{_BASE_URL}/tokens/v1/{chain}/{token_address}",
            "token_pairs",
        )
        raw_pairs = data if isinstance(data, list) else data.get("pairs", []) if data else []
        pairs = self._parse_pairs(raw_pairs)
        pairs.sort(key=lambda p: p.liquidity_usd, reverse=True)
        self._cache_set(cache_key, pairs)
        return pairs

    async def get_pair_by_address(
        self,
        chain: str,
        pair_address: str,
    ) -> DexPairData | None:
        """Get data for a specific pair address.

        Returns None if the pair is not found.
        """
        cache_key = f"pair:{chain}:{pair_address}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        data = await self._get_with_retry(
            f"{_BASE_URL}/pairs/v1/{chain}/{pair_address}",
            "pair",
        )
        raw_pair = (
            data[0]
            if isinstance(data, list) and data
            else data.get("pair", data) if data else None
        )
        if not raw_pair:
            return None

        pairs = self._parse_pairs([raw_pair])
        result = pairs[0] if pairs else None
        if result:
            self._cache_set(cache_key, result)
        return result

    async def get_token_price(
        self,
        chain: str,
        token_address: str,
    ) -> Decimal | None:
        """Get the best available USD price for a token.

        Uses the highest-liquidity pair. Returns None if no price available.
        """
        pairs = await self.get_token_pairs(chain, token_address)
        if not pairs:
            return None
        best = pairs[0]
        return best.price_usd if best.price_usd > 0 else None

    async def get_token_liquidity(
        self,
        chain: str,
        token_address: str,
    ) -> Decimal:
        """Get total USD liquidity across all pairs for a token."""
        pairs = await self.get_token_pairs(chain, token_address)
        return sum((p.liquidity_usd for p in pairs), Decimal("0"))

    async def get_tokens_batch(
        self,
        chain: str,
        token_addresses: list[str],
    ) -> dict[str, DexPairData]:
        """Fetch market data for up to 30 tokens in a single request.

        Returns a dict keyed by token address → best DexPairData (highest liquidity).
        Tokens with no data are absent from the result.
        """
        if not token_addresses:
            return {}

        BATCH_SIZE = 30
        result: dict[str, DexPairData] = {}

        for i in range(0, len(token_addresses), BATCH_SIZE):
            batch = token_addresses[i : i + BATCH_SIZE]
            comma_addrs = ",".join(batch)

            data = await self._get_with_retry(
                f"{_BASE_URL}/tokens/v1/{chain}/{comma_addrs}",
                "batch_tokens",
            )
            raw_pairs = data if isinstance(data, list) else data.get("pairs", []) if data else []
            pairs = self._parse_pairs(raw_pairs)

            for pair in pairs:
                addr = pair.base_token_address
                if addr and (
                    addr not in result
                    or pair.liquidity_usd > result[addr].liquidity_usd
                ):
                    result[addr] = pair

        return result

    async def search_pairs(self, query: str) -> list[DexPairData]:
        """Search for pairs by token name, symbol, or address."""
        data = await self._get_with_retry(
            f"{_BASE_URL}/latest/dex/search",
            "search",
            params={"q": query},
        )
        raw_pairs = data.get("pairs", []) if data else []
        return self._parse_pairs(raw_pairs)

    async def get_boosted_tokens(
        self,
        chain: str | None = None,
    ) -> list[dict]:
        """Get currently boosted (promoted) tokens.

        Boosted tokens are paid promotions — treat with caution.

        Args:
            chain: Optional chain filter (e.g., "solana"). If None, returns all chains.
        """
        cache_key = f"boosted:{chain or 'all'}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        data = await self._get_with_retry(
            f"{_BASE_URL}/token-boosts/latest/v1",
            "boosted",
        )
        items = data if isinstance(data, list) else []
        if chain:
            items = [item for item in items if item.get("chainId") == chain]

        self._cache_set(cache_key, items, ttl=30.0)
        return items

    async def is_token_boosted(
        self,
        chain: str,
        token_address: str,
    ) -> bool:
        """Check if a token is currently boosted (paid promotion)."""
        boosted = await self.get_boosted_tokens(chain)
        return any(
            b.get("tokenAddress", "").lower() == token_address.lower()
            for b in boosted
        )

    # -- Internal helpers ----------------------------------------------------

    async def _wait_429_cooldown(self) -> None:
        now = time.time()
        if now < self._429_cooldown_until:
            wait = self._429_cooldown_until - now
            logger.info("dexscreener 429 cooldown: waiting %.1fs", wait)
            await asyncio.sleep(wait)

    def _trigger_429_cooldown(self, endpoint: str) -> None:
        self._429_consecutive += 1
        backoff = 3.0 * (2 ** min(self._429_consecutive - 1, 3))
        self._429_cooldown_until = time.time() + backoff
        logger.warning(
            "dexscreener 429 cooldown set: endpoint=%s consecutive=%d backoff=%.1fs",
            endpoint,
            self._429_consecutive,
            backoff,
        )

    def _clear_429_cooldown(self) -> None:
        if self._429_consecutive > 0:
            self._429_consecutive = 0

    async def _rate_limit_acquire(self) -> None:
        """Simple token bucket rate limiter."""
        now = time.monotonic()
        elapsed = now - self._rate_last_refill
        self._rate_tokens = min(
            self._rate_limit,
            self._rate_tokens + elapsed * self._rate_limit,
        )
        self._rate_last_refill = now

        if self._rate_tokens < 1.0:
            wait = (1.0 - self._rate_tokens) / self._rate_limit
            await asyncio.sleep(wait)
            self._rate_tokens = 0.0
        else:
            self._rate_tokens -= 1.0

    async def _get_with_retry(
        self,
        url: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET with 429 retry + global cooldown."""
        if self._http is None:
            raise RuntimeError("DexScreenerClient.startup() not called")

        await self._wait_429_cooldown()

        for attempt in range(_MAX_429_RETRIES + 1):
            await self._rate_limit_acquire()

            try:
                resp = await self._http.get(url, params=params)

                if resp.status_code == 429:
                    self._trigger_429_cooldown(endpoint)
                    backoff = _429_BASE_BACKOFF * (2 ** attempt)
                    logger.warning(
                        "dexscreener 429: endpoint=%s attempt=%d backoff=%.1fs",
                        endpoint,
                        attempt + 1,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    continue

                self._clear_429_cooldown()

                if resp.status_code != 200:
                    logger.warning(
                        "dexscreener HTTP %d: endpoint=%s",
                        resp.status_code,
                        endpoint,
                    )
                    return None

                return resp.json()

            except Exception as exc:
                logger.warning(
                    "dexscreener request failed: endpoint=%s error=%s",
                    endpoint,
                    exc,
                )
                return None

        logger.warning(
            "dexscreener 429 exhausted retries: endpoint=%s",
            endpoint,
        )
        return None

    # -- Cache ---------------------------------------------------------------

    def _cache_get(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._cache[key] = (value, time.monotonic() + (ttl or self._cache_ttl))

    # -- Parsing -------------------------------------------------------------

    def _parse_pairs(self, raw_pairs: list[dict]) -> list[DexPairData]:
        """Parse raw pair data into structured DexPairData objects."""
        pairs: list[DexPairData] = []

        for raw in raw_pairs:
            if not isinstance(raw, dict):
                continue

            base = raw.get("baseToken", {})
            quote = raw.get("quoteToken", {})
            volume = raw.get("volume", {})
            price_change = raw.get("priceChange", {})
            txns = raw.get("txns", {})
            liquidity = raw.get("liquidity", {})

            txns_5m = txns.get("m5", {})
            txns_1h = txns.get("h1", {})
            txns_24h = txns.get("h24", {})

            pair = DexPairData(
                chain_id=raw.get("chainId", ""),
                dex_id=raw.get("dexId", ""),
                pair_address=raw.get("pairAddress", ""),
                base_token_address=base.get("address", ""),
                base_token_symbol=base.get("symbol", ""),
                base_token_name=base.get("name", ""),
                quote_token_address=quote.get("address", ""),
                quote_token_symbol=quote.get("symbol", ""),
                price_usd=_safe_decimal(raw.get("priceUsd")),
                price_native=_safe_decimal(raw.get("priceNative")),
                market_cap=_safe_decimal(raw.get("marketCap")),
                fdv=_safe_decimal(raw.get("fdv")),
                liquidity_usd=_safe_decimal(liquidity.get("usd")),
                liquidity_base=_safe_decimal(liquidity.get("base")),
                liquidity_quote=_safe_decimal(liquidity.get("quote")),
                volume_5m=_safe_decimal(volume.get("m5")),
                volume_1h=_safe_decimal(volume.get("h1")),
                volume_6h=_safe_decimal(volume.get("h6")),
                volume_24h=_safe_decimal(volume.get("h24")),
                price_change_5m=_safe_decimal(price_change.get("m5")),
                price_change_1h=_safe_decimal(price_change.get("h1")),
                price_change_6h=_safe_decimal(price_change.get("h6")),
                price_change_24h=_safe_decimal(price_change.get("h24")),
                buys_5m=_safe_int(txns_5m.get("buys")),
                sells_5m=_safe_int(txns_5m.get("sells")),
                buys_1h=_safe_int(txns_1h.get("buys")),
                sells_1h=_safe_int(txns_1h.get("sells")),
                buys_24h=_safe_int(txns_24h.get("buys")),
                sells_24h=_safe_int(txns_24h.get("sells")),
                pair_created_at=_safe_int(raw.get("pairCreatedAt")),
                is_boosted=bool(raw.get("boosts")),
                url=raw.get("url", ""),
                raw=raw,
            )
            pairs.append(pair)

        return pairs
