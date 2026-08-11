"""
Full on-chain wallet scorer using Etherscan + CoinGecko.

Strategy per wallet:
  1. Pull last N days of ERC-20 transfers via Etherscan V2
  2. Group transfers into buy/sell pairs per token
  3. Enrich with CoinGecko historical prices where available
  4. Compute real USD PnL per position → win rate, avg multiplier
"""
import asyncio
from datetime import datetime, timedelta, timezone

from ..chains import get_chain
from ..models.trade import Trade, TradeType
from ..models.wallet import WalletScore
from ..scrapers.coingecko import CoinGeckoClient
from ..scrapers.etherscan import EtherscanClient


class EtherscanWalletScorer:
    def __init__(
        self,
        etherscan_key: str,
        coingecko_key: str = "",
        lookback_days: int = 90,
        min_position_usd: float = 50.0,
        min_multiplier: float = 5.0,
    ) -> None:
        self._etherscan_key = etherscan_key
        self._coingecko_key = coingecko_key
        self._lookback_days = lookback_days
        self._min_position_usd = min_position_usd
        self._min_multiplier = min_multiplier

    async def score_wallet(self, wallet: str, chain: str) -> WalletScore:
        score = WalletScore(address=wallet, source="etherscan", chains=[chain])
        chain_obj = get_chain(chain)
        if not chain_obj.is_evm or chain_obj.etherscan_chain_id == 0:
            return score

        since = datetime.now(tz=timezone.utc) - timedelta(days=self._lookback_days)

        async with EtherscanClient(self._etherscan_key) as escan:
            raw_transfers = await escan.get_token_transfers(
                wallet, chain_obj.etherscan_chain_id,
                page=1, offset=100  # 100 is enough to detect trade history
            )
            trades = escan.transfers_to_trades(raw_transfers, wallet, chain)

        if not trades:
            return score

        # Enrich with CoinGecko prices if key available
        if self._coingecko_key:
            trades = await self._enrich_with_prices(trades, chain)

        # Score from trades
        return self._compute_score(wallet, chain, trades)

    async def _enrich_with_prices(self, trades: list[Trade], chain: str) -> list[Trade]:
        """Fill in amount_usd using CoinGecko batch current prices (fast — no per-trade API calls)."""
        token_addrs = list({t.token_address for t in trades if t.token_address})
        if not token_addrs:
            return trades

        async with CoinGeckoClient(self._coingecko_key) as gecko:
            current_prices = await gecko.get_batch_prices(chain, token_addrs)

        enriched: list[Trade] = []
        for trade in trades:
            if trade.amount_usd > 0:
                enriched.append(trade)
                continue
            price = current_prices.get((trade.token_address or "").lower(), 0.0)
            if price > 0:
                trade.price_usd = price
                trade.amount_usd = trade.amount_tokens * price
            enriched.append(trade)

        return enriched

    def _compute_score(self, wallet: str, chain: str, trades: list[Trade]) -> WalletScore:
        from .win_rate import WinRateAnalyzer
        analyzer = WinRateAnalyzer(min_sell_threshold=0.05)
        score = analyzer.analyze(wallet, trades, min_multiplier=self._min_multiplier)
        score.source = "etherscan+coingecko" if self._coingecko_key else "etherscan"
        score.chains = [chain]
        return score

    async def score_many(
        self,
        wallets: list[tuple[str, str]],  # [(address, chain), ...]
        concurrency: int = 5,
    ) -> list[WalletScore]:
        sem = asyncio.Semaphore(concurrency)

        async def _bounded(addr: str, chain: str) -> WalletScore:
            async with sem:
                try:
                    return await self.score_wallet(addr, chain)
                except Exception:
                    return WalletScore(address=addr, chains=[chain], source="error")

        results = await asyncio.gather(*[_bounded(a, c) for a, c in wallets])
        return [r for r in results if isinstance(r, WalletScore)]
