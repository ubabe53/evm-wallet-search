import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.enrich_token_metadata import (
    JsonRpcClient,
    decode_decimals_result,
    decode_text_result,
    fetch_metadata,
    select_candidates,
    write_rows,
)
from eth_abi import encode


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query):
        return self

    def fetchall(self):
        return self.rows


class FakeMetadataClient:
    def batch(self, requests):
        values = {}
        for _method, _params, (address, field) in requests:
            if address.endswith("1"):
                values[(address, field)] = {
                    "name": "0x" + encode(["string"], ["Token One"]).hex(),
                    "symbol": "0x" + encode(["string"], ["ONE"]).hex(),
                    "decimals": "0x" + (18).to_bytes(32, "big").hex(),
                }[field]
            else:
                values[(address, field)] = None
        return values


class RpcMetadataTest(unittest.TestCase):
    def test_decodes_dynamic_and_legacy_text(self) -> None:
        dynamic = "0x" + encode(["string"], ["USD Coin"]).hex()
        legacy = "0x" + b"USDC".ljust(32, b"\x00").hex()
        self.assertEqual(decode_text_result(dynamic), "USD Coin")
        self.assertEqual(decode_text_result(legacy), "USDC")
        self.assertIsNone(decode_text_result("0x"))

    def test_decodes_only_valid_decimals(self) -> None:
        self.assertEqual(decode_decimals_result("0x" + (18).to_bytes(32, "big").hex()), 18)
        self.assertIsNone(decode_decimals_result("0x" + (256).to_bytes(32, "big").hex()))
        self.assertIsNone(decode_decimals_result("not-hex"))

    def test_selects_next_ranked_batch_and_supports_retry_modes(self) -> None:
        connection = FakeConnection([("0x1", 100), ("0x2", 50), ("0x3", 25)])
        existing = {"0x1": {"fetch_status": "complete"}, "0x2": {"fetch_status": "failed"}}
        self.assertEqual(select_candidates(connection, existing, 10), ["0x3"])
        self.assertEqual(select_candidates(connection, existing, 10, retry_failed=True), ["0x2"])
        self.assertEqual(select_candidates(connection, existing, 2, refresh=True), ["0x1", "0x2"])

    def test_fetches_complete_and_failed_rows_at_one_block(self) -> None:
        rows = fetch_metadata(FakeMetadataClient(), ["0x1", "0x2"], "0x64")
        self.assertEqual(rows[0]["fetch_status"], "complete")
        self.assertEqual(rows[0]["decimals"], 18)
        self.assertEqual(rows[0]["rpc_block_number"], 100)
        self.assertEqual(rows[1]["fetch_status"], "failed")

    def test_json_rpc_batch_maps_results_without_exposing_transport_details(self) -> None:
        def transport(_url, payload):
            return [{"jsonrpc": "2.0", "id": item["id"], "result": "0x01"} for item in payload]

        client = JsonRpcClient("https://private.invalid/key", transport=transport)
        result = client.batch([("eth_call", [], ("0x1", "name"))])
        self.assertEqual(result[("0x1", "name")], "0x01")

    def test_json_rpc_call_rejects_malformed_or_mismatched_responses(self) -> None:
        for response in ([], {"jsonrpc": "2.0", "id": 99, "result": "0x01"}):
            with self.subTest(response=response):
                client = JsonRpcClient("https://private.invalid/key", transport=lambda _url, _payload: response)
                with self.assertRaisesRegex(RuntimeError, "invalid response"):
                    client.call("eth_chainId", [])

    def test_json_rpc_batch_ignores_malformed_items(self) -> None:
        client = JsonRpcClient(
            "https://private.invalid/key",
            transport=lambda _url, _payload: [None, {"jsonrpc": "2.0", "id": 999, "result": "0x01"}],
        )
        result = client.batch([("eth_call", [], ("0x1", "name"))])
        self.assertIsNone(result[("0x1", "name")])

    def test_snapshot_merge_is_idempotent_and_sorted(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.csv"
            existing = {"0x2": {field: "" for field in (
                "name", "symbol", "decimals", "rpc_block_number", "fetched_at", "error_code"
            )} | {"token_address": "0x2", "fetch_status": "failed"}}
            rows = [{
                "token_address": "0x1", "name": "One", "symbol": "ONE", "decimals": 18,
                "rpc_block_number": 100, "fetched_at": "now", "fetch_status": "complete", "error_code": "",
            }]
            write_rows(existing, rows, path)
            write_rows(existing, rows, path)
            with path.open(newline="") as source:
                written = list(csv.DictReader(source))
            self.assertEqual([row["token_address"] for row in written], ["0x1", "0x2"])


if __name__ == "__main__":
    unittest.main()
