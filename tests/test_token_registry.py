import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.project_config import PUBLIC_RPC_FALLBACK, configured_value, load_config, resolved_runtime
from scripts.sync_token_registry import merge_registries, normalize_tokens


class TokenRegistryTest(unittest.TestCase):
    def test_configuration_prefers_environment_then_yaml_then_public_fallback(self) -> None:
        config = {"ethereum": {"rpc_url": "https://yaml.example", "public_rpc_url": "https://public.example"}}
        self.assertEqual(
            configured_value("ETHEREUM_RPC_URL", config, "ethereum", "rpc_url", environ={"ETHEREUM_RPC_URL": "https://env.example"}),
            "https://env.example",
        )
        self.assertEqual(configured_value("ETHEREUM_RPC_URL", config, "ethereum", "rpc_url", environ={}), "https://yaml.example")
        self.assertEqual(resolved_runtime({})["ethereum_rpc_url"], PUBLIC_RPC_FALLBACK)

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
        self.assertEqual(rows[0]["token_status"], "trusted")

    def test_rejects_decimal_conflicts(self) -> None:
        address = "0x" + "a" * 40
        trust = {address: {"token_address": address, "symbol": "AAA", "name": "A", "decimals": 18}}
        uniswap = {address: {"token_address": address, "symbol": "AAA", "name": "A", "decimals": 6}}

        with self.assertRaisesRegex(ValueError, "Conflicting decimals"):
            merge_registries(trust, uniswap)


if __name__ == "__main__":
    unittest.main()
