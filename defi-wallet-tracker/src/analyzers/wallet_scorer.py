"""Aggregate wallet scores from multiple data sources into a unified leaderboard."""
from ..models.wallet import WalletScore


class WalletScorer:
    """Merge scores from multiple sources and compute a final composite score."""

    def merge(self, scores: list[WalletScore]) -> WalletScore:
        """Merge multiple WalletScore objects for the same wallet into one."""
        if not scores:
            raise ValueError("scores list is empty")

        merged = WalletScore(
            address=scores[0].address,
            label=next((s.label for s in scores if s.label), ""),
            chains=list({c for s in scores for c in s.chains}),
            source=", ".join({s.source for s in scores if s.source}),
        )

        # Prefer the source with the most trades for primary metrics
        primary = max(scores, key=lambda s: s.total_trades)
        merged.total_trades = primary.total_trades
        merged.winning_trades = primary.winning_trades
        merged.losing_trades = primary.losing_trades
        merged.win_rate = primary.win_rate
        merged.total_pnl_usd = primary.total_pnl_usd
        merged.avg_pnl_per_trade = primary.avg_pnl_per_trade
        merged.avg_multiplier = primary.avg_multiplier
        merged.max_multiplier = max(s.max_multiplier for s in scores)
        merged.early_entries = max(s.early_entries for s in scores)
        merged.best_early_entry_x = max(s.best_early_entry_x for s in scores)
        merged.best_early_token = primary.best_early_token
        merged.active_since = min((s.active_since for s in scores if s.active_since), default=None)
        merged.last_active = max((s.last_active for s in scores if s.last_active), default=None)

        for s in scores:
            merged.raw.update(s.raw)

        return merged

    def rank(self, scores: list[WalletScore]) -> list[WalletScore]:
        """Sort wallets by composite score descending."""
        return sorted(scores, key=lambda s: s.score, reverse=True)

    def filter_smart_money(
        self,
        scores: list[WalletScore],
        min_win_rate: float = 85.0,
        min_trades: int = 10,
        min_early_entries: int = 1,
    ) -> list[WalletScore]:
        """Return only wallets meeting the smart-money criteria.

        Two-track filter:
          Track A (full history):  win_rate ≥ threshold AND total_trades ≥ min_trades
          Track B (early buyer):   early_entries ≥ 2 (caught multiple high-mult tokens)
        Either track passes. This handles wallets whose history is short because
        they tend to buy early and hold (few completed sell cycles).
        """
        result = []
        for s in scores:
            track_a = (s.win_rate >= min_win_rate and s.total_trades >= min_trades
                       and s.early_entries >= min_early_entries)
            # Track B: strong early-entry signal even with thin trade history
            # Requires either 2+ independent 5x+ catches, or 1 catch that went 10x+
            track_b = (s.early_entries >= 2
                       or (s.early_entries >= 1 and s.best_early_entry_x >= 10.0))
            if track_a or track_b:
                result.append(s)
        return result
