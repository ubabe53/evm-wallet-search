import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from scripts.enrich_counterparty_types import (
    EVIDENCE_SCHEMA_VERSION,
    ZERO_ADDRESS,
    build_evidence_rows,
    decode_code,
    ensure_evidence_store,
    fetch_code_batch,
    read_successful_addresses,
    resolve_observation_block,
    select_candidates,
    write_evidence_rows,
)


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.params = None

    def execute(self, _query, params):
        self.params = params
        return self

    def fetchall(self):
        return self.rows


class FakeBatchClient:
    def __init__(self, failures_before_success=None):
        self.failures = dict(failures_before_success or {})
        self.attempts = {}
        self.batch_sizes = []

    def batch(self, requests):
        self.batch_sizes.append(len(requests))
        results = {}
        for _method, _params, key in requests:
            address = key[0]
            self.attempts[address] = self.attempts.get(address, 0) + 1
            if self.attempts[address] <= self.failures.get(address, 0):
                results[key] = None
            else:
                results[key] = "0x" if address.endswith("1") else "0x6001"
        return results


class FakeBlockClient:
    BLOCK = {"number": "0x64", "hash": "0x" + "ab" * 32, "timestamp": "0x6558b640"}

    def __init__(self, supports_safe=True):
        self.supports_safe = supports_safe
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_getBlockByNumber" and params[0] == "safe":
            if not self.supports_safe:
                raise RuntimeError("unsupported block tag")
            return self.BLOCK
        if method == "eth_blockNumber":
            return "0xa4"
        if method == "eth_getBlockByNumber" and params[0] == "0x64":
            return self.BLOCK
        raise AssertionError((method, params))


class CounterpartyTypeTest(unittest.TestCase):
    def test_account_evidence_table_has_exact_contract(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "account_evidence.duckdb"
            ensure_evidence_store(path)
            with duckdb.connect(str(path), read_only=True) as connection:
                actual = [
                    (row[1], row[2], bool(row[3]), bool(row[5]))
                    for row in connection.execute(
                        "pragma table_info('account_evidence')"
                    ).fetchall()
                ]

        self.assertEqual(
            actual,
            [
                ("chain_id", "INTEGER", True, True),
                ("address", "VARCHAR", True, True),
                ("account_type", "VARCHAR", True, False),
                ("code_state", "VARCHAR", True, False),
                ("code_size_bytes", "BIGINT", False, False),
                ("observation_block_number", "BIGINT", True, False),
                ("observation_block_hash", "VARCHAR", False, False),
                ("observation_block_timestamp", "TIMESTAMP WITH TIME ZONE", True, False),
                ("eip7702_delegation_target", "VARCHAR", False, False),
                ("fetch_status", "VARCHAR", True, False),
                ("reason_code", "VARCHAR", True, False),
                ("finality_policy", "VARCHAR", True, False),
                ("evidence_schema_version", "VARCHAR", True, False),
                ("fetched_at", "TIMESTAMP WITH TIME ZONE", True, False),
            ],
        )

    def test_decodes_public_eoa_contract_and_internal_delegation(self) -> None:
        target = "11" * 20
        self.assertEqual(
            decode_code("0x"),
            ("eoa_candidate", "no_code", 0, None, "complete", "no_code_observed"),
        )
        self.assertEqual(
            decode_code("0xef0100" + target),
            (
                "eoa_candidate",
                "eip7702_delegated",
                23,
                "0x" + target,
                "complete",
                "eip7702_delegation_observed",
            ),
        )
        self.assertEqual(decode_code("0xef0100" + target + "00")[0:2], ("contract", "contract_code"))
        self.assertEqual(decode_code("0x60016000")[0:3], ("contract", "contract_code", 4))
        self.assertEqual(decode_code(None)[0:2], ("unknown", "unknown"))
        self.assertEqual(decode_code("0xnothex")[4:], ("failed", "code_lookup_malformed"))

    def test_selects_every_distinct_nonzero_nonself_unchecked_address_once(self) -> None:
        connection = FakeConnection([("0x1", 100), ("0x2", 50), ("0x3", 25)])
        self.assertEqual(select_candidates(connection, {"0x2"}), ["0x1", "0x3"])
        self.assertEqual(select_candidates(connection, {"0x2"}, limit=1), ["0x1"])
        self.assertEqual(connection.params, [ZERO_ADDRESS])

    def test_retries_only_unresolved_code_calls(self) -> None:
        client = FakeBatchClient({"0x1": 1, "0x2": 3})
        results = fetch_code_batch(client, ["0x1", "0x2", "0x3"], "0x64", max_retries=2)
        self.assertEqual(results["0x1"], "0x")
        self.assertIsNone(results["0x2"])
        self.assertEqual(results["0x3"], "0x6001")
        self.assertEqual(client.batch_sizes, [3, 2, 1])

    def test_pins_safe_block_or_confirmed_fallback(self) -> None:
        tag, block, policy = resolve_observation_block(FakeBlockClient())
        self.assertEqual((tag, block["hash"], policy), ("0x64", FakeBlockClient.BLOCK["hash"], "safe"))

        fallback = FakeBlockClient(supports_safe=False)
        tag, _block, policy = resolve_observation_block(fallback, fallback_confirmations=64)
        self.assertEqual((tag, policy), ("0x64", "latest_minus_64"))
        self.assertIn(("eth_getBlockByNumber", ["0x64", False]), fallback.calls)

    def test_successful_observation_is_never_overwritten_and_failure_is_retryable(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "account_evidence.duckdb"
            ensure_evidence_store(path)
            block = FakeBlockClient.BLOCK
            first = build_evidence_rows(
                ["0x0000000000000000000000000000000000000001"],
                {"0x0000000000000000000000000000000000000001": "0x"},
                block,
                "safe",
            )
            write_evidence_rows(first, path)
            replacement = build_evidence_rows(
                ["0x0000000000000000000000000000000000000001"],
                {"0x0000000000000000000000000000000000000001": "0x6001"},
                {**block, "number": "0x65"},
                "safe",
            )
            write_evidence_rows(replacement, path)
            connection = duckdb.connect(str(path), read_only=True)
            try:
                stored = connection.execute(
                    "select account_type, observation_block_number from account_evidence"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(stored, ("eoa_candidate", 100))
            self.assertEqual(
                read_successful_addresses(path),
                {"0x0000000000000000000000000000000000000001"},
            )

    def test_failed_observation_can_be_replaced_by_success(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "account_evidence.duckdb"
            failed = build_evidence_rows(
                ["0x0000000000000000000000000000000000000002"],
                {"0x0000000000000000000000000000000000000002": None},
                FakeBlockClient.BLOCK,
                "safe",
            )
            write_evidence_rows(failed, path)
            success = build_evidence_rows(
                ["0x0000000000000000000000000000000000000002"],
                {"0x0000000000000000000000000000000000000002": "0x6001"},
                {**FakeBlockClient.BLOCK, "number": "0x65"},
                "safe",
            )
            write_evidence_rows(success, path)
            connection = duckdb.connect(str(path), read_only=True)
            try:
                stored = connection.execute(
                    "select account_type, fetch_status, observation_block_number, evidence_schema_version "
                    "from account_evidence"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(stored, ("contract", "complete", 101, EVIDENCE_SCHEMA_VERSION))


if __name__ == "__main__":
    unittest.main()
