"""Win-rate calculator from a list of trades.

Pairs BUY and SELL trades per token per wallet, marks winners vs losers.
"""
from collections import defaultdict
from datetime import datetime

from ..models.trade import Trade, TradeType
from ..models.wallet import WalletScore


class WinRateAnalyzer:
    def __init__(self, min_sell_threshold: float = 0.1) -> None:
        # A sell returning at least this fraction of buy value counts as a completed trade
        self._min_sell_threshold = min_sell_threshold

    def analyze(self, wallet: str, trades: list[Trade], min_multiplier: float = 5.0) -> WalletScore:
        score = WalletScore(address=wallet)

        # Group by (chain, token_address)
        buckets: dict[tuple[str, str], list[Trade]] = defaultdict(list)
        for t in trades:
            buckets[(t.chain, t.token_address)].append(t)

        winners = 0
        losers = 0
        total_pnl = 0.0
        multipliers: list[float] = []
        early_entries: list[tuple[float, str]] = []  # (multiplier, token_symbol)

        for (chain, token_addr), token_trades in buckets.items():
            token_trades.sort(key=lambda x: x.timestamp)
            result = self._evaluate_position(token_trades)
            if result is None:
                continue
            pnl, multiplier, symbol = result
            total_pnl += pnl
            multipliers.append(multiplier)
            if pnl > 0:
                winners += 1
            else:
                losers += 1
            if multiplier >= min_multiplier:
                early_entries.append((multiplier, symbol))

        total = winners + losers
        score.total_trades = total
        score.winning_trades = winners
        score.losing_trades = losers
        score.win_rate = (winners / total * 100) if total > 0 else 0.0
        score.total_pnl_usd = total_pnl
        score.avg_pnl_per_trade = (total_pnl / total) if total > 0 else 0.0
        score.avg_multiplier = (sum(multipliers) / len(multipliers)) if multipliers else 0.0
        score.max_multiplier = max(multipliers, default=0.0)
        score.early_entries = len(early_entries)
        if early_entries:
            best = max(early_entries, key=lambda x: x[0])
            score.best_early_entry_x = best[0]
            score.best_early_token = best[1]
        return score

    def _evaluate_position(self, trades: list[Trade]) -> tuple[float, float, str] | None:
        """Return (pnl_usd, sell_price/buy_price multiplier, token_symbol)."""
        buys = [t for t in trades if t.trade_type == TradeType.BUY]
        sells = [t for t in trades if t.trade_type == TradeType.SELL]
        if not buys:
            return None

        buy_cost = sum(t.amount_usd for t in buys if t.amount_usd > 0)
        sell_revenue = sum(t.amount_usd for t in sells if t.amount_usd > 0)

        if buy_cost <= 0:
            return None
        if sell_revenue < buy_cost * self._min_sell_threshold:
            # Ignore tiny sells — position likely still open
            return None

        pnl = sell_revenue - buy_cost
        multiplier = sell_revenue / buy_cost if buy_cost > 0 else 0.0
        symbol = buys[0].token_symbol
        return pnl, multiplier, symbol
