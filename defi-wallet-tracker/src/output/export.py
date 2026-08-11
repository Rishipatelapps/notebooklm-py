"""CSV and JSON export for wallet leaderboards."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from ..models.wallet import WalletScore


def export_json(wallets: list[WalletScore], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "count": len(wallets),
        "wallets": [_score_to_dict(w) for w in wallets],
    }
    path.write_text(json.dumps(data, indent=2))
    return path


def export_csv(wallets: list[WalletScore], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank", "address", "chains", "label", "source",
        "win_rate", "total_trades", "winning_trades", "losing_trades",
        "avg_multiplier", "max_multiplier", "early_entries",
        "best_early_entry_x", "best_early_token",
        "total_pnl_usd", "avg_pnl_per_trade", "score",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for i, w in enumerate(wallets, 1):
            row = _score_to_dict(w)
            row["rank"] = i
            row["chains"] = "|".join(w.chains)
            writer.writerow({k: row.get(k, "") for k in fields})
    return path


def _score_to_dict(w: WalletScore) -> dict:
    return {
        "address": w.address,
        "chain": w.chains[0] if w.chains else "",
        "chains": w.chains,
        "label": w.label,
        "source": w.source,
        "win_rate": round(w.win_rate, 2),
        "total_trades": w.total_trades,
        "winning_trades": w.winning_trades,
        "losing_trades": w.losing_trades,
        "avg_multiplier": round(w.avg_multiplier, 3),
        "max_multiplier": round(w.max_multiplier, 2),
        "early_entries": w.early_entries,
        "best_early_entry_x": round(w.best_early_entry_x, 2),
        "best_early_token": w.best_early_token,
        "total_pnl_usd": round(w.total_pnl_usd, 2),
        "avg_pnl_per_trade": round(w.avg_pnl_per_trade, 2),
        "score": round(w.score, 2),
        "active_since": w.active_since.isoformat() if w.active_since else None,
        "last_active": w.last_active.isoformat() if w.last_active else None,
    }
