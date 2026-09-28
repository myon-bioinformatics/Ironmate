# Repository metadata portability contract

Ironmate is the canonical contract and generator source for repository metadata shared by sibling repositories.

## Formats

| Format | Role | Contract |
| --- | --- | --- |
| JSON | canonical machine interchange | generated and validated by Python standard-library code |
| JSONL | aggregate, history, and streaming records | one canonical JSON record per line |

A missing measurement remains JSON `null`. Consumers must not replace it with guessed values.

## Ownership boundary

Metadata collection, normalization, validation, and serialization belong to the Python standard-library
producer. Pages, JavaScript, Dart/Flutter, MCP, and other consumers read the generated JSON/JSONL.
They must not independently reimplement GitHub metadata collection or normalization.

Provider/API observations such as latest pull request, release/tag, and CI state should first be
normalized by the producer. They must not be added ad hoc to the stable v1 public record. Extend the
versioned contract deliberately when those fields are ready to become public compatibility promises.

## Migration

1. Generate and validate canonical JSON/JSONL with Ironmate's Python contract.
2. Make the repository's existing UI/tooling consume those generated files.
3. Compare rendered/observable behavior during migration.
4. Delete redundant JavaScript/Dart metadata collectors after equivalence is established.
5. Keep display-only code in the consumer language only when the UI/runtime requires it.

Initial migration targets:

- `web-ui`: retire metadata collection from `js/repository-diagnostics.js`; retain only rendering as needed.
- `markdown`: replace metadata values distributed across README/module helpers with generated metadata where applicable.
- `ascii_artist`: consume the same generated contract.
- `mcp-toolcall-lab`: consume the same generated contract while keeping MCP-specific presentation separate.
- `browser-test-kit`: consume the same generated contract.
- `flutter_navigation_basic`: retire `tool/build_meta.dart` and metadata collection from
  `lib/shared/diagnostics/build_metadata.dart`; read generated metadata instead.

The target architecture is one producer contract and many read-only consumers, not parallel
implementations in Python, JavaScript, and Dart.
