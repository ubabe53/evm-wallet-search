import os
import unittest
from unittest.mock import patch

from scripts import run_dbt
from scripts.artifact_paths import FIXTURE_DB_PATH, LIVE_DB_PATH


class ArtifactPathsTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
