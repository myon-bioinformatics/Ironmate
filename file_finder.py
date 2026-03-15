# file_finder.py
# __all__: 2

from __future__ import annotations

__all__ = [
    "find_files",
    "find_files_as_map",
]

from pathlib import Path
from typing import Dict, List, Optional


_DEFAULT_EXTENSIONS = (
    ".txt",
    ".md",
    ".markdown",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".log",
    ".json",
    ".csv",
    ".py",
    ".sh",
    ".rst",
    ".ts",
    ".js",
    ".css",
    ".html",
)

_EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".ironmate_venv",
}


def find_files(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> List[Path]:
    """Recursively find files under *directory* matching *extensions*.

    Excludes any file that is inside a directory whose name is in
    ``_EXCLUDE_DIR_NAMES``.

    Args:
        directory: Root directory to search.
        extensions: File suffixes to include (e.g. [".md", ".yaml"]).
                    Defaults to ``_DEFAULT_EXTENSIONS``.

    Returns:
        Sorted list of Path objects.

    Raises:
        ValueError: If *directory* does not exist or is not a directory.
    """
    base = Path(directory)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    exts = set(s.lower() for s in (extensions if extensions is not None else _DEFAULT_EXTENSIONS))

    results: List[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue

        # Exclude if any parent directory is excluded
        if any(parent.name in _EXCLUDE_DIR_NAMES for parent in path.parents):
            continue

        if path.suffix.lower() in exts:
            results.append(path)

    return sorted(results)


def find_files_as_map(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Return a label -> path mapping suitable for use in a Gradio dropdown.

    Labels are relative paths from *directory* using forward slashes.
    """
    base = Path(directory)
    files = find_files(base, extensions=extensions)
    return {
        str(path.relative_to(base)).replace("\\", "/"): path
        for path in files
    }