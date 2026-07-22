import sys
import unittest

from scripts import run_api


class RunApiTest(unittest.TestCase):
    def test_prepare_import_path_makes_server_package_discoverable(self) -> None:
        original_path = sys.path.copy()
        root = str(run_api.ROOT)
        try:
            sys.path[:] = [entry for entry in sys.path if entry != root]
            run_api.prepare_import_path()

            self.assertEqual(sys.path[0], root)
        finally:
            sys.path[:] = original_path


if __name__ == "__main__":
    unittest.main()
