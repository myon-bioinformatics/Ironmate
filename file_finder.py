# file_finder.py
# __all__: 2

__all__ = [
    "find_files",
    "find_files_as_map",
]

from pathlib import Path
from typing import Dict, List, Optional


_DEFAULT_EXTENSIONS = (".txt", ".md", ".yaml", ".yml", ".py", ".sh")


def find_files(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> List[Path]:
    """Recursively find files under *directory* matching *extensions*.

    Args:
        directory: Root directory to search.
        extensions: File suffixes to include (e.g. ``[".md", ".yaml"]``).
                    Defaults to a common set of text-based extensions.

    Returns:
        Sorted list of :class:`pathlib.Path` objects for each matching file.

    Raises:
        ValueError: If *directory* does not exist or is not a directory.
    """
    base = Path(directory)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    exts = set(extensions) if extensions is not None else set(_DEFAULT_EXTENSIONS)

    return sorted(
        path for path in base.rglob("*") if path.is_file() and path.suffix in exts
    )


def find_files_as_map(
    directory: str | Path,
    extensions: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Return a label → path mapping suitable for use with ``gradio_galleria``.

    Labels are the file names relative to *directory*, using forward slashes.

    Args:
        directory: Root directory to search.
        extensions: File suffixes to include.  See :func:`find_files`.

    Returns:
        Dictionary mapping relative file names to their absolute
        :class:`pathlib.Path` objects, sorted by label.

    Raises:
        ValueError: If *directory* does not exist or is not a directory.
    """
    base = Path(directory)
    files = find_files(base, extensions=extensions)
    return {str(path.relative_to(base)): path for path in files}
