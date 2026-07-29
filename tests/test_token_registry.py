import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.project_config import (
    DEFAULT_HYPERINDEX_GRAPHQL_URL,
    PUBLIC_RPC_FALLBACK,
    configured_value,
    load_config,
    resolved_runtime,
)
from scripts.sync_token_registry import (
    merge_registries,
    normalize_coinbase_currencies,
    normalize_tokens,
)


class TokenRegistryTest(unittest.TestCase):
    def test_coingecko_only_oscar_and_puppies_are_single_source_listings(self) -> None:
        seed_path = Path(__file__).parents[1] / "analytics" / "seeds" / "token_metadata.csv"
        with seed_path.open(newline="") as source:
            rows = {row["token_address"]: row for row in csv.DictReader(source)}

        for address in (
            "0xebb66a88cedd12bfe3a289df6dfee377f2963f12",
            "0xcf91b70017eabde82c9671e30e5502d312ea6eb2",
        ):
            with self.subTest(address=address):
                self.assertEqual(rows[address]["metadata_source"], "coingecko")

    def test_configuration_prefers_environment_then_yaml_then_public_fallback(self) -> None:
        config = {"ethereum": {"rpc_url": "https://yaml.example", "public_rpc_url": "https://public.example"}}
        self.assertEqual(
            configured_value("ETHEREUM_RPC_URL", config, "ethereum", "rpc_url", environ={"ETHEREUM_RPC_URL": "https://env.example"}),
            "https://env.example",
        )
        self.assertEqual(configured_value("ETHEREUM_RPC_URL", config, "ethereum", "rpc_url", environ={}), "https://yaml.example")
        self.assertEqual(resolved_runtime({})["ethereum_rpc_url"], PUBLIC_RPC_FALLBACK)
        self.assertEqual(
            resolved_runtime({})["hyperindex_graphql_url"],
            DEFAULT_HYPERINDEX_GRAPHQL_URL,
        )

    def test_configuration_rejects_non_mapping_yaml(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "config.yaml"
            path.write_text("- invalid\n")
            with self.assertRaisesRegex(ValueError, "YAML mapping"):
                load_config(path)

    def test_normalizes_mainnet_addresses_and_ignores_other_chains(self) -> None:
        payload = {
            "tokens": [
                {"chainId": 1, "address": "0x" + "A" * 40, "symbol": " AAA ", "name": "Token A", "decimals": 18},
                {"chainId": 10, "address": "0x" + "B" * 40, "symbol": "BBB", "name": "Token B", "decimals": 6},
            ]
        }

        result = normalize_tokens(payload, "test")

        self.assertEqual(list(result), ["0x" + "a" * 40])
        self.assertEqual(result["0x" + "a" * 40]["symbol"], "AAA")

    def test_accepts_missing_chain_id_for_chain_scoped_sources(self) -> None:
        payload = {
            "tokens": [
                {"address": "0x" + "A" * 40, "symbol": "AAA", "name": "Token A", "decimals": 18},
            ]
        }

        result = normalize_tokens(payload, "test", default_chain_id=1)

        self.assertIn("0x" + "a" * 40, result)

    def test_merges_sources_with_trust_wallet_precedence(self) -> None:
        address = "0x" + "a" * 40
        trust = {address: {"token_address": address, "symbol": "AAA", "name": "Trust Name", "decimals": 18}}
        uniswap = {address: {"token_address": address, "symbol": "A", "name": "Uniswap Name", "decimals": 18}}

        rows = merge_registries(trust, uniswap)

        self.assertEqual(rows[0]["name"], "Trust Name")
        self.assertEqual(rows[0]["metadata_source"], "trustwallet+uniswap")

    def test_adds_coingecko_by_exact_contract_address(self) -> None:
        address = "0x" + "c" * 40
        coingecko = {address: {
            "token_address": address, "symbol": "CG", "name": "CoinGecko Token", "decimals": 18,
        }}

        rows = merge_registries({}, {}, coingecko)

        self.assertEqual(rows[0]["token_address"], address)
        self.assertEqual(rows[0]["metadata_source"], "coingecko")
        self.assertEqual(rows[0]["recognition_status"], "recognized")

    def test_adds_online_coinbase_ethereum_contract_without_inventing_decimals(self) -> None:
        address = "0x" + "d" * 40
        currencies = [{
            "id": "ASSET",
            "name": "Coinbase Asset",
            "status": "online",
            "details": {"type": "crypto"},
            "max_precision": "0.0001",
            "supported_networks": [{
                "name": "Ethereum",
                "status": "online",
                "contract_address": address,
            }],
        }]

        coinbase = normalize_coinbase_currencies(currencies)
        rows = merge_registries({}, {}, {}, coinbase)

        self.assertIsNone(rows[0]["decimals"])
        self.assertEqual(rows[0]["metadata_source"], "coinbase")

    def test_ignores_offline_or_non_ethereum_coinbase_networks(self) -> None:
        address = "0x" + "d" * 40
        currencies = [{
            "id": "ASSET",
            "name": "Coinbase Asset",
            "status": "online",
            "details": {"type": "crypto"},
            "supported_networks": [
                {"name": "Ethereum", "status": "offline", "contract_address": address},
                {"name": "Base", "status": "online", "contract_address": address},
                {"name": "Ethereum", "status": "online", "contract_address": "None"},
            ],
        }]

        self.assertEqual(normalize_coinbase_currencies(currencies), {})

    def test_rejects_decimal_conflicts(self) -> None:
        address = "0x" + "a" * 40
        trust = {address: {"token_address": address, "symbol": "AAA", "name": "A", "decimals": 18}}
        uniswap = {address: {"token_address": address, "symbol": "AAA", "name": "A", "decimals": 6}}

        with self.assertRaisesRegex(ValueError, "Conflicting decimals"):
            merge_registries(trust, uniswap)


if __name__ == "__main__":
    unittest.main()
