from pathlib import Path

import pytest

from python_artifact_provenance import (
    count_literal_all,
    find_header,
    format_header,
    parse_header,
    upsert_header,
    validate_source_header,
)

SHA = "99b6a174a883f60a9c3ed01164a81fd7bd26ff76"
WHEN = "2026-09-27T09:40:47Z"


def _artifact_with_all_export(prefix: str = "") -> str:
    return (
        prefix
        + '__all__ = ["exported_function"]\n'
        + "def exported_function(): pass\n"
    )


def source(header_count=2):
    return (
        "# demo.py\n"
        f"# metadata: __all__={header_count} | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\", \"b\"]\n"
        "def a(): pass\n"
        "def b(): pass\n"
    )


def test_format_and_parse_header_round_trip():
    line = format_header(all_count=2, base_sha=SHA, updated_at=WHEN)
    assert parse_header(line) == {
        "all_count": 2,
        "base_sha": SHA,
        "updated_at": WHEN,
    }


def test_validate_source_header_matches_literal_all():
    metadata = validate_source_header(source())
    assert metadata["all_count"] == 2


def test_validate_source_header_rejects_count_drift():
    with pytest.raises(ValueError, match="count mismatch"):
        validate_source_header(source(header_count=3))


@pytest.mark.parametrize(
    "body",
    [
        "__all__ = make_exports()\n",
        "__all__ = [\"a\"]\n__all__ = [\"b\"]\n",
        "__all__ = [\"a\"]\n__all__ += [\"b\"]\n",
        "__all__ = [\"a\"]\n__all__.extend([\"b\"])\n",
        "__all__ = [\"a\"]\n__all__.append(\"b\")\n",
        "def a(): pass\n",
    ],
)
def test_count_literal_all_rejects_dynamic_missing_or_multiple_assignments(body):
    with pytest.raises(ValueError):
        count_literal_all(body)


def test_count_literal_all_accepts_tuple():
    assert count_literal_all("__all__ = ('a', 'b', 'c')\n") == 3


def test_validate_source_header_rejects_public_function_missing_from_all():
    text = (
        f"# metadata: __all__=1 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\"]\n"
        "def a(): pass\n"
        "def b(): pass\n"
    )
    with pytest.raises(ValueError, match="public functions/classes missing from __all__"):
        validate_source_header(text)


def test_upsert_rejects_exported_name_without_implementation():
    text = (
        '__all__ = ["a", "missing"]\n'
        "def a(): pass\n"
    )
    with pytest.raises(ValueError, match="not implemented"):
        upsert_header(text, base_sha=SHA, updated_at=WHEN)


def test_upsert_rejects_private_helper_in_all():
    text = (
        '__all__ = ["a", "_helper"]\n'
        "def a(): pass\n"
        "def _helper(): pass\n"
    )
    with pytest.raises(ValueError, match="must not be exported"):
        upsert_header(text, base_sha=SHA, updated_at=WHEN)


def test_upsert_rejects_public_function_missing_from_all():
    text = (
        "__all__ = [\"a\"]\n"
        "def a(): pass\n"
        "def b(): pass\n"
    )
    with pytest.raises(ValueError, match="public functions/classes missing from __all__"):
        upsert_header(text, base_sha=SHA, updated_at=WHEN)


def test_validate_source_header_rejects_exported_name_without_implementation():
    text = (
        f"# metadata: __all__=2 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\", \"missing\"]\n"
        "def a(): pass\n"
    )
    with pytest.raises(ValueError, match="not implemented"):
        validate_source_header(text)


def test_validate_source_header_allows_private_helper_outside_all():
    text = (
        f"# metadata: __all__=1 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\"]\n"
        "def a(): pass\n"
        "def _helper(): pass\n"
    )
    assert validate_source_header(text)["all_count"] == 1


def test_validate_source_header_rejects_private_helper_in_all():
    text = (
        f"# metadata: __all__=2 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\", \"_helper\"]\n"
        "def a(): pass\n"
        "def _helper(): pass\n"
    )
    with pytest.raises(ValueError, match="must not be exported"):
        validate_source_header(text)


