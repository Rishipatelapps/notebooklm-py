from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TradeType(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class Trade:
    tx_hash: str
    wallet: str
    token_address: str
    token_symbol: str
    chain: str
    trade_type: TradeType
    amount_usd: float
    amount_tokens: float
    price_usd: float
    timestamp: datetime
    # PnL fields populated after matching buys/sells
    realized_pnl_usd: float = 0.0
    multiplier: float = 0.0
    is_winner: bool = False
    extra: dict = field(default_factory=dict)
