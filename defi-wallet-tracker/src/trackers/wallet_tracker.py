"""Main orchestrator: discovers wallets from DEX data, scores them, returns top list."""
import asyncio
from collections import defaultdict
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..analyzers import EarlyEntryAnalyzer, WalletScorer
from ..analyzers.gecko_scorer import GeckoScorer
from ..chains import CHAINS, Chain
from ..models.token import Token
from ..models.wallet import WalletScore
from ..scrapers.blockscout import BlockscoutClient, BLOCKSCOUT_HOSTS
from ..scrapers.cielo import CieloClient
from ..scrapers.dexscreener import DexScreenerClient
from ..scrapers.geckoterminal import GeckoTerminalClient
from ..scrapers.moralis import MoralisClient

console = Console()


class WalletTracker:
    """
    Pipeline:
      1. Discover new/trending pools via GeckoTerminal + DexScreener (free, no key)
      2. Extract early buyer addresses from pool trades (free)
      3. Score wallets:
         a. Cielo Finance if CIELO_API_KEY set
         b. Moralis if MORALIS_API_KEY set
         c. Blockscout public API as free fallback (EVM chains only)
      4. GeckoScorer: provisional score from pool appearances (for Solana / keyless)
      5. Filter: win_rate >= min_win_rate, early_entries >= 1
      6. Return ranked leaderboard
    """

    def __init__(
        self,
        cielo_key: str = "",
        moralis_key: str = "",
        min_win_rate: float = 85.0,
        min_trades: int = 5,
        min_multiplier: float = 5.0,
        chains: list[str] | None = None,
        max_wallets_per_chain: int = 200,
        use_blockscout: bool = True,
    ) -> None:
        self._cielo_key = cielo_key
        self._moralis_key = moralis_key
        self._min_win_rate = min_win_rate
        self._min_trades = min_trades
        self._min_multiplier = min_multiplier
        self._chains = chains or ["eth", "bsc", "base", "arbitrum", "solana"]
        self._max_wallets = max_wallets_per_chain
        self._use_blockscout = use_blockscout
        self._early = EarlyEntryAnalyzer(min_multiplier=min_multiplier)
        self._scorer = WalletScorer()
        self._gecko_scorer = GeckoScorer(min_multiplier=min_multiplier)

    async def run(self) -> list[WalletScore]:
        """Full discovery + scoring pipeline."""
        # wallet → [(Token, multiplier), ...]
        appearances: dict[str, list[tuple[Token, float]]] = defaultdict(list)
        chain_map: dict[str, str] = {}  # wallet → chain

        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            transient=False,
        ) as prog:
            t_discover = prog.add_task("[cyan]Discovering pools…", total=len(self._chains))

            async with GeckoTerminalClient() as gecko, DexScreenerClient() as dex:
                for chain_id in self._chains:
                    chain = CHAINS.get(chain_id)
                    if not chain:
                        prog.advance(t_discover)
                        continue
                    prog.update(t_discover, description=f"[cyan]Scanning {chain.name}…")
                    found = await self._discover_from_gecko(gecko, chain, appearances)
                    for w in found:
                        chain_map[w] = chain_id
                    prog.advance(t_discover)
                    await asyncio.sleep(0.3)

            console.print(
                f"\n[bold]Found [yellow]{len(appearances)}[/yellow] candidate wallets "
                f"across {len(self._chains)} chains.[/bold]"
            )

            if not appearances:
                return []

            # Limit candidates per chain
            candidates = list(appearances.keys())[: self._max_wallets * len(self._chains)]

            # Stage 1: provisional GeckoScorer scores (free, instant)
            gecko_scores = self._gecko_scorer.score_from_pool_appearances(appearances)
            gecko_score_map = {s.address: s for s in gecko_scores}

            # Stage 2: refine with Blockscout / Cielo / Moralis
            t_score = prog.add_task("[green]Scoring wallets…", total=len(candidates))
            semaphore = asyncio.Semaphore(4)

            tasks = [
                self._score_wallet(w, chain_map.get(w, "eth"), semaphore, prog, t_score, gecko_score_map.get(w))
                for w in candidates
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        scored: list[WalletScore] = []
        for r in results:
            if isinstance(r, WalletScore):
                scored.append(r)

        console.print(f"[dim]Scored {len(scored)} wallets. Applying filters…[/dim]")

        # Show distribution for transparency
        if scored:
            from statistics import mean
            win_rates = [s.win_rate for s in scored if s.total_trades > 0]
            sources = {s.source for s in scored}
            console.print(
                f"[dim]Sources used: {', '.join(sources)} | "
                f"Avg win rate: {mean(win_rates):.1f}% | "
                f"Max: {max(win_rates):.1f}%[/dim]"
                if win_rates else "[dim]No trade data — showing by early entries[/dim]"
            )

        has_real_scores = any(s.source not in ("gecko_terminal",) and s.total_trades > 0 for s in scored)

        if has_real_scores:
            filtered = self._scorer.filter_smart_money(scored, self._min_win_rate, self._min_trades)
        else:
            # Gecko-only: rank by early entries, no win-rate filter possible
            console.print(
                "[yellow]No scoring API keys set — showing provisional ranking "
                "by early pool appearances (add CIELO_API_KEY or MORALIS_API_KEY "
                "to .env for win-rate filtering).[/yellow]"
            )
            filtered = [s for s in scored if s.early_entries >= 1]

        return self._scorer.rank(filtered)

    async def _discover_from_gecko(
        self,
        gecko: GeckoTerminalClient,
        chain: Chain,
        appearances: dict,
    ) -> list[str]:
        """Extract early buyer wallets from GeckoTerminal new + trending pools."""
        new_wallets: list[str] = []
        pools_checked = 0
        pools_hit = 0

        # Fetch new and trending pools
        pool_sets: list[list[Token]] = []
        try:
            pool_sets.append(await gecko.get_new_pools(chain.geckoterminal_id))
        except Exception:
            pass
        try:
            pool_sets.append(await gecko.get_trending_pools(chain.geckoterminal_id))
        except Exception:
            pass

        all_pools = {p.pair_address: p for pl in pool_sets for p in pl if p.pair_address}

        for pool in list(all_pools.values())[:30]:
            pools_checked += 1
            try:
                ohlcv = await gecko.get_pool_ohlcv(chain.geckoterminal_id, pool.pair_address)
                multiplier = self._early.compute_token_multiplier(ohlcv)
                if multiplier < self._min_multiplier:
                    continue
                pool.peak_multiplier = multiplier
                trades = await gecko.get_pool_trades(chain.geckoterminal_id, pool.pair_address, limit=200)
                early = self._early.find_early_buyers(pool, trades)
                for wallet, mult in early:
                    self._gecko_scorer.build_appearances(pool, [(wallet, mult)], appearances)
                    new_wallets.append(wallet)
                pools_hit += 1
            except Exception:
                continue

        console.print(
            f"  [dim]{chain.name}: {pools_checked} pools checked, "
            f"{pools_hit} hit ≥{self._min_multiplier}x, "
            f"{len(set(new_wallets))} new wallets[/dim]"
        )
        return list(set(new_wallets))

    async def _score_wallet(
        self,
        wallet: str,
        chain: str,
        semaphore: asyncio.Semaphore,
        prog: Any,
        task_id: Any,
        gecko_base: WalletScore | None = None,
    ) -> WalletScore | None:
        async with semaphore:
            scores: list[WalletScore] = []

            # Cielo (if key set)
            if self._cielo_key:
                try:
                    async with CieloClient(self._cielo_key) as cielo:
                        s = await cielo.build_wallet_score(wallet)
                        if s.total_trades > 0:
                            scores.append(s)
                except Exception:
                    pass

            # Moralis (if key set, EVM only)
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

            # Blockscout fallback (EVM, no key needed)
            if not scores and self._use_blockscout and chain in BLOCKSCOUT_HOSTS:
                try:
                    async with BlockscoutClient(chain) as bs:
                        s = await bs.build_wallet_score_from_trades(wallet, pages=2)
                        if s.total_trades > 0:
                            scores.append(s)
                except Exception:
                    pass

            prog.advance(task_id)

            if scores:
                merged = self._scorer.merge(scores)
                merged.chains = [chain]
                # Overlay gecko early-entry data if we have it
                if gecko_base and merged.early_entries == 0:
                    merged.early_entries = gecko_base.early_entries
                    merged.best_early_entry_x = gecko_base.best_early_entry_x
                    merged.best_early_token = gecko_base.best_early_token
                return merged

            # Fall back to gecko provisional score
            if gecko_base:
                gecko_base.chains = [chain]
                return gecko_base

            return None
