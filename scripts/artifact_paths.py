"""Canonical paths for isolated fixture and live analytics artifacts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = ROOT / "analytics"
ARTIFACTS_DIR = ANALYTICS_DIR / "artifacts"
FIXTURE_DB_PATH = ARTIFACTS_DIR / "fixture.duckdb"
LIVE_DB_PATH = ARTIFACTS_DIR / "live.duckdb"
ACCOUNT_EVIDENCE_DB_PATH = ARTIFACTS_DIR / "account_evidence.duckdb"
DBT_DUCKDB_PATH_ENV = "EVM_WALLET_DUCKDB_PATH"
ACCOUNT_EVIDENCE_DUCKDB_PATH_ENV = "ACCOUNT_EVIDENCE_DUCKDB_PATH"


def database_path(use_fixture: bool) -> Path:
    """Return the database dedicated to one mutually exclusive source mode."""

    return FIXTURE_DB_PATH if use_fixture else LIVE_DB_PATH
