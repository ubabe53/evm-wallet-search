import signal
import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from scripts.snapshot_runs import SnapshotRun
from scripts.wallet_scan_worker import (
    finalized_block_hash,
    load_worker_input,
    postgres_environment,
    run_bounded_indexer,
    run_worker,
)

WALLET = "0x" + "a" * 40
BLOCK_HASH = "0x" + "b" * 64
STAGING = Path("/tmp/wallet-scan-test/live.duckdb")


def worker_environment() -> dict[str, str]:
    return {
        "WALLET_SCAN_JOB_ID": "12345678-abcd-1234-abcd-1234567890ab",
        "WALLET_SCAN_REQUESTED_VALUE": "alice.eth",
        "WALLET_SCAN_ADDRESS": WALLET,
        "WALLET_SCAN_LABEL": "alice.eth",
        "WALLET_SCAN_FROM_BLOCK": "10",
        "WALLET_SCAN_TO_BLOCK": "20",
        "WALLET_SCAN_OUTPUT_PATH": str(STAGING),
        "WALLET_SCAN_RESOLVER_SOURCE": "ens-registry:test/resolver:test",
        "WALLET_SCAN_OBSERVATION_BLOCK_NUMBER": "20",
        "WALLET_SCAN_OBSERVATION_BLOCK_HASH": BLOCK_HASH,
        "WALLET_SCAN_OBSERVATION_TIMESTAMP": "2026-08-06T12:00:00+00:00",
        "WALLET_SCAN_POSTGRES_DSN": "postgresql://writer:secret@127.0.0.1:5433/envio-dev",
        "ETHEREUM_RPC_URL": "https://rpc.example",
    }


def snapshot_run() -> SnapshotRun:
    return SnapshotRun(
        run_id="run",
        chain_id=1,
        wallet_address=WALLET,
        wallet_label="alice.eth",
        from_block=10,
        to_block=20,
        to_block_hash=BLOCK_HASH,
        scope_version="wallet-transfer-signature-v1",
        generation_id="generation",
    )


class FakeRpc:
    def call(self, method, params):
        if params == ["finalized", False]:
            return {"number": "0x19", "hash": "0x" + "c" * 64}
        if params == ["0x14", False]:
            return {"number": "0x14", "hash": BLOCK_HASH}
        raise AssertionError((method, params))


