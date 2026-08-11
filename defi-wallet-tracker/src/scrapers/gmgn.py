"""GMGN.ai API — Solana & Base wallet leaderboards, win rates, PnL.

GMGN tracks memecoin traders with real PnL, win rates, and early entry stats.
API key header: Authorization: Bearer <key>

NOTE: gmgn.ai is protected by Cloudflare. Server/cloud IPs may receive 403.
On a local machine this works fine. Install curl_cffi for bypass if needed:
  pip install curl_cffi

Key endpoints:
  GET /defi/quotation/v1/rank/sol/wallets/7d        — Solana top traders 7d
  GET /defi/quotation/v1/rank/sol/wallets/30d       — Solana top traders 30d
  GET /defi/quotation/v1/rank/base/wallets/7d       — Base top traders
  GET /api/v1/wallet_holdings/sol/{address}         — wallet token holdings
  GET /api/v1/wallet_stat/sol/{address}/7d          — wallet stats

Response field names (timeframe-specific):
  wallet_address, winrate_7d, winrate_30d (0-1 range)
  txs_7d, buy_7d, sell_7d
  realized_profit_7d, pnl_gt_5x_num_7d
"""
from ..models.wallet import WalletScore
from .base import BaseClient

_BASE = "https://gmgn.ai"
_BROWSER_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Authorization": "",  # filled in __init__
    "DNT": "1",
    "Origin": "https://gmgn.ai",
    "Referer": "https://gmgn.ai/",
    "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}


class GMGNClient(BaseClient):
    def __init__(self, api_key: str) -> None:
        headers = {**_BROWSER_HEADERS, "Authorization": f"Bearer {api_key}"}
        super().__init__(_BASE, headers=headers, rate_limit_rps=1.0)
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
        """GMGN-curated smart money wallet list (if endpoint available)."""
        for path in [
            f"/defi/quotation/v1/smartmoney/{chain}/wallets",
            f"/defi/quotation/v1/rank/{chain}/wallets/30d",
        ]:
            try:
                data = await self._get(path, params={"limit": limit})
                wallets = (
                    (data or {}).get("data", {}).get("wallets")
                    or (data or {}).get("data", {}).get("rank")
                    or []
                )
                if wallets:
                    return wallets
            except Exception:
                continue
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

    def parse_trader_to_score(
        self, trader: dict, chain: str, timeframe: str = "7d"
    ) -> WalletScore | None:
        """Convert a GMGN leaderboard entry into a WalletScore."""
        address = trader.get("wallet_address") or trader.get("address", "")
        if not address:
            return None

        tf = timeframe.replace("d", "")  # "7d" → "7", "30d" → "30"

        # Win rate: field is winrate_7d / winrate_30d (0-1 range)
        raw_wr = (
            trader.get(f"winrate_{tf}d")
            or trader.get(f"winrate_{timeframe}")
            or trader.get("winrate")
            or trader.get("win_rate")
            or 0
        )
        win_rate = float(raw_wr) * 100
        if win_rate > 100:
            win_rate /= 100  # was already in 0-100

        # Trade counts from timeframe-specific fields
        total_trades = int(
            trader.get(f"txs_{tf}d")
            or trader.get(f"txs_{timeframe}")
            or trader.get("total_trade")
            or trader.get("trade_count")
            or 0
        )
        buys = int(trader.get(f"buy_{tf}d") or trader.get("buy") or 0)
        sells = int(trader.get(f"sell_{tf}d") or trader.get("sell") or 0)
        wins = max(buys, sells)  # approximate — GMGN doesn't expose win_count directly
        losses = total_trades - wins

        pnl = float(
            trader.get(f"realized_profit_{tf}d")
            or trader.get(f"realized_profit_{timeframe}")
            or trader.get("realized_profit")
            or trader.get("pnl")
            or 0
        )

        # 5x+ trade count
        early_entries = int(
            trader.get(f"pnl_gt_5x_num_{tf}d")
            or trader.get("pnl_gt_5x_num")
            or 0
        )

        avg_mult = float(trader.get("avg_multiple") or trader.get("multiplier") or 0)
        best_mult = float(trader.get("max_multiple") or 0)
        label = (
            trader.get("name") or trader.get("nickname")
            or (trader.get("tags") or [""])[0] if trader.get("tags") else ""
            or ""
        )

        return WalletScore(
            address=address,
            chains=[chain],
            label=label,
            source="gmgn",
            win_rate=win_rate,
            total_trades=total_trades,
            winning_trades=wins,
            losing_trades=losses,
            total_pnl_usd=pnl,
            avg_multiplier=avg_mult,
            max_multiplier=best_mult,
            early_entries=early_entries,
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

        scores: list[WalletScore] = []
        seen: set[str] = set()
        for trader in traders:
            score = self.parse_trader_to_score(trader, chain, timeframe)
            if score and score.address not in seen:
                seen.add(score.address)
                scores.append(score)

        return [s for s in scores if s.win_rate >= min_win_rate and s.total_trades >= 5]
