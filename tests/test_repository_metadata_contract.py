from repository_metadata_contract import (
    build_repository_record, format_commit_line, pages_candidate_url,
    repository_identity, to_json, to_jsonl, validate_repository_record,
)
import json
import pytest


def sample():
    return build_repository_record(
        full_name="myon-bioinformatics/Ironmate",
        sha="1376c7035e11165257f9f0f2ac7eb88fd363836f",
        branch="main",
        timestamp="2026-09-27T19:09:22+09:00",
        subject="chore: refresh metadata\nignored body",
        generated_at="2026-09-27T20:00:00+09:00",
        github_reported_size_bytes=1177600,
        tooling={"python": "3.14"},
    )


def test_canonical_commit_line():
    assert format_commit_line(sample()) == (
        "Commit 1376c703 · main · 2026-09-27T19:09:22+09:00 · chore: refresh metadata"
    )


def test_json_and_jsonl_are_same_record():
    record = sample()
    assert json.loads(to_json(record)) == record
    assert json.loads(to_jsonl(record)) == record
    assert to_jsonl(record).count("\n") == 1


def test_null_means_not_measured():
    record = sample()
    assert record["measurements"]["working_tree_bytes"] is None
    assert record["measurements"]["release_artifact_bytes"] is None


def test_rejects_unversioned_and_extra_public_data():
    record = sample()
    record["local_path"] = "/home/runner/work/private"
    with pytest.raises(ValueError):
        validate_repository_record(record)


def test_rejects_negative_size_and_naive_time():
    with pytest.raises(ValueError):
        build_repository_record(
            full_name="a/b", sha="abcdef0123456789", branch="main",
            timestamp="2026-09-27T19:09:22", subject="x",
            generated_at="2026-09-27T20:00:00+09:00", working_tree_bytes=-1,
        )


@pytest.mark.parametrize("full_name", ["a.b/demo", "-bad/demo", "bad-/demo", "owner/..", "owner/."])
def test_rejects_invalid_github_repository_identity(full_name):
    with pytest.raises(ValueError):
        repository_identity(full_name)


def test_pages_candidate_url_handles_project_and_user_sites():
    assert pages_candidate_url("octo/demo") == "https://octo.github.io/demo/"
    assert pages_candidate_url("octo/octo.github.io") == "https://octo.github.io/"


def test_validator_rejects_invalid_measurement_values_after_mutation():
    record = sample()
    record["measurements"]["working_tree_bytes"] = -5
    with pytest.raises(ValueError):
        validate_repository_record(record)
    record = sample()
    record["measurements"]["working_tree_bytes"] = "big"
    with pytest.raises(ValueError):
        validate_repository_record(record)


@pytest.mark.parametrize(
    "tooling",
    [
        {"python": "/home/runner/python"},
        {"python": "https://example.invalid/tool"},
        {"bad key": "3.12"},
        {"python": {"version": "3.12"}},
    ],
)
def test_tooling_is_limited_to_short_public_version_labels(tooling):
    record = sample()
    record["tooling"] = tooling
    with pytest.raises(ValueError):
        validate_repository_record(record)
