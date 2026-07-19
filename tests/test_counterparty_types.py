import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.enrich_counterparty_types import (
    EVIDENCE_SCHEMA_VERSION,
    FIELDNAMES,
    decode_address_array,
    decode_code,
    fetch_account_evidence,
    load_manifest,
    safe_evidence,
    select_candidates,
    write_rows,
)


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query):
        return self

    def fetchall(self):
        return self.rows


def word(value: int) -> str:
    return value.to_bytes(32, "big").hex()


def address_word(address: str) -> str:
    return address.removeprefix("0x").rjust(64, "0")


def encoded_owners(*addresses: str) -> str:
    return "0x" + word(32) + word(len(addresses)) + "".join(address_word(address) for address in addresses)


class FakeEvidenceClient:
    SAFE_ADDRESS = "0x3333333333333333333333333333333333333333"
    EOA_ADDRESS = "0x2222222222222222222222222222222222222222"

    def batch(self, requests):
        results = {}
        for method, _params, key in requests:
            address, field = key
            if field == "code":
                results[key] = "0x6001" if address == self.SAFE_ADDRESS else "0x"
            elif field == "singleton":
                results[key] = "0x" + address_word("0xd9db270c1b5e3bd161e8c8503c55ceabee709552")
            elif field == "owners":
                results[key] = encoded_owners(
                    "0x1111111111111111111111111111111111111111",
                    "0x2222222222222222222222222222222222222222",
                )
            elif field == "threshold":
                results[key] = "0x" + word(1)
            elif method == "eth_getLogs" and field == "erc4337:0.7" and address == self.SAFE_ADDRESS:
                results[key] = [{"blockNumber": "0x5a"}]
            elif method == "eth_getLogs":
                results[key] = []
        return results


class CounterpartyTypeTest(unittest.TestCase):
    def test_decodes_no_code_contract_delegation_and_failures(self) -> None:
        target = "11" * 20
        self.assertEqual(decode_code("0x"), ("no_code", 0, None, "complete", "no_code_observed"))
        self.assertEqual(
            decode_code("0xef0100" + target),
            ("eip7702_delegated", 23, "0x" + target, "complete", "eip7702_delegation_observed"),
        )
        self.assertEqual(decode_code("0xef0100" + target + "00")[0], "contract_code")
        self.assertEqual(decode_code("0xef0101" + target)[0], "contract_code")
        self.assertEqual(decode_code("0x60016000"), ("contract_code", 4, None, "complete", "contract_code_observed"))
        self.assertEqual(decode_code(None), ("unknown", None, None, "failed", "code_lookup_missing"))
        self.assertEqual(decode_code("0xnothex"), ("unknown", None, None, "failed", "code_lookup_malformed"))

    def test_requires_official_singleton_and_consistent_safe_calls(self) -> None:
        manifest = load_manifest()
        deployments = {item["address"]: item for item in manifest["safe_singletons"]}
        owners = encoded_owners(
            "0x1111111111111111111111111111111111111111",
            "0x2222222222222222222222222222222222222222",
        )
        verified = safe_evidence(
            "0xd9db270c1b5e3bd161e8c8503c55ceabee709552",
            owners,
            "0x" + word(2),
            deployments,
        )
        self.assertTrue(verified["safe_verified"])
        self.assertEqual(verified["safe_version"], "1.3.0")
        self.assertEqual(verified["safe_owner_count"], 2)
        self.assertEqual(verified["safe_threshold"], 2)

        interface_only = safe_evidence(
            "0x9999999999999999999999999999999999999999",
            owners,
            "0x" + word(1),
            deployments,
        )
        self.assertFalse(interface_only["safe_verified"])
        self.assertEqual(interface_only["safe_verification_status"], "singleton_not_official")

        inconsistent = safe_evidence(
            "0xd9db270c1b5e3bd161e8c8503c55ceabee709552",
            owners,
            "0x" + word(3),
            deployments,
        )
        self.assertFalse(inconsistent["safe_verified"])
        self.assertEqual(inconsistent["safe_verification_status"], "calls_inconsistent")

    def test_decodes_strict_owner_array_shape(self) -> None:
        owners = encoded_owners("0x1111111111111111111111111111111111111111")
        self.assertEqual(decode_address_array(owners), ["0x1111111111111111111111111111111111111111"])
        self.assertIsNone(decode_address_array(owners + "00"))

    def test_retains_safe_and_erc4337_evidence_independently(self) -> None:
        rows = fetch_account_evidence(
            FakeEvidenceClient(),
            [FakeEvidenceClient.SAFE_ADDRESS, FakeEvidenceClient.EOA_ADDRESS],
            "0x64",
            "2023-11-18T12:00:00+00:00",
            80,
            load_manifest(),
        )
        safe = rows[0]
        self.assertEqual(safe["account_type"], "safe")
        self.assertTrue(safe["safe_verified"])
        self.assertTrue(safe["erc4337_observed"])
        self.assertEqual(safe["erc4337_entrypoint_version"], "0.7")
        self.assertEqual(safe["coverage_start_block"], 80)
        self.assertEqual(safe["coverage_end_block"], 100)
        self.assertEqual(rows[1]["account_type"], "eoa_candidate")

    def test_selects_ranked_unattempted_and_retry_candidates(self) -> None:
        connection = FakeConnection([("0x1", 100), ("0x2", 50), ("0x3", 25)])
        existing = {"0x1": {"fetch_status": "complete"}, "0x2": {"fetch_status": "partial"}}
        self.assertEqual(select_candidates(connection, existing, 10), ["0x3"])
        self.assertEqual(select_candidates(connection, existing, 10, retry_failed=True), ["0x2"])
        self.assertEqual(select_candidates(connection, existing, 2, refresh=True), ["0x1", "0x2"])

    def test_snapshot_merge_is_idempotent_and_sorted(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "addresses.csv"
            existing_row = {name: "" for name in FIELDNAMES}
            existing_row.update({
                "chain_id": 1,
                "address": "0x2",
                "account_type": "unknown",
                "code_state": "unknown",
                "fetch_status": "failed",
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
            })
            new_row = dict(existing_row)
            new_row.update({
                "address": "0x1",
                "account_type": "eoa_candidate",
                "code_state": "no_code",
                "code_size_bytes": 0,
                "observation_block_number": 100,
                "fetch_status": "complete",
            })
            write_rows({"0x2": existing_row}, [new_row], path)
            write_rows({"0x2": existing_row}, [new_row], path)
            with path.open(newline="") as source:
                written = list(csv.DictReader(source))
            self.assertEqual([row["address"] for row in written], ["0x1", "0x2"])


if __name__ == "__main__":
    unittest.main()
