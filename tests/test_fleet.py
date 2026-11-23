"""🚢 Fleet contracts through the parent's shared checks (vendor/fleet_check.py): its locked bytes, and scripts."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ironmate_fleet_check", ROOT / "vendor/fleet_check.py")
fleet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fleet)
ACCEPTED = {"vendor/fleet_check.py": "bc57f08a590ee1cb33a8bb37c1bb3b8f28a2f3c9"}


class VendorLock(unittest.TestCase):
    def test_fleet_check_is_the_accepted_parent_commit(self):
        fleet.check_lock(ROOT, commits=ACCEPTED)


# 🧰 Scripts: 📝 each one describes itself and ⌨️ one that reads sys.argv declares its arguments (argparse /
# cli_args). Read with ast, never run; the portfolio's script catalog reads the same facts.

class ScriptsDescribeThemselves(unittest.TestCase):
    def test_every_script_has_a_description_and_declared_arguments(self):
        fleet.check_scripts(ROOT)
