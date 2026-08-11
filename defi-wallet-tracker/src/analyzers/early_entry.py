"""Early entry detector — wallets that buy tokens <N hours after listing."""
from datetime import datetime, timedelta, timezone

from ..models.token import Token
from ..models.trade import Trade, TradeType


class EarlyEntryAnalyzer:
    def __init__(self, max_hours_after_listing: float = 4.0, min_multiplier: float = 5.0) -> None:
        self._window = timedelta(hours=max_hours_after_listing)
        self._min_multiplier = min_multiplier

    def find_early_buyers(
        self,
        token: Token,
        trades: list[Trade],
        current_price_usd: float | None = None,
    ) -> list[tuple[str, float]]:
        """Return [(wallet_address, multiplier_at_first_buy)] sorted by multiplier desc."""
        if token.listed_at is None:
            return []

        # Calculate multiplier (token price growth)
        if current_price_usd and token.listed_at:
            # Use peak_multiplier if set, else current price vs listing price estimate
            multiplier = token.peak_multiplier if token.peak_multiplier > 1 else 1.0
        else:
            multiplier = token.peak_multiplier

        if multiplier < self._min_multiplier:
            return []

        cutoff = token.listed_at + self._window
        results: list[tuple[str, float]] = []
        seen: set[str] = set()

        for trade in sorted(trades, key=lambda t: t.timestamp):
            if trade.trade_type != TradeType.BUY:
                continue
            if trade.wallet in seen:
                continue
            if trade.timestamp > cutoff:
                continue
            seen.add(trade.wallet)
            results.append((trade.wallet, multiplier))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def compute_token_multiplier(self, ohlcv: list[list]) -> float:
        """Calculate ATH/open multiplier from OHLCV candles [[ts, o, h, l, c, v], ...]."""
        if not ohlcv:
            return 1.0
        open_price = float(ohlcv[0][1])
        ath = max(float(c[2]) for c in ohlcv)  # index 2 = high
        if open_price <= 0:
            return 1.0
        return ath / open_price
