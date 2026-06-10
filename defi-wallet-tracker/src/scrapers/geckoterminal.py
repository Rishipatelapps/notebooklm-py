"""GeckoTerminal API client — free, no auth, 30 req/min."""
from datetime import datetime, timezone

from ..models.token import Token
from ..models.trade import Trade, TradeType
from .base import BaseClient

_BASE = "https://api.geckoterminal.com/api/v2"


class GeckoTerminalClient(BaseClient):
    def __init__(self) -> None:
        super().__init__(_BASE, rate_limit_rps=0.5)  # ~30/min → 0.5/s

    async def get_new_pools(self, network: str, page: int = 1) -> list[Token]:
        """Recently created pools on a network."""
        data = await self._get(f"/networks/{network}/new_pools", params={"page": page})
        return [self._parse_pool(p, network) for p in (data or {}).get("data", [])]

    async def get_trending_pools(self, network: str = "") -> list[Token]:
        """Trending pools globally or per network."""
        path = f"/networks/{network}/trending_pools" if network else "/networks/trending_pools"
        data = await self._get(path)
        return [self._parse_pool(p, network or p.get("relationships", {}).get("network", {}).get("data", {}).get("id", ""))
                for p in (data or {}).get("data", [])]

    async def get_pool_trades(self, network: str, pool_address: str, limit: int = 100) -> list[Trade]:
        """Recent trades for a pool — returns maker (wallet) addresses."""
        data = await self._get(
            f"/networks/{network}/pools/{pool_address}/trades",
            params={"trade_volume_in_usd_greater_than": 100},
        )
        trades: list[Trade] = []
        for item in (data or {}).get("data", []):
            attrs = item.get("attributes", {})
            trade_type = TradeType.BUY if attrs.get("kind") == "buy" else TradeType.SELL
            ts_str = attrs.get("block_timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)
            trades.append(Trade(
                tx_hash=attrs.get("tx_hash", ""),
                wallet=attrs.get("tx_from_address", ""),
                token_address="",
                token_symbol="",
                chain=network,
                trade_type=trade_type,
                amount_usd=float(attrs.get("volume_in_usd") or 0),
                amount_tokens=float(attrs.get("to_token_amount") or attrs.get("from_token_amount") or 0),
                price_usd=float(attrs.get("price_to_in_usd") or attrs.get("price_from_in_usd") or 0),
                timestamp=ts,
            ))
        return trades

    async def get_pool_ohlcv(self, network: str, pool_address: str, timeframe: str = "day",
                              limit: int = 100) -> list[dict]:
        """OHLCV candles for ATH multiplier calculation."""
        data = await self._get(
            f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}",
            params={"limit": limit, "currency": "usd"},
        )
        return (data or {}).get("data", {}).get("attributes", {}).get("ohlcv_list", [])

    def _parse_pool(self, item: dict, network: str) -> Token:
        attrs = item.get("attributes", {})
        created_ts = attrs.get("pool_created_at", "")
        try:
            listed_at = datetime.fromisoformat(created_ts.replace("Z", "+00:00"))
        except Exception:
            listed_at = None
        return Token(
            address=attrs.get("base_token_price_usd", ""),  # placeholder — pool addr in relationships
            symbol=attrs.get("name", "").split(" / ")[0],
            name=attrs.get("name", ""),
            chain=network,
            price_usd=float(attrs.get("base_token_price_usd") or 0),
            market_cap=float(attrs.get("market_cap_usd") or 0),
            liquidity_usd=float(attrs.get("reserve_in_usd") or 0),
            volume_24h=float((attrs.get("volume_usd") or {}).get("h24") or 0),
            price_change_24h=float((attrs.get("price_change_percentage") or {}).get("h24") or 0),
            listed_at=listed_at,
            pair_address=item.get("id", "").split("_")[-1],
            dex="",
            extra={"gecko_id": item.get("id", "")},
        )
