"""Repository-wide source hygiene checks."""

import py_compile
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "build", "dist",
}


def repository_python_sources():
    """Prefer tracked sources; fall back for source archives without Git."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "*.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return sorted(
            path
            for path in ROOT.rglob("*.py")
            if not EXCLUDED_PARTS.intersection(path.relative_to(ROOT).parts)
        )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def workflow_structure_escape_failures(text):
    """Find #42-style escaped newlines that splice YAML list entries."""
    failures = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(r'^\s*-\s+["\'][^"\']+["\']\\n\s+-\s+', line):
            failures.append(number)
    return failures


class RepositoryHygieneTest(unittest.TestCase):
    def test_repository_python_files_compile(self):
        sources = repository_python_sources()
        self.assertTrue(sources, "no Python sources discovered")
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

    def test_workflow_files_have_no_spliced_list_entries(self):
        """Catch the exact #42 list-entry corruption without banning valid \\n data."""
        failures = []
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
            for number in workflow_structure_escape_failures(path.read_text(encoding="utf-8")):
                failures.append(f"{path.relative_to(ROOT)}:{number}: escaped newline joins list entries")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_workflow_structure_escape_detector_is_narrow(self):
        broken = '      - "a.py"\\n      - "b.py"'
        legitimate = "      run: printf 'a\\\\nb'"
        self.assertEqual(workflow_structure_escape_failures(broken), [1])
        self.assertEqual(workflow_structure_escape_failures(legitimate), [])

    def test_repository_python_sources_falls_back_without_git(self):
        with mock.patch("tests.test_repository_hygiene.subprocess.run", side_effect=FileNotFoundError):
            sources = repository_python_sources()
        self.assertIn(ROOT / "tests" / "test_repository_hygiene.py", sources)
        self.assertTrue(all(path.suffix == ".py" for path in sources))


if __name__ == "__main__":
    unittest.main()
