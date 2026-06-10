"""Etherscan V2 unified multichain API — one key for 60+ chains.

Free: 5 req/s, 100k/day. https://etherscan.io/myapikey
Supports: ETH(1), BSC(56), Base(8453), Arbitrum(42161), Polygon(137),
          Optimism(10), Avalanche(43114)
"""
from datetime import datetime, timezone

from ..models.trade import Trade, TradeType
from .base import BaseClient

_BASE = "https://api.etherscan.io/v2"


class EtherscanClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(_BASE, rate_limit_rps=4.0)
        self._api_key = api_key

    async def get_token_transfers(
        self,
        wallet: str,
        chain_id: int,
        start_block: int = 0,
        end_block: int = 99999999,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict]:
        """ERC-20 token transfer list for a wallet."""
        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "tokentx",
            "address": wallet,
            "startblock": start_block,
            "endblock": end_block,
            "page": page,
            "offset": offset,
            "sort": "desc",
            "apikey": self._api_key,
        }
        data = await self._get("/api", params=params)
        if (data or {}).get("status") != "1":
            return []
        return data["result"]

    async def get_normal_transactions(
        self,
        wallet: str,
        chain_id: int,
        start_block: int = 0,
        page: int = 1,
        offset: int = 100,
    ) -> list[dict]:
        """Normal (native) transactions for a wallet."""
        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "txlist",
            "address": wallet,
            "startblock": start_block,
            "page": page,
            "offset": offset,
            "sort": "desc",
            "apikey": self._api_key,
        }
        data = await self._get("/api", params=params)
        if (data or {}).get("status") != "1":
            return []
        return data["result"]

    def transfers_to_trades(self, transfers: list[dict], wallet: str, chain: str) -> list[Trade]:
        """Convert raw Etherscan token transfers into Trade objects."""
        trades: list[Trade] = []
        wallet_lower = wallet.lower()
        for tx in transfers:
            is_incoming = tx.get("to", "").lower() == wallet_lower
            trade_type = TradeType.BUY if is_incoming else TradeType.SELL
            ts = datetime.fromtimestamp(int(tx.get("timeStamp", 0)), tz=timezone.utc)
            decimals = int(tx.get("tokenDecimal") or 18)
            amount_tokens = int(tx.get("value", 0)) / (10 ** decimals)
            trades.append(Trade(
                tx_hash=tx.get("hash", ""),
                wallet=wallet,
                token_address=tx.get("contractAddress", ""),
                token_symbol=tx.get("tokenSymbol", ""),
                chain=chain,
                trade_type=trade_type,
                amount_usd=0.0,
                amount_tokens=amount_tokens,
                price_usd=0.0,
                timestamp=ts,
                extra={
                    "block_number": tx.get("blockNumber"),
                    "gas_used": tx.get("gasUsed"),
                },
            ))
        return trades
