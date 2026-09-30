# Repository metadata portability contract

Ironmate is the canonical contract and generator source for repository metadata shared by sibling repositories.

## Formats

| Format | Role | Contract |
| --- | --- | --- |
| JSON | canonical machine interchange | generated and validated by Python standard-library code |
| JSONL | aggregate, history, and streaming records | one canonical JSON record per line |

A missing measurement remains JSON `null`. Consumers must not replace it with guessed values.

`working_tree_bytes` is reserved for the tracked-file population used by the initial Python consumers:
enumerate paths with `git ls-files -z`, count tracked paths that currently resolve to files, and sum their
current `stat().st_size` values. Tracked-but-missing paths are skipped. This is not interchangeable with
Flutter's recursive `sourceBytes` directory-walk measurement; consumers with a different population must
keep a distinct local field rather than relabeling it as `working_tree_bytes`.

## Ownership boundary

Metadata collection, normalization, validation, and serialization belong to the Python standard-library
producer. Pages, JavaScript, Dart/Flutter, MCP, and other consumers read the generated JSON/JSONL.
They must not independently reimplement GitHub metadata collection or normalization.

The canonical commit identity is the checkout `HEAD`: SHA, commit timestamp, and subject are read from
that same commit. On GitHub Actions `pull_request` events, the default checkout may be GitHub's synthetic
merge commit. If a published artifact must identify the pull-request head instead, the workflow must
explicitly check out `${{ github.event.pull_request.head.sha }}` and assert that `git rev-parse HEAD`
matches before generating metadata; changing only a metadata SHA is not permitted.

`head.branch` is a CI/context label, not part of the commit identity. The producer prefers
`GITHUB_HEAD_REF`, then `GITHUB_REF_NAME`, then the checkout's abbreviated Git branch. A workflow that
checks out an arbitrary ref can therefore have a branch label that is not derivable from the commit itself.

### Portable tooling

Portable tool versions are observed and normalized by the Python producer, not by JS/Dart consumers.

- `python` comes from the Python runtime.
- `git`, `gh`, `node`, `npm`, and `npx` come from explicitly requested CLI probes.
- Python distributions are explicitly allowlisted by the caller and use `importlib.metadata`.
- Each public tooling key has exactly one source. Colliding runtime/CLI/distribution/caller keys are an error.
- Missing executables/packages, non-zero exits, timeouts, OS errors, empty output, malformed output, and
  over-length labels are observational failures: the key is omitted from schema v1.
- A successful command probe requires exit status zero before stdout/stderr is considered. Stdout is
  preferred; stderr is considered only when stdout is empty.
- Only normalized short version labels are public. Resolved executable paths, raw stderr, environment
  dumps, credentials, and URLs are never emitted.
- Consumers must not synthesize a fallback for an omitted canonical tooling key.

The v1 `tooling` shape remains `{name: string}`; richer failure/status information requires an explicit
future contract version rather than per-consumer conventions.

Provider/API observations such as latest pull request, release/tag, and CI state should first be
normalized by the producer. They must not be added ad hoc to the stable v1 public record. Extend the
versioned contract deliberately when those fields are ready to become public compatibility promises.

## Migration

1. Keep `repository_metadata_generator.py` beside `repository_metadata_contract.py`, then generate and validate canonical JSON/JSONL with that stdlib-only pair.
2. Make the repository's existing UI/tooling consume those generated files.
3. Compare rendered/observable behavior during migration.
4. Delete redundant JavaScript/Dart metadata collectors after equivalence is established.
5. Keep display-only code in the consumer language only when the UI/runtime requires it.

Initial migration targets:

- `web-ui`: keep `js/repository-diagnostics.js` as a renderer/consumer; move duplicated repository SHA/branch collection out of `tool/tooling_meta.py` and compose it with the canonical record.
- `markdown`: replace metadata values distributed across README/module helpers with generated metadata where applicable.
- `ascii_artist`: consume the same generated contract.
- `mcp-toolcall-lab`: consume the same generated contract while keeping MCP-specific presentation separate.
- `browser-test-kit`: consume the same generated contract.
- `flutter_navigation_basic`: retire repository collection from `tool/build_meta.dart`; keep/shrink `lib/shared/diagnostics/build_metadata.dart` to a read-only model/consumer of generated metadata.

`repository_metadata_generator.py` and `repository_metadata_contract.py` are intentionally a two-file vendorable pair; direct execution of the generator must work without relying on the source repository's import path.

The target architecture is one producer contract and many read-only consumers, not parallel
implementations in Python, JavaScript, and Dart.
