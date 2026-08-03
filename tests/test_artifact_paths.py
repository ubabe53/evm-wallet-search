import os
import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, patch

from scripts import run_dbt
from scripts.artifact_paths import FIXTURE_DB_PATH, LIVE_DB_PATH
from scripts.snapshot_runs import (
    ConfiguredWallet,
    FinalizedBlock,
    HyperIndexMetadata,
    SnapshotRun,
)
from server.ens import ResolvedScanInput

WALLET_A = ConfiguredWallet("0x" + "a" * 40, "wallet-a")
WALLET_B = ConfiguredWallet("0x" + "b" * 40, "wallet-b")


class ArtifactPathsTest(unittest.TestCase):
    @patch("duckdb.connect")
    def test_raw_event_count_is_mainnet_and_wallet_scoped(self, connect) -> None:
        connection = connect.return_value.__enter__.return_value
        connection.execute.return_value.fetchone.return_value = (7,)
        run = SnapshotRun(
            run_id="run",
            chain_id=1,
            wallet_address=WALLET_A.address,
            wallet_label=WALLET_A.label,
            from_block=3,
            to_block=100,
            to_block_hash="0x" + "a" * 64,
            scope_version="wallet-transfer-signature-v1",
            generation_id="generation",
        )

        self.assertEqual(run_dbt.count_hyperindex_events("postgresql://secret", run), 7)
        count_query = connection.execute.call_args_list[2].args[0]
        self.assertIn("chain_id = 1", count_query)
        self.assertIn("lower(from_address) = ? or lower(to_address) = ?", count_query)

    def test_scan_wallet_address_is_normalized_and_selected(self) -> None:
        selected = run_dbt.select_scan_wallet([WALLET_A, WALLET_B], "  " + WALLET_B.address.upper() + "  ")
        self.assertEqual(selected, WALLET_B)

    def test_multiple_wallets_require_scan_wallet_address(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "EVM_WALLET_SCAN_ADDRESS"):
            run_dbt.select_scan_wallet([WALLET_A, WALLET_B], None)

    def test_scan_wallet_address_must_be_configured(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "No configured wallet matches"):
            run_dbt.select_scan_wallet([WALLET_A, WALLET_B], "0x" + "c" * 40)

    def test_scan_wallet_address_rejects_malformed_input(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "canonical Ethereum address"):
            run_dbt.select_scan_wallet([WALLET_A], "0xnot-an-address")

    def test_single_wallet_is_selected_without_scan_wallet_address(self) -> None:
        self.assertEqual(run_dbt.select_scan_wallet([WALLET_A], None), WALLET_A)

    @patch("scripts.run_dbt.finish_snapshot_run")
    @patch("scripts.run_dbt.mark_ingestion_complete")
    @patch("scripts.run_dbt.count_hyperindex_events", return_value=0)
    @patch("scripts.run_dbt.run_dbt")
    @patch("scripts.run_dbt.start_snapshot_runs")
    @patch("scripts.run_dbt.resolve_snapshot_target")
    @patch("scripts.run_dbt.fetch_hyperindex_metadata")
    @patch("server.ens.resolve_scan_input")
    @patch("scripts.run_dbt.read_live_wallet_targets", return_value=[WALLET_A, WALLET_B])
    @patch("scripts.run_dbt.ensure_python_dependencies")
    @patch("scripts.run_dbt.resolved_runtime")
    def test_adding_wallet_b_does_not_create_a_run_for_wallet_a(
        self,
        runtime,
        _ensure_dependencies,
        _read_wallets,
        resolve_scan_input,
        fetch_metadata,
        resolve_target,
        start_runs,
        run,
        _count_hyperindex_events,
        _mark_ingestion_complete,
        _finish,
    ) -> None:
        snapshot = SnapshotRun(
            run_id="run-b",
            chain_id=1,
            wallet_address=WALLET_B.address,
            wallet_label=WALLET_B.label,
            from_block=3,
            to_block=100,
            to_block_hash="0x" + "c" * 64,
            scope_version="wallet-transfer-signature-v1",
            generation_id="generation-b",
        )
        runtime.return_value = {
            "hyperindex_postgres_dsn": "postgresql://secret",
            "hyperindex_graphql_url": "https://graphql.example",
            "ethereum_rpc_url": "https://rpc.example",
        }
        fetch_metadata.return_value = HyperIndexMetadata(3, 100, None, True)
        resolve_target.return_value = FinalizedBlock(100, "0x" + "c" * 64)
        resolve_scan_input.return_value = ResolvedScanInput(
            WALLET_B.address,
            None,
            WALLET_B.address,
            "direct-address",
            100,
            "0x" + "c" * 64,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        start_runs.return_value = [snapshot]
        with patch.dict(
            os.environ,
            {run_dbt.EVM_WALLET_SCAN_ADDRESS_ENV: WALLET_B.address.upper()},
            clear=False,
        ), patch.object(
            run_dbt.sys, "argv", ["run_dbt.py", "build", "--vars", "{use_fixture: false}"]
        ):
            run_dbt.main()

        resolve_scan_input.assert_called_once_with(WALLET_B.address, ANY)
        self.assertEqual(start_runs.call_args.kwargs["wallets"], [WALLET_B])
        self.assertEqual(
            run.call_args.kwargs["extra_env"][run_dbt.EVM_WALLET_SCAN_ADDRESS_ENV], WALLET_B.address
        )

    @patch("scripts.run_dbt.subprocess.run")
    @patch("scripts.run_dbt.shutil.which", return_value="/usr/bin/dbt")
    def test_fixture_build_uses_fixture_database_without_live_dsn(self, _which, run) -> None:
        with patch.dict(os.environ, {run_dbt.HYPERINDEX_DSN_ENV: "postgresql://secret"}):
            run_dbt.run_dbt("build", [], use_hyperindex=False, hyperindex_dsn="postgresql://secret")

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment[run_dbt.DBT_DUCKDB_PATH_ENV], str(FIXTURE_DB_PATH))
        self.assertNotIn(run_dbt.HYPERINDEX_DSN_ENV, environment)

    @patch("scripts.run_dbt.subprocess.run")
    @patch("scripts.run_dbt.shutil.which", return_value="/usr/bin/dbt")
    def test_live_build_uses_live_database_and_read_only_source_dsn(self, _which, run) -> None:
        run_dbt.run_dbt(
            "build",
            ["--vars", '{"use_fixture": false}'],
            use_hyperindex=True,
            hyperindex_dsn="postgresql://secret",
            extra_env={"EVM_WALLET_SNAPSHOT_END_BLOCK": "100"},
        )

        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment[run_dbt.DBT_DUCKDB_PATH_ENV], str(LIVE_DB_PATH))
        self.assertEqual(environment[run_dbt.HYPERINDEX_DSN_ENV], "postgresql://secret")
        self.assertEqual(environment["EVM_WALLET_SNAPSHOT_END_BLOCK"], "100")

    def test_live_build_requires_a_dsn(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Live HyperIndex mode requires"):
            run_dbt.run_dbt("build", [], use_hyperindex=True, hyperindex_dsn=None)

    @patch("scripts.run_dbt.subprocess.run")
    @patch("scripts.run_dbt.shutil.which", return_value="/usr/bin/dbt")
    def test_docs_generate_uses_nested_command_order_and_fixture_database(
        self, _which, run
    ) -> None:
        with patch.dict(os.environ, {run_dbt.HYPERINDEX_DSN_ENV: "postgresql://secret"}):
            run_dbt.run_dbt(
                "docs",
                ["generate", "--static"],
                use_hyperindex=False,
                hyperindex_dsn="postgresql://secret",
            )

        self.assertEqual(
            run.call_args.args[0],
            [
                "/usr/bin/dbt",
                "docs",
                "generate",
                "--project-dir",
                str(run_dbt.ANALYTICS_DIR),
                "--profiles-dir",
                str(run_dbt.ANALYTICS_DIR),
                "--static",
            ],
        )
        environment = run.call_args.kwargs["env"]
        self.assertEqual(environment[run_dbt.DBT_DUCKDB_PATH_ENV], str(FIXTURE_DB_PATH))
        self.assertNotIn(run_dbt.HYPERINDEX_DSN_ENV, environment)

    @patch("scripts.run_dbt.subprocess.run")
    @patch("scripts.run_dbt.shutil.which", return_value="/usr/bin/dbt")
    def test_docs_serve_preserves_options_after_nested_subcommand(
        self, _which, run
    ) -> None:
        run_dbt.run_dbt(
            "docs",
            ["serve", "--no-browser", "--host", "127.0.0.1", "--port", "8081"],
            use_hyperindex=False,
            hyperindex_dsn=None,
        )

        self.assertEqual(
            run.call_args.args[0],
            [
                "/usr/bin/dbt",
                "docs",
                "serve",
                "--project-dir",
                str(run_dbt.ANALYTICS_DIR),
                "--profiles-dir",
                str(run_dbt.ANALYTICS_DIR),
                "--no-browser",
                "--host",
                "127.0.0.1",
                "--port",
                "8081",
            ],
        )

    def test_docs_requires_a_supported_subcommand(self) -> None:
        with self.assertRaisesRegex(SystemExit, "dbt docs requires"):
            run_dbt.run_dbt("docs", [], use_hyperindex=False, hyperindex_dsn=None)

    def test_docs_rejects_live_mode(self) -> None:
        with self.assertRaisesRegex(SystemExit, "fixture mode only"):
            run_dbt.run_dbt(
                "docs",
                ["generate"],
                use_hyperindex=True,
                hyperindex_dsn="postgresql://secret",
            )


if __name__ == "__main__":
    unittest.main()
