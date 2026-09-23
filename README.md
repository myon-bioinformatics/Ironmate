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

- `vendor/markdown.py` is sourced from [`myon-bioinformatics/markdown`](https://github.com/myon-bioinformatics/markdown), currently pinned to `83a325ce`.
- `vendor/ascii_artist.py` is sourced from [`myon-bioinformatics/ascii_artist`](https://github.com/myon-bioinformatics/ascii_artist), currently pinned to `7c21bacf`.

The sibling repositories are the upstream sources; changes should be developed there first and then intentionally refreshed in Ironmate.


---

## MCP Stub UI

The static MCP Stub Explorer at `docs/mcp-stub.html` consumes the shared
`myon-bioinformatics/web-ui` semantic contract and the Modern theme.

Presentation is supplied by pinned `web-ui` CSS at commit
`dfdbb26a76f71b147483f212ec49ca677384b936`. Ironmate continues to own
repository-search semantics, evidence export, history, and MCP-specific behavior.

This migration is presentation-only: the existing MCP Stub search, history,
export, and repository-source behavior are intentionally unchanged.

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
- pinned web-ui CSS at `dfdbb26a`

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
