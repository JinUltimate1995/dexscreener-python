# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-04-11

### Added

- `DexScreenerClient` — async client for the DexScreener API
- `DexPairData` — typed dataclass for parsed pair data with computed properties
- Rate limiting with token bucket (configurable requests/second)
- Automatic 429 retry with exponential backoff
- Global 429 cooldown (prevents request storms)
- Response caching with configurable TTL
- Batch token fetch (up to 30 tokens per request)
- Pair search by token name, symbol, or address
- Boosted token detection
- Works on any chain: Solana, Ethereum, Base, BSC, Arbitrum, etc.
- `async with` context manager support
