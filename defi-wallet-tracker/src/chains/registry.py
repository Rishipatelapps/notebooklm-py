from dataclasses import dataclass, field


@dataclass
class Chain:
    id: str                  # short slug: "eth", "bsc", "sol", etc.
    name: str
    chain_id: int            # EVM chain ID (0 for non-EVM)
    native_symbol: str
    # API slugs per data source
    dexscreener_id: str = ""
    geckoterminal_id: str = ""
    moralis_chain: str = ""
    etherscan_chain_id: int = 0   # for Etherscan v2 multichain
    blockscout_chain_id: str = ""
    covalent_chain: str = ""
    is_evm: bool = True
    explorer_url: str = ""
    rpc_url: str = ""
    extra: dict = field(default_factory=dict)


CHAINS: dict[str, Chain] = {
    "eth": Chain(
        id="eth", name="Ethereum", chain_id=1,
        native_symbol="ETH",
        dexscreener_id="ethereum",
        geckoterminal_id="eth",
        moralis_chain="eth",
        etherscan_chain_id=1,
        blockscout_chain_id="1",
        covalent_chain="eth-mainnet",
        explorer_url="https://etherscan.io",
    ),
    "bsc": Chain(
        id="bsc", name="BNB Chain", chain_id=56,
        native_symbol="BNB",
        dexscreener_id="bsc",
        geckoterminal_id="bsc",
        moralis_chain="bsc",
        etherscan_chain_id=56,
        blockscout_chain_id="56",
        covalent_chain="bsc-mainnet",
        explorer_url="https://bscscan.com",
    ),
    "base": Chain(
        id="base", name="Base", chain_id=8453,
        native_symbol="ETH",
        dexscreener_id="base",
        geckoterminal_id="base",
        moralis_chain="base",
        etherscan_chain_id=8453,
        blockscout_chain_id="8453",
        covalent_chain="base-mainnet",
        explorer_url="https://basescan.org",
    ),
    "arbitrum": Chain(
        id="arbitrum", name="Arbitrum One", chain_id=42161,
        native_symbol="ETH",
        dexscreener_id="arbitrum",
        geckoterminal_id="arbitrum",
        moralis_chain="arbitrum",
        etherscan_chain_id=42161,
        blockscout_chain_id="42161",
        covalent_chain="arbitrum-mainnet",
        explorer_url="https://arbiscan.io",
    ),
    "polygon": Chain(
        id="polygon", name="Polygon", chain_id=137,
        native_symbol="MATIC",
        dexscreener_id="polygon",
        geckoterminal_id="polygon_pos",
        moralis_chain="polygon",
        etherscan_chain_id=137,
        blockscout_chain_id="137",
        covalent_chain="matic-mainnet",
        explorer_url="https://polygonscan.com",
    ),
    "optimism": Chain(
        id="optimism", name="Optimism", chain_id=10,
        native_symbol="ETH",
        dexscreener_id="optimism",
        geckoterminal_id="optimism",
        moralis_chain="optimism",
        etherscan_chain_id=10,
        blockscout_chain_id="10",
        covalent_chain="optimism-mainnet",
        explorer_url="https://optimistic.etherscan.io",
    ),
    "avalanche": Chain(
        id="avalanche", name="Avalanche C-Chain", chain_id=43114,
        native_symbol="AVAX",
        dexscreener_id="avalanche",
        geckoterminal_id="avax",
        moralis_chain="avalanche",
        etherscan_chain_id=43114,
        blockscout_chain_id="43114",
        covalent_chain="avalanche-mainnet",
        explorer_url="https://snowtrace.io",
    ),
    "solana": Chain(
        id="solana", name="Solana", chain_id=0,
        native_symbol="SOL",
        dexscreener_id="solana",
        geckoterminal_id="solana",
        moralis_chain="solana",
        etherscan_chain_id=0,
        blockscout_chain_id="",
        covalent_chain="solana-mainnet",
        is_evm=False,
        explorer_url="https://solscan.io",
    ),
}


def get_chain(chain_id: str) -> Chain:
    chain = CHAINS.get(chain_id.lower())
    if chain is None:
        raise ValueError(f"Unknown chain: {chain_id!r}. Choose from: {list(CHAINS)}")
    return chain


def supported_chains() -> list[str]:
    return list(CHAINS.keys())
