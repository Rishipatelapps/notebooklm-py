"""Unit tests for models and analyzers — no network required."""
from datetime import datetime, timezone

import pytest

from src.models.wallet import WalletScore
from src.models.trade import Trade, TradeType
from src.analyzers.win_rate import WinRateAnalyzer
from src.analyzers.early_entry import EarlyEntryAnalyzer
from src.analyzers.wallet_scorer import WalletScorer
from src.models.token import Token


def make_trade(
    wallet: str,
    token: str,
    symbol: str,
    chain: str,
    trade_type: TradeType,
    amount_usd: float,
    ts: datetime,
) -> Trade:
    return Trade(
        tx_hash=f"0x{hash((wallet, token, ts)):016x}",
        wallet=wallet,
        token_address=token,
        token_symbol=symbol,
        chain=chain,
        trade_type=trade_type,
        amount_usd=amount_usd,
        amount_tokens=amount_usd / 0.01,
        price_usd=0.01,
        timestamp=ts,
    )


class TestWinRateAnalyzer:
    def test_perfect_win_rate(self) -> None:
        analyzer = WinRateAnalyzer()
        now = datetime.now(tz=timezone.utc)
        trades = [
            make_trade("0xABC", "0xTOKEN1", "FOO", "eth", TradeType.BUY, 100.0, now),
            make_trade("0xABC", "0xTOKEN1", "FOO", "eth", TradeType.SELL, 500.0, now),
            make_trade("0xABC", "0xTOKEN2", "BAR", "eth", TradeType.BUY, 200.0, now),
            make_trade("0xABC", "0xTOKEN2", "BAR", "eth", TradeType.SELL, 1000.0, now),
        ]
        score = analyzer.analyze("0xABC", trades)
        assert score.win_rate == 100.0
        assert score.total_trades == 2
        assert score.winning_trades == 2
        assert score.total_pnl_usd == pytest.approx(1200.0)

    def test_mixed_win_rate(self) -> None:
        analyzer = WinRateAnalyzer()
        now = datetime.now(tz=timezone.utc)
        trades = [
            # Winner
            make_trade("0xABC", "0xTOKEN1", "WIN", "eth", TradeType.BUY, 100.0, now),
            make_trade("0xABC", "0xTOKEN1", "WIN", "eth", TradeType.SELL, 500.0, now),
            # Loser
            make_trade("0xABC", "0xTOKEN2", "LOSE", "eth", TradeType.BUY, 100.0, now),
            make_trade("0xABC", "0xTOKEN2", "LOSE", "eth", TradeType.SELL, 20.0, now),
        ]
        score = analyzer.analyze("0xABC", trades)
        assert score.win_rate == 50.0
        assert score.winning_trades == 1
        assert score.losing_trades == 1

    def test_early_entry_detection(self) -> None:
        analyzer = WinRateAnalyzer()
        now = datetime.now(tz=timezone.utc)
        trades = [
            make_trade("0xABC", "0xGEM", "GEM", "eth", TradeType.BUY, 100.0, now),
            make_trade("0xABC", "0xGEM", "GEM", "eth", TradeType.SELL, 700.0, now),
        ]
        score = analyzer.analyze("0xABC", trades, min_multiplier=5.0)
        assert score.early_entries == 1
        assert score.best_early_entry_x == pytest.approx(7.0)
        assert score.best_early_token == "GEM"

    def test_no_sells_skipped(self) -> None:
        analyzer = WinRateAnalyzer()
        now = datetime.now(tz=timezone.utc)
        trades = [
            make_trade("0xABC", "0xHODL", "HODL", "eth", TradeType.BUY, 100.0, now),
        ]
        score = analyzer.analyze("0xABC", trades)
        assert score.total_trades == 0  # no completed positions


class TestWalletScorer:
    def test_passes_filter(self) -> None:
        s = WalletScore(address="0xABC", win_rate=90.0, total_trades=20, early_entries=2)
        assert s.passes_filter(min_win_rate=85.0, min_trades=10)

    def test_fails_win_rate(self) -> None:
        s = WalletScore(address="0xABC", win_rate=80.0, total_trades=20, early_entries=2)
        assert not s.passes_filter(min_win_rate=85.0)

    def test_fails_trade_count(self) -> None:
        s = WalletScore(address="0xABC", win_rate=90.0, total_trades=3, early_entries=2)
        assert not s.passes_filter(min_trades=10)

    def test_merge(self) -> None:
        scorer = WalletScorer()
        s1 = WalletScore(address="0xABC", win_rate=88.0, total_trades=50, chains=["eth"])
        s2 = WalletScore(address="0xABC", win_rate=92.0, total_trades=30, chains=["base"])
        merged = scorer.merge([s1, s2])
        assert merged.address == "0xABC"
        assert set(merged.chains) == {"eth", "base"}
        # primary is s1 (more trades)
        assert merged.total_trades == 50
        assert merged.win_rate == 88.0

    def test_rank(self) -> None:
        scorer = WalletScorer()
        a = WalletScore(address="0xA", win_rate=95.0, total_trades=100, early_entries=10, avg_multiplier=8.0)
        b = WalletScore(address="0xB", win_rate=86.0, total_trades=50, early_entries=2, avg_multiplier=3.0)
        ranked = scorer.rank([b, a])
        assert ranked[0].address == "0xA"


class TestEarlyEntry:
    def test_compute_multiplier(self) -> None:
        analyzer = EarlyEntryAnalyzer()
        ohlcv = [
            [1000000, 0.001, 0.002, 0.0009, 0.0015, 10000],
            [1000060, 0.0015, 0.010, 0.0014, 0.009, 50000],
        ]
        mult = analyzer.compute_token_multiplier(ohlcv)
        assert mult == pytest.approx(10.0)  # ATH 0.010 / open 0.001

    def test_find_early_buyers_within_window(self) -> None:
        analyzer = EarlyEntryAnalyzer(max_hours_after_listing=4.0, min_multiplier=5.0)
        listed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        token = Token(
            address="0xTOK", symbol="TOK", name="Token", chain="eth",
            listed_at=listed, peak_multiplier=10.0
        )
        trades = [
            Trade("0xhash1", "0xEARLY", "0xTOK", "TOK", "eth", TradeType.BUY, 500.0, 500_000, 0.001,
                  datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc)),
            Trade("0xhash2", "0xLATE", "0xTOK", "TOK", "eth", TradeType.BUY, 500.0, 500_000, 0.001,
                  datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)),  # too late
        ]
        buyers = analyzer.find_early_buyers(token, trades)
        assert len(buyers) == 1
        assert buyers[0][0] == "0xEARLY"
        assert buyers[0][1] == 10.0
