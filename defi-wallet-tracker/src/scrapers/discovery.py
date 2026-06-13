"""
Multi-source token discovery for high-multiplier tokens.

Sources:
  1. CoinGecko /coins/markets sorted by 30d/7d price change → tokens that already ran 5x+
  2. CoinGecko /search/trending → currently hot tokens
  3. GeckoTerminal /trending_pools (multiple pages) → high-volume pools
  4. DexScreener /token-boosts/top → promoted tokens with momentum
  5. Birdeye /defi/token_trending + /defi/v2/tokens/new_listing → Solana + multi-chain
"""
import asyncio
from datetime import datetime, timezone

from .base import BaseClient
from .birdeye import BirdeyeClient, BIRDEYE_CHAINS
from .coingecko import CoinGeckoClient, GECKO_NETWORKS
from .geckoterminal import GeckoTerminalClient
from .dexscreener import DexScreenerClient

_COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class TokenDiscovery:
    """Find tokens that have achieved ≥ min_multiplier since listing."""

    MAX_MULTIPLIER = 10_000.0  # sanity cap — anything higher is likely a data artifact

    def __init__(
        self,
        coingecko_key: str = "",
        birdeye_key: str = "",
        min_multiplier: float = 5.0,
        min_liquidity_usd: float = 5_000,
    ) -> None:
        self._cg_key = coingecko_key
        self._birdeye_key = birdeye_key
        self._min_mult = min_multiplier
        self._min_liquidity = min_liquidity_usd

    async def find_high_multiplier_tokens(
        self, chains: list[str], max_tokens: int = 50
    ) -> list[dict]:
        """
        Return list of dicts: {address, symbol, chain, multiplier, pair_address, listed_at}
        """
        results: list[dict] = []
        seen: set[str] = set()

        tasks = []

        if self._cg_key:
            tasks.append(self._from_coingecko_gainers(chains))
            tasks.append(self._from_coingecko_trending(chains))

        tasks.append(self._from_gecko_terminal(chains))
        tasks.append(self._from_dexscreener(chains))

        if self._birdeye_key:
            tasks.append(self._from_birdeye(chains))

        gathered = await asyncio.gather(*tasks, return_exceptions=True)
        for batch in gathered:
            if isinstance(batch, list):
                for item in batch:
                    key = f"{item.get('chain')}:{item.get('address','').lower()}"
                    if key in seen or not item.get('address'):
                        continue
                    seen.add(key)
                    results.append(item)

        # Remove data artifacts: multiplier > 10000x is almost always a bad price feed
        results = [r for r in results if r.get("multiplier", 0) <= self.MAX_MULTIPLIER]
        results.sort(key=lambda x: x.get("multiplier", 0), reverse=True)
        return results[:max_tokens]

    async def _from_coingecko_gainers(self, chains: list[str]) -> list[dict]:
        """Tokens with highest 30d price change — best signal for 5x+ runs."""
        headers = {"x-cg-pro-api-key": self._cg_key}

        class _Client(BaseClient):
            pass

        results = []
        chain_platforms = {
            "eth": "ethereum", "bsc": "binance-smart-chain",
            "base": "base", "arbitrum": "arbitrum-one",
            "polygon": "polygon-pos", "optimism": "optimistic-ethereum",
            "avalanche": "avalanche", "solana": "solana",
        }

        async with _Client(_COINGECKO_BASE, headers={"x-cg-demo-api-key": self._cg_key}, rate_limit_rps=0.8) as client:
            # Get top 250 coins by 30d price change
            for timeframe in ["30d", "7d"]:
                try:
                    data = await client._get(
                        "/coins/markets",
                        params={
                            "vs_currency": "usd",
                            "order": f"price_change_percentage_{timeframe}_desc",
                            "per_page": 250,
                            "price_change_percentage": timeframe,
                            "sparkline": False,
                        },
                    )
                    for coin in (data or []):
                        change = coin.get(f"price_change_percentage_{timeframe}_in_currency") or \
                                 coin.get("price_change_percentage_30d") or 0
                        multiplier = (change / 100) + 1  # e.g. 400% → 5x
                        if multiplier < self._min_mult:
                            continue
                        platforms = coin.get("platforms") or {}
                        for chain_id, addr in platforms.items():
                            # Map CoinGecko platform name to our chain slug
                            slug = next(
                                (s for s, p in chain_platforms.items() if p == chain_id),
                                None
                            )
                            if slug and slug in chains and addr:
                                results.append({
                                    "address": addr.lower(),
                                    "symbol": coin.get("symbol", "").upper(),
                                    "name": coin.get("name", ""),
                                    "chain": slug,
                                    "multiplier": round(multiplier, 2),
                                    "pair_address": "",
                                    "listed_at": None,
                                    "source": f"coingecko_{timeframe}_gainer",
                                })
                except Exception:
                    pass

            # Also fetch trending coins
            try:
                trend_data = await client._get("/search/trending")
                for item in (trend_data or {}).get("coins", []):
                    coin = item.get("item", {})
                    platforms = coin.get("platforms") or {}
                    for chain_id, addr in platforms.items():
                        slug = next(
                            (s for s, p in chain_platforms.items() if p == chain_id),
                            None
                        )
                        if slug and slug in chains and addr:
                            results.append({
                                "address": addr.lower(),
                                "symbol": coin.get("symbol", "").upper(),
                                "chain": slug,
                                "multiplier": self._min_mult,  # unknown, assume qualifying
                                "pair_address": "",
                                "listed_at": None,
                                "source": "coingecko_trending",
                            })
            except Exception:
                pass

        return results

    async def _from_coingecko_trending(self, chains: list[str]) -> list[dict]:
        return []  # Already included in _from_coingecko_gainers

    async def _from_gecko_terminal(self, chains: list[str]) -> list[dict]:
        """
        Two-stage token discovery via GeckoTerminal:
          Stage A (fast): new pools — use h24 price change directly from pool attributes
          Stage B (OHLCV): trending pools — fetch 365-day daily OHLCV to find ATH multiplier
        """
        results = []
        from ..analyzers.early_entry import EarlyEntryAnalyzer
        early = EarlyEntryAnalyzer(min_multiplier=self._min_mult)
        min_gain_pct = (self._min_mult - 1) * 100  # e.g. 400% for 5x

        chain_map = {
            "eth": "eth", "bsc": "bsc", "base": "base",
            "arbitrum": "arbitrum", "polygon": "polygon_pos",
            "optimism": "optimism", "avalanche": "avax",
            "solana": "solana",
        }

        async with GeckoTerminalClient() as gecko:
            for chain in chains:
                chain_slug = chain_map.get(chain, chain)

                # Stage A: new pools — no OHLCV, use h24 price change attribute
                for page in range(1, 5):
                    try:
                        pools = await gecko.get_new_pools(chain_slug, page=page)
                        for pool in pools:
                            if not pool.pair_address or pool.volume_24h < 3_000:
                                continue
                            # price_change_24h is % (e.g. 400 = 5x)
                            h24_pct = pool.price_change_24h
                            if h24_pct >= min_gain_pct:
                                mult = round(h24_pct / 100 + 1, 2)
                                results.append({
                                    "address": pool.address or "",
                                    "symbol": pool.symbol,
                                    "chain": chain,
                                    "multiplier": mult,
                                    "pair_address": pool.pair_address,
                                    "listed_at": pool.listed_at,
                                    "source": "gecko_new",
                                })
                        await asyncio.sleep(0.3)
                    except Exception:
                        break

                # Stage B: trending pools — full 365-day OHLCV multiplier
                try:
                    trend_pools = await gecko.get_trending_pools(chain_slug)
                    for pool in trend_pools:
                        if not pool.pair_address or pool.volume_24h < 5_000:
                            continue
                        try:
                            # 365-day daily candles → catch tokens that ran 5x at any point
                            ohlcv = await gecko.get_pool_ohlcv(
                                chain_slug, pool.pair_address, timeframe="day", limit=365
                            )
                            mult = early.compute_token_multiplier(ohlcv)
                            if mult >= self._min_mult:
                                results.append({
                                    "address": pool.address or "",
                                    "symbol": pool.symbol,
                                    "chain": chain,
                                    "multiplier": round(mult, 2),
                                    "pair_address": pool.pair_address,
                                    "listed_at": pool.listed_at,
                                    "source": "gecko_trending",
                                })
                        except Exception:
                            continue
                except Exception:
                    pass

        return results

    async def _from_dexscreener(self, chains: list[str]) -> list[dict]:
        """DexScreener boosted/trending tokens + high-gain new pairs."""
        results = []
        dex_chain_map = {
            "eth": "ethereum", "bsc": "bsc", "base": "base",
            "arbitrum": "arbitrum", "polygon": "polygon",
            "optimism": "optimism", "avalanche": "avalanche",
            "solana": "solana",
        }
        min_gain_pct = (self._min_mult - 1) * 100  # 400% for 5x

        async with DexScreenerClient() as dex:
            # Boosted tokens (sorted by boost activity — good proxy for momentum)
            try:
                boosted = await dex.get_trending_tokens()
                boosted_addrs = {t.address.lower(): t.chain for t in boosted}
            except Exception:
                boosted_addrs = {}

            for chain in chains:
                dex_chain = dex_chain_map.get(chain, chain)
                try:
                    pairs = await dex.get_new_pairs(dex_chain, limit=50)
                    for token in pairs:
                        if not token.address:
                            continue
                        # Direct 24h gain filter
                        if token.price_change_24h >= min_gain_pct and token.volume_24h >= 5_000:
                            results.append({
                                "address": token.address,
                                "symbol": token.symbol,
                                "chain": chain,
                                "multiplier": round(token.price_change_24h / 100 + 1, 2),
                                "pair_address": token.pair_address,
                                "listed_at": token.listed_at,
                                "source": "dexscreener_new",
                            })
                        # Boosted tokens with any gain ≥ 50% (momentum signal)
                        elif (token.address.lower() in boosted_addrs
                              and token.price_change_24h >= 50
                              and token.volume_24h >= 10_000):
                            results.append({
                                "address": token.address,
                                "symbol": token.symbol,
                                "chain": chain,
                                "multiplier": max(round(token.price_change_24h / 100 + 1, 2),
                                                  self._min_mult),
                                "pair_address": token.pair_address,
                                "listed_at": token.listed_at,
                                "source": "dexscreener_boosted",
                            })
                except Exception:
                    pass
        return results

    async def _from_birdeye(self, chains: list[str]) -> list[dict]:
        """
        Birdeye trending + new listings across supported chains.
        Especially valuable for Solana where GeckoTerminal coverage is thinner.
        """
        results = []
        min_gain_pct = (self._min_mult - 1) * 100  # e.g. 400% for 5x

        birdeye_chains = [c for c in chains if c in BIRDEYE_CHAINS]
        if not birdeye_chains:
            return results

        async with BirdeyeClient(self._birdeye_key, chain=birdeye_chains[0]) as birdeye:
            for chain in birdeye_chains:
                # Trending tokens: find those with 24h price change ≥ min threshold
                try:
                    trending = await birdeye.get_trending_tokens(chain, limit=50)
                    for token in trending:
                        change = token.get("price_change_24h", 0)
                        liquidity = token.get("liquidity", 0)
                        if change >= min_gain_pct and liquidity >= self._min_liquidity:
                            results.append({
                                "address": token["address"],
                                "symbol": token.get("symbol", ""),
                                "chain": chain,
                                "multiplier": round(change / 100 + 1, 2),
                                "pair_address": token.get("address", ""),
                                "listed_at": None,
                                "source": "birdeye_trending",
                            })
                    await asyncio.sleep(0.7)
                except Exception:
                    pass

                # New listings: recently listed tokens with high 24h change
                try:
                    new_tokens = await birdeye.get_new_listings(
                        chain, limit=30, min_liquidity_usd=self._min_liquidity
                    )
                    for token in new_tokens:
                        change = token.get("price_change_24h", 0)
                        if change >= min_gain_pct:
                            results.append({
                                "address": token["address"],
                                "symbol": token.get("symbol", ""),
                                "chain": chain,
                                "multiplier": round(change / 100 + 1, 2),
                                "pair_address": token.get("address", ""),
                                "listed_at": None,
                                "source": "birdeye_new",
                            })
                    await asyncio.sleep(0.7)
                except Exception:
                    pass

        return results