class WalletScanWorkerTest(unittest.TestCase):
    @patch("scripts.wallet_scan_worker.os.killpg")
    @patch("scripts.wallet_scan_worker.time.sleep")
    @patch(
        "scripts.wallet_scan_worker.bounded_indexer_completed",
        side_effect=[False, True],
    )
    @patch("scripts.wallet_scan_worker.subprocess.Popen")
    def test_supervises_envio_until_checkpoint_then_terminates_process(
        self,
        popen,
        completed,
        _sleep,
        killpg,
    ) -> None:
        process = popen.return_value
        process.pid = 4321
        process.poll.return_value = None
        process.wait.return_value = 0

        run_bounded_indexer(
            load_worker_input(worker_environment()),
            worker_environment()["WALLET_SCAN_POSTGRES_DSN"],
            timeout_seconds=30,
            envio_api_token="token",
        )

        self.assertEqual(completed.call_count, 2)
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        self.assertEqual(popen.call_args.kwargs["env"]["ENVIO_API_TOKEN"], "token")
        self.assertEqual(Path(popen.call_args.args[0][5]).parent, Path(__file__).parents[1] / "indexer")
        killpg.assert_called_once_with(4321, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=30)

    def test_loads_typed_finalized_worker_contract(self) -> None:
        scan = load_worker_input(worker_environment())

        self.assertEqual((scan.wallet_address, scan.from_block, scan.to_block), (WALLET, 10, 20))
        self.assertEqual(scan.schema_name, "wallet_scan_12345678abcd1234abcd1234567890ab")
        self.assertEqual(scan.observation_timestamp.tzinfo, timezone.utc)

    def test_rejects_mismatched_scan_and_observation_blocks(self) -> None:
        environment = worker_environment()
        environment["WALLET_SCAN_OBSERVATION_BLOCK_NUMBER"] = "19"

        with self.assertRaisesRegex(RuntimeError, "do not match"):
            load_worker_input(environment)

    def test_translates_explicit_write_dsn_for_envio(self) -> None:
        result = postgres_environment(
            "postgresql://scan%2Duser:p%40ss@127.0.0.1:5433/envio-dev?sslmode=require"
        )

        self.assertEqual(result["ENVIO_PG_USER"], "scan-user")
        self.assertEqual(result["ENVIO_PG_PASSWORD"], "p@ss")
        self.assertNotIn("ENVIO_PG_SCHEMA", result)
        self.assertEqual(result["ENVIO_PG_SSL_MODE"], "require")

    def test_rechecks_historical_block_inside_current_finalized_coverage(self) -> None:
        self.assertEqual(finalized_block_hash(FakeRpc(), 20), BLOCK_HASH)

    @patch("scripts.wallet_scan_worker.finish_snapshot_run")
    @patch("scripts.wallet_scan_worker.run_dbt")
    @patch("scripts.wallet_scan_worker.mark_ingestion_complete")
    @patch("scripts.wallet_scan_worker.run_bounded_indexer")
    @patch("scripts.wallet_scan_worker.completed_ingestion", return_value=3)
    @patch("scripts.wallet_scan_worker.finalized_block_hash", return_value=BLOCK_HASH)
    @patch("scripts.wallet_scan_worker.start_snapshot_run", return_value=snapshot_run())
    @patch("scripts.wallet_scan_worker.configured_start_block", return_value=10)
    @patch("scripts.wallet_scan_worker.resolved_runtime", return_value={})
    def test_retry_reuses_durable_raw_checkpoint_without_reindexing(
        self,
        _runtime,
        _configured_start,
        _start,
        verify_hash,
        _completed,
        run_indexer,
        mark_ingestion,
        run_dbt,
        finish,
    ) -> None:
        run_worker(worker_environment())

        run_indexer.assert_not_called()
        verify_hash.assert_called_once()
        mark_ingestion.assert_called_once()
        self.assertEqual(mark_ingestion.call_args.kwargs["raw_events_found"], 3)
        self.assertEqual(run_dbt.call_args.kwargs["database_path_override"], STAGING)
        self.assertEqual(
            run_dbt.call_args.kwargs["hyperindex_dsn"],
            worker_environment()["WALLET_SCAN_POSTGRES_DSN"],
        )
        finish.assert_called_once_with(snapshot_run(), database_path=STAGING, succeeded=True)

    @patch("scripts.wallet_scan_worker.finish_snapshot_run")
    @patch("scripts.wallet_scan_worker.run_dbt")
    @patch("scripts.wallet_scan_worker.mark_ingestion_complete")
    @patch("scripts.wallet_scan_worker.drop_temporary_schema")
    @patch("scripts.wallet_scan_worker.merge_bounded_ingestion", return_value=4)
    @patch("scripts.wallet_scan_worker.run_bounded_indexer")
    @patch("scripts.wallet_scan_worker.completed_ingestion", return_value=None)
    @patch("scripts.wallet_scan_worker.finalized_block_hash", return_value=BLOCK_HASH)
    @patch("scripts.wallet_scan_worker.start_snapshot_run", return_value=snapshot_run())
    @patch("scripts.wallet_scan_worker.configured_start_block", return_value=10)
    @patch("scripts.wallet_scan_worker.resolved_runtime", return_value={})
    def test_new_interval_indexes_merges_and_drops_temporary_schema(
        self,
        _runtime,
        _configured_start,
        _start,
        _verify_hash,
        _completed,
        run_indexer,
        merge,
        drop_schema,
        mark_ingestion,
        _run_dbt,
        finish,
    ) -> None:
        run_worker(worker_environment())

        run_indexer.assert_called_once()
        merge.assert_called_once()
        drop_schema.assert_called_once()
        self.assertEqual(mark_ingestion.call_args.kwargs["raw_events_found"], 4)
        finish.assert_called_once_with(snapshot_run(), database_path=STAGING, succeeded=True)


if __name__ == "__main__":
    unittest.main()
