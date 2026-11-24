"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): its locked bytes, and scripts."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ironmate_fleet_check", ROOT / "vendor/fleet_check.py")
fleet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fleet)
ACCEPTED = {"vendor/fleet_check.py": "20de01921e50e9339aa9271b0547a5be7649b3b3"}


class VendorLock(unittest.TestCase):
    def test_fleet_check_is_the_accepted_parent_commit(self):
        fleet.check_lock(ROOT, commits=ACCEPTED)


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(ROOT)

    def test_pull_request_ci_stays_quick(self):
        # ⏱ push limited to branches, superseded PR runs cancelled, every job timed (fleet_check.check_ci)
        fleet.check_ci(fleet.repo_root(__file__))
