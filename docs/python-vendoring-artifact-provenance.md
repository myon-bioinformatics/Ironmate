# Python vendoring artifact provenance

This contract applies only to Python single-file artifacts that are intended to be copied,
vendored, pinned, or synchronized between repositories. It is separate from repository
metadata JSON/JSONL.

## Canonical header

```python
# metadata: __all__=<count> | base_sha=<full commit SHA> | updated_at=<timezone-aware ISO 8601>
```

Example:

```python
# metadata: __all__=127 | base_sha=99b6a174a883f60a9c3ed01164a81fd7bd26ff76 | updated_at=2026-09-27T09:40:47Z
```

The header should appear within the first eight physical lines so it remains visible when a
single file is copied without its repository.

- `__all__` is the number of names in one literal top-level Python `__all__` list or tuple.
- `base_sha` is the full source/upstream commit used to produce or synchronize the artifact.
  It is not automatically the consumer repository HEAD.
- `updated_at` records the artifact update/synchronization time and must include a timezone.
- Files without a literal `__all__` are not forced into this contract.
- Repository-level SHA, CI, release, size, and branch information remain in repository
  metadata and must not be duplicated into this header.

`python_artifact_provenance.py` provides stdlib-only parsing, formatting, validation,
literal-`__all__` counting, and header insertion/replacement.

## Rollout

Use this header for Python single-file artifacts such as `markdown.py`, `ascii_artist.py`,
and pinned/vendored Python modules in sibling repositories when they expose a literal
`__all__`. Preserve additional provenance files when they already carry useful upstream
hashes or source URLs; the header is a compact human-visible summary, not a replacement for
richer provenance evidence.
