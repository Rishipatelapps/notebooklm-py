# DeFi Wallet Tracker

Automatically discover and rank smart-money DeFi wallets across 8 chains by win rate, early-entry accuracy, and PnL. Filters to wallets with **≥85% win rate** that entered tokens **5–10x+ early**.

## Chains Supported

| Chain | DEX Data | Wallet Scoring |
|-------|----------|----------------|
| Ethereum | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| BNB Chain | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Base | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Arbitrum | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Polygon | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Optimism | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Avalanche | GeckoTerminal, DexScreener | Cielo, Moralis, Etherscan V2 |
| Solana | GeckoTerminal, DexScreener | Cielo |

## How It Works

```
1. Discovery  →  GeckoTerminal new pools + DexScreener trending
2. Filter     →  Only tokens with ≥5x ATH since listing
3. Extract    →  Wallets that bought within 4h of listing
4. Score      →  Cielo win rate + Moralis profitability API
5. Rank       →  Composite score (win rate 60% + multiplier 20% + early entries 20%)
6. Export     →  Rich table, CSV, JSON
```

## Quick Start

```bash
# 1. Install
cd defi-wallet-tracker
pip install -e .

# 2. Configure API keys
cp .env.example .env
# Edit .env — at minimum add CIELO_API_KEY or MORALIS_API_KEY

# 3. Scan all chains (default: ETH, BSC, Base, Arbitrum, Solana)
defi-tracker scan

# 4. Custom scan
defi-tracker scan --chain eth --chain base --min-win-rate 90 --min-mult 10 --top 20

# 5. Analyze a specific wallet
defi-tracker wallet 0xYourWalletAddress --chain eth

# 6. Export to CSV
defi-tracker scan --csv results/wallets.csv --json results/wallets.json
```

## Data Sources

### Free (no API key required)
- **GeckoTerminal** — new pool discovery, trade extraction, OHLCV
- **DexScreener** — trending tokens, pair data

### Free tier (API key required)
| Source | Free Tier | Best For |
|--------|-----------|----------|
| [Cielo Finance](https://cielo.finance) | Credit-based | Win rates, PnL, real-time feed |
| [Moralis](https://moralis.io) | 40k CU/day | Wallet profitability summary |
| [Etherscan V2](https://etherscan.io/myapikey) | 100k calls/day | Token transfer history (60+ chains) |
| [Covalent/GoldRush](https://goldrush.dev) | 100k credits/month | Unified multi-chain data |

### Paid (optional, better coverage)
| Source | Best For |
|--------|----------|
| [Nansen](https://nansen.ai) | Smart money labels, entity tagging |
| [Arkham Intelligence](https://arkhamintelligence.com) | Entity clustering, DEX swap tracking |
| [DeBank Pro](https://debank.com) | Multi-chain portfolio, leaderboards |

## CLI Reference

```
defi-tracker scan         Discover and rank wallets across chains
defi-tracker wallet ADDR  Analyze a single wallet
defi-tracker list-chains  Show supported chains
defi-tracker export-seeds Export built-in seed wallet list
```

### scan options
```
--chain / -c         Chain to scan (repeatable). Default: eth bsc base arbitrum solana
--min-win-rate / -w  Minimum win rate % (default: 85)
--min-trades / -t    Minimum trade count (default: 10)
--min-mult / -m      Min multiplier for early entry (default: 5)
--top / -n           Show top N results (default: 50)
--csv PATH           Export CSV
--json PATH          Export JSON
--max-wallets        Max candidates per chain (default: 200)
```

## Output Example

```
╭────────────────────────────────────────────────────────────────────────────────────────╮
│         Top DeFi Smart Money Wallets (Win Rate ≥ 85%)                                 │
├──┬───────────────┬──────────────────┬──────────┬────────┬──────────┬──────────┬───────┤
│ #│ Wallet        │ Chains           │ Win Rate │ Trades │ Avg Mult │ Max Mult │ Score │
├──┼───────────────┼──────────────────┼──────────┼────────┼──────────┼──────────┼───────┤
│ 1│ 0xab12…ef56  │ eth, base        │ 94.2%    │    143 │   6.81x  │  127.4x  │  87.3 │
│ 2│ GThUX1…hFMJ  │ solana           │ 91.5%    │     87 │   4.92x  │   43.2x  │  74.1 │
│ 3│ 0xcd34…ab78  │ bsc, arbitrum    │ 88.0%    │     55 │   3.44x  │   18.6x  │  66.2 │
╰──┴───────────────┴──────────────────┴──────────┴────────┴──────────┴──────────┴───────╯
```

## Architecture

```
defi-wallet-tracker/
├── src/
│   ├── chains/         Chain registry (ETH, BSC, Base, Arb, Polygon, OP, AVAX, SOL)
│   ├── scrapers/       API clients
│   │   ├── dexscreener.py    New pairs, trending tokens
│   │   ├── geckoterminal.py  Pool trades, OHLCV, new pools
│   │   ├── cielo.py          Win rates, PnL
│   │   ├── moralis.py        Wallet profitability, swap history
│   │   └── etherscan.py      Token transfers (multi-chain)
│   ├── analyzers/      Analysis logic
│   │   ├── win_rate.py       Pair buy/sell, calculate PnL
│   │   ├── early_entry.py    Detect sub-4h entries in 5x+ tokens
│   │   └── wallet_scorer.py  Composite ranking
│   ├── trackers/
│   │   └── wallet_tracker.py Full pipeline orchestrator
│   ├── output/
│   │   ├── console.py        Rich table rendering
│   │   └── export.py         CSV/JSON export
│   └── models/         Dataclasses: Wallet, Trade, Token, WalletScore
├── data/
│   └── known_smart_money.json  Seed wallet list + source directory
├── tests/
└── .env.example
```

## Scoring Formula

```
score = (win_rate × 0.60) + (min(avg_multiplier, 20) × 2) + (min(early_entries, 10) × 1.5) + volume_bonus
```

Wallets need `win_rate ≥ 85%` and `total_trades ≥ 10` to appear in results.
