"""Repository-wide source hygiene checks."""

import py_compile
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RepositoryHygieneTest(unittest.TestCase):
    def test_tracked_python_files_compile(self):
        """Every Git-tracked Python source must be syntactically compilable."""
        result = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        sources = [ROOT / line for line in result.stdout.splitlines() if line]
        self.assertTrue(sources, "no tracked Python sources discovered")

        failures = []
        with tempfile.TemporaryDirectory() as directory:
            cache_root = Path(directory)
            for path in sources:
                relative = path.relative_to(ROOT)
                cache = cache_root / relative.with_suffix(".pyc")
                cache.parent.mkdir(parents=True, exist_ok=True)
                try:
                    py_compile.compile(str(path), cfile=str(cache), doraise=True)
                except py_compile.PyCompileError as exc:
                    failures.append(f"{relative}: {exc.msg}")

        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
