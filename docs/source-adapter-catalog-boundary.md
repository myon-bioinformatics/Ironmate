# Source adapter to catalog boundary

Status: design checkpoint for Issue #20 / PR #38.

Recorded: 2026-09-28.

Ironmate separates provider transport semantics from catalog/index semantics.

```text
source_adapter.py
  provider-neutral URL/provenance primitives
        |
        +-- github_adapter.py
        +-- future provider adapters
                 |
                 v
        normalized record/envelope
                 |
                 v
           catalog / index
```

## Rules

- A provider adapter owns provider-specific parsing, request construction, fetch policy, normalization, and provider-specific fields.
- The shared source-adapter layer owns only primitives that are genuinely provider-neutral.
- **Target boundary:** catalog/index consumes normalized records. It should not reconstruct provider request URLs or know provider authentication/rate-limit rules.
- **Current known exception:** `github_catalog.py` still participates in request orchestration and carries GitHub token/rate-limit state. PR #38 removes the remaining hand-built item request URLs, but does not claim that the target boundary is fully implemented. Moving transport/auth/rate-limit ownership completely behind provider adapters is follow-up work.
- The existence of `github_catalog.py` does not imply one catalog module per provider.
- Do not flatten unrelated provider fields into a single universal schema merely to make providers look identical.

## Candidate envelope

The next provider integration should validate a minimal envelope before it becomes a stable contract:

- `provider`: source identity, for example `github`
- `kind`: provider resource kind
- `identifier`: stable provider identifier when available (for example, a GitHub commit SHA / PR number or a niconico content ID)
- `html_url`: canonical human-facing URL when available
- `api_url`: canonical item API URL when available
- `source_url`: collection/search/query URL that produced the record
- `data`: provider-specific normalized fields

This is deliberately a candidate, not a frozen schema. A second provider should test whether each common field is genuinely portable before the contract is promoted.

## Follow-up provider

The niconico Snapshot Search API v2 adapter should be a sibling of `github_adapter.py`, not a mode inside it. Its API-specific query schema, version/snapshot metadata, throttling, and content fields stay in the niconico provider adapter. It may reuse provider-neutral URL/provenance primitives.

Implementation of that provider is outside PR #38.