def test_validate_source_header_rejects_duplicate_all_names():
    text = (
        f"# metadata: __all__=2 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"a\", \"a\"]\n"
        "def a(): pass\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_source_header(text)


def test_count_literal_all_accepts_leading_utf8_bom():
    assert count_literal_all("\ufeff__all__ = [\"a\", \"b\"]\n") == 2


def test_upsert_preserves_leading_utf8_bom():
    original = "\ufeff" + _artifact_with_all_export()
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    assert updated.startswith("\ufeff# metadata: __all__=1")
    assert validate_source_header(updated)["all_count"] == 1


@pytest.mark.parametrize(
    "sha",
    ["abc123", "A" * 40, "g" * 40],
)
def test_header_rejects_non_full_lowercase_commit_sha(sha):
    with pytest.raises(ValueError):
        format_header(all_count=1, base_sha=sha, updated_at=WHEN)


def test_header_requires_timezone():
    with pytest.raises(ValueError, match="timezone"):
        format_header(all_count=1, base_sha=SHA, updated_at="2026-09-27T09:40:47")


def test_upsert_replaces_existing_header_and_recounts():
    updated = upsert_header(source(header_count=999), base_sha=SHA, updated_at=WHEN)
    assert "__all__=2" in updated
    assert validate_source_header(updated)["all_count"] == 2


def test_upsert_inserts_after_shebang():
    original = _artifact_with_all_export("#!/usr/bin/env python3\n")
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    assert updated.splitlines()[1].startswith("# metadata: __all__=1")


@pytest.mark.parametrize(
    ("original", "coding_index"),
    [
        (
            _artifact_with_all_export("# demo.py\n# -*- coding: utf-8 -*-\n"),
            1,
        ),
        (
            _artifact_with_all_export("# -*- coding: utf-8 -*-\n# demo.py\n"),
            0,
        ),
        (
            _artifact_with_all_export("#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n# demo.py\n"),
            1,
        ),
    ],
)
def test_upsert_preserves_valid_pep263_coding_position(original, coding_index):
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    lines = updated.splitlines()
    assert "coding:" in lines[coding_index]
    assert coding_index <= 1
    assert validate_source_header(updated)["all_count"] == 1


def test_upsert_accepts_pep263_decoding_spelling():
    original = _artifact_with_all_export("# decoding: latin-1\n")
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    lines = updated.splitlines()
    assert lines[0] == "# decoding: latin-1"
    assert lines[1].startswith("# metadata: __all__=1")
    assert validate_source_header(updated)["all_count"] == 1


def test_duplicate_headers_are_rejected():
    duplicate = (
        f"# metadata: __all__=1 | base_sha={SHA} | updated_at={WHEN}\n"
        f"# metadata: __all__=1 | base_sha={SHA} | updated_at={WHEN}\n"
        "__all__ = [\"exported_function\"]\n"
        "def exported_function(): pass\n"
    )
    with pytest.raises(ValueError, match="exactly one"):
        find_header(duplicate)
    with pytest.raises(ValueError, match="at most one"):
        upsert_header(duplicate, base_sha=SHA, updated_at=WHEN)


def test_header_outside_scan_window_is_rejected_on_upsert():
    original = (
        "".join(f"# line {i}\n" for i in range(8))
        + f"# metadata: __all__=1 | base_sha={SHA} | updated_at={WHEN}\n"
        + "__all__ = [\"exported_function\"]\n"
        + "def exported_function(): pass\n"
    )
    with pytest.raises(ValueError, match="within the first 8 lines"):
        upsert_header(original, base_sha=SHA, updated_at=WHEN)


def test_real_vendored_markdown_preserves_valid_embedded_header():
    path = Path(__file__).resolve().parents[1] / "vendor" / "markdown.py"
    source = path.read_text(encoding="utf-8")
    metadata = validate_source_header(source)
    assert metadata["all_count"] == 127


def test_upsert_keeps_leading_python_filename_comment_first():
    original = _artifact_with_all_export("# demo.py\n")
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    assert updated.splitlines()[0] == "# demo.py"
    assert updated.splitlines()[1].startswith("# metadata: __all__=1")
