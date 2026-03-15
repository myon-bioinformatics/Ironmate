# file_finder.py
# __all__: 2

__all__ = [
    "find_files",
    "find_files_as_map",
]

from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_EXTENSIONS = (".txt", ".md", ".yaml", ".yml", ".sh", "json", ".csv", ".log")
_EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".ironmate_venv",
}


def find_files(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> List[Path]:
    """Recursively find files under *directory* matching *extensions*."""
    base = Path(directory)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    exts = set(s.lower() for s in (extensions if extensions is not None else DEFAULT_EXTENSIONS))

    results: List[Path] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue

        if any(parent.name in _EXCLUDE_DIR_NAMES for parent in path.parents):
            continue

        if path.suffix.lower() in exts:
            results.append(path)

    return sorted(results)


def find_files_as_map(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Return a label -> path mapping suitable for use in a Gradio dropdown."""
    base = Path(directory)
    files = find_files(base, extensions=extensions)
    return {
        str(path.relative_to(base)).replace("\\", "/"): path
        for path in files
    }
