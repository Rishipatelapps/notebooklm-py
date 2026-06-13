"""GMGN.ai API — Solana & Base wallet leaderboards, win rates, PnL.

GMGN tracks memecoin traders with real PnL, win rates, and early entry stats.
API key header: Authorization: Bearer <key>

Key endpoints (discovered from GMGN.ai):
  GET /defi/quotation/v1/rank/sol/wallets/7d        — Solana top traders 7d
  GET /defi/quotation/v1/rank/sol/wallets/30d       — Solana top traders 30d
  GET /defi/quotation/v1/smartmoney/sol/wallets     — Solana smart money list
  GET /defi/quotation/v1/rank/base/wallets/7d       — Base top traders
  GET /api/v1/wallet_holdings/sol/{address}         — wallet token holdings
  GET /api/v1/wallet_stat/sol/{address}/7d          — wallet stats (win rate, PnL)
"""
from ..models.wallet import WalletScore
from .base import BaseClient

_BASE = "https://gmgn.ai"


class GMGNClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        super().__init__(
            _BASE,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "Mozilla/5.0"},
            rate_limit_rps=1.0,
        )
        self._key = api_key

    async def get_top_traders(
        self, chain: str = "sol", timeframe: str = "7d", limit: int = 100
    ) -> list[dict]:
        """Leaderboard of top traders by PnL/win rate for a given chain."""
        try:
            data = await self._get(
                f"/defi/quotation/v1/rank/{chain}/wallets/{timeframe}",
                params={"limit": limit, "orderby": "pnl", "direction": "desc"},
            )
            return (data or {}).get("data", {}).get("rank", []) or []
        except Exception:
            return []

    async def get_smart_money(self, chain: str = "sol", limit: int = 100) -> list[dict]:
        """GMGN-curated smart money wallet list."""
        try:
            data = await self._get(
                f"/defi/quotation/v1/smartmoney/{chain}/wallets",
                params={"limit": limit},
            )
            return (data or {}).get("data", {}).get("wallets", []) or []
        except Exception:
            return []

    async def get_wallet_stat(self, address: str, chain: str = "sol", timeframe: str = "7d") -> dict:
        """Per-wallet trading stats: win_rate, realized_profit, trade counts."""
        try:
            return await self._get(f"/api/v1/wallet_stat/{chain}/{address}/{timeframe}")
        except Exception:
            return {}

    async def get_wallet_holdings(self, address: str, chain: str = "sol") -> list[dict]:
        """Current token holdings for a wallet."""
        try:
            data = await self._get(f"/api/v1/wallet_holdings/{chain}/{address}")
            return (data or {}).get("data", {}).get("holdings", []) or []
        except Exception:
            return []

    def parse_trader_to_score(self, trader: dict, chain: str) -> WalletScore | None:
        """Convert a GMGN leaderboard entry into a WalletScore."""
        address = trader.get("wallet_address") or trader.get("address", "")
        if not address:
            return None

        win_rate = float(trader.get("winrate") or trader.get("win_rate") or 0) * 100
        # Some responses give 0-1 range, others 0-100
        if win_rate <= 1.0 and win_rate > 0:
            win_rate *= 100

        pnl = float(trader.get("realized_profit") or trader.get("pnl") or 0)
        total_trades = int(trader.get("total_trade") or trader.get("trade_count") or 0)
        wins = int(trader.get("win_count") or 0)
        losses = total_trades - wins

        avg_mult = float(trader.get("avg_multiple") or trader.get("multiplier") or 0)
        best_mult = float(trader.get("max_multiple") or 0)

        return WalletScore(
            address=address,
            chains=[chain],
            label=trader.get("name") or trader.get("tag") or "",
            source="gmgn",
            win_rate=win_rate,
            total_trades=total_trades,
            winning_trades=wins,
            losing_trades=losses,
            total_pnl_usd=pnl,
            avg_multiplier=avg_mult,
            max_multiplier=best_mult,
            early_entries=int(trader.get("pnl_gt_5x_num") or 0),
            best_early_entry_x=best_mult,
            raw={"gmgn": trader},
        )

    async def get_top_wallet_scores(
        self,
        chain: str = "sol",
        timeframe: str = "7d",
        min_win_rate: float = 85.0,
        limit: int = 200,
    ) -> list[WalletScore]:
        """Pull leaderboard and return WalletScores passing win rate threshold."""
        traders = await self.get_top_traders(chain, timeframe, limit)
        traders += await self.get_smart_money(chain, min(limit, 100))

        scores: list[WalletScore] = []
        seen: set[str] = set()
        for trader in traders:
            score = self.parse_trader_to_score(trader, chain)
            if score and score.address not in seen:
                seen.add(score.address)
                scores.append(score)

        return [s for s in scores if s.win_rate >= min_win_rate and s.total_trades >= 5]
