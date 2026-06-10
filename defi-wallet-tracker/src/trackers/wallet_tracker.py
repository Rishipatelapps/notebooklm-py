"""Main orchestrator: discovers wallets from DEX data, scores them, returns top list."""
import asyncio
from typing import Any

from rich.progress import Progress, SpinnerColumn, TextColumn

from ..analyzers import EarlyEntryAnalyzer, WalletScorer
from ..chains import CHAINS, Chain
from ..models.wallet import WalletScore
from ..scrapers.cielo import CieloClient
from ..scrapers.dexscreener import DexScreenerClient
from ..scrapers.geckoterminal import GeckoTerminalClient
from ..scrapers.moralis import MoralisClient


class WalletTracker:
    """
    Pipeline:
      1. Discover new/trending pools via GeckoTerminal + DexScreener
      2. Extract early buyer addresses from pool trades
      3. Score wallets via Cielo / Moralis profitability APIs
      4. Filter: win_rate >= min_win_rate, early_entries >= 1
      5. Return ranked leaderboard
    """

    def __init__(
        self,
        cielo_key: str = "",
        moralis_key: str = "",
        min_win_rate: float = 85.0,
        min_trades: int = 10,
        min_multiplier: float = 5.0,
        chains: list[str] | None = None,
        max_wallets_per_chain: int = 200,
    ) -> None:
        self._cielo_key = cielo_key
        self._moralis_key = moralis_key
        self._min_win_rate = min_win_rate
        self._min_trades = min_trades
        self._min_multiplier = min_multiplier
        self._chains = chains or ["eth", "bsc", "base", "arbitrum", "solana"]
        self._max_wallets = max_wallets_per_chain
        self._early = EarlyEntryAnalyzer(min_multiplier=min_multiplier)
        self._scorer = WalletScorer()

    async def run(self) -> list[WalletScore]:
        """Full discovery + scoring pipeline."""
        all_candidates: set[tuple[str, str]] = set()  # (wallet, chain)

        with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True) as prog:
            t1 = prog.add_task("Discovering wallets from DEX pools…")
            async with GeckoTerminalClient() as gecko, DexScreenerClient() as dex:
                for chain_id in self._chains:
                    chain = CHAINS.get(chain_id)
                    if not chain:
                        continue
                    prog.update(t1, description=f"Scanning {chain.name} pools…")
                    candidates = await self._discover_from_gecko(gecko, chain)
                    all_candidates.update((w, chain_id) for w in candidates)

                    # Also grab trending from DexScreener
                    dex_candidates = await self._discover_from_dexscreener(dex, chain)
                    all_candidates.update((w, chain_id) for w in dex_candidates)

                    await asyncio.sleep(0.5)

            prog.update(t1, description=f"Found {len(all_candidates)} candidate wallets. Scoring…")

            # Score wallets
            scored: list[WalletScore] = []
            t2 = prog.add_task("Scoring wallets…")
            semaphore = asyncio.Semaphore(5)  # max concurrent API calls

            tasks = [
                self._score_wallet(wallet, chain, semaphore, prog, t2)
                for wallet, chain in list(all_candidates)[: self._max_wallets * len(self._chains)]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, WalletScore):
                    scored.append(r)

        filtered = self._scorer.filter_smart_money(
            scored, self._min_win_rate, self._min_trades
        )
        return self._scorer.rank(filtered)

    async def _discover_from_gecko(self, gecko: GeckoTerminalClient, chain: Chain) -> list[str]:
        """Extract early buyer wallets from GeckoTerminal new pools."""
        wallets: list[str] = []
        try:
            pools = await gecko.get_new_pools(chain.geckoterminal_id)
            for pool in pools[:20]:
                if not pool.pair_address:
                    continue
                # Check if token has potential (volume, liquidity)
                if pool.volume_24h < 10_000 or pool.liquidity_usd < 5_000:
                    continue
                try:
                    ohlcv = await gecko.get_pool_ohlcv(chain.geckoterminal_id, pool.pair_address)
                    multiplier = self._early.compute_token_multiplier(ohlcv)
                    if multiplier < self._min_multiplier:
                        continue
                    pool.peak_multiplier = multiplier
                    trades = await gecko.get_pool_trades(chain.geckoterminal_id, pool.pair_address)
                    early = self._early.find_early_buyers(pool, trades)
                    wallets.extend(w for w, _ in early)
                except Exception:
                    continue
        except Exception:
            pass
        return list(set(wallets))

    async def _discover_from_dexscreener(self, dex: DexScreenerClient, chain: Chain) -> list[str]:
        """Use DexScreener trending tokens as signal for active chains."""
        wallets: list[str] = []
        try:
            tokens = await dex.get_trending_tokens(chain.dexscreener_id)
            # DexScreener doesn't provide wallet addresses directly —
            # use as a signal to cross-reference with Moralis
            _ = tokens  # reserved for future address enrichment
        except Exception:
            pass
        return wallets

    async def _score_wallet(
        self,
        wallet: str,
        chain: str,
        semaphore: asyncio.Semaphore,
        prog: Any,
        task_id: Any,
    ) -> WalletScore | None:
        async with semaphore:
            scores: list[WalletScore] = []

            if self._cielo_key:
                try:
                    async with CieloClient(self._cielo_key) as cielo:
                        s = await cielo.build_wallet_score(wallet)
                        if s.total_trades > 0:
                            scores.append(s)
                except Exception:
                    pass

            if self._moralis_key and chain != "solana":
                chain_obj = CHAINS.get(chain)
                if chain_obj and chain_obj.moralis_chain:
                    try:
                        async with MoralisClient(self._moralis_key) as moralis:
                            s = await moralis.build_wallet_score(wallet, chain_obj.moralis_chain)
                            if s.total_trades > 0:
                                scores.append(s)
                    except Exception:
                        pass

            if not scores:
                return None

            merged = self._scorer.merge(scores)
            merged.chains = [chain]
            prog.advance(task_id)
            return merged
