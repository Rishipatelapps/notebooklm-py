"""Rich console leaderboard renderer."""
from rich.console import Console
from rich.table import Table
from rich import box

from ..models.wallet import WalletScore

console = Console()


def print_leaderboard(wallets: list[WalletScore], top_n: int = 50, min_win_rate: float = 85.0) -> None:
    if not wallets:
        console.print("[yellow]No wallets found matching criteria.[/yellow]")
        return

    table = Table(
        title=f"[bold green]Top DeFi Smart Money Wallets (Win Rate ≥ {min_win_rate:.0f}%)[/bold green]",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold cyan",
    )

    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Wallet", style="bright_blue", min_width=12, max_width=20)
    table.add_column("Chains", style="yellow", width=18)
    table.add_column("Win Rate", style="bold green", justify="right", width=10)
    table.add_column("Trades", justify="right", width=8)
    table.add_column("Avg Mult", justify="right", width=10)
    table.add_column("Max Mult", justify="right", width=10)
    table.add_column("Early (≥5x)", justify="right", width=12)
    table.add_column("Best Entry", justify="right", width=12)
    table.add_column("Total PnL", justify="right", width=14)
    table.add_column("Score", justify="right", width=8)
    table.add_column("Source", style="dim", width=12)

    for i, w in enumerate(wallets[:top_n], 1):
        addr = w.address
        short_addr = f"{addr[:6]}…{addr[-4:]}" if len(addr) > 12 else addr
        chains = ", ".join(sorted(set(w.chains))[:3])

        win_color = "green" if w.win_rate >= 90 else "yellow"
        pnl_color = "green" if w.total_pnl_usd >= 0 else "red"
        pnl_str = f"${w.total_pnl_usd:,.0f}"

        table.add_row(
            str(i),
            short_addr,
            chains,
            f"[{win_color}]{w.win_rate:.1f}%[/{win_color}]",
            str(w.total_trades),
            f"{w.avg_multiplier:.2f}x",
            f"[bold]{w.max_multiplier:.1f}x[/bold]",
            str(w.early_entries),
            f"[bold green]{w.best_early_entry_x:.1f}x[/bold green] {w.best_early_token[:6]}" if w.best_early_token else f"{w.best_early_entry_x:.1f}x",
            f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
            f"{w.score:.1f}",
            w.source[:10],
        )

    console.print(table)
    console.print(f"\n[dim]Showing top {min(top_n, len(wallets))} of {len(wallets)} qualifying wallets.[/dim]")


def print_wallet_detail(w: WalletScore) -> None:
    console.rule(f"[bold cyan]Wallet: {w.address}[/bold cyan]")
    console.print(f"  Chains:        {', '.join(w.chains)}")
    console.print(f"  Label:         {w.label or '—'}")
    console.print(f"  Source:        {w.source}")
    console.print(f"  Win Rate:      [bold green]{w.win_rate:.1f}%[/bold green]")
    console.print(f"  Total Trades:  {w.total_trades}  (W:{w.winning_trades} / L:{w.losing_trades})")
    console.print(f"  Avg Multiplier:{w.avg_multiplier:.2f}x  Max: {w.max_multiplier:.1f}x")
    console.print(f"  Early Entries: {w.early_entries} (≥5x tokens)")
    console.print(f"  Best Entry:    {w.best_early_entry_x:.1f}x — {w.best_early_token}")
    console.print(f"  Total PnL:     ${w.total_pnl_usd:,.0f}")
    console.print(f"  Composite Score: {w.score:.1f}")
