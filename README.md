# README.md

# Ironmate

Local CLI for lightweight LLM text generation, ASCII art generation, and safe file operations.

## Features

- Light text generation
- Interactive tool REPL
- Direct ASCII art generation
- Direct ASCII art save
- Predefined ASCII template save
- Safe tool execution via whitelist

---

## Install

```bash
pip install -r requirements.txt
```

---

## Default Models

Recommended default:

- main/light: `Qwen/Qwen3-4B-Instruct-2507`
- tool: `Qwen/Qwen3-4B-Instruct-2507`

Lighter alternative:

- main/light: `Qwen/Qwen3-1.7B`
- tool: `Qwen/Qwen3-1.7B`

Notes:

- `Qwen/Qwen3-4B-Instruct-2507` is a stronger default for instruction-following.
- `Qwen/Qwen3-1.7B` is lighter and faster to load.

---

## Environment Overrides

### Linux / macOS

```bash
export IRONMATE_MODEL="Qwen/Qwen3-4B-Instruct-2507"
export IRONMATE_LIGHT_MODEL="Qwen/Qwen3-4B-Instruct-2507"
export IRONMATE_TOOL_MODEL="Qwen/Qwen3-4B-Instruct-2507"
export IRONMATE_LOAD_4BIT="1"
```

### PowerShell

```powershell
$env:IRONMATE_MODEL="Qwen/Qwen3-4B-Instruct-2507"
$env:IRONMATE_LIGHT_MODEL="Qwen/Qwen3-4B-Instruct-2507"
$env:IRONMATE_TOOL_MODEL="Qwen/Qwen3-4B-Instruct-2507"
$env:IRONMATE_LOAD_4BIT="1"
```

Lighter option:

### Linux / macOS

```bash
export IRONMATE_MODEL="Qwen/Qwen3-1.7B"
export IRONMATE_LIGHT_MODEL="Qwen/Qwen3-1.7B"
export IRONMATE_TOOL_MODEL="Qwen/Qwen3-1.7B"
export IRONMATE_LOAD_4BIT="1"
```

### PowerShell

```powershell
$env:IRONMATE_MODEL="Qwen/Qwen3-1.7B"
$env:IRONMATE_LIGHT_MODEL="Qwen/Qwen3-1.7B"
$env:IRONMATE_TOOL_MODEL="Qwen/Qwen3-1.7B"
$env:IRONMATE_LOAD_4BIT="1"
```

---

## Commands

### Light text generation

```bash
python i_am_ironmate.py light --prompt "Markdownで実験ログのテンプレを作って"
```

### Tool mode

The tool model outputs one-line JSON such as:

```json
{"tool":"save_markdown","args":{"content":"# Hello","filepath":"notes/test.md"}}
```

Run:

```bash
python i_am_ironmate.py tool --prompt "notes/test.md に '# Hello' を保存して"
```

Dry-run:

```bash
python i_am_ironmate.py tool --dry-run --prompt "notes/test.md に '# Hello' を保存して"
```

Show raw model output too:

```bash
python i_am_ironmate.py tool --print-raw --prompt "notes/test.md に '# Hello' を保存して"
```

### Tool REPL

Keeps the model loaded and accepts prompts interactively.

```bash
python i_am_ironmate.py tool-repl
```

Example session:

```text
> notes/test.md に '# Hello' を保存して
> What ASCII templates are available?
> exit
```

### Direct ASCII generation

Generate ASCII art directly with the light model:

```bash
python i_am_ironmate.py ascii --prompt "cat"
```

### Direct ASCII save

Generate ASCII art directly and save it to a file:

```bash
python i_am_ironmate.py ascii-save --prompt "cat" --output "templates_ascii/cat.txt"
```

### Predefined template save

Save a predefined ASCII template to a file:

```bash
python i_am_ironmate.py template-save --name ironmate --output "templates_ascii/ironmate_copy.txt"
```

---

## Predefined ASCII Templates

Current predefined templates:

- `arc_reactor`
- `icon_ironmate`
- `ironmate`

You can also list them through tool mode or REPL.

---

## Suggested Usage

For repeated use, prefer:

```bash
python i_am_ironmate.py tool-repl
```

or direct commands such as:

```bash
python i_am_ironmate.py ascii-save --prompt "cat" --output "templates_ascii/cat.txt"
```

This avoids repeated model loading and is more reliable than routing every request through tool JSON.

---

## Notes

- `ascii-save` is the most reliable path for free-form ASCII generation plus file output.
- `template-save` is the most reliable path for predefined ASCII templates.
- `tool` mode is still available, but direct subcommands are preferred for deterministic tasks.
- If a model echoes `system`, `user`, or code fences, output sanitization should remove them before saving.

