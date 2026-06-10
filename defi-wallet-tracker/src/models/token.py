from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Token:
    address: str
    symbol: str
    name: str
    chain: str
    price_usd: float = 0.0
    market_cap: float = 0.0
    liquidity_usd: float = 0.0
    volume_24h: float = 0.0
    price_change_24h: float = 0.0
    # Peak multiplier observed since listing
    peak_multiplier: float = 1.0
    listed_at: datetime | None = None
    pair_address: str = ""
    dex: str = ""
    extra: dict = field(default_factory=dict)
