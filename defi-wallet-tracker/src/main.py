"""DeFi Wallet Tracker CLI."""
import asyncio
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from .chains import supported_chains
from .output.console import print_leaderboard, print_wallet_detail
from .output.export import export_csv, export_json
from .trackers import WalletTracker
from .analyzers import WinRateAnalyzer
from .scrapers.cielo import CieloClient
from .scrapers.moralis import MoralisClient
from .scrapers.etherscan import EtherscanClient
from .chains import get_chain

load_dotenv()
app = typer.Typer(name="defi-tracker", help="Track top DeFi smart-money wallets across chains.")
console = Console()


@app.command("scan")
def scan(
    chains: list[str] = typer.Option(
        ["eth", "bsc", "base", "arbitrum", "solana"],
        "--chain", "-c",
        help="Chains to scan. Available: " + ", ".join(supported_chains()),
    ),
    min_win_rate: float = typer.Option(85.0, "--min-win-rate", "-w", help="Minimum win rate % (default 85)"),
    min_trades: int = typer.Option(10, "--min-trades", "-t", help="Minimum trade count"),
    min_multiplier: float = typer.Option(5.0, "--min-mult", "-m", help="Min multiplier for early entry"),
    top_n: int = typer.Option(50, "--top", "-n", help="Show top N wallets"),
    output_csv: Path | None = typer.Option(None, "--csv", help="Export results to CSV"),
    output_json: Path | None = typer.Option(None, "--json", help="Export results to JSON"),
    max_wallets: int = typer.Option(200, "--max-wallets", help="Max candidate wallets per chain"),
) -> None:
    """Discover and rank smart-money wallets across DeFi chains."""
    cielo_key = os.getenv("CIELO_API_KEY", "")
    moralis_key = os.getenv("MORALIS_API_KEY", "")

    if not cielo_key and not moralis_key:
        console.print(
            "[yellow]Warning: No CIELO_API_KEY or MORALIS_API_KEY set in .env — "
            "wallet scoring will be limited to on-chain trade analysis only.[/yellow]"
        )

    console.print(f"[bold]Scanning {len(chains)} chain(s): {', '.join(chains)}[/bold]")
    console.print(f"  Criteria: win rate ≥ {min_win_rate}%, min {min_trades} trades, min {min_multiplier}x entries\n")

    tracker = WalletTracker(
        cielo_key=cielo_key,
        moralis_key=moralis_key,
        min_win_rate=min_win_rate,
        min_trades=min_trades,
        min_multiplier=min_multiplier,
        chains=list(chains),
        max_wallets_per_chain=max_wallets,
    )

    wallets = asyncio.run(tracker.run())
    print_leaderboard(wallets, top_n=top_n, min_win_rate=min_win_rate)

    if output_csv:
        p = export_csv(wallets, output_csv)
        console.print(f"[green]CSV exported → {p}[/green]")
    if output_json:
        p = export_json(wallets, output_json)
        console.print(f"[green]JSON exported → {p}[/green]")


@app.command("wallet")
def wallet_detail(
    address: str = typer.Argument(..., help="Wallet address to analyze"),
    chain: str = typer.Option("eth", "--chain", "-c", help="Chain slug (eth, bsc, base, ...)"),
) -> None:
    """Analyze a single wallet's performance."""
    cielo_key = os.getenv("CIELO_API_KEY", "")
    moralis_key = os.getenv("MORALIS_API_KEY", "")
    from .models.wallet import WalletScore
    from .analyzers import WalletScorer

    async def _run() -> WalletScore:
        scores = []
        chain_obj = get_chain(chain)

        if cielo_key:
            async with CieloClient(cielo_key) as cielo:
                s = await cielo.build_wallet_score(address)
                if s.total_trades > 0:
                    scores.append(s)

        if moralis_key and chain_obj.moralis_chain:
            async with MoralisClient(moralis_key) as moralis:
                s = await moralis.build_wallet_score(address, chain_obj.moralis_chain)
                if s.total_trades > 0:
                    scores.append(s)

        if not scores:
            return WalletScore(address=address, chains=[chain], source="none")
        return WalletScorer().merge(scores)

    result = asyncio.run(_run())
    print_wallet_detail(result)


@app.command("list-chains")
def list_chains() -> None:
    """Print all supported chains."""
    from rich.table import Table
    from ..chains import CHAINS
    table = Table(title="Supported Chains", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Chain ID", justify="right")
    table.add_column("Native")
    table.add_column("EVM", justify="center")
    for cid, c in CHAINS.items():
        table.add_row(cid, c.name, str(c.chain_id), c.native_symbol, "✓" if c.is_evm else "✗")
    console.print(table)


@app.command("export-seeds")
def export_seeds(
    output: Path = typer.Option(Path("data/smart_money_seeds.json"), "--output", "-o"),
) -> None:
    """Export the built-in seed wallet list."""
    import json
    seed_path = Path(__file__).parent.parent / "data" / "known_smart_money.json"
    data = json.loads(seed_path.read_text())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2))
    console.print(f"[green]Seed wallets exported → {output}[/green]")


if __name__ == "__main__":
    app()
