import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.enrich_counterparty_types import decode_code, fetch_address_types, select_candidates, write_rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query):
        return self

    def fetchall(self):
        return self.rows


class FakeCodeClient:
    def batch(self, requests):
        return {
            key: "0x60016000" if key[0].endswith("1") else "0x"
            for _method, _params, key in requests
        }


class CounterpartyTypeTest(unittest.TestCase):
    def test_decodes_wallet_contract_and_failed_results(self) -> None:
        self.assertEqual(decode_code("0x"), ("wallet", 0, "complete", ""))
        self.assertEqual(decode_code("0x60016000"), ("contract", 4, "complete", ""))
        self.assertEqual(decode_code(None), ("unknown", None, "failed", "missing:eth_getCode"))
        self.assertEqual(decode_code("0xnothex"), ("unknown", None, "failed", "malformed:eth_getCode"))

    def test_selects_ranked_unattempted_and_retry_candidates(self) -> None:
        connection = FakeConnection([("0x1", 100), ("0x2", 50), ("0x3", 25)])
        existing = {"0x1": {"fetch_status": "complete"}, "0x2": {"fetch_status": "failed"}}
        self.assertEqual(select_candidates(connection, existing, 10), ["0x3"])
        self.assertEqual(select_candidates(connection, existing, 10, retry_failed=True), ["0x2"])
        self.assertEqual(select_candidates(connection, existing, 2, refresh=True), ["0x1", "0x2"])

    def test_fetches_all_addresses_at_one_pinned_block(self) -> None:
        rows = fetch_address_types(FakeCodeClient(), ["0x1", "0x2"], "0x64")
        self.assertEqual(rows[0]["address_type"], "contract")
        self.assertEqual(rows[0]["code_size_bytes"], 4)
        self.assertEqual(rows[0]["rpc_block_number"], 100)
        self.assertEqual(rows[1]["address_type"], "wallet")

    def test_snapshot_merge_is_idempotent_and_sorted(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "addresses.csv"
            existing = {"0x2": {
                "address": "0x2", "address_type": "unknown", "code_size_bytes": "",
                "rpc_block_number": "", "fetched_at": "", "fetch_status": "failed", "error_code": "missing",
            }}
            rows = [{
                "address": "0x1", "address_type": "wallet", "code_size_bytes": 0,
                "rpc_block_number": 100, "fetched_at": "now", "fetch_status": "complete", "error_code": "",
            }]
            write_rows(existing, rows, path)
            write_rows(existing, rows, path)
            with path.open(newline="") as source:
                written = list(csv.DictReader(source))
            self.assertEqual([row["address"] for row in written], ["0x1", "0x2"])


if __name__ == "__main__":
    unittest.main()
