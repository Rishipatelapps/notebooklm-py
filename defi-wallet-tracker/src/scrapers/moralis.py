"""Moralis Web3 API — wallet profitability + decoded swap history.

Free tier: 40,000 CU/day. https://moralis.io
Key endpoints:
  GET /wallets/{address}/profitability/summary  — win rate, PnL (EVM)
  GET /wallets/{address}/history                — decoded swaps timeline
  GET /{address}/erc20/transfers                — token transfer log
"""
from datetime import datetime, timezone

from ..models.trade import Trade, TradeType
from ..models.wallet import WalletScore
from .base import BaseClient

_BASE = "https://deep-index.moralis.io/api/v2.2"


class MoralisClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(_BASE, headers={"X-API-Key": api_key}, rate_limit_rps=2.0)

    async def get_profitability_summary(self, wallet: str, chain: str = "eth") -> dict:
        """Win rate, PnL summary per wallet."""
        return await self._get(f"/wallets/{wallet}/profitability/summary", params={"chain": chain})

    async def get_wallet_history(
        self,
        wallet: str,
        chain: str = "eth",
        from_date: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Decoded transaction + swap history."""
        params: dict = {"chain": chain, "limit": limit, "order": "DESC"}
        if from_date:
            params["from_date"] = from_date
        if cursor:
            params["cursor"] = cursor
        return await self._get(f"/wallets/{wallet}/history", params=params)

    async def get_token_transfers(
        self,
        wallet: str,
        chain: str = "eth",
        from_date: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """ERC-20 token transfer list."""
        params: dict = {"chain": chain, "limit": limit}
        if from_date:
            params["from_date"] = from_date
        data = await self._get(f"/{wallet}/erc20/transfers", params=params)
        return (data or {}).get("result", [])

    async def build_wallet_score(self, wallet: str, chain: str = "eth") -> WalletScore:
        score = WalletScore(address=wallet, source="moralis", chains=[chain])
        try:
            summary = await self.get_profitability_summary(wallet, chain)
            score.win_rate = float((summary or {}).get("winrate") or 0)
            score.total_trades = int((summary or {}).get("total_count_of_trades") or 0)
            score.winning_trades = int((summary or {}).get("total_count_of_profitable_trades") or 0)
            score.losing_trades = score.total_trades - score.winning_trades
            score.total_pnl_usd = float((summary or {}).get("total_realized_profit_usd") or 0)
            score.avg_multiplier = float((summary or {}).get("average_buy_sell_ratio") or 0)
            score.raw["moralis_summary"] = summary
        except Exception:
            pass
        return score

    def parse_swap_trades(self, history_result: dict, chain: str) -> list[Trade]:
        """Extract swap trades from wallet history response."""
        trades: list[Trade] = []
        for item in (history_result or {}).get("result", []):
            if item.get("category") not in ("token purchase", "token sale"):
                continue
            trade_type = TradeType.BUY if item["category"] == "token purchase" else TradeType.SELL
            ts_str = item.get("block_timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)
            for tx_detail in item.get("erc20_transfers", []):
                trades.append(Trade(
                    tx_hash=item.get("hash", ""),
                    wallet=item.get("from_address", ""),
                    token_address=tx_detail.get("address", ""),
                    token_symbol=tx_detail.get("token_symbol", ""),
                    chain=chain,
                    trade_type=trade_type,
                    amount_usd=float(tx_detail.get("value_formatted") or 0),
                    amount_tokens=float(tx_detail.get("value_formatted") or 0),
                    price_usd=0.0,
                    timestamp=ts,
                ))
        return trades
