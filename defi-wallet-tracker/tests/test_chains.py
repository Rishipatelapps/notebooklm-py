"""Test chain registry."""
import pytest
from src.chains import get_chain, supported_chains, CHAINS


def test_all_chains_have_required_fields() -> None:
    for cid, chain in CHAINS.items():
        assert chain.id == cid
        assert chain.name
        assert chain.native_symbol
        assert chain.dexscreener_id
        assert chain.geckoterminal_id


def test_get_chain_valid() -> None:
    eth = get_chain("eth")
    assert eth.chain_id == 1
    assert eth.is_evm is True
    assert eth.moralis_chain == "eth"


def test_get_chain_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown chain"):
        get_chain("moon")


def test_supported_chains_includes_solana() -> None:
    chains = supported_chains()
    assert "solana" in chains
    assert "eth" in chains
    assert "bsc" in chains
    assert "base" in chains


def test_solana_is_non_evm() -> None:
    sol = get_chain("solana")
    assert sol.is_evm is False
    assert sol.chain_id == 0
