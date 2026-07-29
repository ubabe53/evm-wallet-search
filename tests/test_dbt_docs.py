import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_dbt_docs import documentation_errors


class DbtDocumentationTest(unittest.TestCase):
    def test_manifest_only_resource_is_still_validated(self) -> None:
        manifest = {
            "nodes": {},
            "sources": {
                "source.evm_wallet_search.hyperindex.transfer_event": {
                    "description": "",
                    "meta": {},
                    "columns": {
                        "chain_id": {"description": ""},
                    },
                }
            },
        }
        catalog = {"nodes": {}, "sources": {}}

        with TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "manifest.json").write_text(json.dumps(manifest))
            (target / "catalog.json").write_text(json.dumps(catalog))
            errors = documentation_errors(target)

        self.assertIn(
            "source.evm_wallet_search.hyperindex.transfer_event: missing resource description",
            errors,
        )
        self.assertIn(
            "source.evm_wallet_search.hyperindex.transfer_event: missing meta.grain",
            errors,
        )
        self.assertIn(
            "source.evm_wallet_search.hyperindex.transfer_event.chain_id: missing column description",
            errors,
        )


if __name__ == "__main__":
    unittest.main()
