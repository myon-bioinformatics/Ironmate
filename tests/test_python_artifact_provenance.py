from pathlib import Path

import pytest

from python_artifact_provenance import (
    count_literal_all,
    format_header,
    parse_header,
    upsert_header,
    validate_source_header,
)

SHA = "99b6a174a883f60a9c3ed01164a81fd7bd26ff76"
WHEN = "2026-09-27T09:40:47Z"


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
        "def a(): pass\n",
    ],
)
def test_count_literal_all_rejects_dynamic_missing_or_multiple_assignments(body):
    with pytest.raises(ValueError):
        count_literal_all(body)


def test_count_literal_all_accepts_tuple():
    assert count_literal_all("__all__ = ('a', 'b', 'c')\n") == 3


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
    original = "#!/usr/bin/env python3\n__all__ = [\"x\"]\n"
    updated = upsert_header(original, base_sha=SHA, updated_at=WHEN)
    assert updated.splitlines()[1].startswith("# metadata: __all__=1")


def test_real_vendored_markdown_preserves_valid_embedded_header():
    path = Path(__file__).resolve().parents[1] / "vendor" / "markdown.py"
    source = path.read_text(encoding="utf-8")
    metadata = validate_source_header(source)
    assert metadata["all_count"] == 127
