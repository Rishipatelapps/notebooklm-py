from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Wallet:
    address: str
    chain: str
    label: str = ""
    source: str = ""  # where it was discovered: nansen, cielo, gecko, etc.
    first_seen: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class WalletScore:
    address: str
    chains: list[str] = field(default_factory=list)
    label: str = ""
    source: str = ""

    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_multiplier: float = 0.0
    max_multiplier: float = 0.0
    total_pnl_usd: float = 0.0
    avg_pnl_per_trade: float = 0.0

    # Early entry stats
    early_entries: int = 0          # trades that hit ≥ min_multiplier
    best_early_entry_x: float = 0.0  # highest multiplier achieved
    best_early_token: str = ""

    # Activity
    active_since: datetime | None = None
    last_active: datetime | None = None

    # Raw data snapshots from each source
    raw: dict = field(default_factory=dict)

    @property
    def score(self) -> float:
        """Composite ranking score (higher = better)."""
        if self.total_trades == 0 and self.early_entries == 0:
            return 0.0
        # Win rate contribution scaled by statistical confidence (more trades = more weight)
        trade_confidence = min(self.total_trades / 10.0, 1.0)
        win_component = self.win_rate * trade_confidence * 0.6        # 0–60
        multiplier_component = min(self.avg_multiplier, 20) * 2       # 0–40
        early_component = min(self.early_entries, 10) * 3.0           # 0–30
        best_entry_component = min(self.best_early_entry_x / 50, 1.0) * 10  # 0–10
        volume_bonus = min(self.total_trades / 100, 1.0) * 5          # 0–5
        return win_component + multiplier_component + early_component + best_entry_component + volume_bonus

    def passes_filter(self, min_win_rate: float = 85.0, min_trades: int = 5) -> bool:
        return self.win_rate >= min_win_rate and self.total_trades >= min_trades
