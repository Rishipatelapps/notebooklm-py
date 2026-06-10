"""
Score wallets using only GeckoTerminal data — no API key required.

Strategy:
  For each candidate wallet, count how many distinct high-multiplier pools
  they appeared in as early buyers. Wallets present in 2+ such pools get
  a provisional win_rate estimate and are passed forward for Blockscout
  on-chain verification.
"""
from collections import defaultdict

from ..models.token import Token
from ..models.trade import Trade, TradeType
from ..models.wallet import WalletScore


class GeckoScorer:
    def __init__(self, min_multiplier: float = 5.0, max_entry_hours: float = 4.0) -> None:
        self._min_mult = min_multiplier
        self._max_hours = max_entry_hours

    def score_from_pool_appearances(
        self,
        pool_appearances: dict[str, list[tuple[Token, float]]],
        # wallet_address → [(token, multiplier), ...]
    ) -> list[WalletScore]:
        """
        pool_appearances: mapping of wallet → pools where it was an early buyer.
        Returns WalletScore objects ranked by number of early entries.
        """
        scores: list[WalletScore] = []
        for wallet, entries in pool_appearances.items():
            if not entries:
                continue
            multipliers = [m for _, m in entries]
            score = WalletScore(
                address=wallet,
                source="gecko_terminal",
                total_trades=len(entries),
                winning_trades=len(entries),  # all early entries = wins
                losing_trades=0,
                # Provisional: we'll say 100% since we only see early buys here;
                # Blockscout pass will refine this with sell data
                win_rate=100.0,
                avg_multiplier=sum(multipliers) / len(multipliers),
                max_multiplier=max(multipliers),
                early_entries=len(entries),
                best_early_entry_x=max(multipliers),
                best_early_token=next(
                    (t.symbol for t, m in entries if m == max(multipliers)), ""
                ),
            )
            scores.append(score)
        return sorted(scores, key=lambda s: s.early_entries, reverse=True)

    def build_appearances(
        self,
        token: Token,
        early_buyers: list[tuple[str, float]],
        appearances: dict[str, list[tuple[Token, float]]] | None = None,
    ) -> dict[str, list[tuple[Token, float]]]:
        """Accumulate pool appearances across multiple tokens."""
        if appearances is None:
            appearances = defaultdict(list)
        for wallet, mult in early_buyers:
            appearances[wallet].append((token, mult))
        return appearances
