"""Birdeye Data API client — multi-chain price and trader analytics.

Free tier available at bds.birdeye.so. Best-in-class for Solana pricing and
top-trader data across Solana, Ethereum, BSC, Base, Arbitrum, and more.

Key endpoints used:
  GET /defi/price                   — current price (single token)
  GET /defi/multi_price             — batch current prices
  GET /defi/token_trending          — trending tokens with price change
  GET /defi/v2/tokens/new_listing   — newly listed tokens
  GET /defi/v2/tokens/top_traders   — top traders by token (key for discovery)
  GET /defi/v3/token/trade-data/single — 24h volume, buys, sells
"""
import asyncio
from datetime import datetime, timezone

from .base import BaseClient

_BASE = "https://public-api.birdeye.so"

BIRDEYE_CHAINS: dict[str, str] = {
    "eth": "ethereum",
    "bsc": "bsc",
    "base": "base",
    "arbitrum": "arbitrum",
    "polygon": "polygon",
    "optimism": "optimism",
    "avalanche": "avalanche",
    "solana": "solana",
    "zksync": "zksync",
}


class BirdeyeClient(BaseClient):
    """
    Birdeye multi-chain price and analytics client.
    Rate limits: 100 req/min on free tier; use rate_limit_rps=1.5 to stay safe.
    """

    def __init__(self, api_key: str, chain: str = "solana") -> None:
        chain_id = BIRDEYE_CHAINS.get(chain, "solana")
        super().__init__(
            _BASE,
            headers={
                "X-API-KEY": api_key,
                "x-chain": chain_id,
                "Accept": "application/json",
            },
            rate_limit_rps=1.5,
        )
        self._api_key = api_key
        self._chain = chain

    def _chain_headers(self, chain: str) -> dict[str, str]:
        return {"X-API-KEY": self._api_key, "x-chain": BIRDEYE_CHAINS.get(chain, "solana")}

    async def get_price(self, token_address: str, chain: str | None = None) -> float:
        """Current USD price for a token. Returns 0.0 on failure."""
        try:
            data = await self._get(
                "/defi/price",
                params={"address": token_address},
                headers=self._chain_headers(chain or self._chain),
            )
            return float((data or {}).get("data", {}).get("value") or 0.0)
        except Exception:
            return 0.0

    async def get_price_with_liquidity(
        self, token_address: str, chain: str | None = None
    ) -> dict:
        """Current price plus 24h change and liquidity."""
        try:
            data = await self._get(
                "/defi/price",
                params={"address": token_address, "include_liquidity": True},
                headers=self._chain_headers(chain or self._chain),
            )
            return (data or {}).get("data") or {}
        except Exception:
            return {}

    async def get_batch_prices(
        self, token_addresses: list[str], chain: str
    ) -> dict[str, float]:
        """Batch price lookup: up to 100 tokens per call. Returns {addr_lower: price_usd}."""
        if not token_addresses:
            return {}
        # Birdeye multi_price accepts comma-separated addresses via POST body
        try:
            chunk = token_addresses[:100]
            data = await self._post(
                "/defi/multi_price",
                json={"list_address": ",".join(chunk)},
                headers=self._chain_headers(chain),
            )
            prices = {}
            for addr, info in ((data or {}).get("data") or {}).items():
                val = (info or {}).get("value")
                if val is not None:
                    prices[addr.lower()] = float(val)
            return prices
        except Exception:
            return {}

    async def get_trending_tokens(
        self, chain: str, limit: int = 50
    ) -> list[dict]:
        """
        Top trending tokens by rank — rank #1 is most trending.
        Returns list of {address, symbol, price, price_change_24h, liquidity}.
        """
        try:
            data = await self._get(
                "/defi/token_trending",
                # sort_type asc = rank 1 first (most trending)
                params={"sort_by": "rank", "sort_type": "asc", "offset": 0, "limit": limit},
                headers=self._chain_headers(chain),
            )
            # Response: data.tokens (list)
            tokens = ((data or {}).get("data") or {}).get("tokens") or []
            results = []
            for item in tokens:
                results.append({
                    "address": item.get("address", ""),
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "price": float(item.get("price") or 0),
                    "price_change_24h": float(item.get("price24hChangePercent") or 0),
                    "liquidity": float(item.get("liquidity") or 0),
                    "volume_24h": float(item.get("volume24hUSD") or 0),
                    "rank": int(item.get("rank") or 9999),
                    "chain": chain,
                })
            return results
        except Exception:
            return []

    async def get_new_listings(
        self, chain: str, limit: int = 20, min_liquidity_usd: float = 5_000
    ) -> list[dict]:
        """
        Newly listed tokens — find tokens from the last 24-72h.
        Returns list of {address, symbol, price_change_24h, liquidity, listed_at}.
        """
        try:
            data = await self._get(
                "/defi/v2/tokens/new_listing",
                params={"limit": limit, "meme_platform_enabled": False},
                headers=self._chain_headers(chain),
            )
            items = ((data or {}).get("data") or {}).get("items") or []
            results = []
            for item in items:
                liquidity = float(item.get("liquidity") or 0)
                if liquidity < min_liquidity_usd:
                    continue
                results.append({
                    "address": item.get("address", ""),
                    "symbol": item.get("symbol", ""),
                    "name": item.get("name", ""),
                    "price_change_24h": float(item.get("priceChange24hPercent") or 0),
                    "liquidity": liquidity,
                    "volume_24h": float(item.get("v24hUSD") or 0),
                    "chain": chain,
                })
            return results
        except Exception:
            return []

    async def get_top_traders(
        self, token_address: str, chain: str, limit: int = 20, timeframe: str = "24h"
    ) -> list[dict]:
        """
        Top traders for a specific token — returns the wallets that traded most.
        timeframe: "30m", "1h", "2h", "4h", "6h", "8h", "12h", "24h", "48h", "1w", "1m"
        Returns [{address, buy_volume_usd, sell_volume_usd, net_volume_usd, trades}].
        """
        try:
            data = await self._get(
                "/defi/v2/tokens/top_traders",
                params={
                    "address": token_address,
                    "time_frame": timeframe,
                    "sort_type": "desc",
                    "sort_by": "volume",
                    "offset": 0,
                    "limit": limit,
                },
                headers=self._chain_headers(chain),
            )
            items = ((data or {}).get("data") or {}).get("items") or []
            results = []
            for item in items:
                results.append({
                    "address": item.get("address", ""),
                    "buy_volume_usd": float(item.get("volumeBuy") or 0),
                    "sell_volume_usd": float(item.get("volumeSell") or 0),
                    "net_volume_usd": float(item.get("volume") or 0),
                    "trades": int(item.get("tradingCount") or 0),
                    "tags": item.get("tags") or [],
                })
            return results
        except Exception:
            return []

    async def get_token_trade_data(self, token_address: str, chain: str) -> dict:
        """24h trade stats for a token: buys, sells, buyers, sellers, volume."""
        try:
            data = await self._get(
                "/defi/v3/token/trade-data/single",
                params={"address": token_address},
                headers=self._chain_headers(chain),
            )
            return (data or {}).get("data") or {}
        except Exception:
            return {}
