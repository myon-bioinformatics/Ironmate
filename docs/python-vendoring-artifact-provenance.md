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
- `base_sha` is the full baseline commit recorded by the artifact source when that artifact
  is refreshed. Downstream vendoring should preserve this embedded value verbatim.
- `base_sha` is not the downstream consumer repository HEAD and does not have to equal the
  exact upstream commit from which a downstream copy was fetched.
- When exact vendoring provenance matters, keep it separately (for example source commit,
  source blob SHA, and vendored-file SHA-256 in a provenance JSON file).
- `updated_at` records the source artifact refresh time and must include a timezone. Downstream copying preserves it; downstream vendor-sync time belongs in richer provenance evidence when needed.
- Files without a literal `__all__` are not forced into this contract.
- `__all__` is the public API source of truth for this artifact contract. Public top-level
  functions/classes must be listed there; exported names must exist in the artifact.
- Internal helpers use a leading underscore (for example `_parse_source`) and are not
  exported through `__all__`.
- Validation is intentionally static and simple. One literal top-level `__all__` declaration
  is required; top-level `+=` / method mutation is rejected. Arbitrary runtime mutation inside
  nested control flow is outside this contract and is not dynamically evaluated.
- Repository-level SHA, CI, release, size, and branch information remain in repository
  metadata and must not be duplicated into this header.

`python_artifact_provenance.py` provides stdlib-only parsing, formatting, validation,
literal-`__all__` counting, and header insertion/replacement.

## Rollout

Use this header for Python single-file artifacts such as `markdown.py`, `ascii_artist.py`,
and pinned/vendored Python modules in sibling repositories when they expose a literal
`__all__`. Preserve additional provenance files when they carry the exact vendoring source commit,
blob/hash, or source URL. The embedded header travels with the artifact and is a compact
human-visible baseline summary; it does not replace richer vendoring provenance evidence.
