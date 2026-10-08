# Cleanup stage two: ownership and vendor findings

Baseline: Ironmate `a24e356503b73b7daf1537c6e5f26a0426a6d876`, parent
`380d877` (catalog introduced by parent PR #60).

## Removed prototypes

| Removed surface | Ownership / disposition |
| --- | --- |
| github_adapter, github_comment, github_pr | Use shared parent / gh_identity tools for GitHub operations; no root compatibility shims retained |
| github_catalog, repository_metadata, repository_metadata_contract, repository_metadata_generator | Retire Ironmate-specific catalog and diagnostics product; not a claim that all old metadata APIs migrated |
| ironmate_mcp, requirements-mcp | Retire Ironmate MCP server; future adapter ownership tracked in mcp-toolcall-lab #107 |
| provenance, python_artifact_provenance | Retire local provenance generators; keep consumer lock identity validation through parent vendor_sync |
| build_repository_diagnostics, build_web_ui_consumer_examples, unreviewed | Retire old prototype consumers and their tests |
| MCP stub / generated catalog Pages and screenshot CI | Replace Pages with a static project landing; remove obsolete scheduled API collection and screenshot job |

Source and niconico implementations, offline fixture and regression tests transfer
into mcp-toolcall-lab PR #108. Merge that transfer before this deletion. The copies
in Ironmate are removed, including obsolete prototype design notes. Routing design
remains #107; the implementation transfer is not a live MCP registration.

Vendor update/check, locked-baseline tests and JUnit failure identity CI remain.
`scripts/sync_vendor_provenance.py` remains only to project legacy vendor JSON
receipts for the existing CI contract. Source and license identity are still
verified by the pinned parent `vendor_sync.py`; all existing lock entries and
vendor bytes are unchanged.

## Why xprobe and yourself are not in vendor

| Tool | Parent recommended catalog | Ironmate consumer lock | Actual placement |
| --- | --- | --- | --- |
| xprobe | Present, commit `642999cea4185a68bffa7f7ccc46bd78dde03e5a`; default source `xprobe.py` | Absent | CI separately checks out `7e7015b2df69ad446b968f6fa49711b5b1dbdd3f` into `build/shared` for JUnit evidence |
| yourself | Absent | Absent | No enrolled copy or machine-readable skip record in these configurations |

The parent catalog currently lists gh_identity and xprobe. It has no Ironmate
consumer-specific skip entry explaining either absence. Recommendation does not
automatically enroll consumers or rewrite locks. Therefore xprobe's absence is a
separate test-checkout arrangement, not a catalog exclusion; yourself has not been
registered in the inspected catalog/lock. This does not establish why an earlier
human decision omitted it. No rule rejection was found in these records.

This cleanup does not enroll new tools or promote either pin. A later enrollment
change should select a full recommended SHA, inspect source identity with parent
vendor_sync, then explicitly update the consumer lock and tests.
