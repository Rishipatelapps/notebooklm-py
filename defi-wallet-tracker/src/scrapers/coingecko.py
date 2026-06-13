"""CoinGecko Pro API — historical token prices for PnL calculation.

Pro key: 50 calls/min, 10k/month. https://www.coingecko.com/en/api
Key endpoints:
  GET /coins/{network}/contract/{address}          — token metadata + current price
  GET /coins/{id}/market_chart/range               — historical OHLC by timestamp range
  GET /coins/list                                  — full token id list
  GET /simple/token_price/{network}               — batch current prices
"""
import asyncio
from datetime import datetime, timezone
from functools import lru_cache

from .base import BaseClient

_BASE = "https://api.coingecko.com/api/v3"  # Demo/free key; use pro-api.coingecko.com for paid

# CoinGecko network IDs per chain slug
GECKO_NETWORKS: dict[str, str] = {
    "eth": "ethereum",
    "bsc": "binance-smart-chain",
    "base": "base",
    "arbitrum": "arbitrum-one",
    "polygon": "polygon-pos",
    "optimism": "optimistic-ethereum",
    "avalanche": "avalanche",
    "solana": "solana",
}


class CoinGeckoClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(_BASE, headers={"x-cg-demo-api-key": api_key}, rate_limit_rps=0.8)
        self._price_cache: dict[str, dict[int, float]] = {}  # (token_addr, ts) → price_usd

    async def get_token_info(self, chain: str, token_address: str) -> dict:
        """Token metadata including current price and market data."""
        network = GECKO_NETWORKS.get(chain, "ethereum")
        try:
            return await self._get(f"/coins/{network}/contract/{token_address.lower()}")
        except Exception:
            return {}

    async def get_price_at_timestamp(
        self, chain: str, token_address: str, timestamp: datetime
    ) -> float:
        """Get token USD price closest to a given timestamp."""
        network = GECKO_NETWORKS.get(chain, "ethereum")
        cache_key = f"{chain}:{token_address.lower()}"
        ts_unix = int(timestamp.timestamp())

        # Check cache
        if cache_key in self._price_cache:
            prices = self._price_cache[cache_key]
            # Find closest cached price (within 1 hour = 3600s)
            closest = min(prices.keys(), key=lambda t: abs(t - ts_unix))
            if abs(closest - ts_unix) < 3600:
                return prices[closest]

        # Fetch 7-day range around timestamp
        from_ts = ts_unix - 3600
        to_ts = ts_unix + 86400

        try:
            data = await self._get(
                f"/coins/{network}/contract/{token_address.lower()}/market_chart/range",
                params={"vs_currency": "usd", "from": from_ts, "to": to_ts},
            )
            prices_raw = (data or {}).get("prices", [])
            if prices_raw:
                price_map = {int(ts_ms / 1000): price for ts_ms, price in prices_raw}
                if cache_key not in self._price_cache:
                    self._price_cache[cache_key] = {}
                self._price_cache[cache_key].update(price_map)
                closest = min(price_map.keys(), key=lambda t: abs(t - ts_unix))
                return price_map[closest]
        except Exception:
            pass
        return 0.0

    async def get_batch_prices(self, chain: str, token_addresses: list[str]) -> dict[str, float]:
        """Current prices for multiple tokens at once."""
        if not token_addresses:
            return {}
        network = GECKO_NETWORKS.get(chain, "ethereum")
        addrs = ",".join(a.lower() for a in token_addresses[:100])
        try:
            data = await self._get(
                f"/simple/token_price/{network}",
                params={"contract_addresses": addrs, "vs_currencies": "usd"},
            )
            return {addr: (v.get("usd") or 0.0) for addr, v in (data or {}).items()}
        except Exception:
            return {}

    async def get_token_ath_multiplier(
        self, chain: str, token_address: str, since_timestamp: datetime
    ) -> float:
        """Compute ATH/listing-price multiplier since a given date."""
        network = GECKO_NETWORKS.get(chain, "ethereum")
        from_ts = int(since_timestamp.timestamp())
        to_ts = int(datetime.now(tz=timezone.utc).timestamp())
        try:
            data = await self._get(
                f"/coins/{network}/contract/{token_address.lower()}/market_chart/range",
                params={"vs_currency": "usd", "from": from_ts, "to": to_ts},
            )
            prices = [p for _, p in (data or {}).get("prices", [])]
            if len(prices) < 2:
                return 1.0
            open_price = prices[0]
            ath = max(prices)
            return ath / open_price if open_price > 0 else 1.0
        except Exception:
            return 1.0
