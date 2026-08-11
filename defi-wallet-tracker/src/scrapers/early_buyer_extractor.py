"""
Extract early buyers of a token using Etherscan V2.

For each high-multiplier token:
  1. Get the first 500 ERC-20 transfers (sorted asc) → find the first buyers
  2. Filter to wallets that bought within the first N hours of the first transfer
  3. Exclude: contracts, known routers/DEXes, the token deployer
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable

from ..chains import get_chain
from ..scrapers.etherscan import EtherscanClient

# Known DEX routers / aggregators to exclude
EXCLUDE_ADDRESSES = {
    # Uniswap V2/V3
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    "0xe592427a0aece92de3edee1f18e0157c05861564",
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45",
    # 1inch
    "0x1111111254eeb25477b68fb85ed929f73a960582",
    "0x1111111254fb6c44bac0bed2854e76f90643097d",
    # Uniswap Universal Router
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad",
    # SushiSwap
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f",
    # PancakeSwap
    "0x10ed43c718714eb63d5aa57b78b54704e256024e",
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4",
    # Null / burn
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}


class EarlyBuyerExtractor:
    def __init__(
        self,
        etherscan_key: str,
        max_hours_after_first_tx: float = 6.0,
        max_buyers: int = 100,
    ) -> None:
        self._key = etherscan_key
        self._window = timedelta(hours=max_hours_after_first_tx)
        self._max_buyers = max_buyers

    async def get_early_buyers(
        self,
        token_address: str,
        chain: str,
        listed_at: datetime | None = None,
    ) -> list[str]:
        """
        Return wallet addresses that bought the token early.
        Uses ascending token transfer order to find the first buyers.
        """
        chain_obj = get_chain(chain)
        if not chain_obj.is_evm:
            return []

        async with EtherscanClient(self._key) as escan:
            # Get first 200 transfers sorted ascending (earliest = first buyers)
            raw = await escan.get_token_transfers_by_contract(
                token_address,
                chain_obj.etherscan_chain_id,
                page=1,
                offset=200,
                sort="asc",
            )

        if not raw:
            return []

        # Sort ascending by block number
        raw.sort(key=lambda x: int(x.get("blockNumber") or 0))

        # Find the timestamp of the first transfer
        first_ts = None
        for tx in raw:
            ts = int(tx.get("timeStamp") or 0)
            if ts > 0:
                first_ts = datetime.fromtimestamp(ts, tz=timezone.utc)
                break

        if first_ts is None:
            if listed_at:
                first_ts = listed_at
            else:
                return []

        cutoff = first_ts + self._window
        buyers: list[str] = []
        seen: set[str] = set()

        for tx in raw:
            ts = int(tx.get("timeStamp") or 0)
            tx_time = datetime.fromtimestamp(ts, tz=timezone.utc) if ts > 0 else first_ts

            if tx_time > cutoff:
                break

            # "to" is the wallet receiving the token (buyer in a pool buy)
            to_addr = (tx.get("to") or "").lower()
            from_addr = (tx.get("from") or "").lower()

            # The receiver of the token is the buyer
            wallet = to_addr
            if wallet in EXCLUDE_ADDRESSES or wallet in seen or not wallet:
                # Try the sender too (in some transfer patterns)
                wallet = from_addr
                if wallet in EXCLUDE_ADDRESSES or wallet in seen or not wallet:
                    continue

            seen.add(wallet)
            buyers.append(wallet)

            if len(buyers) >= self._max_buyers:
                break

        return buyers

    async def get_early_buyers_many(
        self,
        tokens: list[dict],  # [{address, chain, listed_at, multiplier}, ...]
        concurrency: int = 3,
    ) -> dict[str, list[str]]:
        """
        Returns {token_address: [wallet, ...]} for all provided tokens.
        """
        sem = asyncio.Semaphore(concurrency)

        async def _fetch(token: dict) -> tuple[str, str, list[str]]:
            async with sem:
                addr = token.get("address", "")
                chain = token.get("chain", "eth")
                listed_at = token.get("listed_at")
                try:
                    buyers = await self.get_early_buyers(addr, chain, listed_at)
                    return addr, chain, buyers
                except Exception:
                    return addr, chain, []

        results = await asyncio.gather(*[_fetch(t) for t in tokens])
        return {addr: (chain, buyers) for addr, chain, buyers in results}
