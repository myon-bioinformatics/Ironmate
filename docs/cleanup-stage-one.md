> Historical design: the root prototypes and associated demos were retired in cleanup stage two. See [current ownership](cleanup-stage-two.md). Commands below describe the retired implementation.

# cleanup-stage-one.md

# Stage one: tidying up the old assistant layout

Scope: [Ironmate #77](https://github.com/myon-bioinformatics/Ironmate/issues/77).
Destination PR: [mcp-toolcall-lab #104](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/104). Merge it first.

Inventory baseline: main at Ironmate `1281553` and mcp-toolcall-lab `e403593`.
This stage introduces no new product and no new prototype directory layout.

| Target | Action | Reason / destination |
| --- | --- | --- |
| `gradio_galleria.py` | Move to mcp-toolcall-lab | Reuses the existing vendored ASCII/Markdown and loader. Runs with its own Gradio requirements file and virtual environment. Old imports fixed; callbacks and real UI construction verified |
| `file_finder.py` | Delete the standalone file | Only the old screen used it. Scanning is consolidated into the destination's small viewer, tidying JSON extensions, hidden directories and symlinks |
| `i_am_ironmate.py`, `llm_launchpad.py`, `llm_loader.py` | Delete | Old model loading, quantization and character REPL. Not needed to verify the prototypes, and not re-ported on top of the lab's existing model experiments |
| `template_store.py`, `templates_ascii/`, `templates_prompt/` | Delete | Old character assets and their dedicated loader. Generic ASCII templates remain in the already-independent library |
| `requirements.txt` | No required dependencies | torch / transformers / accelerate / bitsandbytes / Gradio / PyYAML removed from the core. PyYAML for tests and FastMCP for optional MCP stay in dedicated requirements |
| `repository_metadata*.py`, `python_artifact_provenance.py`, `provenance.py` | Keep | Existing shared contracts and producers used by other repos |
| GitHub/Niconico adapters, catalog, MCP, PR/comment consumers | Keep | Prototypes with fixtures and real usage paths. Use the parent's gh_ops / gh_identity |
| `vendor/`, `vendor.lock.json`, provenance | Keep | Upstream source, LICENSE and pinned identity. Keep using the parent's vendor_sync / vendor_stage |
| `scripts/`, `tests/`, CI / Pages | Keep | Regression paths for JUnit, shared evidence, diagnostic pages and consumer display |
| README / Pages entry / CONTRIBUTING | Update | Remove retired launch examples and old goals |

## Cross-checks and order

1. ascii_artist's generic shapes and built-in templates, and markdown's save/load/heading extraction, are already independent. No re-port into the core is needed.
2. markdown also has an existing Gradio analysis demo, but galleria, which combines several libraries, goes to mcp-toolcall-lab, which already has both vendors. It must not depend on that repo's MCP or model experiments.
3. Verify callbacks and real Gradio construction in the destination, merge that PR, then merge Ironmate's deletion PR. Do not point new users to deleted commands.
4. Check Ironmate's pytest/JUnit and existing CI. Metadata, the Pages catalog URL and vendor contracts are unchanged.

The old source is available at the [pre-cleanup commit](https://github.com/myon-bioinformatics/Ironmate/tree/1281553). No archive copies of deleted files are kept in the current tree.

## Decisions for later

New placement or automation candidates follow the user's plans for the next stage.
For now, existing tests record reproduction conditions, target SHAs and results, and upstream
bugs are reported back to that repo. Candidates may be kept until shared demand and
responsibility are clear; becoming an independent repo is not a completion criterion.
