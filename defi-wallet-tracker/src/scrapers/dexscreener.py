"""DexScreener API client — no auth required, ~300 req/min."""
from datetime import datetime, timezone

from ..models.token import Token
from .base import BaseClient

_BASE = "https://api.dexscreener.com"


class DexScreenerClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(_BASE, rate_limit_rps=4.0)

    async def get_new_pairs(self, chain: str, limit: int = 50) -> list[Token]:
        """Return recently listed pairs on a chain."""
        data = await self._get(f"/token-pairs/v1/{chain}/new", params={"limit": limit})
        return [self._parse_pair(p, chain) for p in (data or []) if p]

    async def get_trending_tokens(self, chain: str = "") -> list[Token]:
        """Return boosted/trending tokens (optionally filtered by chain)."""
        data = await self._get("/token-boosts/top/v1")
        pairs: list[Token] = []
        for item in (data or []):
            if chain and item.get("chainId", "") != chain:
                continue
            pairs.append(self._parse_boosted(item))
        return pairs

    async def get_token_pairs(self, chain: str, token_address: str) -> list[Token]:
        """All pairs for a specific token address."""
        data = await self._get(f"/token-pairs/v1/{chain}/{token_address}")
        return [self._parse_pair(p, chain) for p in (data or []) if p]

    async def search_tokens(self, query: str) -> list[Token]:
        """Text search across all chains."""
        data = await self._get("/latest/dex/search", params={"q": query})
        pairs = (data or {}).get("pairs") or []
        return [self._parse_pair(p, p.get("chainId", "")) for p in pairs]

    def _parse_pair(self, p: dict, chain: str) -> Token:
        base = p.get("baseToken", {})
        price_usd = float(p.get("priceUsd") or 0)
        liquidity = float((p.get("liquidity") or {}).get("usd") or 0)
        volume_24h = float((p.get("volume") or {}).get("h24") or 0)
        price_change = float((p.get("priceChange") or {}).get("h24") or 0)
        created_ts = p.get("pairCreatedAt")
        listed_at = datetime.fromtimestamp(created_ts / 1000, tz=timezone.utc) if created_ts else None
        return Token(
            address=base.get("address", ""),
            symbol=base.get("symbol", ""),
            name=base.get("name", ""),
            chain=chain,
            price_usd=price_usd,
            liquidity_usd=liquidity,
            volume_24h=volume_24h,
            price_change_24h=price_change,
            listed_at=listed_at,
            pair_address=p.get("pairAddress", ""),
            dex=p.get("dexId", ""),
        )

    def _parse_boosted(self, item: dict) -> Token:
        return Token(
            address=item.get("tokenAddress", ""),
            symbol="",
            name=item.get("description", ""),
            chain=item.get("chainId", ""),
            dex=item.get("url", ""),
        )
