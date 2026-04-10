"""Tests for DexScreenerClient."""

import asyncio
from decimal import Decimal

import httpx
import pytest
import respx

from dexscreener import DexPairData, DexScreenerClient


SAMPLE_PAIR = {
    "chainId": "solana",
    "dexId": "raydium",
    "pairAddress": "PAIR123",
    "baseToken": {"address": "TOKEN_A", "symbol": "BONK", "name": "Bonk"},
    "quoteToken": {"address": "TOKEN_Q", "symbol": "SOL", "name": "Solana"},
    "priceUsd": "0.00001234",
    "priceNative": "0.0000001",
    "marketCap": "500000",
    "fdv": "1000000",
    "liquidity": {"usd": "250000", "base": "1000000000", "quote": "100"},
    "volume": {"m5": "5000", "h1": "50000", "h6": "200000", "h24": "800000"},
    "priceChange": {"m5": "2.5", "h1": "-1.0", "h6": "5.0", "h24": "10.0"},
    "txns": {
        "m5": {"buys": 15, "sells": 10},
        "h1": {"buys": 100, "sells": 80},
        "h24": {"buys": 1000, "sells": 900},
    },
    "pairCreatedAt": 1700000000000,
}


@pytest.mark.asyncio
@respx.mock
async def test_get_token_pairs():
    respx.get("https://api.dexscreener.com/tokens/v1/solana/TOKEN_A").mock(
        return_value=httpx.Response(200, json=[SAMPLE_PAIR]),
    )

    async with DexScreenerClient() as client:
        pairs = await client.get_token_pairs("solana", "TOKEN_A")

    assert len(pairs) == 1
    pair = pairs[0]
    assert isinstance(pair, DexPairData)
    assert pair.base_token_symbol == "BONK"
    assert pair.price_usd == Decimal("0.00001234")
    assert pair.liquidity_usd == Decimal("250000")
    assert pair.buys_5m == 15
    assert pair.sells_5m == 10


@pytest.mark.asyncio
@respx.mock
async def test_get_token_price():
    respx.get("https://api.dexscreener.com/tokens/v1/solana/TOKEN_A").mock(
        return_value=httpx.Response(200, json=[SAMPLE_PAIR]),
    )

    async with DexScreenerClient() as client:
        price = await client.get_token_price("solana", "TOKEN_A")

    assert price == Decimal("0.00001234")


@pytest.mark.asyncio
@respx.mock
async def test_get_token_price_none_when_empty():
    respx.get("https://api.dexscreener.com/tokens/v1/solana/NOPE").mock(
        return_value=httpx.Response(200, json=[]),
    )

    async with DexScreenerClient() as client:
        price = await client.get_token_price("solana", "NOPE")

    assert price is None


@pytest.mark.asyncio
@respx.mock
async def test_search_pairs():
    respx.get("https://api.dexscreener.com/latest/dex/search").mock(
        return_value=httpx.Response(200, json={"pairs": [SAMPLE_PAIR]}),
    )

    async with DexScreenerClient() as client:
        results = await client.search_pairs("BONK")

    assert len(results) == 1
    assert results[0].base_token_symbol == "BONK"


@pytest.mark.asyncio
@respx.mock
async def test_429_retry():
    route = respx.get("https://api.dexscreener.com/tokens/v1/solana/TOKEN_A")
    route.side_effect = [
        httpx.Response(429),
        httpx.Response(200, json=[SAMPLE_PAIR]),
    ]

    async with DexScreenerClient(rate_limit=100.0) as client:
        pairs = await client.get_token_pairs("solana", "TOKEN_A")

    assert len(pairs) == 1


@pytest.mark.asyncio
@respx.mock
async def test_cache_dedup():
    call_count = 0

    def make_response(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=[SAMPLE_PAIR])

    respx.get("https://api.dexscreener.com/tokens/v1/solana/TOKEN_A").mock(
        side_effect=make_response,
    )

    async with DexScreenerClient(cache_ttl=10.0) as client:
        await client.get_token_pairs("solana", "TOKEN_A")
        await client.get_token_pairs("solana", "TOKEN_A")

    assert call_count == 1  # second call served from cache


@pytest.mark.asyncio
@respx.mock
async def test_batch_tokens():
    pair_b = {**SAMPLE_PAIR, "baseToken": {**SAMPLE_PAIR["baseToken"], "address": "TOKEN_B", "symbol": "WIF"}}

    respx.get("https://api.dexscreener.com/tokens/v1/solana/TOKEN_A,TOKEN_B").mock(
        return_value=httpx.Response(200, json=[SAMPLE_PAIR, pair_b]),
    )

    async with DexScreenerClient() as client:
        result = await client.get_tokens_batch("solana", ["TOKEN_A", "TOKEN_B"])

    assert "TOKEN_A" in result
    assert "TOKEN_B" in result
    assert result["TOKEN_A"].base_token_symbol == "BONK"
    assert result["TOKEN_B"].base_token_symbol == "WIF"


@pytest.mark.asyncio
@respx.mock
async def test_boosted_tokens():
    respx.get("https://api.dexscreener.com/token-boosts/latest/v1").mock(
        return_value=httpx.Response(200, json=[
            {"chainId": "solana", "tokenAddress": "BOOST1"},
            {"chainId": "ethereum", "tokenAddress": "BOOST2"},
        ]),
    )

    async with DexScreenerClient() as client:
        all_boosted = await client.get_boosted_tokens()
        assert len(all_boosted) == 2

        sol_boosted = await client.get_boosted_tokens("solana")
        assert len(sol_boosted) == 1
        assert sol_boosted[0]["tokenAddress"] == "BOOST1"
