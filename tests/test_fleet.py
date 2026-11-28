"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): its locked bytes, and scripts."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ironmate_fleet_check", ROOT / "vendor/fleet_check.py")
fleet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fleet)


class VendorLock(unittest.TestCase):
    def test_vendor_lock_matches_placed_bytes(self):
        fleet.check_lock(ROOT)  # 🔁 own rows follow main: no accepted commit to pin


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(ROOT)

    def test_no_top_level_vendor_package_imports(self):
        # 📦 vendored modules load by path under a repo-unique name (cli_args README: Loading a vendored copy)
        self.assertEqual(fleet.check_no_vendor_package_imports(ROOT), [])

    def test_pull_request_ci_stays_quick(self):
        # ⏱ push limited to branches, superseded PR runs cancelled, every job timed (fleet_check.check_ci)
        fleet.check_ci(fleet.repo_root(__file__))
