"""
Blockscout public API client — no API key required.

Public instances:
  ETH:       https://eth.blockscout.com/api/v2
  BSC:       https://bsc.blockscout.com/api/v2
  Base:      https://base.blockscout.com/api/v2
  Arbitrum:  https://arbitrum.blockscout.com/api/v2
  Polygon:   https://polygon.blockscout.com/api/v2
  Optimism:  https://optimism.blockscout.com/api/v2
  Avalanche: https://avalanche.blockscout.com/api/v2
"""
from datetime import datetime, timezone

from ..models.trade import Trade, TradeType
from ..models.wallet import WalletScore
from .base import BaseClient

# Public Blockscout instances per chain slug
BLOCKSCOUT_HOSTS: dict[str, str] = {
    "eth": "https://eth.blockscout.com",
    "bsc": "https://bsc.blockscout.com",
    "base": "https://base.blockscout.com",
    "arbitrum": "https://arbitrum.blockscout.com",
    "polygon": "https://polygon.blockscout.com",
    "optimism": "https://optimism.blockscout.com",
    "avalanche": "https://avalanche.blockscout.com",
}


class BlockscoutClient(BaseClient):
    def __init__(self, chain: str) -> None:
        host = BLOCKSCOUT_HOSTS.get(chain, "https://eth.blockscout.com")
        super().__init__(f"{host}/api/v2", rate_limit_rps=2.0)
        self._chain = chain

    async def get_token_transfers(
        self,
        address: str,
        limit: int = 50,
        page_params: dict | None = None,
    ) -> dict:
        """ERC-20 token transfer list for a wallet address."""
        params: dict = {"filter": "to,from", "limit": limit}
        if page_params:
            params.update(page_params)
        return await self._get(f"/addresses/{address}/token-transfers", params=params)

    async def get_address_info(self, address: str) -> dict:
        """Basic address info including tx count."""
        return await self._get(f"/addresses/{address}")

    async def get_transactions(self, address: str, limit: int = 50) -> dict:
        """Transaction list for a wallet."""
        return await self._get(f"/addresses/{address}/transactions", params={"limit": limit})

    def transfers_to_trades(self, data: dict, wallet: str) -> list[Trade]:
        """Parse Blockscout v2 token-transfers response into Trade objects."""
        trades: list[Trade] = []
        wallet_lower = wallet.lower()
        for item in (data or {}).get("items", []):
            token = item.get("token", {})
            ts_str = item.get("timestamp", "")
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                ts = datetime.now(tz=timezone.utc)

            is_incoming = (item.get("to", {}).get("hash", "")).lower() == wallet_lower
            trade_type = TradeType.BUY if is_incoming else TradeType.SELL

            decimals = int(token.get("decimals") or 18)
            try:
                amount_tokens = int(item.get("total", {}).get("value", 0)) / (10 ** decimals)
            except Exception:
                amount_tokens = 0.0

            # Use token exchange rate if available
            price_usd = float(token.get("exchange_rate") or 0)
            amount_usd = amount_tokens * price_usd

            trades.append(Trade(
                tx_hash=item.get("tx_hash", ""),
                wallet=wallet,
                token_address=(token.get("address") or "").lower(),
                token_symbol=token.get("symbol", ""),
                chain=self._chain,
                trade_type=trade_type,
                amount_usd=amount_usd,
                amount_tokens=amount_tokens,
                price_usd=price_usd,
                timestamp=ts,
            ))
        return trades

    async def build_wallet_score_from_trades(self, wallet: str, pages: int = 3) -> WalletScore:
        """Build a WalletScore by fetching on-chain transfers and computing PnL."""
        from ..analyzers.win_rate import WinRateAnalyzer
        all_trades: list[Trade] = []
        next_params: dict | None = None

        for _ in range(pages):
            try:
                data = await self.get_token_transfers(wallet, limit=50, page_params=next_params)
                all_trades.extend(self.transfers_to_trades(data, wallet))
                next_page = (data or {}).get("next_page_params")
                if not next_page:
                    break
                next_params = next_page
            except Exception:
                break

        analyzer = WinRateAnalyzer()
        score = analyzer.analyze(wallet, all_trades)
        score.source = "blockscout"
        score.chains = [self._chain]
        return score