---

## Project Structure

```text
.
├─ i_am_ironmate.py
├─ llm_loader.py
├─ llm_launchpad.py
├─ vendor/
│  ├─ ascii_artist.py
│  └─ markdown.py
├─ template_store.py
├─ templates_ascii/
└─ templates_prompt/
```


## Vendored utilities

Ironmate keeps pinned source snapshots under `vendor/` instead of treating these helpers as runtime package dependencies.

- `vendor/markdown.py` is sourced from [`myon-bioinformatics/markdown`](https://github.com/myon-bioinformatics/markdown), currently pinned to `c3063e08`.
- `vendor/ascii_artist.py` is sourced from [`myon-bioinformatics/ascii_artist`](https://github.com/myon-bioinformatics/ascii_artist), currently pinned to `7c21bacf`.
- `vendor/nvd_nist_known_vulns.py` is an exact source snapshot from `myon-bioinformatics/nvd_nist_known_vulns` merge `986e17192442b84adfae8e434ab4bf32bf2347af` (Git blob `16028101be84f6c1b9dd05afb8199280e721f069`). Tests verify the blob identity before exercising the producer-to-consumer contract.

The sibling repositories are the upstream sources; changes should be developed there first and then intentionally refreshed in Ironmate.

For a Markdown refresh, copy `markdown.py` from an explicit upstream commit and update
`vendor/markdown.provenance.json`, the literals in `tests/test_vendor_markdown_provenance.py`,
`MARKDOWN_SHA` in the consumer builder, and the README pin together. Verify the upstream
commit/blob mapping during refresh; offline tests verify the recorded pins and local
file hashes, not the remote commit history. The source file's embedded `base_sha` is
upstream artifact-header metadata, distinct from the vendoring commit; preserve it
so the snapshot stays byte-identical.

The current snapshot includes markdown#78: input NUL is replaced with U+FFFD before
all Markdown-to-HTML parsing paths. `html.escape` alone does not sanitize NUL.


---

## MCP Stub UI

The static MCP Stub Explorer at `docs/mcp-stub.html` consumes the shared
`myon-bioinformatics/web-ui` semantic contract and the Modern theme.

Presentation is supplied by pinned `web-ui` CSS at commit
`adb23d7ba6ea94672b76457573f6655a081ee054`. Ironmate continues to own
repository-search semantics, evidence export, history, and MCP-specific behavior.

This migration is presentation-only: the existing MCP Stub search, history,
export, and repository-source behavior are intentionally unchanged.

The existing **Technology stack** summary is also preserved; it now lives inside
the primary `stub-result` pane alongside repository details rather than in a
separate top-level panel. Its `#stats` target and `renderStats()` behavior are unchanged.

CI captures deterministic Chromium screenshots for:

- desktop `1440x900`
- mobile `390x844`

The screenshots are uploaded as the `ironmate-mcp-stub-screenshots` artifact.
Open the relevant **Test MCP stub** Actions run and use its Artifacts section to
inspect the desktop/mobile evidence. Run artifacts are evidence for that commit;
they are not a permanent release asset.


---

## web-ui v1 consumer integration

Ironmate now exercises the frozen web-ui v1 contract through both vendored
sibling libraries rather than only through hand-written Stub markup.

`scripts/build_web_ui_consumer_examples.py` composes:

- `vendor/markdown.py::markdown_to_web_ui_v1()`
- `vendor/ascii_artist.py::to_web_ui_v1_html()`
- pinned web-ui CSS at `a0867e45`

The libraries emit semantic HTML only. Ironmate remains responsible for loading
the pinned presentation assets, which keeps the upstream libraries stdlib-only
and dependency-free.

GitHub Pages generates these integration examples at deploy time:

- `/consumer-v1/index.html`
- `/consumer-v1/markdown.html`
- `/consumer-v1/ascii.html`

CI compiles the vendored modules and builder, validates the semantic classes and
text escaping, and captures deterministic Chromium evidence in the
`ironmate-web-ui-consumer-screenshots` artifact.

This also records the exact upstream revisions in generated HTML comments, so a
render can be traced back to the web-ui, markdown, and ascii_artist commits that
produced it.

When advancing the web-ui pin, update the MCP Stub stylesheet pin and the
consumer-example `WEB_UI_SHA` together in the same PR so both presentation
lanes remain on one contract revision.


---

## GitHub source adapter

`github_adapter.py` is Ironmate's reference read-only source adapter. It separates
**Parse → Build URL → Fetch → Normalize/inspect** so URL construction and fixture
tests remain useful even when a runner cannot reach GitHub.

Public resources can be inspected anonymously; a token passed by the caller is
optional rate-limit headroom rather than a requirement for URL construction.
Bearer credentials are attached only to HTTPS requests for `api.github.com`
and are stripped if a redirect leaves that host. Consumers
may also call `inspect_public(..., fetch=False)` to produce canonical GitHub
HTML and REST API URLs without any network request.

The adapter is intentionally small and stdlib-only. Future API/MCP adapters
should use this shape as a reference rather than copying GitHub-specific request
logic into each consumer. Live GitHub availability is not a normal CI
requirement.


### Catalog integration and Pages verification

`github_catalog.py` now reuses `github_adapter.fetch_json()` for GitHub
transport instead of maintaining a second request implementation. The catalog
keeps its existing output vocabulary (`detected`, `not_found`,
`fetch_failed`) at the consumer boundary; the adapter deliberately keeps the
smaller transport outcome plus raw HTTP/error evidence.

The GitHub Pages deploy remains the live integration lane. A deploy builds the
catalog through the shared adapter and publishes the generated files under
`docs/api/`. Normal adapter tests stay offline and deterministic; Pages is
where the public GitHub fetch path is exercised. After deployment, verify that
`api/catalog.min.json` is present and that repository metadata such as
`api/repos/Ironmate.json` is refreshed for the deployed revision.


### Live read-only example

Public resources can be inspected without a token when network access is intentionally requested:

```python
from github_adapter import inspect_public

result = inspect_public("openai/openai-python", fetch=True)
print(result["fetch"]["status"])
```

Normal CI remains fixture/offline-driven; this live form is for manual/browser validation. A token is optional rate-limit headroom, not a requirement for public resources.


## Python artifact provenance contract

`python_artifact_provenance.py` is a stdlib-only static contract for standalone or vendored
single-file Python artifacts. It is intentionally separate from repository metadata JSON/JSONL.

The canonical `__all__` declaration must be one literal top-level list or tuple of strings.
Top-level functions, classes, and assigned constants count as artifact implementations.
Imported names and names defined only inside control-flow blocks such as `if` or `try` do
not count as implementations for this static check, so re-exporting them is rejected.
Public top-level functions/classes must be exported, while underscore-prefixed helpers must
remain internal.

Dynamic or nested mutation is outside the contract. In particular, slice assignment such as
`__all__[:] = [...]` and mutations hidden inside control flow are not interpreted as a
canonical declaration. Top-level `+=`, `.extend(...)`, and `.append(...)` are rejected
rather than guessed.


## Cross-repository anti-patterns

Ironmate also keeps a discovery index for recurring CI/design failures across
the sibling repositories:

- [docs/antipatterns.md](docs/antipatterns.md)

The owning repositories remain the source of truth for their detailed catalogs;
Ironmate links and summarizes shared IDs so the same failure class is searchable
across repository boundaries.


---

## NVD security metadata adapter

`vendor/nvd_nist_known_vulns.py` is an unchanged snapshot of upstream
`myon-bioinformatics/nvd_nist_known_vulns` merge `a3d8f18`. Upstream now owns
both production and generic `nvd-cve-summary/1` JSONL consumption
(`parse_jsonl`, `read_jsonl`, and `select_cpe_records`), so Ironmate no
longer maintains a parallel `security_nvd.py` implementation.

Ironmate keeps only its repository-specific boundary in `repository_metadata.py`:
the explicit `ironmate-security-cpe/1` repository-to-CPE mapping and conversion
of upstream selection results into repository metadata. It does **not** infer a
CPE from a Python package or repository name. Missing mapping or incomplete query
completion remains `not_measured`, while a completed zero-CVE query is
`measured` with count zero. Normal tests are offline and pin the vendored Git
blob, so CI does not call NVD. NVD evidence remains complementary to package-native
advisory sources such as Dependabot.

### Unreviewed diagnostics

`scripts/unreviewed.py` treats an item as reviewed only when a comment or review body contains a standalone `from: <reviewer>` line. Author identity alone is intentionally insufficient: bot-authored Action/error responses such as `claude[bot]` failures do not count as reviews unless that tag line is present.


### Repository metadata portability

Repository metadata uses the stdlib-only Python producer and canonical JSON/JSONL contract documented in [docs/repository-metadata-portability.md](docs/repository-metadata-portability.md). UI/runtime consumers read generated records rather than reimplementing GitHub metadata collection.
