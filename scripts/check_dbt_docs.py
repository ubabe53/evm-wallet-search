#!/usr/bin/env python3
"""Fail when the generated dbt catalog exposes an undocumented data contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = ROOT / "analytics" / "target"
PROJECT_PREFIXES = (
    "model.evm_wallet_search.",
    "seed.evm_wallet_search.",
    "source.evm_wallet_search.",
)
REQUIRED_META = ("grain", "primary_key", "provenance", "consumers")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing {path}; run `bun run analytics:docs:generate` first.")
    return json.loads(path.read_text())


def documentation_errors(target: Path) -> list[str]:
    manifest = read_json(target / "manifest.json")
    catalog = read_json(target / "catalog.json")
    manifest_resources = {
        **manifest.get("nodes", {}),
        **manifest.get("sources", {}),
    }
    catalog_resources = {
        **catalog.get("nodes", {}),
        **catalog.get("sources", {}),
    }
    errors: list[str] = []

    for unique_id, resource in sorted(manifest_resources.items()):
        if not unique_id.startswith(PROJECT_PREFIXES):
            continue
        if not str(resource.get("description", "")).strip():
            errors.append(f"{unique_id}: missing resource description")

        meta = resource.get("meta", {})
        for field in REQUIRED_META:
            value = meta.get(field)
            if value is None or value == "" or value == []:
                errors.append(f"{unique_id}: missing meta.{field}")

        documented_columns = resource.get("columns", {})
        for column_name, column in documented_columns.items():
            if not str(column.get("description", "")).strip():
                errors.append(f"{unique_id}.{column_name}: missing column description")

        catalog_resource = catalog_resources.get(unique_id)
        if catalog_resource is None:
            continue
        for column_name in catalog_resource.get("columns", {}):
            if column_name not in documented_columns:
                errors.append(f"{unique_id}.{column_name}: missing column declaration")

    for unique_id in sorted(catalog_resources):
        if unique_id.startswith(PROJECT_PREFIXES) and unique_id not in manifest_resources:
            errors.append(f"{unique_id}: missing from manifest")

    return errors


def main() -> None:
    target = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_TARGET
    errors = documentation_errors(target)
    if errors:
        print("dbt documentation contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        raise SystemExit(1)
    print("dbt documentation contract passed")


if __name__ == "__main__":
    main()
