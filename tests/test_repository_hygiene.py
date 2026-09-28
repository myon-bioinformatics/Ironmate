"""Repository-wide source hygiene checks."""

import py_compile
import subprocess
import tempfile
import unittest
from pathlib import Path


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

    def test_workflow_files_have_no_literal_newline_escape_in_structure(self):
        """Catch the exact corruption class that broke #42 without adding PyYAML."""
        failures = []
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "\\n" in line and not line.lstrip().startswith("#"):
                    failures.append(f"{path.relative_to(ROOT)}:{number}: literal \\n")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
