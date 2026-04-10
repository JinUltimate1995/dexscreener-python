<div align="center">
  <h1>dexscreener-python</h1>
  <p><strong>async dexscreener api client for python.</strong></p>
  <p>rate limiting. 429 retry. response caching. request dedup. works on any chain.</p>

  <br/>

  <img src="https://img.shields.io/github/actions/workflow/status/JinUltimate1995/dexscreener-python/ci.yml?branch=main&style=flat-square&label=tests" />
  <img src="https://img.shields.io/pypi/v/dexscreener-python?style=flat-square" />
  <img src="https://img.shields.io/pypi/pyversions/dexscreener-python?style=flat-square" />
  <img src="https://img.shields.io/badge/async-first-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" />
</div>

---

> extracted from a production trading system. handles rate limits gracefully.

## why

dexscreener's api is free and powerful, but:

- **429s kill your app** if you don't handle them
- **no python client exists** that handles rate limits properly
- **concurrent requests** for the same token waste your quota

this library solves all three:

```python
from dexscreener import DexScreenerClient

async with DexScreenerClient() as client:
    # get all trading pairs for a token
    pairs = await client.get_token_pairs("solana", "So11111111111111111111111111111111111111112")

    for pair in pairs:
        print(f"{pair.base_token_symbol}: ${pair.price_usd} | liq: ${pair.liquidity_usd}")
```

429s → automatic exponential backoff (3s → 6s → 12s).
duplicate requests → deduplicated into one HTTP call.
results → cached with configurable TTL.

## install

```bash
pip install dexscreener-python
```

requires python 3.11+

## features

| feature | description |
|---|---|
| **any chain** | solana, ethereum, base, bsc, arbitrum — anything dexscreener supports |
| **adaptive rate limiting** | token bucket that backs off on 429 and recovers after success |
| **global 429 cooldown** | one 429 pauses ALL requests briefly (prevents request storms) |
| **response cache** | configurable TTL per endpoint. concurrent calls share one request. |
| **batch support** | fetch up to 30 tokens in a single request |
| **typed data** | `DexPairData` dataclass with computed properties (buy/sell ratio, age, etc.) |

## usage

### token pairs

```python
pairs = await client.get_token_pairs("solana", token_address)

best_pair = pairs[0]  # sorted by liquidity (highest first)
print(f"Price: ${best_pair.price_usd}")
print(f"Liquidity: ${best_pair.liquidity_usd}")
print(f"24h Volume: ${best_pair.volume_24h}")
print(f"Buy/Sell 5m: {best_pair.buy_sell_ratio_5m:.2f}")
print(f"Age: {best_pair.pair_age_seconds // 3600}h")
```

### token price

```python
price = await client.get_token_price("solana", token_address)
print(f"${price}")
```

### batch fetch (up to 30 tokens)

```python
data = await client.get_tokens_batch("solana", [addr1, addr2, addr3])
for addr, pair in data.items():
    print(f"{pair.base_token_symbol}: ${pair.price_usd}")
```

### search

```python
results = await client.search_pairs("BONK")
for pair in results:
    print(f"{pair.base_token_symbol} on {pair.dex_id}: ${pair.price_usd}")
```

### boosted tokens

```python
boosted = await client.get_boosted_tokens("solana")
# boosted tokens are paid promotions — treat with caution
```

### specific pair

```python
pair = await client.get_pair_by_address("solana", pair_address)
print(f"{pair.dex_id}: ${pair.price_usd}")
```

## DexPairData

all methods return `DexPairData` objects with these fields:

| field | type | description |
|---|---|---|
| `chain_id` | str | chain identifier |
| `dex_id` | str | dex identifier (raydium, uniswap_v3, etc.) |
| `pair_address` | str | pair contract address |
| `base_token_address` | str | base token mint/address |
| `base_token_symbol` | str | token symbol |
| `price_usd` | Decimal | current price in USD |
| `price_native` | Decimal | price in native token (SOL, ETH, etc.) |
| `liquidity_usd` | Decimal | total liquidity in USD |
| `volume_5m / 1h / 6h / 24h` | Decimal | volume by timeframe |
| `price_change_5m / 1h / 6h / 24h` | Decimal | price change % |
| `buys_5m / 1h / 24h` | int | buy transactions |
| `sells_5m / 1h / 24h` | int | sell transactions |
| `pair_created_at` | int | unix timestamp (ms) |

computed properties:

| property | description |
|---|---|
| `buy_sell_ratio_5m` | buy/sell ratio over 5 minutes (>1 = more buying) |
| `buy_sell_ratio_1h` | buy/sell ratio over 1 hour |
| `has_liquidity` | True if liquidity > $1000 |
| `pair_age_seconds` | pair age in seconds |

## configuration

```python
client = DexScreenerClient(
    rate_limit=5.0,      # requests/second (default: 5.0, dexscreener limit is ~300/min)
    cache_ttl=8.0,       # default cache TTL in seconds
)
```

## license

MIT
