import unittest
from datetime import datetime, timezone

from server.ens import (
    ENS_REGISTRY_ADDRESS,
    ENSNotRecognizedError,
    FinalizedObservation,
    namehash,
    normalize_address,
    normalize_ens_name,
    resolve_scan_input,
)

TARGET = "0x" + "12" * 20
RESOLVER = "0x" + "34" * 20
OBSERVATION = FinalizedObservation(
    19_000_000,
    "0x" + "ab" * 32,
    datetime(2026, 1, 2, tzinfo=timezone.utc),
)


def encoded_address(address: str) -> str:
    return "0x" + "0" * 24 + address[2:]


class MockRpc:
    def __init__(self) -> None:
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_call" and params[0]["to"] == ENS_REGISTRY_ADDRESS:
            return encoded_address(RESOLVER)
        if method == "eth_call" and params[0]["to"] == RESOLVER:
            return encoded_address(TARGET)
        raise AssertionError((method, params))


class FinalizedMockRpc(MockRpc):
    def call(self, method, params):
        if method == "eth_getBlockByNumber":
            self.calls.append((method, params))
            return {
                "number": hex(OBSERVATION.block_number),
                "hash": OBSERVATION.block_hash,
                "timestamp": hex(int(OBSERVATION.observed_at.timestamp())),
            }
        return super().call(method, params)


class ENSResolutionTest(unittest.TestCase):
    def test_normalizes_addresses_and_safe_names(self) -> None:
        self.assertEqual(normalize_address("  0xAB" + "CD" * 19 + "  "), "0x" + "ab" + "cd" * 19)
        self.assertEqual(normalize_ens_name(" Vitalik.ETH. "), "vitalik.eth")
        with self.assertRaises(ENSNotRecognizedError):
            normalize_ens_name("paypa\u043b.eth")
        with self.assertRaises(ENSNotRecognizedError):
            normalize_ens_name("-bad.eth")

    def test_resolves_ens_at_one_pinned_observation_block(self) -> None:
        rpc = MockRpc()
        result = resolve_scan_input(" Vitalik.ETH ", rpc, observation=OBSERVATION)

        self.assertEqual(result.original_input, "Vitalik.ETH")
        self.assertEqual(result.normalized_name, "vitalik.eth")
        self.assertEqual(result.resolved_address, TARGET)
        self.assertIn(f"resolver:{RESOLVER}", result.resolver_source)
        self.assertEqual(result.observation_block_number, OBSERVATION.block_number)
        self.assertEqual(result.observation_block_hash, OBSERVATION.block_hash)
        self.assertEqual([call[1][1] for call in rpc.calls], [hex(OBSERVATION.block_number)] * 2)

    def test_fetches_finalized_block_and_records_timestamp_when_not_injected(self) -> None:
        rpc = FinalizedMockRpc()
        result = resolve_scan_input("vitalik.eth", rpc)
        self.assertEqual(result.observation_block_number, OBSERVATION.block_number)
        self.assertEqual(result.observation_block_hash, OBSERVATION.block_hash)
        self.assertEqual(result.observed_at, OBSERVATION.observed_at)
        self.assertEqual(rpc.calls[0][1], ["finalized", False])

    def test_direct_address_does_not_call_ens_contracts(self) -> None:
        rpc = MockRpc()
        result = resolve_scan_input("0x" + TARGET[2:].upper(), rpc, observation=OBSERVATION)
        self.assertEqual(result.resolved_address, TARGET)
        self.assertEqual(result.resolver_source, "direct-address")
        self.assertEqual(rpc.calls, [])

    def test_unresolved_name_cannot_become_a_target(self) -> None:
        class UnresolvedRpc(MockRpc):
            def call(self, method, params):
                self.calls.append((method, params))
                return "0x" + "0" * 64

        with self.assertRaisesRegex(ENSNotRecognizedError, "not recognized"):
            resolve_scan_input("missing.eth", UnresolvedRpc(), observation=OBSERVATION)

    def test_namehash_matches_ens_empty_name_vector(self) -> None:
        self.assertEqual(namehash("eth").hex(), "93cdeb708b7545dc668eb9280176169d1c33cfd8ed6f04690a0bcc88a93fc4ae")


if __name__ == "__main__":
    unittest.main()
