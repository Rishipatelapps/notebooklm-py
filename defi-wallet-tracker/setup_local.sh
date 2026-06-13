#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DeFi Wallet Tracker — local setup script
#
# Run this once after cloning into your Subway/projects folder:
#   cd ~/Subway/projects
#   git clone https://github.com/Rishipatelapps/notebooklm-py -b claude/defi-wallet-tracker-0a7t9m
#   cd notebooklm-py/defi-wallet-tracker
#   bash setup_local.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "=== DeFi Wallet Tracker — Local Setup ==="
echo ""

# Check Python
python3 --version || { echo "ERROR: Python 3.11+ required"; exit 1; }

# Create virtual env
echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install all dependencies (includes streamlit + plotly for dashboard)
echo "Installing dependencies..."
pip install -e ".[dev]" --quiet

# Copy env template
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "✅ Created .env from template."
  echo "   Edit .env and fill in your API keys:"
  echo ""
  echo "   Required (free):"
  echo "   - ETHERSCAN_API_KEY   → etherscan.io/myapikey      (covers ETH/BSC/Base/Arbitrum)"
  echo "   - COINGECKO_API_KEY   → coingecko.com/en/api       (demo key, free)"
  echo ""
  echo "   Optional (improves results):"
  echo "   - GMGN_API_KEY        → gmgn.ai                    (Solana/Base leaderboard)"
  echo "   - BIRDEYE_API_KEY     → bds.birdeye.so             (best Solana token data)"
  echo "   - CIELO_API_KEY       → cielo.finance/developer    (on-chain PnL scoring)"
  echo ""
  echo "   Pre-filled (from session):"
  echo "   - CIELO_API_KEY=a7a41571-3cf9-4985-8a54-b3ac0267286d"
else
  echo "✅ .env already exists — skipping copy"
fi

# Prefill Cielo key if not already set
if [ -f .env ] && ! grep -q "CIELO_API_KEY=." .env; then
  echo "CIELO_API_KEY=a7a41571-3cf9-4985-8a54-b3ac0267286d" >> .env
  echo "✅ Added Cielo API key to .env"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "┌─────────────────────────────────────────────────────────────┐"
echo "│  ACTIVATE VENV:    source .venv/bin/activate                │"
echo "│                                                             │"
echo "│  DASHBOARD:        defi-tracker dashboard                   │"
echo "│  (opens at http://localhost:8501 — best way to explore)     │"
echo "│                                                             │"
echo "│  CLI SCANS:                                                 │"
echo "│    defi-tracker scan --chain eth --top 50                   │"
echo "│    defi-tracker scan --chain eth --chain solana --top 50    │"
echo "│    defi-tracker scan --min-mult 10 --top 20                 │"
echo "│    defi-tracker scan --json data/my_scan.json               │"
echo "│                                                             │"
echo "│  SINGLE WALLET:                                             │"
echo "│    defi-tracker wallet 0xYourAddress --chain eth            │"
echo "│                                                             │"
echo "│  HELP:             defi-tracker scan --help                 │"
echo "└─────────────────────────────────────────────────────────────┘"
echo ""
