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
    fetch_erc4337_evidence,
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

    def __init__(self):
        self.log_filters = []

    def batch(self, requests):
        results = {}
        for method, _params, key in requests:
            if method == "eth_getLogs":
                log_filter = _params[0]
                self.log_filters.append(log_filter)
                sender_topics = log_filter["topics"][2]
                results[key] = [{
                    "blockNumber": "0x5a",
                    "topics": [
                        log_filter["topics"][0],
                        "0x" + "00" * 32,
                        "0x" + address_word(self.SAFE_ADDRESS),
                    ],
                }] if "0x" + address_word(self.SAFE_ADDRESS) in sender_topics else []
                continue
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
        return results


class RetryingLogClient:
    def __init__(self, fail_once=None, fail_always=None):
        self.fail_once = set(fail_once or [])
        self.fail_always = set(fail_always or [])
        self.attempts = {}

    def batch(self, requests):
        results = {}
        for _method, params, key in requests:
            log_filter = params[0]
            block_range = (int(log_filter["fromBlock"], 16), int(log_filter["toBlock"], 16))
            self.attempts[block_range] = self.attempts.get(block_range, 0) + 1
            if block_range in self.fail_always or (
                block_range in self.fail_once and self.attempts[block_range] == 1
            ):
                results[key] = None
            else:
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
        manifest = load_manifest()
        manifest["erc4337"]["entrypoints"] = [{
            **manifest["erc4337"]["entrypoints"][1],
            "deployment_block": 85,
        }]
        client = FakeEvidenceClient()
        rows = fetch_account_evidence(
            client,
            [FakeEvidenceClient.SAFE_ADDRESS, FakeEvidenceClient.EOA_ADDRESS],
            "0x64",
            "2023-11-18T12:00:00+00:00",
            80,
            manifest,
            erc4337_block_chunk_size=10,
            erc4337_address_batch_size=2,
            erc4337_max_retries=1,
        )
        safe = rows[0]
        self.assertEqual(safe["account_type"], "safe")
        self.assertTrue(safe["safe_verified"])
        self.assertTrue(safe["erc4337_observed"])
        self.assertEqual(safe["erc4337_entrypoint_version"], "0.7")
        self.assertEqual(safe["erc4337_entrypoint_deployment_block"], "85")
        self.assertIn(":85-100", safe["erc4337_effective_coverage"])
        self.assertEqual(safe["coverage_start_block"], 80)
        self.assertEqual(safe["coverage_end_block"], 100)
        self.assertEqual(rows[1]["account_type"], "eoa_candidate")
        self.assertEqual(
            [(int(item["fromBlock"], 16), int(item["toBlock"], 16)) for item in client.log_filters],
            [(85, 94), (95, 100)],
        )
        self.assertTrue(all(len(item["topics"][2]) == 2 for item in client.log_filters))

    def test_retries_failed_chunks_without_losing_successful_coverage(self) -> None:
        manifest = load_manifest()
        manifest["erc4337"]["entrypoints"] = [{
            **manifest["erc4337"]["entrypoints"][0],
            "deployment_block": 90,
        }]
        client = RetryingLogClient(fail_once={(90, 99)})
        evidence = fetch_erc4337_evidence(
            client,
            [FakeEvidenceClient.EOA_ADDRESS],
            80,
            109,
            manifest,
            block_chunk_size=10,
            address_batch_size=1,
            max_retries=1,
        )[FakeEvidenceClient.EOA_ADDRESS]
        self.assertTrue(evidence["complete"])
        self.assertEqual(evidence["failed_ranges"], "")
        self.assertIn(":90-109", evidence["effective_coverage"])
        self.assertEqual(client.attempts[(90, 99)], 2)
        self.assertEqual(client.attempts[(100, 109)], 1)

    def test_records_partial_evidence_after_chunk_retries_are_exhausted(self) -> None:
        manifest = load_manifest()
        manifest["erc4337"]["entrypoints"] = [{
            **manifest["erc4337"]["entrypoints"][0],
            "deployment_block": 90,
        }]
        client = RetryingLogClient(fail_always={(100, 109)})
        evidence = fetch_erc4337_evidence(
            client,
            [FakeEvidenceClient.EOA_ADDRESS],
            80,
            109,
            manifest,
            block_chunk_size=10,
            address_batch_size=1,
            max_retries=1,
        )[FakeEvidenceClient.EOA_ADDRESS]
        self.assertFalse(evidence["complete"])
        self.assertIn(":90-99", evidence["effective_coverage"])
        self.assertIn(":100-109", evidence["failed_ranges"])
        self.assertEqual(client.attempts[(100, 109)], 2)

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
