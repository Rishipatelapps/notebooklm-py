"""Cielo Finance API — win rates, PnL, profitability stats.

Free tier: credit-based. See https://developer.cielo.finance
Endpoints used:
  GET /api/v1/stats/profitability?wallet=... — win rate, realized PnL
  GET /api/v1/stats/trading?wallet=...        — trade count breakdown
  GET /api/v1/pnl/tokens?wallet=...           — per-token PnL history
"""
from ..models.wallet import WalletScore
from .base import BaseClient

_BASE = "https://feed-api.cielo.finance"


class CieloClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(_BASE, headers={"X-API-KEY": api_key}, rate_limit_rps=1.0)

    async def get_profitability(self, wallet: str, chain: str = "") -> dict:
        """Returns win_rate, realized_profit, unrealized_profit fields."""
        params: dict = {"wallet": wallet}
        if chain:
            params["chain"] = chain
        return await self._get("/api/v1/stats/profitability", params=params)

    async def get_trading_stats(self, wallet: str, chain: str = "") -> dict:
        """Returns total_trades, wins, losses, win_rate, roi."""
        params: dict = {"wallet": wallet}
        if chain:
            params["chain"] = chain
        return await self._get("/api/v1/stats/trading", params=params)

    async def get_token_pnl(self, wallet: str, chain: str = "") -> list[dict]:
        """Per-token realized PnL list."""
        params: dict = {"wallet": wallet}
        if chain:
            params["chain"] = chain
        data = await self._get("/api/v1/pnl/tokens", params=params)
        return (data or {}).get("data", [])

    async def build_wallet_score(self, wallet: str) -> WalletScore:
        """Hydrate a WalletScore from Cielo data."""
        score = WalletScore(address=wallet, source="cielo")
        try:
            prof = await self.get_profitability(wallet)
            stats = await self.get_trading_stats(wallet)
            score.win_rate = float((stats or {}).get("win_rate") or (prof or {}).get("win_rate") or 0)
            score.total_trades = int((stats or {}).get("total_trades") or 0)
            score.winning_trades = int((stats or {}).get("wins") or 0)
            score.losing_trades = int((stats or {}).get("losses") or 0)
            score.total_pnl_usd = float((prof or {}).get("realized_profit") or 0)
            score.raw["cielo_profitability"] = prof
            score.raw["cielo_trading"] = stats
        except Exception:
            pass
        return score
