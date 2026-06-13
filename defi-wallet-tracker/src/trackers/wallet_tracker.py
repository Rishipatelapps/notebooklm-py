"""Main orchestrator — full DeFi smart money discovery pipeline."""
import asyncio
from collections import defaultdict
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ..analyzers import EarlyEntryAnalyzer, WalletScorer
from ..analyzers.etherscan_scorer import EtherscanWalletScorer
from ..analyzers.gecko_scorer import GeckoScorer
from ..chains import CHAINS, Chain
from ..models.token import Token
from ..models.wallet import WalletScore
from ..scrapers.blockscout import BlockscoutClient, BLOCKSCOUT_HOSTS
from ..scrapers.cielo import CieloClient
from ..scrapers.discovery import TokenDiscovery
from ..scrapers.dexscreener import DexScreenerClient
from ..scrapers.early_buyer_extractor import EarlyBuyerExtractor
from ..scrapers.geckoterminal import GeckoTerminalClient
from ..scrapers.moralis import MoralisClient
from ..scrapers.gmgn import GMGNClient

console = Console()


class WalletTracker:
    """
    Pipeline:
      1. Discover high-multiplier tokens via CoinGecko gainers + GeckoTerminal trending
      2. Extract early buyers of those tokens via Etherscan V2
      3. Score each wallet's full trade history via Etherscan + CoinGecko prices
      4. Filter: win_rate ≥ min_win_rate, min_trades, min early_entries
      5. Return ranked leaderboard
    """

    def __init__(
        self,
        cielo_key: str = "",
        moralis_key: str = "",
        etherscan_key: str = "",
        coingecko_key: str = "",
        min_win_rate: float = 85.0,
        min_trades: int = 5,
        min_multiplier: float = 5.0,
        chains: list[str] | None = None,
        max_wallets_per_chain: int = 200,
        use_blockscout: bool = True,
    ) -> None:
        self._cielo_key = cielo_key
        self._moralis_key = moralis_key
        self._etherscan_key = etherscan_key
        self._coingecko_key = coingecko_key
        self._min_win_rate = min_win_rate
        self._min_trades = min_trades
        self._min_multiplier = min_multiplier
        self._chains = [c for c in (chains or ["eth", "bsc", "base", "arbitrum", "solana"])
                        if CHAINS.get(c)]
        self._max_wallets = max_wallets_per_chain
        self._use_blockscout = use_blockscout
        self._early = EarlyEntryAnalyzer(min_multiplier=min_multiplier)
        self._scorer = WalletScorer()
        self._gecko_scorer = GeckoScorer(min_multiplier=min_multiplier)
        self._escan_scorer = (
            EtherscanWalletScorer(etherscan_key, coingecko_key, min_multiplier=min_multiplier)
            if etherscan_key else None
        )
        self._discovery = TokenDiscovery(
            coingecko_key=coingecko_key,
            min_multiplier=min_multiplier,
        )
        self._extractor = (
            EarlyBuyerExtractor(etherscan_key) if etherscan_key else None
        )
        import os as _os
        self._gmgn_key = _os.getenv("GMGN_API_KEY", "")

    async def run(self) -> list[WalletScore]:
        """Full discovery + scoring pipeline."""

        # ── Step 0: Pull GMGN leaderboard (Solana + Base — direct win rates) ─
        gmgn_scores: list[WalletScore] = []
        if self._gmgn_key and "solana" in self._chains:
            console.print("\n[bold cyan]Step 0 — Pulling GMGN.ai smart money leaderboard…[/bold cyan]")
            async with GMGNClient(self._gmgn_key) as gmgn:
                for chain_slug, gmgn_chain in [("solana", "sol"), ("base", "base")]:
                    if chain_slug not in self._chains:
                        continue
                    for tf in ["7d", "30d"]:
                        try:
                            batch = await gmgn.get_top_wallet_scores(
                                gmgn_chain, tf, self._min_win_rate, limit=200
                            )
                            gmgn_scores.extend(batch)
                            console.print(
                                f"  GMGN {chain_slug.upper()} {tf}: "
                                f"[yellow]{len(batch)}[/yellow] qualifying wallets"
                            )
                        except Exception as e:
                            console.print(f"  [dim]GMGN {chain_slug} {tf}: {e}[/dim]")
            # Deduplicate by address
            seen_gmgn: set[str] = set()
            deduped = []
            for s in gmgn_scores:
                if s.address not in seen_gmgn:
                    seen_gmgn.add(s.address)
                    deduped.append(s)
            gmgn_scores = deduped
            console.print(f"  Total unique GMGN wallets: [green]{len(gmgn_scores)}[/green]")

        # ── Step 1: Find high-multiplier tokens ──────────────────────────────
        console.print("\n[bold cyan]Step 1/3 — Discovering high-multiplier tokens…[/bold cyan]")
        evm_chains = [c for c in self._chains if CHAINS[c].is_evm]
        tokens = await self._discovery.find_high_multiplier_tokens(
            evm_chains, max_tokens=60
        )
        console.print(
            f"  Found [yellow]{len(tokens)}[/yellow] tokens with "
            f"≥{self._min_multiplier}x multiplier"
        )
        for t in tokens[:10]:
            console.print(
                f"  [dim]{t['chain'].upper():8} {t['symbol']:<10} "
                f"{t['multiplier']:.1f}x  ({t['source']})[/dim]"
            )
        if len(tokens) > 10:
            console.print(f"  [dim]… and {len(tokens) - 10} more[/dim]")

        if not tokens:
            console.print("[yellow]No qualifying tokens found. Try lowering --min-mult.[/yellow]")
            return []

        # ── Step 2: Extract early buyers ──────────────────────────────────────
        console.print("\n[bold cyan]Step 2/3 — Extracting early buyers via Etherscan…[/bold cyan]")
        # wallet → (chain, [tokens where it was early])
        wallet_chain: dict[str, str] = {}
        wallet_tokens: dict[str, list[dict]] = defaultdict(list)

        # EVM chains: use Etherscan extractor (fast, accurate early buyers)
        evm_tokens = [t for t in tokens[:40] if CHAINS.get(t["chain"], CHAINS["eth"]).is_evm]
        sol_tokens = [t for t in tokens[:20] if not CHAINS.get(t["chain"], CHAINS["eth"]).is_evm]

        if self._extractor and evm_tokens:
            results = await self._extractor.get_early_buyers_many(evm_tokens, concurrency=4)
            for token_addr, (chain, buyers) in results.items():
                token_info = next((t for t in evm_tokens if t["address"] == token_addr), {})
                for wallet in buyers:
                    wallet_chain[wallet] = chain
                    wallet_tokens[wallet].append(token_info)
        elif not self._extractor:
            # No Etherscan key: use GeckoTerminal pool trades for EVM too
            sol_tokens = tokens[:20]

        # Solana + non-EVM: GeckoTerminal pool trades → recent buyers
        if sol_tokens:
            console.print("  [dim]Solana: extracting traders via GeckoTerminal pool trades…[/dim]")
            async with GeckoTerminalClient() as gecko:
                for token in sol_tokens:
                    if not token.get("pair_address"):
                        continue
                    chain_slug = token["chain"]
                    chain_obj = CHAINS.get(chain_slug)
                    if not chain_obj:
                        continue
                    try:
                        trades = await gecko.get_pool_trades(
                            chain_obj.geckoterminal_id, token["pair_address"], limit=100
                        )
                        for trade in trades:
                            if trade.wallet:
                                wallet_chain[trade.wallet] = chain_slug
                                wallet_tokens[trade.wallet].append(token)
                    except Exception:
                        continue

        console.print(
            f"  Found [yellow]{len(wallet_chain)}[/yellow] candidate wallets"
        )
        if not wallet_chain:
            return []

        # Limit candidates
        candidates = list(wallet_chain.items())[: self._max_wallets]

        # ── Step 3: Score each wallet ─────────────────────────────────────────
        console.print(f"\n[bold cyan]Step 3/3 — Scoring {len(candidates)} wallets…[/bold cyan]")
        semaphore = asyncio.Semaphore(4)

        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      BarColumn(), TaskProgressColumn()) as prog:
            t_score = prog.add_task("Scoring…", total=len(candidates))
            tasks = [
                self._score_wallet(w, c, wallet_tokens[w], semaphore, prog, t_score)
                for w, c in candidates
            ]
            results_raw = await asyncio.gather(*tasks, return_exceptions=True)

        scored: list[WalletScore] = [r for r in results_raw if isinstance(r, WalletScore)]

        # Stats
        if scored:
            from statistics import mean
            has_real = any(s.source not in ("gecko_terminal",) and s.total_trades > 0 for s in scored)
            if has_real:
                win_rates = [s.win_rate for s in scored if s.total_trades > 0]
                if win_rates:
                    console.print(
                        f"\n  Avg win rate: [green]{mean(win_rates):.1f}%[/green]  "
                        f"Max: [bold green]{max(win_rates):.1f}%[/bold green]  "
                        f"≥85%: [yellow]{sum(1 for r in win_rates if r >= 85)}[/yellow] wallets"
                    )
                filtered = self._scorer.filter_smart_money(scored, self._min_win_rate, self._min_trades)
            else:
                console.print(
                    "\n[yellow]No scoring API — showing provisional ranking by early entries. "
                    "Add ETHERSCAN_API_KEY to .env for real win rates.[/yellow]"
                )
                filtered = [s for s in scored if s.early_entries >= 1]
        else:
            filtered = []

        # Merge EVM results with GMGN Solana results
        all_results = filtered + [s for s in gmgn_scores if s.address not in {r.address for r in filtered}]
        return self._scorer.rank(all_results)

    async def _score_wallet(
        self,
        wallet: str,
        chain: str,
        early_tokens: list[dict],
        semaphore: asyncio.Semaphore,
        prog: Any,
        task_id: Any,
    ) -> WalletScore | None:
        async with semaphore:
            scores: list[WalletScore] = []

            # Etherscan + CoinGecko (primary — real on-chain PnL)
            if self._escan_scorer and chain != "solana":
                try:
                    s = await self._escan_scorer.score_wallet(wallet, chain)
                    if s.total_trades > 0:
                        scores.append(s)
                except Exception:
                    pass

            # Cielo (if key set)
            if self._cielo_key:
                try:
                    async with CieloClient(self._cielo_key) as cielo:
                        s = await cielo.build_wallet_score(wallet)
                        if s.total_trades > 0:
                            scores.append(s)
                except Exception:
                    pass

            # Moralis (EVM only)
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

            # Blockscout fallback
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
                # Overlay early entry data from discovery
                if early_tokens and merged.early_entries == 0:
                    best = max(early_tokens, key=lambda t: t.get("multiplier", 0))
                    merged.early_entries = len(early_tokens)
                    merged.best_early_entry_x = best.get("multiplier", 0)
                    merged.best_early_token = best.get("symbol", "")
                return merged

            # Provisional gecko score if no real data
            if early_tokens:
                best = max(early_tokens, key=lambda t: t.get("multiplier", 0))
                return WalletScore(
                    address=wallet,
                    chains=[chain],
                    source="gecko_terminal",
                    total_trades=len(early_tokens),
                    winning_trades=len(early_tokens),
                    win_rate=100.0,
                    avg_multiplier=sum(t.get("multiplier", 0) for t in early_tokens) / len(early_tokens),
                    max_multiplier=best.get("multiplier", 0),
                    early_entries=len(early_tokens),
                    best_early_entry_x=best.get("multiplier", 0),
                    best_early_token=best.get("symbol", ""),
                )

            return None
