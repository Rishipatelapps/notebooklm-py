#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# DeFi Wallet Tracker — local setup script
# Run this once after cloning into your Subway/projects folder:
#   cd Subway/projects
#   git clone https://github.com/Rishipatelapps/notebooklm-py -b claude/defi-wallet-tracker-0a7t9m
#   cd notebooklm-py/defi-wallet-tracker
#   bash setup_local.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "=== DeFi Wallet Tracker — Local Setup ==="

# Check Python
python3 --version || { echo "ERROR: Python 3.11+ required"; exit 1; }

# Create virtual env
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -e ".[dev]" --quiet

# Copy env template
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "✅ Created .env from template."
  echo "   Edit .env and add your API keys:"
  echo "   - ETHERSCAN_API_KEY  (free at etherscan.io)  ← most important"
  echo "   - COINGECKO_API_KEY  (free at coingecko.com)"
  echo "   - GMGN_API_KEY       (gmgn.ai)"
else
  echo "✅ .env already exists — skipping"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Activate venv:   source .venv/bin/activate"
echo "Run scan:        defi-tracker scan"
echo "Full options:    defi-tracker scan --help"
echo ""
echo "Quick scan examples:"
echo "  defi-tracker scan --chain eth --chain solana --top 20"
echo "  defi-tracker scan --min-win-rate 90 --min-mult 10 --csv results.csv"
echo "  defi-tracker wallet 0xYourAddress --chain eth"
