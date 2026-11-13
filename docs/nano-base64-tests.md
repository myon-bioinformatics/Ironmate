# Base64 focused test environment

From the repository root:

```sh
PYTHONPATH=. uv run --locked --only-group test --exact python -m pytest -q tests/test_grid.py
```

This reuses the existing test group. It does not replace full CI, codecs, preview, Docker, Marp or browser checks. No dependencies or lock records are changed. `--exact` removes leftover optional dependencies; use a separate UV_PROJECT_ENVIRONMENT when retaining a full development environment.

## Local reference measurement, 2026-11-03

Linux x86_64, CPython 3.12.14, source ae99a861d3f487674990b83b6e91e0bb6751bfda, unchanged uv.lock. Full `uv sync --locked --python 3.12` versus a fresh separate environment with `--only-group test --exact`. Both selected test files: 29 passed, zero skips, same JUnit identities and outcomes. Both have no third-party pytest entry-point plugins.

Installed distributions: 13 to 6. Environment regular-file logical bytes after tests: 290,355,508 to 11,567,453 (about 276.9 to 11.0 MiB). Excludes symlinks, shared Python and uv cache; includes bytecode. One run per profile, no fair cold/warm timing experiment and no general or CI-wide speed claim. Full test wall 0.76s and focused 0.48s are single observations only.

The full suite is still needed for optional dependencies and integrations. This recipe proves only the named 29 tests can run in the existing smaller profile.
