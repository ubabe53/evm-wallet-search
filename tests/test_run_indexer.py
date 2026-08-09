import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_indexer


class RunIndexerTest(unittest.TestCase):
    def test_bounded_config_sets_inclusive_mainnet_interval(self) -> None:
        config = run_indexer.bounded_config(
            from_block=101,
            to_block=200,
            schema_name="wallet_scan_job_123",
        )

        self.assertEqual(config["name"], "wallet-scan-job-123")
        self.assertEqual(config["chains"][0]["id"], 1)
        self.assertEqual(config["chains"][0]["start_block"], 101)
        self.assertEqual(config["chains"][0]["end_block"], 200)

    @patch("scripts.run_indexer.subprocess.run")
    def test_scan_uses_isolated_schema_and_runtime_wallet(self, run) -> None:
        wallet = "0x" + "a" * 40
        environment: dict[str, str] = {}
        with tempfile.TemporaryDirectory() as directory:
            indexer_directory = Path(directory) / "indexer"
            indexer_directory.mkdir()
            with patch.object(run_indexer, "INDEXER_DIR", indexer_directory):
                run_indexer.run_bounded_scan(
                    [
                        "--wallet", wallet,
                        "--from-block", "101",
                        "--to-block", "200",
                        "--schema", "wallet_scan_job_123",
                        "--indexer-port", "9082",
                    ],
                    environment,
                )
                expected_directory = run_indexer.INDEXER_DIR

        self.assertEqual(environment["ENVIO_WALLET_SCAN_ADDRESS"], wallet)
        self.assertEqual(environment["ENVIO_PG_SCHEMA"], "wallet_scan_job_123")
        self.assertEqual(environment["ENVIO_INDEXER_PORT"], "9082")
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["bunx", "envio", "start", "--restart"])
        generated_path = Path(command[5])
        self.assertEqual(generated_path.parent, expected_directory)
        self.assertFalse(generated_path.exists())
        self.assertEqual(run.call_args.kwargs["cwd"], expected_directory)

    def test_scan_rejects_unscoped_schema(self) -> None:
        with self.assertRaisesRegex(SystemExit, "wallet_scan"):
            run_indexer.run_bounded_scan(
                [
                    "--wallet", "0x" + "a" * 40,
                    "--from-block", "1",
                    "--to-block", "2",
                    "--schema", "public",
                ],
                {},
            )


if __name__ == "__main__":
    unittest.main()
