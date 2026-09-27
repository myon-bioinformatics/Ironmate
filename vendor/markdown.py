# markdown.py
# metadata: __all__=99 | base_sha=cae5618bd940ded29d4b61f71e4a11ee51faa9d9 | updated_at=2026-09-21T15:05:00Z
"""Stdlib-only Markdown utility functions.

This module is intentionally a single file with no CLI / ``main`` entry point.
It focuses on reusable helpers for Markdown I/O, structure extraction, and
conservative HTML <-> Markdown conversions (links, images, common tags).

It is **not** a full CommonMark implementation. Prefer the inventory helpers
and tests to see what is and is not handled.
"""

from __future__ import annotations

__all__ = [
    "save_markdown",
    "read_markdown",
    "run_markdown_doctest",
    "extract_sections",
    "split_sections",
    "extract_links",
    "extract_images",
    "extract_code_blocks",
    "extract_raw_html",
    "extract_urls",
    "extract_data_uris",
    "extract_section",
    "strip_prose_keep_structure",
    "minify_markdown",
    "safe_truncate",
    "inventory",
    "make_link",
    "make_image",
    "html_image_to_markdown",
    "markdown_image_to_html",
    "html_link_to_markdown",
    "markdown_link_to_html",
    "html_to_markdown",
    "markdown_to_html",
    "markdown_to_web_ui_v1",
    "HtmlNode",
    "parse_html_dom",
    "html_text_content",
    "find_html_text",
    "dom_to_html",
    "dom_to_markdown",
    "markdown_to_dom",
    "markdown_to_kramdown",
    "kramdown_to_markdown",
    "ial",
    "with_attributes",
    "alert_stylesheet",
    "default_stylesheet",
    "is_probably_url",
    "heading",
    "bold",
    "italic",
    "strikethrough",
    "blockquote",
    "alert",
    "horizontal_rule",
    "bullet_list",
    "numbered_list",
    "task_item",
    "task_list",
    "details",
    "footnote_ref",
    "footnote",
    "code_block",
    "mermaid_block",
    "extract_mermaid_blocks",
    "markdown_headings_to_mermaid_mindmap",
    "markdown_tasks_to_mermaid_flowchart",
    "python_to_mermaid_class_diagram",
    "markdown_links_to_dot",
    "inspect_to_markdown",
    "argparse_to_markdown",
    "distribution_to_markdown",
    "table",
    "aligned_table",
    "markdown_table_to_rows",
    "markdown_table_to_records",
    "csv_to_markdown_table",
    "markdown_table_to_csv",
    "markdown_table_statistics",
    "json_to_markdown",
    "markdown_to_json",
    "structured_to_markdown",
    "markdown_to_structured",
    "ini_to_markdown",
    "markdown_to_ini",
    "toml_to_markdown",
    "markdown_to_toml",
    "dotenv_to_markdown",
    "markdown_to_dotenv",
    "redis_snapshot_to_markdown",
    "sql_ddl_to_markdown",
    "markdown_to_sql_ddl",
    "markdown_to_ipynb",
    "ipynb_to_markdown",
    "markdown_to_py_percent",
    "py_percent_to_markdown",
    "key_value_table",
    "section",
    "inline_code",
    "json_block",
    "status_line",
    "wrap_section",
    "md_table",
    "md_kv",
    "ALERT_FLAVORS",
    "GITHUB_ALERT_KINDS",
    "QIITA_NOTE_KINDS",
    "ZENN_MESSAGE_KINDS",
    "SUPPORTED",
    "UNSUPPORTED",
]

import argparse
import ast
import configparser
import csv
import doctest
import graphlib
import html as html_module
import importlib.metadata as importlib_metadata
import inspect
import io
import json
import math
import re
import statistics
import tokenize
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None

# ---------------------------------------------------------------------------
# Capability notes (kept in-module so a vendored single file stays honest)
# ---------------------------------------------------------------------------

SUPPORTED = {
    "io": ["save_markdown", "read_markdown"],
    "structure": [
        "ATX headings (# ## ...)",
        "fenced code blocks",
        "inline links [text](url)",
        "reference-style link definitions [id]: url",
        "images ![alt](url)",
        "raw HTML tags (best-effort extraction)",
        "horizontal rules (--- *** ___)",
        "context helpers: extract_section / strip_prose_keep_structure / minify_markdown / safe_truncate",
    ],
    "conversion": [
        "link/image builders",
        "HTML <a>/<img> <-> Markdown link/image",
        "conservative html_to_markdown / markdown_to_html for common tags",
        "lightweight HtmlNode / parse_html_dom / dom_to_html / dom_to_markdown / markdown_to_dom",
        "GitHub / Qiita / Zenn / Obsidian alerts and callouts in markdown_to_html "
        "(shared <aside class=\"markdown-alert\"> HTML; alerts win over ordinary > quotes)",
        "ordinary > blockquotes in markdown_to_html (multi-line, blank > lines; "
        "inner ATX/lists/tables stay paragraph text)",
        "simple GFM pipe tables in markdown_to_html "
        "(header + | --- | separator + rows -> <table>/<thead>/<th>/<tbody>/<td>)",
        "strikethrough in markdown_to_html (~~text~~ -> <del>text</del>)",
        "GFM task lists in markdown_to_html "
        "(- [ ] / - [x] / - [X], also * and +; disabled checkbox <input>; mixed with ordinary <li> in one <ul>)",
        "angle-bracket autolinks in markdown_to_html "
        "(<https://...> / <http://...> -> <a href>; bare URLs stay literal)",
        ":::details summary containers in markdown_to_html "
        "(Zenn-style :::details ... ::: -> <details><summary>; raw HTML <details> stays escaped)",
        "GFM/Pandoc-like footnotes in markdown_to_html "
        "([^id] refs + [^id]: definitions -> <sup><a> + <section class=\"footnotes\">)",
        "simple HTML <table> in html_to_markdown (GFM pipe table; headerless rows use an empty header)",
        "HTML <del> -> ~~text~~ and <li><input type=checkbox> -> - [ ] / - [x] in html_to_markdown",
        "heading/paragraph id+class (+ other simple attrs) in html_to_markdown "
        "as Pandoc-style {#id .class key=\"value\"} so markdown_to_kramdown can attach IAL",
        "structured_to_markdown / markdown_to_structured for JSON-compatible Python data "
        "(typed canonical Markdown table; reusable by INI/TOML adapters)",
        "INI / TOML / dotenv <-> canonical structured Markdown adapters "
        "(semantic round-trip; source comments/spacing/quote style are canonicalized)",
        "markdown_to_kramdown: Pandoc/PHP-Extra {#id .class key=value} on headings/paragraphs "
        "-> Kramdown block IAL ({: #id .class key=\"value\"}); ordinary Markdown left alone",
        "kramdown_to_markdown: strip known heading/paragraph IAL back to plain Markdown "
        "(attributes dropped; {:toc} / {::extensions} / Liquid / front matter left as-is)",
        "alert_stylesheet / default_stylesheet (compact CSS strings for markdown_to_html output)",
        "markdown_to_web_ui_v1 (web-ui HTML contract v1 document wrapper; no CSS/runtime dependency)",
    ],
    "generation": [
        "heading / bold / italic / strikethrough / blockquote / horizontal_rule",
        "alert (GitHub > [!NOTE], Qiita :::note, Zenn :::message, Obsidian callouts; "
        "GitLab > [!note] generation)",
        "bullet_list / numbered_list / task_item / task_list",
        "details (Zenn :::details summary / body; markdown_to_html -> <details><summary>)",
        "footnote_ref / footnote ([^id] inline ref and [^id]: definition)",
        "inline_code / code_block / json_block",
        "mermaid_block / extract_mermaid_blocks (opaque Mermaid source only; no parsing/rendering)",
        "structural diagrams: headings -> Mermaid mindmap, task deps -> Mermaid flowchart, "
        "Python classes -> Mermaid classDiagram, Markdown links -> Graphviz DOT",
        "reference generators: inspect object -> API reference, argparse parser -> CLI reference, "
        "installed distribution metadata -> package reference",
        "table / key_value_table",
        "md_table / md_kv (*args-friendly wrappers, no list/dict pre-building needed)",
        "status_line",
        "section (heading + blocks) / wrap_section (tool-detectable markers)",
        "ial / with_attributes (Kramdown {: #id .class key=\"value\"} lines)",
    ],
}

UNSUPPORTED = {
    "parser": [
        "full CommonMark / GFM compliance",
        "backslash escaping (\\* stays literal, does not suppress emphasis)",
        "lazy blockquote continuation (a quoted paragraph must keep > on every line)",
        "nested blockquotes / inner block constructs inside > quotes "
        "(headings, lists, and tables inside a quote stay paragraph text; "
        "GitHub/Obsidian [!type] openers still render as <aside> and win over quotes)",
        "GitLab >>> multiline alert blockquotes (the > [!note] form is generated; "
        "title-less lowercase five-kind markers parse as Obsidian, not a separate GitLab flavor)",
        "nested alert/callout containers (Obsidian > > [!type], Zenn ::::details, Qiita nested :::)",
        "nested emphasis edge cases (asymmetric delimiter runs, whitespace-adjacent "
        "delimiters -- see fixtures/benchmark/commonmark_examples.yaml)",
        "GFM tables without a delimiter row of 3+ hyphens (header-only pipe lines "
        "stay paragraphs; alignment colons are accepted but not emitted as HTML attributes)",
        "html_to_markdown nested tables / colspan / rowspan / <caption> "
        "(nested tables flatten to cell text; extra spans are ignored; caption text is dropped)",
        "numbered-list task items (1. [ ] stays ordinary <li> text; only -/*/ + markers are tasks)",
        "raw HTML <details> in Markdown (escaped, not passed through; use details() / :::details)",
        "nested :::details / ::::details containers (the first ::: closes the block)",
        "footnote lazy continuation (unindented wrapping stays a new paragraph; "
        "only 2+ space / tab indented continuation is kept). Unused definitions are "
        "dropped. Undefined [^id] stays literal. Duplicate ids: first definition wins",
        "bare URL autolinks (https://example.com stays literal; only <https://...> / "
        "<http://...> and [text](url) become <a>)",
        "angle autolinks with schemes other than http/https (mailto:, ftp:, uppercase HTTP://)",
        "unmatched strikethrough (a lone ~~ stays literal; ~~a~~b~~ takes the first pair)",
        "Math / Mermaid rendering (Mermaid helpers only fence/extract opaque source)",
        "full Kramdown (extensions {::comment}/{::options}/{::nomarkdown}, math, "
        "TOC macros {:toc}, span IAL, IAL on lists/quotes/tables, attribute references)",
        "Liquid {% %} / {{ }}, YAML front matter, Jekyll tags / includes / baseurl",
    ],
    "conversion": [
        "lossy round-trips for complex nested HTML",
        "browser DOM / HTML5 tree-construction fidelity (HtmlNode is a small normalized tree)",
        "JavaScript / SVG behavior preservation",
        "CSS class and style fidelity (HTML style= is dropped; IAL class names are kept)",
        "raw inline HTML tags are escaped, not passed through, by markdown_to_html",
        "kramdown_to_markdown drops IAL attributes (lossy); markdown_to_html does not "
        "apply IAL as HTML id/class",
    ],
}

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^(?:\s*[-*_]){3,}\s*$")
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)$")
_INLINE_LINK_RE = re.compile(
    r"(?<!!)\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)"
)
_INLINE_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)"
)
_LINKED_IMAGE_RE = re.compile(
    r"\[(?:!\[[^\]]*\]\([^)]+\))\]\(([^)\s]+)(?:\s+\"([^\"]*)\")?\)"
)
_REF_DEF_RE = re.compile(
    r"^\s*\[([^\]]+)\]:\s*(\S+)(?:\s+\"([^\"]*)\")?\s*$"
)
_REF_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\[([^\]]*)\]")
_REF_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\[([^\]]+)\]")
_ANGLE_URL_RE = re.compile(r"<(https?://[^>\s]+)>")
_BARE_URL_RE = re.compile(r"(?<![\"'(\\[])(https?://[^\s)<>\"]+)")
_DATA_URI_RE = re.compile(r"(?<![A-Za-z0-9_-])data:([^,\s]*),([^\s]*)", re.IGNORECASE)
_DATA_URI_MEDIA_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._+-]*/[A-Za-z0-9._+-]+\Z")
_HTML_TAG_RE = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)\b[^>]*>", re.DOTALL)
_HTML_IMG_RE = re.compile(
    r"<img\b([^>]*)/?>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_A_RE = re.compile(
    r"<a\b([^>]*)>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(
    r"""([^\s=]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+))""",
    re.DOTALL,
)

# GitHub docs: https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#alerts
# Qiita cheat sheet (Note): https://qiita.com/Qiita/items/c686397e4a0f4f11683d
# Zenn Markdown guide (メッセージ): https://zenn.dev/zenn/articles/markdown-guide
# Obsidian Help (Callouts): https://help.obsidian.md/callouts
# GitLab GLFM alerts: https://docs.gitlab.com/ee/user/markdown/#alerts
ALERT_FLAVORS = ("github", "qiita", "zenn", "obsidian", "gitlab")
GITHUB_ALERT_KINDS = ("NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION")
QIITA_NOTE_KINDS = ("info", "warn", "alert")
ZENN_MESSAGE_KINDS = ("message", "alert")
_GITHUB_ALERT_KIND_SET = frozenset(GITHUB_ALERT_KINDS)
_QIITA_NOTE_KIND_SET = frozenset(QIITA_NOTE_KINDS)
_OBSIDIAN_KIND_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_BLOCKQUOTE_ALERT_RE = re.compile(
    r"^\s{0,3}>\s*\[!([A-Za-z][A-Za-z0-9_-]*)\]([+-]?)(?:[ \t]+(\S.*?))?[ \t]*$"
)
_BLOCKQUOTE_PREFIX_RE = re.compile(r"^\s{0,3}>( ?)?(.*)$")
_QIITA_NOTE_OPEN_RE = re.compile(
    r"^\s{0,3}:::note(?:\s+(info|warn|alert))?\s*$",
    re.IGNORECASE,
)
_ZENN_MESSAGE_OPEN_RE = re.compile(
    r"^\s{0,3}:::message(?:\s+(alert))?\s*$",
    re.IGNORECASE,
)
_DETAILS_OPEN_RE = re.compile(
    r"^\s{0,3}:::details(?:[ \t]+(.*))?\s*$",
    re.IGNORECASE,
)
_COLON_CONTAINER_CLOSE_RE = re.compile(r"^\s{0,3}:::\s*$")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:[ \t]?(.*)$")
_FOOTNOTE_CONT_RE = re.compile(r"^(?: {2,}|\t)(.*)$")
_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\]")
_TABLE_SEP_CELL_RE = re.compile(r"^:?-{3,}:?$")
_LIST_ITEM_RE = re.compile(r"^(\s*)(?:[-*+]|\d+\.)\s+")
_TASK_ITEM_RE = re.compile(r"^\[([ xX])\](?:[ \t]+(.*))?$")
_STRIKETHROUGH_RE = re.compile(r"~~((?:(?!~~)[^\n])+?)~~")
_IAL_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_IAL_NAME_RE = re.compile(r"^[^\s.#{}]+$")
_ATTR_LIST_TOKEN_RE = re.compile(
    r"#(?P<id>[^\s.#{}]+)"
    r"|\.(?P<cls>[^\s.#{}]+)"
    r"|(?P<key>[A-Za-z_][A-Za-z0-9_-]*)"
    r"(?:=(?:\"(?P<dval>[^\"]*)\"|'(?P<sval>[^']*)'|(?P<uval>[^\s{}]+)))?"
)
_STANDALONE_IAL_RE = re.compile(r"^\{:(?!:)[ \t]*(?P<inner>[^{}]*)\}\s*$")
_TRAILING_KRAMDOWN_IAL_RE = re.compile(
    r"^(?P<body>.*?)(?P<list>\{:(?!:)[ \t]*(?P<inner>[^{}]*)\})\s*$"
)
_TRAILING_PANDOC_ATTR_RE = re.compile(
    r"^(?P<body>.*?)(?P<list>\{(?![%{:])(?P<inner>[^{}]*)\})\s*$"
)
_HTML_ATTR_SKIP = frozenset({"id", "class", "style"})
_HOST_PORT_REFERENCE_RE = re.compile(
    r"^(?P<host>(?:localhost|(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+|(?:\d{1,3}\.){3}\d{1,3}|\[[0-9A-Fa-f:.]+\]))"
    r":(?P<port>\d{1,5})(?P<rest>(?:[/?#].*)?)$"
)


# === SECTION: scanner ===
# Shared lexical helpers. New format converters should use these helpers
# instead of re-implementing fence state or treating inline code as prose.

@dataclass(frozen=True)
class _ScannedLine:
    """One physical Markdown line with its code-context classification."""

    text: str
    in_fenced_code: bool
    is_fence_open: bool = False
    is_fence_close: bool = False


def _advance_fence(active_fence: str | None, line: str) -> tuple[str | None, bool, bool]:
    """Return next fence state, plus whether ``line`` opens or closes it."""
    match = _FENCE_RE.match(line)
    if active_fence is not None:
        if match and line.startswith(active_fence):
            return None, False, True
        return active_fence, False, False
    if match:
        return match.group(1), True, False
    return None, False, False


def _scan_lines(lines: list[str]) -> list[_ScannedLine]:
    """Classify lines as ordinary text or fenced-code context.

    This is deliberately lexical and dependency-free. It preserves the
    repository's existing ``_FENCE_RE`` contract.
    """
    active_fence: str | None = None
    scanned: list[_ScannedLine] = []
    for line in lines:
        next_fence, opened, closed = _advance_fence(active_fence, line)
        scanned.append(
            _ScannedLine(
                text=line,
                in_fenced_code=active_fence is not None or opened,
                is_fence_open=opened,
                is_fence_close=closed,
            )
        )
        active_fence = next_fence
    return scanned


def _mask_inline_code(text: str) -> str:
    """Replace balanced backtick code spans with spaces, preserving indexes.

    This conservative helper is for scanners/extractors, not an inline
    renderer. Unbalanced runs stay untouched; fenced code is handled by
    ``_scan_lines`` first.
    """
    chars = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`":
            index += 1
            continue
        end = index
        while end < len(text) and text[end] == "`":
            end += 1
        marker = text[index:end]
        close = text.find(marker, end)
        if close < 0:
            index = end
            continue
        for masked_index in range(index, close + len(marker)):
            chars[masked_index] = " "
        index = close + len(marker)
    return "".join(chars)


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def save_markdown(content: str, filepath: str) -> str:
    """Save Markdown content to a file."""
    try:
        path = Path(filepath).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"Error saving file: {e}"
    return f"Saved successfully: {path}"


def read_markdown(filepath: str, count_hashtags: bool = False) -> dict:
    """Read a Markdown file and optionally count heading ``#`` markers.

    Returns:
        dict with keys ``content`` (str), ``hashtag_count`` (int | None),
        ``success`` (bool).
    """
    result: dict[str, Any] = {
        "content": "",
        "hashtag_count": None,
        "success": False,
    }
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        result["content"] = content
        result["success"] = True
        if count_hashtags:
            total = 0
            for line in content.splitlines():
                match = re.match(r"^(#+)", line)
                if match:
                    total += len(match.group(1))
            result["hashtag_count"] = total
    except OSError as e:
        result["content"] = f"Error reading file: {e}"
    return result


def run_markdown_doctest(content: str, name: str = "<markdown>", globs: Any = None) -> doctest.TestResults:
    """Run Python doctest prompts found in fenced Markdown code blocks.

    Only Python-family fences participate. The examples are executed, so this
    helper is for trusted project documentation and test suites only.
    """
    source = _markdown_doctest_source(content)
    test = doctest.DocTestParser().get_doctest(
        source, dict(globs or {}), name, name, 0,
    )
    runner = doctest.DocTestRunner()
    runner.run(test, out=lambda _message: None)
    return doctest.TestResults(runner.failures, runner.tries)


def _markdown_doctest_source(content: str) -> str:
    """Keep Python fence contents while preserving Markdown line numbers.

    Fence state is supplied by the shared P0 scanner rather than a parallel
    fence parser. Fence info strings use their first token as the language.
    """
    lines = content.splitlines(keepends=True)
    scanned = _scan_lines([line.rstrip("\r\n") for line in lines])
    output: list[str] = []
    in_python = False
    for line, item in zip(lines, scanned):
        match = _FENCE_RE.match(item.text)
        if item.is_fence_open:
            info = match.group(2).strip() if match else ""
            language = info.split()[0].lower() if info else ""
            in_python = language in {"python", "python3", "py", "pycon"}
            output.append("\n" if line.endswith("\n") else "")
        elif item.is_fence_close:
            in_python = False
            output.append("\n" if line.endswith("\n") else "")
        elif in_python:
            output.append(item.text + ("\n" if line.endswith("\n") else ""))
        else:
            output.append("\n" if line.endswith("\n") else "")
    return "".join(output)

# ---------------------------------------------------------------------------
# Structure extraction
# ---------------------------------------------------------------------------

def extract_sections(content: str) -> list[dict[str, Any]]:
    """List ATX headings (``level`` + ``title``), without their body text.

    For heading-delimited sections that keep each section's body, use
    ``split_sections()`` instead.
    """
    sections: list[dict[str, Any]] = []
    for line in content.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            sections.append(
                {
                    "level": len(match.group(1)),
                    "title": match.group(2).strip(),
                }
            )
    return sections


def split_sections(content: str) -> list[dict[str, Any]]:
    """Split content into heading-delimited sections, each with its body text.

    Each item has ``level``, ``title``, and ``content`` (the heading line
    plus everything up to the next heading of any level). The prelude
    before the first heading is returned with ``level`` 0 and an empty
    ``title`` when it is non-empty. For a heading list without body text,
    use ``extract_sections()`` instead.
    """
    lines = content.splitlines(keepends=True)
    parts: list[dict[str, Any]] = []
    current = {"level": 0, "title": "", "content": ""}
    body: list[str] = []

    def flush() -> None:
        text = "".join(body)
        if current["level"] == 0 and current["title"] == "" and text.strip() == "":
            return
        item = dict(current)
        item["content"] = text
        parts.append(item)

    for line in lines:
        match = _HEADING_RE.match(line.rstrip("\n"))
        if match:
            flush()
            current = {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
                "content": "",
            }
            body = [line]
        else:
            body.append(line)
    flush()
    return parts


def _parse_attrs(attr_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for match in _ATTR_RE.finditer(attr_text):
        key = match.group(1).lower()
        value = match.group(2) or match.group(3) or match.group(4) or ""
        attrs[key] = html_module.unescape(value)
    return attrs


def _reference_map(content: str) -> dict[str, dict[str, str]]:
    refs: dict[str, dict[str, str]] = {}
    for line in content.splitlines():
        match = _REF_DEF_RE.match(line)
        if match:
            key = match.group(1).strip().lower()
            refs[key] = {
                "url": match.group(2).strip("<>"),
                "title": match.group(3) or "",
            }
    return refs


def extract_links(content: str) -> list[dict[str, Any]]:
    """Extract inline and reference-style links (not bare images)."""
    refs = _reference_map(content)
    links: list[dict[str, Any]] = []

    # Linked images: [![alt](img)](href) — record the outer link.
    for match in _LINKED_IMAGE_RE.finditer(content):
        links.append(
            {
                "text": "",
                "url": match.group(1),
                "title": match.group(2) or "",
                "style": "linked-image",
            }
        )

    # Mask constructs that would confuse the inline-link regex.
    masked = _LINKED_IMAGE_RE.sub(lambda m: " " * len(m.group(0)), content)
    masked = _INLINE_IMAGE_RE.sub(lambda m: " " * len(m.group(0)), masked)
    masked = _REF_IMAGE_RE.sub(lambda m: " " * len(m.group(0)), masked)

    for match in _INLINE_LINK_RE.finditer(masked):
        text = match.group(1)
        links.append(
            {
                "text": text,
                "url": match.group(2),
                "title": match.group(3) or "",
                "style": "inline",
            }
        )

    for match in _REF_LINK_RE.finditer(masked):
        text = match.group(1)
        key = (match.group(2) or text).strip().lower()
        ref = refs.get(key, {})
        links.append(
            {
                "text": text,
                "url": ref.get("url", ""),
                "title": ref.get("title", ""),
                "style": "reference",
                "ref": key,
            }
        )

    for match in _HTML_A_RE.finditer(content):
        attrs = _parse_attrs(match.group(1))
        href = attrs.get("href", "")
        if href:
            links.append(
                {
                    "text": re.sub(r"<[^>]+>", "", match.group(2)).strip(),
                    "url": href,
                    "title": attrs.get("title", ""),
                    "style": "html",
                }
            )
    return links


def extract_images(content: str) -> list[dict[str, Any]]:
    """Extract Markdown and HTML images."""
    refs = _reference_map(content)
    images: list[dict[str, Any]] = []

    for match in _INLINE_IMAGE_RE.finditer(content):
        images.append(
            {
                "alt": match.group(1),
                "url": match.group(2),
                "title": match.group(3) or "",
                "style": "inline",
            }
        )

    for match in _REF_IMAGE_RE.finditer(content):
        alt = match.group(1)
        key = match.group(2).strip().lower()
        ref = refs.get(key, {})
        images.append(
            {
                "alt": alt,
                "url": ref.get("url", ""),
                "title": ref.get("title", ""),
                "style": "reference",
                "ref": key,
            }
        )

    for match in _HTML_IMG_RE.finditer(content):
        attrs = _parse_attrs(match.group(1))
        src = attrs.get("src", "")
        if src:
            images.append(
                {
                    "alt": attrs.get("alt", ""),
                    "url": src,
                    "title": attrs.get("title", ""),
                    "style": "html",
                    "width": attrs.get("width"),
                    "height": attrs.get("height"),
                }
            )
    return images


def extract_code_blocks(content: str) -> list[dict[str, Any]]:
    """Extract fenced code blocks (``` or ~~~)."""
    blocks: list[dict[str, Any]] = []
    lines = content.splitlines()
    scanned = _scan_lines(lines)
    i = 0
    while i < len(lines):
        if not scanned[i].is_fence_open:
            i += 1
            continue
        match = _FENCE_RE.match(lines[i])
        assert match is not None  # guaranteed by _scan_lines
        fence = match.group(1)
        info = match.group(2).strip()
        lang = info.split()[0] if info else ""
        body: list[str] = []
        i += 1
        while i < len(lines) and not scanned[i].is_fence_close:
            body.append(lines[i])
            i += 1
        blocks.append(
            {
                "language": lang,
                "info": info,
                "code": "\n".join(body),
            }
        )
        if i < len(lines):
            i += 1
    return blocks


def extract_raw_html(content: str) -> list[dict[str, Any]]:
    """Best-effort list of raw HTML tags found in the document."""
    found: list[dict[str, Any]] = []
    for match in _HTML_TAG_RE.finditer(content):
        tag = match.group(1).lower()
        snippet = match.group(0)
        # Skip tags that appear inside fenced code by a cheap heuristic:
        # handled via inventory after code stripping when needed.
        found.append({"tag": tag, "snippet": snippet})
    return found


def extract_urls(content: str, *, base_url: str | None = None) -> list[str]:
    """Collect unique URLs from links, images, autolinks, and bare URLs."""
    urls: list[str] = []
    seen: set[str] = set()

    def add(url: str) -> None:
        url = url.strip()
        if not url:
            return
        if base_url:
            url = urljoin(base_url, url)
        if url not in seen:
            seen.add(url)
            urls.append(url)

    for item in extract_links(content):
        add(item.get("url", ""))
    for item in extract_images(content):
        add(item.get("url", ""))
    for match in _ANGLE_URL_RE.finditer(content):
        add(match.group(1))
    for match in _BARE_URL_RE.finditer(content):
        add(match.group(1).rstrip(".,;:)"))
    return urls


def extract_data_uris(content: str) -> list[dict[str, str]]:
    """List well-formed literal data URIs without decoding their payloads.

    The helper is observation-only: it does not fetch, decode, or execute
    a URI. A missing media type uses the RFC default ``text/plain``.
    Payload punctuation is preserved; only explicit surrounding delimiters
    and an unmatched Markdown closing parenthesis are removed.
    """
    found: list[dict[str, str]] = []
    for match in _DATA_URI_RE.finditer(content):
        metadata = match.group(1)
        parts = metadata.split(";") if metadata else []
        declared_type = parts[0].lower() if parts and parts[0] else ""
        if declared_type and not _DATA_URI_MEDIA_TYPE_RE.match(declared_type):
            continue
        if any(part and "=" not in part and part.lower() != "base64" for part in parts[1:]):
            continue
        uri = match.group(0).rstrip("\"'>")
        # Drop unmatched Markdown ")" chars and any prose punctuation
        # trailing *after* them (e.g. "...hello)." from "(data:...,hello).",
        # or "...hello))" from a prose paren wrapping a "(...)" link/image),
        # but keep payload punctuation that sits *before* them (e.g. the "!"
        # in "(data:...,Hello!)" is data, not a delimiter). Multiple stacked
        # wrappers can leave more than one unmatched ")" at the end, so cut
        # at the excess-th ")" from the right in the trailing run, not
        # always just the last one.
        trim = len(uri)
        while trim > 0 and uri[trim - 1] in ").,;:!?":
            trim -= 1
        tail = uri[trim:]
        paren_positions = [i for i, char in enumerate(tail) if char == ")"]
        excess = uri.count(")") - uri.count("(")
        if paren_positions and excess > 0:
            cut_at = paren_positions[-min(excess, len(paren_positions))]
            uri = uri[: trim + cut_at]
            # Removing a wrapping ")" can expose a quote/angle delimiter
            # that was only hidden behind it, e.g. "(<data:...,x>)".
            uri = uri.rstrip("\"'>")
        found.append({
            "uri": uri,
            "media_type": declared_type or "text/plain",
            "metadata": metadata,
        })
    return found


def inventory(content: str) -> dict[str, Any]:
    """Summarize common Markdown constructs present in ``content``."""
    sections = extract_sections(content)
    links = extract_links(content)
    images = extract_images(content)
    codes = extract_code_blocks(content)
    # Avoid counting HTML that only appears inside fenced code.
    scrubbed = content
    for block in codes:
        scrubbed = scrubbed.replace(block["code"], "")
    html_tags = extract_raw_html(scrubbed)
    hr_count = sum(1 for line in content.splitlines() if _HR_RE.match(line))
    return {
        "headings": sections,
        "heading_count": len(sections),
        "links": links,
        "link_count": len(links),
        "images": images,
        "image_count": len(images),
        "code_blocks": codes,
        "code_block_count": len(codes),
        "raw_html": html_tags,
        "raw_html_count": len(html_tags),
        "horizontal_rule_count": hr_count,
        "urls": extract_urls(content),
        "supported": SUPPORTED,
        "unsupported": UNSUPPORTED,
    }

def extract_section(
    content: str,
    heading_name: str,
    *,
    level: int | None = None,
    partial: bool = False,
) -> str:
    """Return one ATX heading section, including nested child headings.

    Matching is case-insensitive and exact by default. Set partial=True for a
    case-insensitive substring match, and level to restrict heading depth. The
    section ends at the next heading with a level less than or equal to the
    selected heading. A missing or empty heading name returns an empty string.
    """
    wanted = str(heading_name).strip()
    if not wanted:
        return ""

    selected_start: int | None = None
    selected_level: int | None = None
    lines = content.splitlines(keepends=True)

    for index, line in enumerate(lines):
        match = _HEADING_RE.match(line.rstrip("\r\n"))
        if not match:
            continue
        current_level = len(match.group(1))
        title = match.group(2).strip()
        if level is not None and current_level != level:
            continue
        normalized_title = title.casefold()
        normalized_wanted = wanted.casefold()
        matched = (
            normalized_wanted in normalized_title
            if partial
            else normalized_title == normalized_wanted
        )
        if matched:
            selected_start = index
            selected_level = current_level
            break

    if selected_start is None or selected_level is None:
        return ""

    selected_end = len(lines)
    for index in range(selected_start + 1, len(lines)):
        match = _HEADING_RE.match(lines[index].rstrip("\r\n"))
        if match and len(match.group(1)) <= selected_level:
            selected_end = index
            break

    result = "".join(lines[selected_start:selected_end])
    if result and not result.endswith(("\n", "\r")):
        result += "\n"
    return result


def strip_prose_keep_structure(content: str) -> str:
    """Keep Markdown structure while dropping ordinary prose lines.

    Headings, lists, blockquotes, thematic breaks, and complete fenced code
    blocks are preserved verbatim. Lines inside a fenced block are always
    retained, including prose-looking lines. This is a deterministic
    extraction heuristic, not a summarizer.
    """
    kept: list[str] = []
    active_fence: str | None = None

    for line in content.splitlines():
        fence = _FENCE_RE.match(line)
        if active_fence is not None:
            kept.append(line)
            if fence and line.startswith(active_fence):
                active_fence = None
            continue

        if fence:
            kept.append(line)
            active_fence = fence.group(1)
            continue

        if not line.strip():
            if kept and kept[-1] != "":
                kept.append("")
            continue

        if (
            _HEADING_RE.match(line)
            or _HR_RE.match(line)
            or re.match(r"^\s*(?:[-+*]\s+|\d+[.)]\s+|>)", line)
        ):
            kept.append(line)

    while kept and kept[-1] == "":
        kept.pop()

    if not kept:
        return ""
    result = "\n".join(kept)
    return result + ("\n" if content.endswith(("\n", "\r")) else "")


def minify_markdown(content: str, strip_html: bool = True) -> str:
    """Apply conservative physical Markdown minification.

    When strip_html is true, HTML comments are removed. Three or more
    consecutive newlines are reduced to two, and surrounding whitespace is
    stripped. No Markdown parsing or semantic conversion is performed.
    """
    if strip_html:
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return re.sub(r"\n{3,}", "\n\n", content).strip()


def safe_truncate(content: str, max_chars: int) -> str:
    """Truncate to max_chars while closing an open fenced code block.

    The length limit is hard: when there is enough room, a matching closing
    fence is appended within the limit. If the limit is too small to retain
    both the prefix and a closing fence, the raw prefix is returned.
    ValueError is raised for a negative limit.
    """
    if max_chars < 0:
        raise ValueError("max_chars must be non-negative")
    if len(content) <= max_chars:
        return content

    prefix = content[:max_chars]
    active_fence: str | None = None
    for line in prefix.splitlines():
        match = _FENCE_RE.match(line)
        if not match:
            continue
        marker = match.group(1)
        if active_fence is None:
            active_fence = marker
        elif line.startswith(active_fence):
            active_fence = None

    if active_fence is None:
        return prefix

    suffix = ("" if prefix.endswith(("\n", "\r")) else "\n") + active_fence
    if len(suffix) > max_chars:
        return prefix
    return prefix[: max_chars - len(suffix)] + suffix


# ---------------------------------------------------------------------------
# Builders & focused HTML <-> Markdown helpers
# ---------------------------------------------------------------------------

def make_link(text: str, url: str, title: str | None = None) -> str:
    """Build a Markdown inline link."""
    if title:
        return f'[{text}]({url} "{title}")'
    return f"[{text}]({url})"


def make_image(alt: str, url: str, title: str | None = None) -> str:
    """Build a Markdown image."""
    if title:
        return f'![{alt}]({url} "{title}")'
    return f"![{alt}]({url})"


def html_image_to_markdown(html: str) -> str:
    """Convert an ``<img>`` tag (or HTML snippet containing one) to Markdown."""
    match = _HTML_IMG_RE.search(html)
    if not match:
        return ""
    attrs = _parse_attrs(match.group(1))
    return make_image(attrs.get("alt", ""), attrs.get("src", ""), attrs.get("title") or None)


def markdown_image_to_html(
    markdown: str,
    *,
    width: str | None = None,
    height: str | None = None,
) -> str:
    """Convert a Markdown image (or image URL string) to an ``<img>`` tag."""
    match = _INLINE_IMAGE_RE.search(markdown.strip())
    if match:
        alt, url, title = match.group(1), match.group(2), match.group(3) or ""
    else:
        # Treat bare path/URL as image source.
        alt, url, title = "", markdown.strip(), ""
    safe_url = _sanitize_url_scheme(url)
    if not safe_url:
        return html_module.escape(alt)
    attrs = [
        f'src="{html_module.escape(safe_url, quote=True)}"',
        f'alt="{html_module.escape(alt, quote=True)}"',
    ]
    if title:
        attrs.append(f'title="{html_module.escape(title, quote=True)}"')
    if width:
        attrs.append(f'width="{html_module.escape(width, quote=True)}"')
    if height:
        attrs.append(f'height="{html_module.escape(height, quote=True)}"')
    return "<img " + " ".join(attrs) + " />"


def html_link_to_markdown(html: str) -> str:
    """Convert an ``<a>...</a>`` tag to a Markdown link."""
    match = _HTML_A_RE.search(html)
    if not match:
        return ""
    attrs = _parse_attrs(match.group(1))
    text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
    return make_link(text, attrs.get("href", ""), attrs.get("title") or None)


def markdown_link_to_html(markdown: str) -> str:
    """Convert a Markdown inline link to an ``<a>`` tag."""
    match = _INLINE_LINK_RE.search(markdown.strip())
    if not match:
        return ""
    text, url, title = match.group(1), match.group(2), match.group(3) or ""
    safe_url = _sanitize_url_scheme(url)
    if not safe_url:
        return html_module.escape(text)
    attrs = [f'href="{html_module.escape(safe_url, quote=True)}"']
    if title:
        attrs.append(f'title="{html_module.escape(title, quote=True)}"')
    return f"<a {' '.join(attrs)}>{html_module.escape(text)}</a>"


# ---------------------------------------------------------------------------
# Markdown generation building blocks
# ---------------------------------------------------------------------------

def heading(text: str, level: int = 1) -> str:
    """Build an ATX heading (``level`` is clamped to 1-6).

    >>> heading("Title")
    '# Title\\n'
    >>> heading("Sub", level=2)
    '## Sub\\n'
    """
    level = max(1, min(level, 6))
    return "#" * level + " " + str(text) + "\n"


def bold(text: str) -> str:
    """Wrap ``text`` in ``**bold**`` markers."""
    return f"**{text}**"


def italic(text: str) -> str:
    """Wrap ``text`` in ``*italic*`` markers."""
    return f"*{text}*"


def strikethrough(text: str) -> str:
    """Wrap ``text`` in ``~~strikethrough~~`` markers.

    ``markdown_to_html()`` turns this into ``<del>``. Unmatched ``~~``
    stays literal; a run like ``~~a~~b~~`` takes the first pair.
    """
    return f"~~{text}~~"


def blockquote(text: str) -> str:
    """Prefix every line of ``text`` with ``> `` to form a blockquote.

    ``markdown_to_html()`` turns this into ``<blockquote>``. Blank lines
    become blank ``>`` lines and split paragraphs. A ``> [!TYPE]`` opener
    is an alert, not a quote.
    """
    lines = str(text).splitlines() or [""]
    return "\n".join(f"> {line}" if line else ">" for line in lines) + "\n"


def _normalize_alert_flavor(flavor: str) -> str:
    name = str(flavor).strip().lower()
    if name not in ALERT_FLAVORS:
        raise ValueError(
            f"unknown alert flavor {flavor!r}; expected one of {ALERT_FLAVORS}"
        )
    return name


def _colon_container(open_line: str, text: str) -> str:
    body = str(text)
    if body and not body.endswith("\n"):
        body += "\n"
    return f"{open_line}\n{body}:::\n"


def _blockquote_alert_markdown(marker: str, text: str) -> str:
    body = str(text)
    if not body:
        return marker + "\n"
    return marker + "\n" + blockquote(body)


def alert(
    kind: str,
    text: str = "",
    *,
    flavor: str = "github",
    title: str | None = None,
    fold: str | None = None,
) -> str:
    """Build a site-flavored Markdown alert / callout / note block.

    ``flavor`` selects the syntax (default GitHub). ``kind`` is
    case-insensitive for the fixed vocabularies; unknown kinds raise
    ``ValueError`` except Obsidian, which allows custom type identifiers
    (Obsidian itself falls unknown types back to ``note`` visually).

    GitHub (docs.github.com, Alerts)::

        > [!NOTE]
        > Useful information that users should know

    Kinds: ``NOTE``, ``TIP``, ``IMPORTANT``, ``WARNING``, ``CAUTION``.
    Emitted uppercase. Same-line titles and fold markers are not part of
    GitHub's syntax and raise ``ValueError``.

    Qiita (qiita.com/Qiita/items/c686397e4a0f4f11683d, Note)::

        :::note info
        インフォメーション
        :::

    Kinds: ``info`` (also ``note``), ``warn``, ``alert``. ``info`` is
    optional in Qiita's parser; this helper emits ``:::note info`` for
    the info kind so the type is explicit.

    Zenn (zenn.dev/zenn/articles/markdown-guide, メッセージ)::

        :::message
        メッセージをここに
        :::

        :::message alert
        警告メッセージをここに
        :::

    Kinds: ``message`` (also ``info`` / empty) or ``alert``.

    Obsidian (help.obsidian.md/callouts)::

        > [!note]
        > body

        > [!warning] Custom title
        > body

    Kind identifiers are emitted lowercase. Optional ``title`` is written
    on the marker line. Optional ``fold`` is ``+`` (expanded) or ``-``
    (collapsed), immediately after ``[!type]``. Custom types matching
    ``[A-Za-z][A-Za-z0-9_-]*`` are allowed.

    GitLab (docs.gitlab.com, GLFM Alerts) is generation-only: the same
    five kinds as GitHub, emitted lowercase, with optional ``title``.
    GitLab's ``>>>`` multiline blockquote alerts are not generated.
    Parsed title-less lowercase five-kind markers are classified as
    Obsidian (see ``markdown_to_html``); uppercase title-less five-kind
    markers are classified as GitHub.

    Multi-line ``text``: GitHub/Obsidian/GitLab prefix each line with
    ``> `` (blank lines become ``>``); Qiita/Zenn keep the body verbatim
    between the opening and closing ``:::``.
    """
    flavor_name = _normalize_alert_flavor(flavor)
    if fold is not None and fold not in {"+", "-"}:
        raise ValueError("fold must be '+' or '-' when set")
    if title is not None:
        title = str(title)
    kind_raw = str(kind).strip()

    if flavor_name == "github":
        if title is not None:
            raise ValueError("GitHub alerts do not support a same-line title")
        if fold is not None:
            raise ValueError("GitHub alerts do not support Obsidian fold markers")
        canonical = kind_raw.upper()
        if canonical not in _GITHUB_ALERT_KIND_SET:
            raise ValueError(
                f"unknown GitHub alert kind {kind!r}; "
                f"expected one of {GITHUB_ALERT_KINDS}"
            )
        return _blockquote_alert_markdown(f"> [!{canonical}]", text)

    if flavor_name == "gitlab":
        if fold is not None:
            raise ValueError("GitLab alerts do not support Obsidian fold markers")
        canonical = kind_raw.upper()
        if canonical not in _GITHUB_ALERT_KIND_SET:
            raise ValueError(
                f"unknown GitLab alert kind {kind!r}; "
                f"expected one of {GITHUB_ALERT_KINDS}"
            )
        marker = f"> [!{canonical.lower()}]"
        if title:
            marker += f" {title}"
        return _blockquote_alert_markdown(marker, text)

    if flavor_name == "qiita":
        if title is not None or fold is not None:
            raise ValueError("Qiita notes do not support title= or fold=")
        qiita_kind = kind_raw.lower()
        if qiita_kind in {"", "note"}:
            qiita_kind = "info"
        if qiita_kind not in _QIITA_NOTE_KIND_SET:
            raise ValueError(
                f"unknown Qiita note kind {kind!r}; "
                f"expected one of {QIITA_NOTE_KINDS}"
            )
        return _colon_container(f":::note {qiita_kind}", text)

    if flavor_name == "zenn":
        if title is not None or fold is not None:
            raise ValueError("Zenn messages do not support title= or fold=")
        zenn_kind = kind_raw.lower()
        if zenn_kind in {"", "message", "info"}:
            return _colon_container(":::message", text)
        if zenn_kind == "alert":
            return _colon_container(":::message alert", text)
        raise ValueError(
            f"unknown Zenn message kind {kind!r}; "
            f"expected one of {ZENN_MESSAGE_KINDS}"
        )

    # obsidian
    if not _OBSIDIAN_KIND_RE.fullmatch(kind_raw):
        raise ValueError(
            f"invalid Obsidian callout type {kind!r}; "
            "expected a letter followed by letters, digits, '_' or '-'"
        )
    fold_mark = fold or ""
    marker = f"> [!{kind_raw.lower()}]{fold_mark}"
    if title:
        marker += f" {title}"
    return _blockquote_alert_markdown(marker, text)


def horizontal_rule() -> str:
    """Return a thematic break (``---``)."""
    return "---\n"


def bullet_list(items: Any) -> str:
    """Build an unordered (``-``) list from an iterable of strings."""
    lines = [f"- {item}" for item in items]
    return "\n".join(lines) + ("\n" if lines else "")


def numbered_list(items: Any) -> str:
    """Build an ordered (``1.``) list from an iterable of strings."""
    lines = [f"{i}. {item}" for i, item in enumerate(items, start=1)]
    return "\n".join(lines) + ("\n" if lines else "")


def task_item(text: str = "", *, checked: bool = False) -> str:
    """Build one GFM task-list line (``- [ ] text`` / ``- [x] text``).

    ``markdown_to_html()`` turns this into a ``<ul>`` item with a
    disabled checkbox (``checked`` when ``checked`` is true). The box
    is not interactive.
    """
    mark = "x" if checked else " "
    body = str(text)
    if body:
        return f"- [{mark}] {body}\n"
    return f"- [{mark}]\n"


def task_list(items: Any) -> str:
    """Build a GFM task list from strings or ``(text, checked)`` pairs.

    A bare string is an unchecked item. Empty ``items`` yields ``""``.
    Mixed task and ordinary bullets in one source list stay one ``<ul>``
    with mixed ``<li>`` shapes (see ``markdown_to_html``).
    """
    lines: list[str] = []
    for item in items:
        if isinstance(item, (tuple, list)):
            if len(item) >= 2:
                text, checked = item[0], bool(item[1])
            elif len(item) == 1:
                text, checked = item[0], False
            else:
                text, checked = "", False
            lines.append(task_item(text, checked=checked).rstrip("\n"))
        else:
            lines.append(task_item(item, checked=False).rstrip("\n"))
    return "\n".join(lines) + ("\n" if lines else "")


def details(summary: str, body: str = "") -> str:
    """Build a collapsible section using Zenn's ``:::details`` form.

    ``markdown_to_html()`` turns this into ``<details><summary>…</summary>…``.
    Summary and body inlines (bold / italic / code / links) are parsed; nested
    block constructs inside the body stay paragraph text (small contract).
    Raw HTML ``<details>`` in Markdown input stays escaped — this helper is
    the supported way to emit the element.

    Nested ``:::details`` / ``::::details`` is unsupported: the first ``:::``
    closer ends the block.
    """
    summary_line = str(summary).replace("\n", " ").strip()
    opener = f":::details {summary_line}" if summary_line else ":::details"
    body_text = str(body)
    if not body_text.strip():
        return f"{opener}\n:::\n"
    if not body_text.endswith("\n"):
        body_text += "\n"
    return f"{opener}\n{body_text}:::\n"


def footnote_ref(ident: str) -> str:
    """Build an inline footnote reference (``[^id]``).

    ``markdown_to_html()`` turns a defined ref into a superscript link.
    Undefined ids stay literal (documented degrade).
    """
    return f"[^{ident}]"


def footnote(ident: str, text: str = "") -> str:
    """Build a footnote definition line (``[^id]: text``).

    Pair with :func:`footnote_ref` (or a hand-written ``[^id]``) in the
    body. Duplicate ids: first definition wins. Unused definitions are
    dropped from HTML. Continuation lines may be indented with 2+ spaces
    or a tab; unindented wrapping is a new paragraph, not a continuation.
    """
    return f"[^{ident}]: {text}\n"


def inline_code(text: str) -> str:
    """Wrap ``text`` in single backticks for inline code."""
    return f"`{text}`"


_FENCE_CHARS = ("`", "~")


def _adaptive_fence(code: str, fence_char: str = "`") -> str:
    """A fence of ``fence_char`` one longer than the longest run already in ``code``.

    ``_FENCE_RE`` (and this module's own fence-closing scan) accept any
    length-3-or-more fence, but only close on a line starting with a run of
    the same fence character at least as long as the opening fence -- so a
    fixed triple-backtick fence is ambiguous the moment ``code`` itself
    contains a triple-backtick run (e.g. Markdown source shown as an example
    inside a code block). Picking a fence longer than anything already in
    ``code`` keeps that scan unambiguous with no changes to the reading side.

    ``fence_char`` must be a single backtick or tilde -- the only two
    characters Markdown recognizes as a fence at all (``_FENCE_RE``). Any
    other value raises ``ValueError`` rather than silently building a fence
    nothing would ever close (a multi-character ``fence_char`` isn't a valid
    fence line, and an empty one breaks the run-length regex outright).
    """
    if fence_char not in _FENCE_CHARS:
        raise ValueError(f"fence_char must be one of {_FENCE_CHARS!r}, got {fence_char!r}")
    longest = 0
    for run in re.findall(re.escape(fence_char) + r"+", code):
        longest = max(longest, len(run))
    return fence_char * max(3, longest + 1)


def code_block(code: str, lang: str = "", *, fence_char: str = "`") -> str:
    """Wrap ``code`` in a fenced code block, optionally tagged with ``lang``.

    The fence length adapts to ``code``'s content: if it already contains a
    run of ``fence_char`` as long as (or longer than) a plain triple fence
    -- typically Markdown-inside-Markdown, like a fenced example embedded in
    a doc -- the fence grows just enough to stay unambiguous, the same way
    CommonMark itself requires. Plain content keeps the original triple
    fence, so existing callers see no change. Pass ``fence_char="~"`` for a
    tilde fence (e.g. when ``code`` itself contains backtick runs).

    :raises ValueError: if ``fence_char`` isn't ``"`"`` or ``"~"`` -- the
        only two characters Markdown recognizes as a fence.
    """
    fence = _adaptive_fence(code, fence_char)
    return f"{fence}{lang}\n{code}\n{fence}\n"


def mermaid_block(source: str, *, fence_char: str = "`") -> str:
    """Wrap opaque Mermaid source in a safe ``mermaid`` fenced block.

    Line endings are normalized to LF. Mermaid syntax is not parsed or
    validated, and no renderer, browser, JavaScript runtime, or I/O is used.
    """
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    return code_block(normalized, lang="mermaid", fence_char=fence_char)


def extract_mermaid_blocks(content: str) -> list[str]:
    """Return Mermaid fenced-block sources in document order.

    The info-string language match is case-insensitive and must be exactly
    ``mermaid`` as its first token. Non-Mermaid fences and inline code are
    ignored. Returned line endings follow the module-wide LF convention.
    """
    return [
        block["code"]
        for block in extract_code_blocks(content)
        if block["language"].lower() == "mermaid"
    ]


def _diagram_label(text: Any) -> str:
    """Escape a label for quoted Mermaid/DOT output."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _live_markdown_lines(content: str) -> list[tuple[str, str]]:
    """Return ``(raw, inline-masked)`` lines outside fenced code."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    scanned = _scan_lines(lines)
    result: list[tuple[str, str]] = []
    for line, item in zip(lines, scanned):
        if item.in_fenced_code:
            continue
        result.append((line, _mask_inline_code(line)))
    return result


def markdown_headings_to_mermaid_mindmap(content: str, *, root: str = "Document") -> str:
    """Generate deterministic Mermaid mindmap source from live ATX headings."""
    headings: list[tuple[int, str]] = []
    for raw, masked in _live_markdown_lines(content):
        match = _HEADING_RE.match(masked)
        if match:
            headings.append((len(match.group(1)), raw[len(match.group(1)):].strip()))

    out = ["mindmap", f'  root["{_diagram_label(root)}"]']
    stack: list[tuple[int, str]] = []
    for index, (level, title) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        depth = len(stack) + 2
        node_id = f"n{index}"
        out.append("  " * depth + f'{node_id}["{_diagram_label(title)}"]')
        stack.append((level, node_id))
    return "\n".join(out) + "\n"


_TASK_DEP_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(.+?)(?:\s+<-\s+(.+))?\s*$")


def markdown_tasks_to_mermaid_flowchart(content: str) -> str:
    """Generate Mermaid flowchart source from narrow GFM task dependencies.

    Syntax: ``- [ ] Deploy <- Build, Test`` means Deploy depends on Build and
    Test. Every referenced dependency must also appear as a task item.
    """
    tasks: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for raw, masked in _live_markdown_lines(content):
        match = _TASK_DEP_RE.match(masked)
        if not match:
            continue
        name = raw[match.start(1):match.end(1)].strip()
        deps_text = match.group(2)
        if " <- " in name:
            name = name.split(" <- ", 1)[0].rstrip()
        if not name or name in seen:
            raise ValueError(f"Task names must be unique and non-empty: {name!r}")
        seen.add(name)
        deps = [part.strip() for part in deps_text.split(",")] if deps_text else []
        if any(not dep for dep in deps):
            raise ValueError(f"Empty dependency for task {name!r}")
        tasks.append((name, deps))

    names = {name for name, _ in tasks}
    missing = sorted({dep for _, deps in tasks for dep in deps if dep not in names})
    if missing:
        raise ValueError("Unknown task dependencies: " + ", ".join(missing))

    graph = {name: set(deps) for name, deps in tasks}
    try:
        tuple(graphlib.TopologicalSorter(graph).static_order())
    except graphlib.CycleError as exc:
        raise ValueError("Task dependency cycle detected") from exc

    ids = {name: f"n{index}" for index, (name, _) in enumerate(tasks)}
    out = ["flowchart TD"]
    for name, _ in tasks:
        out.append(f'  {ids[name]}["{_diagram_label(name)}"]')
    for name, deps in tasks:
        for dep in deps:
            out.append(f"  {ids[dep]} --> {ids[name]}")
    return "\n".join(out) + "\n"


def _ast_base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _ast_base_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def python_to_mermaid_class_diagram(source: str) -> str:
    """Generate Mermaid ``classDiagram`` source from Python class structure."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"Invalid Python source: {exc}") from exc

    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    known_names = [node.name for node in classes]
    external_bases: list[str] = []
    for node in classes:
        for base in node.bases:
            name = _ast_base_name(base)
            if name and name not in known_names and name not in external_bases:
                external_bases.append(name)

    ids: dict[str, str] = {}
    for index, name in enumerate(known_names + external_bases):
        ids[name] = f"c{index}"

    out = ["classDiagram"]
    for node in classes:
        class_id = ids[node.name]
        out.append(f'  class {class_id}["{_diagram_label(node.name)}"] {{')
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in item.args.args]
                if args and args[0] in {"self", "cls"}:
                    args = args[1:]
                out.append(f"    {item.name}({', '.join(args)})")
        out.append("  }")
    for name in external_bases:
        out.append(f'  class {ids[name]}["{_diagram_label(name)}"]')
    for node in classes:
        for base in node.bases:
            name = _ast_base_name(base)
            if name:
                out.append(f"  {ids[name]} <|-- {ids[node.name]}")
    return "\n".join(out) + "\n"


def markdown_links_to_dot(content: str) -> str:
    """Generate a deterministic DOT link graph grouped by current heading.

    Links before the first heading belong to ``Document``. If a syntactically
    matched ATX heading becomes empty after stripping, that section also falls
    back to ``Document`` instead of creating an empty node label.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    scanned = _scan_lines(lines)
    current = "Document"
    edges: list[tuple[str, str, str]] = []
    refs = _reference_map(normalized)
    for line, item in zip(lines, scanned):
        if item.in_fenced_code:
            continue
        masked = _mask_inline_code(line)
        heading_match = _HEADING_RE.match(masked)
        if heading_match:
            current = line[len(heading_match.group(1)):].strip() or "Document"
            continue
        safe = _INLINE_IMAGE_RE.sub(lambda m: " " * len(m.group(0)), masked)
        for match in _INLINE_LINK_RE.finditer(safe):
            edges.append((current, match.group(2), match.group(1)))
        for match in _REF_LINK_RE.finditer(safe):
            text_value = match.group(1)
            key = (match.group(2) or text_value).strip().lower()
            target = refs.get(key, {}).get("url", "")
            if target:
                edges.append((current, target, text_value))

    sources: list[str] = []
    targets: list[str] = []
    for source, target, _ in edges:
        if source not in sources:
            sources.append(source)
        if target not in targets:
            targets.append(target)
    source_ids = {name: f"s{i}" for i, name in enumerate(sources)}
    target_ids = {url: f"u{i}" for i, url in enumerate(targets)}

    out = ["digraph markdown_links {"]
    for name in sources:
        out.append(f'  {source_ids[name]} [label="{_diagram_label(name)}"];')
    for url in targets:
        out.append(f'  {target_ids[url]} [label="{_diagram_label(url)}"];')
    for source, target, label in edges:
        out.append(
            f'  {source_ids[source]} -> {target_ids[target]} [label="{_diagram_label(label)}"];'
        )
    out.append("}")
    return "\n".join(out) + "\n"


def _reference_summary(value: Any) -> str:
    """Return the first non-empty documentation line for a known object."""
    try:
        doc = inspect.getdoc(value) or ""
    except (AttributeError, TypeError):
        return ""
    return next((line.strip() for line in doc.splitlines() if line.strip()), "")


def _reference_signature(value: Any) -> str:
    """Return a stable signature when ``inspect.signature`` supports value."""
    try:
        return str(inspect.signature(value))
    except (TypeError, ValueError):
        return ""


def _reference_member(value: Any) -> Any:
    """Unwrap class/static methods without invoking descriptors."""
    if isinstance(value, (classmethod, staticmethod)):
        return value.__func__
    return value


def inspect_to_markdown(obj: Any, *, title: str | None = None) -> str:
    """Generate a small API reference for an already-provided Python object.

    Module/class members are read from ``vars()`` so properties and other
    descriptors are not invoked. No module discovery or dynamic import occurs.
    """
    if inspect.ismodule(obj):
        kind = "module"
    elif inspect.isclass(obj):
        kind = "class"
    elif inspect.isfunction(obj):
        kind = "function"
    elif inspect.ismethod(obj):
        kind = "method"
    elif inspect.isbuiltin(obj):
        kind = "builtin"
    else:
        kind = type(obj).__name__

    name = getattr(obj, "__qualname__", None) or getattr(obj, "__name__", None) or type(obj).__name__
    module_name = getattr(obj, "__module__", "") or ""
    doc = inspect.getdoc(obj) or ""
    output = [heading(title or f"API: {name}")]
    metadata_rows = [["Name", name], ["Kind", kind]]
    if module_name:
        metadata_rows.append(["Module", module_name])
    signature = _reference_signature(obj)
    if signature:
        metadata_rows.append(["Signature", signature])
    output.append(table(["Field", "Value"], metadata_rows))
    if doc:
        output.append(heading("Description", 2))
        output.append(doc.rstrip() + "\n")

    members: list[list[str]] = []
    if inspect.ismodule(obj) or inspect.isclass(obj):
        owner_module = getattr(obj, "__name__", "") if inspect.ismodule(obj) else ""
        for member_name, raw_value in sorted(vars(obj).items()):
            if member_name.startswith("_"):
                continue
            value = _reference_member(raw_value)
            if not (inspect.isfunction(value) or inspect.isclass(value) or inspect.isbuiltin(value)):
                continue
            if owner_module and getattr(value, "__module__", owner_module) != owner_module:
                continue
            member_kind = "class" if inspect.isclass(value) else "function"
            members.append([
                member_name,
                member_kind,
                _reference_signature(value),
                _reference_summary(value),
            ])
    if members:
        output.append(heading("Public API", 2))
        output.append(table(["Name", "Kind", "Signature", "Summary"], members))
    return "\n".join(part.rstrip("\n") for part in output if part) + "\n"


def _argparse_value(value: Any) -> str:
    """Render argparse metadata without unstable object reprs."""
    if value == argparse.SUPPRESS:
        return "SUPPRESS"
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(_argparse_value(item) for item in value)
    return type(value).__name__


def _argparse_type_name(value: Any) -> str:
    """Return a compact, stable display name for an argparse ``type`` value."""
    if value is None:
        return ""
    name = getattr(value, "__name__", None)
    if name:
        return str(name)
    return type(value).__name__


def _argparse_action_name(action: argparse.Action) -> str:
    """Normalize common argparse action classes to user-facing action names."""
    mapping = {
        "_StoreAction": "store",
        "_StoreConstAction": "store_const",
        "_StoreTrueAction": "store_true",
        "_StoreFalseAction": "store_false",
        "_AppendAction": "append",
        "_AppendConstAction": "append_const",
        "_CountAction": "count",
        "_HelpAction": "help",
        "_VersionAction": "version",
        "BooleanOptionalAction": "boolean_optional",
    }
    return mapping.get(action.__class__.__name__, action.__class__.__name__.lstrip("_"))


def argparse_to_markdown(parser: argparse.ArgumentParser, *, title: str | None = None) -> str:
    """Generate deterministic CLI reference Markdown from an ArgumentParser.

    The parser is never executed. Reading ``_actions`` is the only intentional
    narrow dependency on argparse private state; public parser metadata and
    ``format_usage()`` are used otherwise. Type, metavar, and common action
    kinds are rendered as stable descriptive names rather than object reprs.
    """
    if not isinstance(parser, argparse.ArgumentParser):
        raise TypeError("parser must be an argparse.ArgumentParser")

    output = [heading(title or f"CLI: {parser.prog}")]
    if parser.description:
        output.append(str(parser.description).rstrip() + "\n")
    usage = parser.format_usage().strip()
    if usage:
        output.append(heading("Usage", 2))
        output.append(code_block(usage, lang="text"))

    argument_rows: list[list[str]] = []
    subcommands: list[list[str]] = []
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            for command, child in sorted(action.choices.items()):
                subcommands.append([command, child.description or ""])
            continue
        if action.dest == argparse.SUPPRESS:
            continue
        label = ", ".join(action.option_strings) if action.option_strings else action.dest
        choices = ""
        if action.choices is not None:
            try:
                choices = ", ".join(str(choice) for choice in action.choices)
            except TypeError:
                choices = _argparse_value(action.choices)
        argument_rows.append([
            label,
            "yes" if action.required else "no",
            _argparse_value(action.nargs),
            choices,
            _argparse_value(action.default),
            _argparse_type_name(action.type),
            _argparse_value(action.metavar),
            _argparse_action_name(action),
            "" if action.help == argparse.SUPPRESS else str(action.help or ""),
        ])

    if argument_rows:
        output.append(heading("Arguments", 2))
        output.append(table(
            ["Argument", "Required", "Nargs", "Choices", "Default", "Type", "Metavar", "Action", "Help"],
            argument_rows,
        ))
    if subcommands:
        output.append(heading("Subcommands", 2))
        output.append(table(["Command", "Description"], subcommands))
    if parser.epilog:
        output.append(heading("Epilog", 2))
        output.append(str(parser.epilog).rstrip() + "\n")
    return "\n".join(part.rstrip("\n") for part in output if part) + "\n"


def distribution_to_markdown(name: str, *, title: str | None = None) -> str:
    """Generate package metadata Markdown for an installed distribution."""
    if not str(name).strip():
        raise ValueError("distribution name must be non-empty")
    try:
        dist = importlib_metadata.distribution(str(name))
    except importlib_metadata.PackageNotFoundError as exc:
        raise ValueError(f"Distribution not found: {name}") from exc

    metadata = dist.metadata
    package_name = metadata.get("Name") or str(name)
    output = [heading(title or f"Package: {package_name}")]
    fields = [
        ("Name", package_name),
        ("Version", dist.version),
        ("Summary", metadata.get("Summary", "")),
        ("Requires-Python", metadata.get("Requires-Python", "")),
        ("License", metadata.get("License", "")),
        ("Author", metadata.get("Author", "")),
        ("Author-email", metadata.get("Author-email", "")),
        ("Home-page", metadata.get("Home-page", "")),
    ]
    output.append(table(["Field", "Value"], [[key, value] for key, value in fields if value]))

    project_urls = sorted(metadata.get_all("Project-URL") or [])
    if project_urls:
        output.append(heading("Project URLs", 2))
        rows = []
        for value in project_urls:
            label, separator, url = value.partition(",")
            rows.append([label.strip() if separator else "", url.strip() if separator else value.strip()])
        output.append(table(["Label", "URL"], rows))

    requirements = sorted(dist.requires or [])
    if requirements:
        output.append(heading("Requires", 2))
        output.append(bullet_list(requirements))

    entry_points = sorted(dist.entry_points, key=lambda item: (item.group, item.name, item.value))
    if entry_points:
        output.append(heading("Entry Points", 2))
        output.append(table(
            ["Group", "Name", "Value"],
            [[item.group, item.name, item.value] for item in entry_points],
        ))
    return "\n".join(part.rstrip("\n") for part in output if part) + "\n"


def json_block(obj: Any, indent: int = 2) -> str:
    """Serialize ``obj`` as JSON and wrap it in a ```json fenced code block."""
    text = json.dumps(obj, ensure_ascii=False, indent=indent)
    return code_block(text, lang="json")


def table(headers: Any, rows: Any) -> str:
    """Build a Markdown (GFM-style) table.

    ``headers`` is a sequence of column names; ``rows`` is a sequence of
    sequences of cell values (converted with ``str``). Short rows are padded
    with empty cells; extra cells beyond ``len(headers)`` are dropped.

    ``markdown_to_html()`` parses this pipe-table form into
    ``<table>/<thead>/<th>/<tbody>/<td>``.

    >>> table(["a", "b"], [[1, 2], [3, 4]])
    '| a | b |\\n| --- | --- |\\n| 1 | 2 |\\n| 3 | 4 |\\n'
    """
    headers = [_escape_table_cell(h) for h in headers]
    if not headers:
        return ""
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        cells = [_escape_table_cell(v) for v in row][: len(headers)]
        cells += [""] * (len(headers) - len(cells))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


# === SECTION: table ===

def _display_width(value: Any) -> int:
    """Return a terminal-style display width for a Markdown table cell.

    Combining marks take no column; full-width and wide East Asian characters
    take two. Ambiguous-width characters deliberately stay one column so the
    result is stable across common Western and Japanese terminals.
    """
    width = 0
    for char in str(value):
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _escape_table_cell(value: Any) -> str:
    """Escape a cell for the small GFM pipe-table subset used by this module."""
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def aligned_table(headers: Any, rows: Any) -> str:
    """Build a pipe table aligned by display width, including CJK cells.

    This is presentation-oriented: parsing it with :func:`markdown_table_to_rows`
    recovers the escaped cell text, but physical padding is not preserved.
    """
    header_cells = [_escape_table_cell(header) for header in headers]
    if not header_cells:
        return ""
    body = []
    for row in rows:
        cells = [_escape_table_cell(value) for value in row][: len(header_cells)]
        body.append(cells + [""] * (len(header_cells) - len(cells)))
    widths = [
        max(3, _display_width(header_cells[index]), *(_display_width(row[index]) for row in body))
        for index in range(len(header_cells))
    ]

    def render(cells: list[str]) -> str:
        return "| " + " | ".join(
            cell + " " * (widths[index] - _display_width(cell))
            for index, cell in enumerate(cells)
        ) + " |"

    out = [render(header_cells), "| " + " | ".join("-" * width for width in widths) + " |"]
    out.extend(render(row) for row in body)
    return "\n".join(out) + "\n"


def markdown_table_to_rows(content: str) -> tuple[list[str], list[list[str]]]:
    """Read the first live GFM pipe table as ``(headers, rows)``.

    A table must have a header and a ``| --- |`` delimiter row. Fenced
    examples, malformed tables, and all text after the first table are
    ignored. Escaped pipes become literal pipes.
    """
    lines = content.splitlines()
    scanned = _scan_lines(lines)
    for index, line in enumerate(lines):
        if scanned[index].in_fenced_code or not _is_table_start(lines, index):
            continue
        headers = _split_table_row(line)
        rows: list[list[str]] = []
        cursor = index + 2
        while cursor < len(lines):
            candidate = lines[cursor]
            if not candidate.strip() or not _looks_like_table_row(candidate):
                break
            if scanned[cursor].in_fenced_code or _is_table_separator(candidate):
                break
            cells = _split_table_row(candidate)[: len(headers)]
            rows.append(cells + [""] * (len(headers) - len(cells)))
            cursor += 1
        return headers, rows
    return [], []


def markdown_table_to_records(content: str) -> list[dict[str, str]]:
    """Read the first GFM pipe table as dictionaries keyed by its headers.

    Duplicate headers have no lossless dictionary representation and raise
    ``ValueError`` rather than silently overwriting a column.
    """
    headers, rows = markdown_table_to_rows(content)
    if len(set(headers)) != len(headers):
        raise ValueError("Markdown table headers must be unique for records")
    return [dict(zip(headers, row)) for row in rows]


def csv_to_markdown_table(content: str, *, align: bool = False) -> str:
    """Convert CSV text to a GFM pipe table using the first row as headers.

    CSV quoting is handled by :mod:`csv`; a blank CSV document produces an
    empty result. Set ``align=True`` for East Asian display-width padding.
    """
    rows = list(csv.reader(io.StringIO(content)))
    if not rows:
        return ""
    renderer = aligned_table if align else table
    return renderer(rows[0], rows[1:])


def markdown_table_to_csv(content: str) -> str:
    """Convert the first live GFM pipe table to RFC-style CSV text."""
    headers, rows = markdown_table_to_rows(content)
    if not headers:
        return ""
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue()


def markdown_to_ipynb(content: str, *, indent: int | None = 2) -> str:
    """Make a minimal nbformat-4 JSON notebook from Markdown and Python fences.

    Fenced-code state comes from the shared ``_scan_lines`` scanner. The
    converter does not execute cells, create outputs, or infer kernels.
    """
    lines = content.splitlines(keepends=True)
    scanned = _scan_lines([line.rstrip("\r\n") for line in lines])
    cells: list[dict[str, Any]] = []
    prose: list[str] = []
    index = 0
    while index < len(lines):
        item = scanned[index]
        match = _FENCE_RE.match(item.text)
        info = match.group(2).strip() if match else ""
        language = info.split()[0].lower() if info else ""
        if item.is_fence_open and language in {"python", "py", "python3"}:
            if prose:
                cells.append({"cell_type": "markdown", "metadata": {}, "source": prose})
                prose = []
            index += 1
            code: list[str] = []
            while index < len(lines) and not scanned[index].is_fence_close:
                code.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code,
            })
            continue
        prose.append(lines[index])
        index += 1
    if prose:
        cells.append({"cell_type": "markdown", "metadata": {}, "source": prose})
    notebook = {
        "cells": cells,
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(notebook, ensure_ascii=False, indent=indent) + "\n"


def ipynb_to_markdown(notebook: str | dict[str, Any]) -> str:
    """Render Markdown and code cell sources from a minimal nbformat notebook.

    Outputs and execution counts are deliberately ignored.
    """
    data = json.loads(notebook) if isinstance(notebook, str) else notebook
    if not isinstance(data, dict) or not isinstance(data.get("cells"), list):
        raise ValueError("notebook must be an nbformat object with a cells list")
    parts: list[str] = []
    for cell in data["cells"]:
        if not isinstance(cell, dict):
            continue
        source = cell.get("source", [])
        text = source if isinstance(source, str) else "".join(source)
        if cell.get("cell_type") == "markdown":
            parts.append(text)
        elif cell.get("cell_type") == "code":
            parts.append("```python\n" + text + ("" if text.endswith("\n") or not text else "\n") + "```\n")
    return "".join(parts)


_PY_PERCENT_MARKER_RE = re.compile(r"^#\s*%%(?:\s+\[markdown\])?\s*$")


def _py_percent_marker_rows(content: str) -> dict[int, str]:
    """Return 1-based marker rows mapped to markdown or code.

    tokenize is used only to recognize real Python comment tokens, so text
    such as "# %%" inside a string never becomes a cell boundary.
    """
    rows: dict[int, str] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT or token.start[1] != 0:
                continue
            text = token.string.strip()
            if not _PY_PERCENT_MARKER_RE.fullmatch(text):
                continue
            rows[token.start[0]] = "markdown" if "[markdown]" in text else "code"
    except (tokenize.TokenError, IndentationError) as exc:
        raise ValueError(f"Invalid py:percent Python source: {exc}") from exc
    return rows


def markdown_to_py_percent(content: str) -> str:
    """Convert Markdown/Python fences to a narrow Jupytext py:percent form.

    The existing Markdown -> ipynb converter defines the cell split. Markdown
    cells become # %% [markdown] blocks with line comments; Python cells
    become # %% blocks and keep their source text unchanged.
    """
    notebook = json.loads(markdown_to_ipynb(content))
    out: list[str] = []
    for cell in notebook["cells"]:
        source = cell.get("source", [])
        text = source if isinstance(source, str) else "".join(source)
        if cell.get("cell_type") == "markdown":
            out.append("# %% [markdown]\n")
            for line in text.splitlines(keepends=True):
                body = line.rstrip("\r\n")
                ending = "\n" if line.endswith(("\n", "\r")) else ""
                out.append(("# " + body if body else "#") + ending)
            if text and not text.endswith(("\n", "\r")):
                out.append("\n")
        elif cell.get("cell_type") == "code":
            out.append("# %%\n")
            out.append(text)
            if text and not text.endswith(("\n", "\r")):
                out.append("\n")
    return "".join(out)


def py_percent_to_markdown(content: str) -> str:
    """Convert the canonical narrow py:percent subset back to Markdown.

    Marker comments must start in column zero. Markdown-cell payload lines must
    be blank or comment lines. Code-cell source is copied verbatim; it is never
    parsed through AST/unparse, so ordinary Python comments are preserved.
    """
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    marker_rows = _py_percent_marker_rows(normalized)
    if not marker_rows:
        raise ValueError("No py:percent cell markers found")

    lines = normalized.splitlines(keepends=True)
    marker_indices = sorted(row - 1 for row in marker_rows)
    parts: list[str] = []
    for offset, marker_index in enumerate(marker_indices):
        kind = marker_rows[marker_index + 1]
        end = marker_indices[offset + 1] if offset + 1 < len(marker_indices) else len(lines)
        body = lines[marker_index + 1:end]
        if kind == "markdown":
            for line_number, line in enumerate(body, marker_index + 2):
                raw = line[:-1] if line.endswith("\n") else line
                if raw == "":
                    parts.append("\n" if line.endswith("\n") else "")
                elif raw == "#":
                    parts.append("\n" if line.endswith("\n") else "")
                elif raw.startswith("# "):
                    parts.append(raw[2:] + ("\n" if line.endswith("\n") else ""))
                else:
                    raise ValueError(
                        f"py:percent markdown cell line {line_number} must be a comment"
                    )
        else:
            code = "".join(body)
            parts.append("~~~python\n")
            parts.append(code)
            if code and not code.endswith("\n"):
                parts.append("\n")
            parts.append("~~~\n")
    return "".join(parts)

# === SECTION: structured snapshots ===

def markdown_table_statistics(content: str) -> dict[str, Any]:
    """Return a small, non-mutating summary of the first Markdown table.

    Numeric aggregates appear only when every non-empty value in a column
    parses as a finite number (``nan``/``inf`` spellings are treated as
    non-numeric text, not data); no schema inference or value conversion
    is applied.

    :raises ValueError: if two columns share a header -- ``numeric_columns``
        is keyed by header text, which cannot represent both losslessly
        (same contract as :func:`markdown_table_to_records`).
    """
    headers, data_rows = markdown_table_to_rows(content)
    if not headers:
        return {"rows": 0, "columns": 0, "headers": [], "numeric_columns": {}}
    if len(set(headers)) != len(headers):
        raise ValueError("Markdown table headers must be unique for statistics")
    numeric_columns: dict[str, dict[str, float | int]] = {}
    for index, header in enumerate(headers):
        values = [row[index] for row in data_rows if index < len(row) and row[index] != ""]
        if not values:
            continue
        try:
            numbers = [float(value) for value in values]
        except ValueError:
            continue
        if not all(math.isfinite(number) for number in numbers):
            continue
        numeric_columns[header] = {
            "count": len(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "mean": statistics.mean(numbers),
            "median": statistics.median(numbers),
        }
    return {
        "rows": len(data_rows),
        "columns": len(headers),
        "headers": headers,
        "numeric_columns": numeric_columns,
    }

_SQL_IDENTIFIER_RE = (
    r'(?:"(?:""|[^"])*"|`(?:``|[^`])*`|\[(?:\]\]|[^\]])*\]|[A-Za-z_][A-Za-z0-9_$]*)'
)
_CREATE_TABLE_NAME_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(" + _SQL_IDENTIFIER_RE + r"(?:\." + _SQL_IDENTIFIER_RE + r")*)",
    re.IGNORECASE,
)
_SQL_TRAILING_NEWLINES_RE = re.compile(
    r"<!-- markdown\.py:sql-trailing-newlines=(\d+) -->"
)


def json_to_markdown(value: Any, title: str = "JSON") -> str:
    """Wrap JSON data as a Markdown document without performing I/O."""
    return heading(title) + json_block(value)


def markdown_to_json(content: str) -> Any:
    """Read the first JSON fence emitted by :func:`json_to_markdown`."""
    for block in extract_code_blocks(content):
        if block["language"].lower() == "json":
            return json.loads(block["code"])
    raise ValueError("No fenced JSON block found")



_STRUCTURED_TABLE_HEADERS = ["id", "parent", "slot", "type", "value"]
_STRUCTURED_MARKER = "<!-- markdown.py:structured-v1 -->\n"
_STRUCTURED_SCALAR_TYPES = {"str", "int", "float", "bool", "null"}


def _structured_scalar_type(value: Any) -> str | None:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "str"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return None


def _structured_json_dumps(value: Any) -> str:
    """Encode one structured scalar/key with stable JSON settings."""
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _structured_json_loads(text: str, *, what: str) -> Any:
    """Decode one JSON-backed structured field with a focused error."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Structured {what} is not valid JSON") from exc


def _structured_encode_scalar(value: Any) -> tuple[str, str]:
    kind = _structured_scalar_type(value)
    if kind is None:
        raise TypeError(
            "structured data must use JSON-compatible dict/list/scalar values"
        )
    return kind, _structured_json_dumps(value)


def _structured_decode_scalar(kind: str, encoded: str) -> Any:
    if kind not in _STRUCTURED_SCALAR_TYPES:
        raise ValueError(f"Unknown structured node type: {kind!r}")
    value = _structured_json_loads(encoded, what="scalar value")
    actual = _structured_scalar_type(value)
    if actual != kind:
        raise ValueError(
            f"Structured scalar type mismatch: declared {kind}, got {actual}"
        )
    return value


def _structured_validate(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("structured mappings require string keys")
            _structured_validate(child)
        return
    if isinstance(value, list):
        for child in value:
            _structured_validate(child)
        return
    _structured_encode_scalar(value)


def structured_to_markdown(value: Any, title: str = "Structured data") -> str:
    """Render JSON-compatible Python data as a canonical typed Markdown table.

    The representation is intended as a small common layer for format adapters
    such as INI and TOML. Mapping keys must be strings. Supported values are
    dict, list, str, int, finite float, bool and None. Object order and list
    order are preserved.

    This is a semantic round-trip format, not a source-text preservation
    format: whitespace, comments, quoting style, and source-format trivia from
    an upstream format belong to that adapter's declared lossiness contract.
    """
    _structured_validate(value)
    rows: list[list[str]] = []

    def visit(node: Any, parent: str = "", slot: str = "") -> None:
        node_id = str(len(rows))
        if isinstance(node, dict):
            rows.append([node_id, parent, slot, "dict", ""])
            for key, child in node.items():
                visit(child, node_id, _structured_json_dumps(key))
            return
        if isinstance(node, list):
            rows.append([node_id, parent, slot, "list", ""])
            for index, child in enumerate(node):
                visit(child, node_id, str(index))
            return

        kind, encoded = _structured_encode_scalar(node)
        rows.append([node_id, parent, slot, kind, encoded])

    visit(value)
    return heading(title) + _STRUCTURED_MARKER + table(_STRUCTURED_TABLE_HEADERS, rows)


def markdown_to_structured(content: str) -> Any:
    """Restore data emitted by structured_to_markdown.

    A live structured marker must be paired with the immediately following
    canonical pipe table. Node ids and rows use contiguous pre-order traversal;
    that ordering is part of the canonical representation. Malformed node ids,
    parent references, slots, type tags, or scalar JSON values raise ValueError
    instead of being guessed.
    """
    lines = content.splitlines()
    scanned = _scan_lines(lines)
    marker = _STRUCTURED_MARKER.strip()
    marker_index = next(
        (
            index
            for index, line in enumerate(lines)
            if not scanned[index].in_fenced_code and line.strip() == marker
        ),
        None,
    )
    if marker_index is None:
        raise ValueError("No structured-data marker found")

    table_index = marker_index + 1
    while table_index < len(lines) and not lines[table_index].strip():
        table_index += 1
    if table_index >= len(lines) or not _is_table_start(lines, table_index):
        raise ValueError("Structured-data marker is not paired with a table")

    headers, rows = markdown_table_to_rows("\n".join(lines[table_index:]))
    if headers != _STRUCTURED_TABLE_HEADERS:
        raise ValueError("No canonical structured-data table found")
    if not rows:
        raise ValueError("Structured-data table has no root node")

    nodes: list[Any] = []
    for expected_id, row in enumerate(rows):
        raw_id, raw_parent, slot, kind, encoded = row
        try:
            node_id = int(raw_id)
        except ValueError as exc:
            raise ValueError("Structured node id must be an integer") from exc
        if node_id != expected_id:
            raise ValueError("Structured node ids must be contiguous and ordered")

        if kind == "dict":
            if encoded:
                raise ValueError("Structured container rows must have empty values")
            node: Any = {}
        elif kind == "list":
            if encoded:
                raise ValueError("Structured container rows must have empty values")
            node = []
        else:
            node = _structured_decode_scalar(kind, encoded)

        if expected_id == 0:
            if raw_parent or slot:
                raise ValueError("Structured root node cannot have parent or slot")
            nodes.append(node)
            continue

        try:
            parent_id = int(raw_parent)
        except ValueError as exc:
            raise ValueError("Structured parent id must be an integer") from exc
        if parent_id < 0 or parent_id >= len(nodes):
            raise ValueError("Structured parent must reference an earlier node")

        parent = nodes[parent_id]
        if isinstance(parent, dict):
            key = _structured_json_loads(slot, what="mapping slot")
            if not isinstance(key, str):
                raise ValueError("Structured mapping slot must decode to a string")
            if key in parent:
                raise ValueError("Structured mapping contains a duplicate key")
            parent[key] = node
        elif isinstance(parent, list):
            try:
                index = int(slot)
            except ValueError as exc:
                raise ValueError("Structured list slot must be an integer") from exc
            if index != len(parent):
                raise ValueError("Structured list slots must be contiguous and ordered")
            parent.append(node)
        else:
            raise ValueError("Structured scalar nodes cannot have children")

        nodes.append(node)

    return nodes[0]



_INI_DEFAULT_SENTINEL = "\\x00markdown.py:no-default\\x00"
_DOTENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TOML_BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _ini_loads(content: str) -> dict[str, dict[str, str]]:
    """Parse the supported INI subset without interpolation or case folding."""
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.default_section = _INI_DEFAULT_SENTINEL
    try:
        parser.read_string(content)
    except configparser.Error as exc:
        raise ValueError(f"Invalid INI: {exc}") from exc
    return {
        section_name: dict(parser.items(section_name, raw=True))
        for section_name in parser.sections()
    }


def _ini_dumps(value: Any) -> str:
    if not isinstance(value, dict):
        raise ValueError("INI root must be a mapping of sections")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.default_section = _INI_DEFAULT_SENTINEL
    for section_name, options in value.items():
        if not isinstance(section_name, str) or "\n" in section_name or "\r" in section_name:
            raise ValueError("INI section names must be single-line strings")
        if section_name == _INI_DEFAULT_SENTINEL:
            raise ValueError("INI section name is reserved")
        if not isinstance(options, dict):
            raise ValueError("INI sections must contain key/value mappings")
        parser.add_section(section_name)
        for key, item in options.items():
            if (
                not isinstance(key, str)
                or not key
                or "\n" in key
                or "\r" in key
                or "=" in key
                or ":" in key
            ):
                raise ValueError("INI keys must be non-empty single-line strings without = or :")
            if not isinstance(item, str):
                raise ValueError("INI values must be strings")
            parser.set(section_name, key, item)
    stream = io.StringIO()
    parser.write(stream, space_around_delimiters=False)
    return stream.getvalue()


def ini_to_markdown(content: str, title: str = "INI") -> str:
    """Convert INI to canonical structured Markdown.

    Section names, key case, and string values round-trip. Comments, delimiter
    choice, and whitespace are intentionally canonicalized. [DEFAULT] is
    treated as an ordinary section so implicit interpolation/inheritance is not
    invented during conversion.
    """
    return structured_to_markdown(_ini_loads(content), title)


def markdown_to_ini(content: str) -> str:
    """Convert canonical structured Markdown to deterministic INI text."""
    return _ini_dumps(markdown_to_structured(content))


def _dotenv_loads(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _DOTENV_KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid dotenv assignment on line {line_number}")
        if key in result:
            raise ValueError(f"Duplicate dotenv key: {key}")

        raw_value = raw_value.strip()
        if raw_value.startswith('"'):
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid quoted dotenv value on line {line_number}") from exc
            if not isinstance(value, str):
                raise ValueError(f"Dotenv values must be strings on line {line_number}")
        elif raw_value.startswith("'"):
            if len(raw_value) < 2 or not raw_value.endswith("'"):
                raise ValueError(f"Invalid quoted dotenv value on line {line_number}")
            value = raw_value[1:-1]
        else:
            value = raw_value
        result[key] = value
    return result


def _dotenv_dumps(value: Any) -> str:
    if not isinstance(value, dict):
        raise ValueError("dotenv root must be a mapping")
    lines: list[str] = []
    for key, item in value.items():
        if not isinstance(key, str) or not _DOTENV_KEY_RE.fullmatch(key):
            raise ValueError(f"Invalid dotenv key: {key!r}")
        if not isinstance(item, str):
            raise ValueError("dotenv values must be strings")
        lines.append(f"{key}={_structured_json_dumps(item)}")
    return "".join(line + "\n" for line in lines)


def dotenv_to_markdown(content: str, title: str = ".env") -> str:
    """Convert a narrow dotenv subset to canonical structured Markdown.

    Blank lines and full-line comments are ignored; optional export is
    accepted. Variable expansion is never performed. The canonical writer uses
    deterministic double-quoted JSON-compatible string escaping.
    """
    return structured_to_markdown(_dotenv_loads(content), title)


def markdown_to_dotenv(content: str) -> str:
    """Convert canonical structured Markdown to deterministic dotenv text."""
    return _dotenv_dumps(markdown_to_structured(content))


def _toml_key(key: str) -> str:
    if _TOML_BARE_KEY_RE.fullmatch(key):
        return key
    return _structured_json_dumps(key)


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return _structured_json_dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("TOML canonical writer requires finite floats")
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        fields = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("TOML mappings require string keys")
            fields.append(f"{_toml_key(key)} = {_toml_value(item)}")
        return "{ " + ", ".join(fields) + " }"
    if value is None:
        raise ValueError("TOML has no null value")
    raise ValueError(f"Unsupported TOML value type: {type(value).__name__}")


def _toml_dumps(value: Any) -> str:
    if not isinstance(value, dict):
        raise ValueError("TOML document root must be a mapping")
    lines = []
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("TOML mappings require string keys")
        lines.append(f"{_toml_key(key)} = {_toml_value(item)}")
    return "".join(line + "\n" for line in lines)


def toml_to_markdown(content: str, title: str = "TOML") -> str:
    """Convert TOML to canonical structured Markdown on Python 3.11+.

    The reversible subset is the JSON-compatible TOML value space. TOML
    datetime/date/time values and non-finite floats are rejected rather than
    silently stringified.
    """
    if tomllib is None:
        raise RuntimeError("toml_to_markdown requires Python 3.11+ (tomllib)")
    try:
        value = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML: {exc}") from exc
    try:
        _structured_validate(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "TOML contains values outside the reversible structured subset"
        ) from exc
    return structured_to_markdown(value, title)


def markdown_to_toml(content: str) -> str:
    """Convert canonical structured Markdown to deterministic TOML text."""
    return _toml_dumps(markdown_to_structured(content))


def redis_snapshot_to_markdown(snapshot: Any, title: str = "Redis snapshot") -> str:
    """Document an already obtained Redis/RedisJSON snapshot without connecting."""
    return json_to_markdown(snapshot, title)


def sql_ddl_to_markdown(sql: str, title: str = "SQL schema") -> str:
    """Document a supplied SQL DDL snapshot without parsing or executing it.

    Input line endings are normalized to LF before fencing. The normalized
    trailing-newline count is recorded in a Markdown comment so the companion
    reader restores the LF-normalized snapshot exactly.
    """
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")
    names = _CREATE_TABLE_NAME_RE.findall(sql)
    outline = bullet_list(["Table: " + name for name in names]) if names else ""
    trailing_newlines = len(sql) - len(sql.rstrip("\n"))
    body = sql.rstrip("\n")
    fence = _adaptive_fence(sql, "`")
    fenced = fence + "sql\n" + body + "\n" + fence + "\n"
    marker = "<!-- markdown.py:sql-trailing-newlines=" + str(trailing_newlines) + " -->\n"
    return heading(title) + outline + marker + fenced


def markdown_to_sql_ddl(content: str) -> str:
    """Return the first SQL snapshot without validating or executing it."""
    for block in extract_code_blocks(content):
        if block["language"].lower() == "sql":
            marker = _SQL_TRAILING_NEWLINES_RE.search(content)
            trailing_newlines = int(marker.group(1)) if marker else 0
            return block["code"].rstrip("\n") + "\n" * trailing_newlines
    raise ValueError("No fenced SQL block found")

def key_value_table(
    data: Any,
    key_label: str = "Key",
    value_label: str = "Value",
) -> str:
    """Render a mapping as a two-column Markdown table via ``table``."""
    rows = [[key, value] for key, value in dict(data).items()]
    return table([key_label, value_label], rows)


def _record_to_cells(record: Any) -> list[str]:
    if isinstance(record, dict):
        return [str(v) for v in record.values()]
    if isinstance(record, (list, tuple)):
        return [str(v) for v in record]
    return [str(record)]


def md_table(*headers_and_rows: Any) -> str:
    """``*args`` version of ``table`` — pass values directly, no list needed.

    Dispatches on the first argument:

    - a ``dict`` -> every argument is a record; headers come from the first
      record's keys, and each record's ``.values()`` become that row's cells.
    - a ``list``/``tuple`` -> treated as the header row; the remaining
      arguments are data rows (each a list/tuple of cells, a dict of values,
      or a single scalar rendered as a one-cell row).
    - anything else -> every argument becomes a single-cell row under a
      generic ``value`` header.

    >>> md_table(["name", "val"], ["loss", "0.01"], ["iou", "0.85"])
    '| name | val |\\n| --- | --- |\\n| loss | 0.01 |\\n| iou | 0.85 |\\n'
    >>> md_table({"name": "loss", "val": "0.01"}, {"name": "iou", "val": "0.85"})
    '| name | val |\\n| --- | --- |\\n| loss | 0.01 |\\n| iou | 0.85 |\\n'
    """
    if not headers_and_rows:
        return ""

    first = headers_and_rows[0]
    if isinstance(first, dict):
        headers = [str(k) for k in first.keys()]
        rows = [_record_to_cells(rec) for rec in headers_and_rows]
        return table(headers, rows)

    if isinstance(first, (list, tuple)):
        headers = [str(h) for h in first]
        rows = [_record_to_cells(rec) for rec in headers_and_rows[1:]]
        return table(headers, rows)

    return table(["value"], [[str(v)] for v in headers_and_rows])


def md_kv(*pairs: Any, key_label: str = "Key", value_label: str = "Value") -> str:
    """``*args`` version of ``key_value_table`` — pass ``key, value`` pairs or dicts.

    Alternating positional ``key, value`` arguments and ``dict`` arguments can
    be freely mixed; a trailing key with no value gets an empty string.

    >>> md_kv("mode", "train", "epochs", 10)
    '| Key | Value |\\n| --- | --- |\\n| mode | train |\\n| epochs | 10 |\\n'
    >>> md_kv({"mode": "train"}, "device", "cuda")
    '| Key | Value |\\n| --- | --- |\\n| mode | train |\\n| device | cuda |\\n'
    """
    merged: dict[str, Any] = {}
    it = iter(pairs)
    for item in it:
        if isinstance(item, dict):
            merged.update(item)
        else:
            merged[str(item)] = next(it, "")
    return key_value_table(merged, key_label=key_label, value_label=value_label)


def status_line(ok: bool, msg_ok: str, msg_ng: str) -> str:
    """Build a one-line status message, prefixed with a checkmark or warning."""
    prefix = "✓" if ok else "⚠"
    return f"{prefix} {msg_ok if ok else msg_ng}\n"


def section(title: str, blocks: Any, level: int = 2) -> str:
    """Join a heading with a sequence of pre-rendered Markdown blocks.

    Every builder in this module (``bullet_list``, ``table``, ``code_block``,
    ...) already ends its output in a trailing newline, so back-to-back
    blocks never need anything inserted between them. A plain string used
    directly as a block -- typically hand-written prose with no trailing
    newline of its own -- is the one case that doesn't: joined with nothing
    in between, its text runs directly onto the next block's own leading
    syntax (``- ``, ``# ``, a fence), so e.g. a following bullet list's
    first item silently becomes part of the previous line's plain text
    instead of a list. A newline is inserted only when the accumulated
    output doesn't already end in one, so well-formed blocks are untouched.
    """
    body = heading(title, level=level)
    for block in blocks:
        block = str(block)
        if not block:
            continue
        if not body.endswith("\n"):
            body += "\n"
        body += block
    return body


def wrap_section(name: str, content: str) -> str:
    """Wrap ``content`` in HTML-comment markers so tools/LLMs can find section boundaries."""
    content = content if content.endswith("\n") else content + "\n"
    return f"<!-- BEGIN_SECTION:{name} -->\n{content}<!-- END_SECTION:{name} -->\n"


# ---------------------------------------------------------------------------
# Kramdown IAL (thin heading/paragraph subset — not full Kramdown)
# ---------------------------------------------------------------------------

def _escape_ial_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _parse_attr_list_inner(inner: str) -> dict[str, Any] | None:
    """Parse ``#id .class key=value`` tokens. ``None`` if leftover junk remains."""
    text = inner.strip()
    parsed: dict[str, Any] = {
        "id": None,
        "classes": [],
        "attrs": {},
        "flags": [],
    }
    if not text:
        return parsed
    pos = 0
    length = len(text)
    while pos < length:
        if text[pos].isspace():
            pos += 1
            continue
        match = _ATTR_LIST_TOKEN_RE.match(text, pos)
        if not match:
            return None
        if match.group("id"):
            parsed["id"] = match.group("id")
        elif match.group("cls"):
            parsed["classes"].append(match.group("cls"))
        elif match.group("key"):
            key = match.group("key")
            if match.group("dval") is not None:
                parsed["attrs"][key] = match.group("dval")
            elif match.group("sval") is not None:
                parsed["attrs"][key] = match.group("sval")
            elif match.group("uval") is not None:
                parsed["attrs"][key] = match.group("uval")
            else:
                parsed["flags"].append(key)
        pos = match.end()
    return parsed


def _is_toc_only(parsed: dict[str, Any]) -> bool:
    if parsed["id"] or parsed["classes"] or parsed["attrs"]:
        return False
    flags = [flag.lower() for flag in parsed["flags"]]
    return flags == ["toc"]


def _format_attr_tokens(
    ident: str | None,
    classes: list[str],
    attrs: dict[str, str],
    flags: list[str] | None = None,
) -> list[str]:
    parts: list[str] = []
    if ident:
        parts.append("#" + ident)
    for item in classes:
        parts.append("." + item)
    for key, value in attrs.items():
        parts.append(f'{key}="{_escape_ial_value(value)}"')
    for flag in flags or []:
        parts.append(flag)
    return parts


def _format_ial_line(
    ident: str | None,
    classes: list[str],
    attrs: dict[str, str],
    flags: list[str] | None = None,
) -> str:
    tokens = _format_attr_tokens(ident, classes, attrs, flags)
    if not tokens:
        return "{:}"
    return "{: " + " ".join(tokens) + "}"


def _format_pandoc_attr_list(
    ident: str | None,
    classes: list[str],
    attrs: dict[str, str],
) -> str:
    tokens = _format_attr_tokens(ident, classes, attrs)
    return "{" + " ".join(tokens) + "}"


def _html_attrs_to_pandoc_suffix(attr: dict[str, str]) -> str:
    ident = (attr.get("id") or "").strip()
    if ident and not _IAL_NAME_RE.fullmatch(ident):
        ident = ""
    classes: list[str] = []
    for item in (attr.get("class") or "").split():
        item = item.strip()
        if item and _IAL_NAME_RE.fullmatch(item):
            classes.append(item)
    extra: dict[str, str] = {}
    for key, value in attr.items():
        if key in _HTML_ATTR_SKIP or not value:
            continue
        if not _IAL_KEY_RE.fullmatch(key):
            continue
        extra[key] = value
    if not ident and not classes and not extra:
        return ""
    return " " + _format_pandoc_attr_list(ident or None, classes, extra)


def _normalize_ial_id(ident: str | None) -> str | None:
    if ident is None:
        return None
    ident = str(ident).strip().lstrip("#")
    if not ident:
        return None
    if not _IAL_NAME_RE.fullmatch(ident):
        raise ValueError(f"invalid IAL id {ident!r}")
    return ident


def _normalize_ial_classes(classes: Any) -> list[str]:
    if classes is None:
        return []
    if isinstance(classes, str):
        items = classes.split()
    else:
        items = [str(item) for item in classes]
    out: list[str] = []
    for item in items:
        item = item.strip().lstrip(".")
        if not item:
            continue
        if not _IAL_NAME_RE.fullmatch(item):
            raise ValueError(f"invalid IAL class {item!r}")
        out.append(item)
    return out


def _normalize_ial_attrs(attrs: dict[str, Any]) -> dict[str, str]:
    extra: dict[str, str] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if not _IAL_KEY_RE.fullmatch(str(key)):
            raise ValueError(f"invalid IAL key {key!r}")
        extra[str(key)] = str(value)
    return extra


def ial(
    *,
    id: str | None = None,
    classes: Any = None,
    **attrs: Any,
) -> str:
    """Build a Kramdown Inline Attribute List line.

    Emits ``{: #id .class key="value"}\\n``. Empty input (no id, classes, or
    attrs) returns ``""``. ``classes`` may be a string (whitespace-split) or
    a sequence. A leading ``#`` / ``.`` on id / class names is stripped.

    This is a generator only — ``markdown_to_html`` does not apply IAL as
    HTML attributes.

    >>> ial(id="intro", classes="hero")
    '{: #intro .hero}\\n'
    >>> ial(id="box", classes=["note", "wide"], role="note")
    '{: #box .note .wide role="note"}\\n'
    """
    ident = _normalize_ial_id(id)
    class_list = _normalize_ial_classes(classes)
    extra = _normalize_ial_attrs(attrs)
    if not ident and not class_list and not extra:
        return ""
    return _format_ial_line(ident, class_list, extra) + "\n"


def with_attributes(
    block_md: str,
    *,
    id: str | None = None,
    classes: Any = None,
    **attrs: Any,
) -> str:
    """Append a block IAL after ``block_md``.

    Intended for headings and paragraphs (tiny contract). ``block_md`` is
    left unchanged when no attributes are given.

    >>> with_attributes(heading("Title"), id="intro", classes="hero")
    '# Title\\n{: #intro .hero}\\n'
    """
    suffix = ial(id=id, classes=classes, **attrs)
    if not suffix:
        return str(block_md)
    body = str(block_md)
    if body and not body.endswith("\n"):
        body += "\n"
    return body + suffix


def _join_converted_lines(lines: list[str], original: str) -> str:
    if not lines:
        return "\n" if original.endswith("\n") else ""
    text = "\n".join(lines)
    if original.endswith("\n") and not text.endswith("\n"):
        text += "\n"
    return text


def _is_heading_or_paragraph_line(line: str) -> bool:
    """True when a trailing attr list may attach (headings / paragraphs only)."""
    if _HEADING_RE.match(line):
        return True
    stripped = line.strip()
    if not stripped:
        return False
    if _HR_RE.match(line) or _FENCE_RE.match(line):
        return False
    if _LIST_ITEM_RE.match(line):
        return False
    if line.lstrip().startswith(">"):
        return False
    if _FOOTNOTE_DEF_RE.match(line):
        return False
    if _details_open_summary(line) is not None:
        return False
    if _COLON_CONTAINER_CLOSE_RE.match(line):
        return False
    if _qiita_note_kind(line) is not None or _zenn_message_kind(line) is not None:
        return False
    if stripped.startswith("|"):
        return False
    if stripped.startswith("<!--") or stripped.startswith("{%"):
        return False
    if stripped.startswith("{{"):
        return False
    if stripped == "---":
        return False
    return True


def _rewrite_trailing_attr_list(line: str) -> tuple[str, str] | None:
    """Peel a trailing Pandoc or inline IAL list into ``(body, ial_line)``."""
    if not _is_heading_or_paragraph_line(line):
        return None
    ial_match = _TRAILING_KRAMDOWN_IAL_RE.match(line)
    if ial_match and ial_match.group("body").strip():
        parsed = _parse_attr_list_inner(ial_match.group("inner"))
        if parsed is None or _is_toc_only(parsed):
            return None
        body = ial_match.group("body").rstrip()
        return body, _format_ial_line(
            parsed["id"], parsed["classes"], parsed["attrs"], parsed["flags"]
        )
    pandoc_match = _TRAILING_PANDOC_ATTR_RE.match(line)
    if pandoc_match and pandoc_match.group("body").strip():
        parsed = _parse_attr_list_inner(pandoc_match.group("inner"))
        if parsed is None or _is_toc_only(parsed):
            return None
        if not (
            parsed["id"]
            or parsed["classes"]
            or parsed["attrs"]
            or parsed["flags"]
        ):
            return None
        body = pandoc_match.group("body").rstrip()
        return body, _format_ial_line(
            parsed["id"], parsed["classes"], parsed["attrs"], parsed["flags"]
        )
    return None


def markdown_to_kramdown(content: str) -> str:
    """Rewrite a Markdown subset into Kramdown-leaning Markdown.

    **Rewritten**

    - Pandoc / PHP Markdown Extra trailing braces on headings and
      paragraphs: ``# Title {#id .class key=value}`` becomes a block IAL
      on the next line (``{: #id .class key="value"}``).
    - Inline IAL already on a heading/paragraph (``# Title {: #id}``) is
      moved to a following block IAL and normalized (id, then classes,
      then ``key="value"``).
    - A standalone parseable IAL line is normalized the same way.

    **Left alone**

    - Ordinary Markdown with no attribute list (headings, lists, tables,
      fences, alerts, ``:::details``, footnotes, …).
    - Fenced code (attribute-looking braces inside stay literal).
    - ``{:toc}`` (Kramdown TOC macro), ``{::comment}`` / other extensions,
      span IAL, IAL on lists / quotes / tables, Liquid ``{% %}`` / ``{{ }}``,
      YAML front matter, and unknown brace constructs (safe degrade:
      leave-as-is).

    This is **not** a Kramdown engine. ``markdown_to_html`` does not apply
    IAL as HTML attributes.

    >>> markdown_to_kramdown("# Title {#intro .hero}").splitlines()
    ['# Title', '{: #intro .hero}']
    """
    lines = content.splitlines()
    out: list[str] = []
    in_fence: str | None = None
    for line in lines:
        fence = _FENCE_RE.match(line)
        if fence:
            mark = fence.group(1)
            if in_fence is None:
                in_fence = mark
            elif line.startswith(in_fence):
                in_fence = None
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        standalone = _STANDALONE_IAL_RE.match(line)
        if standalone:
            parsed = _parse_attr_list_inner(standalone.group("inner"))
            if parsed is None or _is_toc_only(parsed):
                out.append(line)
            else:
                out.append(
                    _format_ial_line(
                        parsed["id"],
                        parsed["classes"],
                        parsed["attrs"],
                        parsed["flags"],
                    )
                )
            continue
        rewritten = _rewrite_trailing_attr_list(line)
        if rewritten is not None:
            body, ial_line = rewritten
            out.append(body)
            out.append(ial_line)
            continue
        out.append(line)
    return _join_converted_lines(out, content)


def kramdown_to_markdown(content: str) -> str:
    """Strip the supported IAL subset back toward plain Markdown.

    **Rewritten (lossy)**

    - A standalone IAL line ``{: #id .class key="value"}`` after a block
      is removed. Attributes are dropped.
    - A trailing inline IAL on a heading or paragraph
      (``# Title {: #id}``) is stripped.

    **Kept / left alone**

    - The heading or paragraph text itself.
    - Ordinary Markdown, including Pandoc-style ``{#id}`` that was never
      converted to IAL.
    - ``{:toc}``, ``{::comment}`` / ``{::options}`` / ``{::nomarkdown}``,
      unparseable IAL, Liquid ``{% %}`` / ``{{ }}``, YAML front matter,
      and fenced code. Standalone parseable IAL is stripped wherever it
      appears (the line does not record which block it attached to).

    Round-trip ``markdown_to_kramdown`` → ``kramdown_to_markdown`` keeps
    prose and structure; attribute lists are lost. That is intentional.

    >>> kramdown_to_markdown("# Title\\n{: #intro .hero}\\n").splitlines()
    ['# Title']
    """
    lines = content.splitlines()
    out: list[str] = []
    in_fence: str | None = None
    for line in lines:
        fence = _FENCE_RE.match(line)
        if fence:
            mark = fence.group(1)
            if in_fence is None:
                in_fence = mark
            elif line.startswith(in_fence):
                in_fence = None
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        standalone = _STANDALONE_IAL_RE.match(line)
        if standalone:
            parsed = _parse_attr_list_inner(standalone.group("inner"))
            if parsed is None or _is_toc_only(parsed):
                out.append(line)
            continue
        ial_match = _TRAILING_KRAMDOWN_IAL_RE.match(line)
        if ial_match:
            body = ial_match.group("body").rstrip()
            parsed = _parse_attr_list_inner(ial_match.group("inner"))
            if (
                parsed is not None
                and not _is_toc_only(parsed)
                and _is_heading_or_paragraph_line(body)
            ):
                out.append(body)
                continue
        out.append(line)
    return _join_converted_lines(out, content)


# ---------------------------------------------------------------------------
# Conservative HTML <-> Markdown (common tags only)
# ---------------------------------------------------------------------------

@dataclass
class HtmlNode:
    """Small normalized HTML tree node; not a browser DOM implementation.

    ``kind`` is ``"root"``, ``"element"``, or ``"text"``. Element nodes use
    lowercase ``tag`` names and sanitized attributes. Unknown tags are retained
    as transparent containers so their safe text/children can degrade without
    passing unsupported markup through.
    """

    kind: str
    tag: str = ""
    attrs: dict[str, str] | None = None
    children: list["HtmlNode"] | None = None
    text: str = ""

    def __post_init__(self) -> None:
        if self.attrs is None:
            self.attrs = {}
        if self.children is None:
            self.children = []


_DOM_SAFE_TAGS = frozenset({
    "a", "aside", "b", "blockquote", "br", "code", "del", "details", "em",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "input", "li",
    "ol", "p", "pre", "s", "section", "strong", "summary", "sup", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
})
_DOM_VOID_TAGS = frozenset({"br", "hr", "img", "input"})
_HTML_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})
_DOM_DROP_TAGS = frozenset({"script", "style"})
_DOM_URL_ATTRS = frozenset({"href", "src"})
_DOM_COMMON_ATTRS = frozenset({
    "alt", "checked", "class", "disabled", "href", "id", "open", "src",
    "title", "type",
})


def _sanitize_url_scheme(value: str) -> str:
    """Normalize and validate a URL for generated HTML attributes.

    C0 controls and DEL are removed before parsing. http/https/mailto and
    ordinary relative URLs are kept; other absolute schemes are rejected.
    An unambiguous host:port reference such as ``example.com:8080/path`` is
    normalized to ``//example.com:8080/path`` so browsers treat it as a
    network-path reference rather than an unknown custom scheme.
    """
    cleaned = "".join(ch for ch in value.strip() if ord(ch) >= 0x20 and ord(ch) != 0x7F)
    if not cleaned:
        return ""
    if cleaned.startswith(("#", "/", "./", "../")):
        return cleaned
    host_port = _HOST_PORT_REFERENCE_RE.fullmatch(cleaned)
    if host_port:
        port = int(host_port.group("port"))
        if 1 <= port <= 65535:
            return "//" + cleaned
        return ""
    parsed = urlparse(cleaned)
    if not parsed.scheme:
        return cleaned
    if parsed.scheme.lower() in {"http", "https", "mailto"}:
        return cleaned
    return ""


def _dom_sanitize_attrs(tag: str, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for raw_key, raw_value in attrs:
        key = raw_key.lower()
        if key.startswith("on") or key == "style":
            continue
        if key not in _DOM_COMMON_ATTRS and not key.startswith("data-"):
            continue
        value = raw_value or ""
        if key in _DOM_URL_ATTRS:
            value = _sanitize_url_scheme(value)
            if not value:
                continue
        safe[key] = value
    if tag == "input" and safe.get("type", "").lower() != "checkbox":
        return {}
    return safe


class _LightweightDomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("root")
        self.stack: list[HtmlNode] = [self.root]
        self._suppress_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _DOM_DROP_TAGS:
            self._suppress_depth += 1
            return
        if self._suppress_depth:
            return
        node = HtmlNode(
            "element",
            tag=tag,
            attrs=_dom_sanitize_attrs(tag, attrs) if tag in _DOM_SAFE_TAGS else {},
        )
        assert self.stack[-1].children is not None
        self.stack[-1].children.append(node)
        if tag not in _DOM_VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _DOM_VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _DOM_DROP_TAGS:
            if self._suppress_depth:
                self._suppress_depth -= 1
            return
        if self._suppress_depth:
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._suppress_depth or not data:
            return
        assert self.stack[-1].children is not None
        self.stack[-1].children.append(HtmlNode("text", text=data))


def parse_html_dom(html: str) -> HtmlNode:
    """Parse HTML into a small sanitized in-memory tree.

    This uses html.parser.HTMLParser, not browser HTML5 tree construction.
    script/style subtrees are dropped, event/style attributes are removed,
    unsafe URL schemes are rejected, and unknown tags become transparent
    containers when serialized.
    """
    parser = _LightweightDomParser()
    parser.feed(html)
    parser.close()
    return parser.root


def html_text_content(node: HtmlNode) -> str:
    """Return decoded descendant text from a lightweight DOM node."""
    if node.kind == "text":
        return node.text
    return "".join(html_text_content(child) for child in (node.children or []))


def find_html_text(html: str, *, tag: str | None = None, attrs: dict[str, str] | None = None) -> str | None:
    """Return textContent-like decoded text for the first matching safe element.

    Matching is depth-first pre-order and attribute values use exact equality.
    No separators are inserted between descendant text nodes. Filters apply to
    the sanitized lightweight DOM; unsupported tags or filtered attributes
    raise ValueError instead of being confused with a missing element.
    """
    wanted_tag = tag.lower() if tag is not None else None
    wanted_attrs = attrs or {}
    normalized_attrs = {key.lower(): value for key, value in wanted_attrs.items()}
    if wanted_tag is not None and wanted_tag not in _DOM_SAFE_TAGS:
        raise ValueError(f"unsupported HTML tag filter: {tag!r}")
    unsupported_attrs = [key for key in wanted_attrs if key.lower() not in _DOM_COMMON_ATTRS and not key.lower().startswith("data-")]
    if unsupported_attrs:
        raise ValueError(f"unsupported HTML attribute filter(s): {', '.join(unsupported_attrs)}")
    if wanted_tag == "input" and normalized_attrs and normalized_attrs.get("type", "").lower() != "checkbox":
        raise ValueError("attribute filters for input require type=checkbox")
    root = parse_html_dom(html)

    def walk(node: HtmlNode) -> HtmlNode | None:
        if node.kind == "element":
            node_attrs = node.attrs or {}
            if ((wanted_tag is None or node.tag == wanted_tag)
                    and all(node_attrs.get(key.lower()) == value for key, value in wanted_attrs.items())):
                return node
        for child in node.children or []:
            found = walk(child)
            if found is not None:
                return found
        return None

    found = walk(root)
    return None if found is None else html_text_content(found)


def dom_to_html(node: HtmlNode) -> str:
    """Serialize a lightweight DOM tree to sanitized HTML."""

    def render(current: HtmlNode) -> str:
        if current.kind == "text":
            return html_module.escape(current.text, quote=False)
        children = "".join(render(child) for child in (current.children or []))
        if current.kind == "root":
            return children
        if current.kind != "element":
            return children
        tag = current.tag.lower()
        if tag not in _DOM_SAFE_TAGS:
            return children
        attrs = current.attrs or {}
        if tag == "a" and not attrs.get("href"):
            return children
        if tag == "img" and not attrs.get("src"):
            return html_module.escape(attrs.get("alt", ""), quote=False)
        attr_text = "".join(
            (f' {key}="{html_module.escape(str(value), quote=True)}"'
             if value != "" else f" {key}")
            for key, value in sorted(attrs.items())
        )
        if tag in _DOM_VOID_TAGS:
            return f"<{tag}{attr_text} />"
        return f"<{tag}{attr_text}>{children}</{tag}>"

    return render(node)


def _dom_details_to_markdown(node: HtmlNode) -> str:
    summary = "Details"
    body_nodes: list[HtmlNode] = []
    for child in node.children or []:
        if child.kind == "element" and child.tag == "summary":
            summary = _html_to_markdown_impl(dom_to_html(child)).strip() or "Details"
        else:
            body_nodes.append(child)
    body_root = HtmlNode("root", children=body_nodes)
    body = _html_to_markdown_impl(dom_to_html(body_root)).strip()
    if body:
        return f":::details {summary}\n{body}\n:::\n"
    return f":::details {summary}\n:::\n"


def dom_to_markdown(node: HtmlNode) -> str:
    """Convert a lightweight DOM tree to normalized Markdown.

    Existing html_to_markdown remains the compatibility engine. details is
    handled explicitly so the DOM path preserves the repository contract.
    """
    if node.kind == "element" and node.tag == "details":
        return _dom_details_to_markdown(node)
    if node.kind == "root":
        parts: list[str] = []
        pending: list[HtmlNode] = []

        def flush_pending() -> None:
            if not pending:
                return
            fragment = HtmlNode("root", children=list(pending))
            converted = _html_to_markdown_impl(dom_to_html(fragment))
            if converted.strip():
                parts.append(converted.strip())
            pending.clear()

        for child in node.children or []:
            if child.kind == "element" and child.tag == "details":
                flush_pending()
                parts.append(_dom_details_to_markdown(child).strip())
            else:
                pending.append(child)
        flush_pending()
        return "\n\n".join(part for part in parts if part).strip() + ("\n" if parts else "")
    return _html_to_markdown_impl(dom_to_html(node))


def markdown_to_dom(content: str) -> HtmlNode:
    """Convert the repository supported Markdown subset to HtmlNode."""
    return parse_html_dom(markdown_to_html(content))


class _HTMLToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._list_stack: list[str] = []
        self._li_index: list[int] = []
        self._in_pre = False
        self._in_code = False
        self._suppress = 0
        self._link_href = ""
        self._link_title = ""
        self._link_open = False
        self._table_depth = 0
        self._table_header: list[str] | None = None
        self._table_rows: list[list[str]] = []
        self._table_row: list[str] | None = None
        self._table_cell: list[str] | None = None
        self._table_row_is_header = False
        self._in_thead = False
        self._block_attr_suffixes: list[str] = []
        self._details_stack: list[dict[str, Any]] = []
        self._blockquote_paragraphs: list[int] = []
        self._skip_next_list_structural_whitespace = False
        self._protected_trailing_space_kind: str | None = None
        self._open_tags: list[str] = []

    def _emit(self, text: str, *, trailing_space_kind: str | None = None) -> None:
        if self._table_cell is not None:
            self._table_cell.append(text)
        elif self._table_depth:
            return
        else:
            self.parts.append(text)
        if text:
            self._protected_trailing_space_kind = trailing_space_kind

    def _trim_structural_boundary(self) -> None:
        """Drop source-formatting whitespace before a block boundary.

        Markdown syntax emitted by this parser can intentionally end in one
        space. Those spaces are tracked by provenance instead of inferred from
        the rendered text, so source text that merely looks similar is still
        normalized normally.
        """
        target = self._table_cell if self._table_cell is not None else self.parts
        if not target or not target[-1]:
            return
        if self._protected_trailing_space_kind is not None:
            return
        target[-1] = target[-1].rstrip(" \t")

    def _flush_cell(self) -> None:
        if self._table_cell is None or self._table_row is None:
            self._table_cell = None
            return
        text = re.sub(r"\s+", " ", "".join(self._table_cell)).strip()
        text = text.replace("|", r"\|")
        self._table_row.append(text)
        self._table_cell = None

    def _flush_row(self) -> None:
        self._flush_cell()
        if self._table_row is None:
            return
        if self._in_thead or self._table_row_is_header:
            if self._table_header is None:
                self._table_header = self._table_row
            else:
                self._table_rows.append(self._table_row)
        else:
            self._table_rows.append(self._table_row)
        self._table_row = None
        self._table_row_is_header = False

    def _table_to_markdown(self) -> str:
        self._flush_row()
        rows = self._table_rows
        header = self._table_header
        if header is None:
            if not rows:
                return ""
            width = max(len(row) for row in rows)
            if width == 0:
                return ""
            header = [""] * width
        width = len(header)
        if width == 0:
            return ""

        def fmt(cells: list[str]) -> str:
            padded = list(cells[:width]) + [""] * (width - min(len(cells), width))
            return "| " + " | ".join(padded) + " |"

        lines = [fmt(header), "| " + " | ".join(["---"] * width) + " |"]
        for row in rows:
            lines.append(fmt(row))
        return "\n\n" + "\n".join(lines) + "\n\n"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        parent_tag = self._open_tags[-1] if self._open_tags else None
        if tag not in _HTML_VOID_TAGS:
            self._open_tags.append(tag)
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag in {"script", "style"}:
            self._suppress += 1
            return
        if self._suppress:
            return
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._table_header = None
                self._table_rows = []
                self._table_row = None
                self._table_cell = None
                self._table_row_is_header = False
                self._in_thead = False
            return
        if self._table_depth > 1 and tag in {
            "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col",
        }:
            return
        if tag == "thead":
            if self._table_depth == 1:
                self._in_thead = True
            return
        if tag == "tr":
            if self._table_depth == 1:
                self._flush_row()
                self._table_row = []
                self._table_row_is_header = False
            return
        if tag in {"td", "th"}:
            if self._table_depth != 1:
                return
            if self._table_row is None:
                self._table_row = []
                self._table_row_is_header = False
            self._flush_cell()
            self._table_cell = []
            if tag == "th":
                self._table_row_is_header = True
            return
        if tag in {"tbody", "tfoot", "caption", "colgroup", "col"}:
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._trim_structural_boundary()
            level = int(tag[1])
            self._emit("\n\n" + ("#" * level) + " ")
            self._block_attr_suffixes.append(_html_attrs_to_pandoc_suffix(attr))
        elif tag == "p":
            self._trim_structural_boundary()
            if parent_tag == "blockquote" and self._blockquote_paragraphs:
                if self._blockquote_paragraphs[-1] > 0:
                    self._emit(
                        "\n>\n> ",
                        trailing_space_kind="blockquote-prefix",
                    )
                self._blockquote_paragraphs[-1] += 1
                self._block_attr_suffixes.append(_html_attrs_to_pandoc_suffix(attr))
            else:
                self._emit("\n\n")
                self._block_attr_suffixes.append(_html_attrs_to_pandoc_suffix(attr))
        elif tag == "br":
            self._emit("  \n")
        elif tag == "hr":
            self._emit("\n\n---\n\n")
        elif tag in {"strong", "b"}:
            self._emit("**")
        elif tag in {"em", "i"}:
            self._emit("*")
        elif tag in {"del", "s"}:
            self._emit("~~")
        elif tag == "code" and not self._in_pre:
            self._emit("`")
            self._in_code = True
        elif tag == "pre":
            self._in_pre = True
            self._emit("\n\n```\n")
        elif tag == "a":
            safe_href = _sanitize_url_scheme(attr.get("href", ""))
            if safe_href:
                self._emit("[")
                self._link_href = safe_href
                self._link_title = attr.get("title", "")
                self._link_open = True
            else:
                self._link_href = ""
                self._link_title = ""
                self._link_open = False
        elif tag == "img":
            alt = attr.get("alt", "")
            safe_src = _sanitize_url_scheme(attr.get("src", ""))
            if safe_src:
                self._emit(
                    make_image(
                        alt,
                        safe_src,
                        attr.get("title") or None,
                    )
                )
            else:
                self._emit(alt)
        elif tag == "input":
            if attr.get("type", "").lower() == "checkbox":
                mark = "x" if "checked" in attr else " "
                self._emit(f"[{mark}]")
        elif tag == "blockquote":
            self._blockquote_paragraphs.append(0)
            self._emit(
                "\n\n> ",
                trailing_space_kind="blockquote-prefix",
            )
        elif tag in {"ul", "ol"}:
            if self._list_stack:
                target = self._table_cell if self._table_cell is not None else self.parts
                if (
                    target
                    and target[-1]
                    and self._protected_trailing_space_kind != "list-marker"
                ):
                    target[-1] = target[-1].rstrip()
            self._list_stack.append(tag)
            self._li_index.append(0)
            if len(self._list_stack) == 1:
                self._emit("\n")
        elif tag == "li":
            self._trim_structural_boundary()
            depth = max(len(self._list_stack) - 1, 0)
            indent = "  " * depth
            kind = self._list_stack[-1] if self._list_stack else "ul"
            if kind == "ol":
                self._li_index[-1] += 1
                bullet = f"{self._li_index[-1]}."
            else:
                bullet = "-"
            self._emit(
                f"\n{indent}{bullet} ",
                trailing_space_kind="list-marker",
            )
        elif tag == "details":
            # A fenced :::details block cannot live safely inside one GFM table
            # cell. Preserve the pre-#41 behavior there by flattening the
            # contents instead of reconstructing a multiline container.
            special = self._table_cell is None
            self._details_stack.append(
                {
                    "special": special,
                    "start": len(self.parts) if special else None,
                    "summary_start": None,
                    "summary": "Details",
                }
            )
        elif tag == "summary" and self._details_stack:
            current = self._details_stack[-1]
            if current.get("special") and parent_tag == "details":
                current["summary_start"] = len(self.parts)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        implicitly_closed: list[str] = []
        matched_open_tag = False
        for index in range(len(self._open_tags) - 1, -1, -1):
            if self._open_tags[index] == tag:
                matched_open_tag = True
                implicitly_closed = self._open_tags[index + 1:]
                del self._open_tags[index:]
                break

        # html.parser does not synthesize end-tag callbacks for malformed
        # descendants. The lightweight DOM path nevertheless serializes those
        # descendants as balanced HTML before conversion. Mirror that narrow
        # recovery for inline Markdown delimiters when an ancestor closes.
        for implicit_tag in reversed(implicitly_closed):
            if implicit_tag in {"strong", "b"}:
                self._emit("**")
            elif implicit_tag in {"em", "i"}:
                self._emit("*")
            elif implicit_tag in {"del", "s"}:
                self._emit("~~")
            elif implicit_tag == "code" and self._in_code and not self._in_pre:
                self._emit("`")
                self._in_code = False
        if tag in {"script", "style"}:
            self._suppress = max(0, self._suppress - 1)
            return
        if self._suppress:
            return
        if tag == "table":
            if self._table_depth == 1:
                markdown = self._table_to_markdown()
                self._table_depth = 0
                self._table_cell = None
                self._table_row = None
                if markdown:
                    self.parts.append(markdown)
            elif self._table_depth > 1:
                self._table_depth -= 1
            return
        if self._table_depth > 1 and tag in {
            "thead", "tbody", "tfoot", "tr", "td", "th", "caption", "colgroup", "col",
        }:
            return
        if tag == "thead":
            if self._table_depth == 1:
                self._flush_row()
                self._in_thead = False
            return
        if tag == "tr":
            if self._table_depth == 1:
                self._flush_row()
            return
        if tag in {"td", "th"}:
            if self._table_depth == 1:
                self._flush_cell()
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p"}:
            self._trim_structural_boundary()
            suffix = (
                self._block_attr_suffixes.pop()
                if self._block_attr_suffixes
                else ""
            )
            if suffix:
                self._emit(suffix)
            if tag == "p" and self._blockquote_paragraphs:
                parent_tag = self._open_tags[-1] if self._open_tags else None
                if parent_tag == "blockquote":
                    return
            self._emit("\n\n")
        elif tag in {"strong", "b"} and matched_open_tag:
            self._emit("**")
        elif tag in {"em", "i"} and matched_open_tag:
            self._emit("*")
        elif tag in {"del", "s"} and matched_open_tag:
            self._emit("~~")
        elif tag == "code" and matched_open_tag and self._in_code and not self._in_pre:
            self._emit("`")
            self._in_code = False
        elif tag == "pre":
            self._emit("\n```\n\n")
            self._in_pre = False
        elif tag == "a" and self._link_open:
            if self._link_title:
                self._emit(f']({self._link_href} "{self._link_title}")')
            else:
                self._emit(f"]({self._link_href})")
            self._link_open = False
        elif tag == "summary" and self._details_stack:
            current = self._details_stack[-1]
            summary_start = current.get("summary_start")
            if current.get("special") and isinstance(summary_start, int):
                summary = "".join(self.parts[summary_start:]).strip()
                del self.parts[summary_start:]
                current["summary"] = summary or "Details"
                current["summary_start"] = None
        elif tag == "details" and self._details_stack:
            current = self._details_stack.pop()
            if current.get("special"):
                start = current.get("start")
                if isinstance(start, int):
                    body = "".join(self.parts[start:])
                    del self.parts[start:]
                    body = re.sub(r"\n{3,}", "\n\n", body).strip()
                    summary = str(current.get("summary") or "Details")
                    if body:
                        self._emit(f"\n\n:::details {summary}\n{body}\n:::\n\n")
                    else:
                        self._emit(f"\n\n:::details {summary}\n:::\n\n")
        elif tag == "blockquote":
            if self._blockquote_paragraphs:
                self._blockquote_paragraphs.pop()
            self._emit("\n\n")
        elif tag in {"ul", "ol"}:
            if self._list_stack:
                self._list_stack.pop()
            if self._li_index:
                self._li_index.pop()
            if self._list_stack:
                self._skip_next_list_structural_whitespace = True
            else:
                self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._suppress:
            return
        if self._table_depth and self._table_cell is None:
            return
        if self._skip_next_list_structural_whitespace:
            self._skip_next_list_structural_whitespace = False
            if not data.strip():
                return
        if (
            not data.strip()
            and self._open_tags
            and self._open_tags[-1] in {"blockquote", "ul", "ol"}
        ):
            return
        if self._in_pre or self._in_code:
            self._emit(data)
        else:
            collapsed = re.sub(r"\s+", " ", data)
            # HTML comments and transparent/ignored markup can split what is
            # semantically one whitespace run into multiple handle_data()
            # callbacks. Coalesce that boundary so legacy conversion matches
            # the DOM path, which removes such nodes before re-serialization.
            target = self._table_cell if self._table_cell is not None else self.parts
            if (
                collapsed.startswith(" ")
                and target
                and target[-1]
                and target[-1][-1].isspace()
            ):
                collapsed = collapsed[1:]
            if collapsed:
                self._emit(collapsed)

    def output(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"\n{3,}", "\n\n", text)
        normalized = text.strip()
        return normalized + "\n" if normalized else ""


def _html_to_markdown_impl(html: str) -> str:
    """Conservatively convert common HTML tags to Markdown.

    Simple ``<table>`` trees become GFM pipe tables (``| a | b |`` plus a
    ``| --- |`` separator). ``<thead>`` / ``<th>`` rows are headers;
    headerless tables use an empty header row so every ``<td>`` row stays
    data (GFM cannot represent a table with no header). ``|`` inside cells
    is escaped as ``\\|``. Nested tables flatten to cell text; ``colspan`` /
    ``rowspan`` and ``<caption>`` are ignored.

    ``<del>`` (and ``<s>``) become ``~~text~~``. A checkbox
    ``<input type="checkbox">`` (optional ``checked``) becomes ``[ ]`` /
    ``[x]``, which pairs with ``<li>`` as ``- [ ]`` / ``- [x]``.

    ``id`` / ``class`` (and other simple key=value attrs except ``style``)
    on ``<h1>``–``<h6>`` and ``<p>`` become a trailing Pandoc-style
    ``{#id .class key="value"}`` so :func:`markdown_to_kramdown` can attach
    a Kramdown IAL. This is not applied to tables, lists, or other tags.
    """
    parser = _HTMLToMarkdownParser()
    parser.feed(html)
    parser.close()
    return parser.output()



def markdown_to_web_ui_v1(
    content: str,
    *,
    title: str | None = None,
    theme: Literal["modern", "github-like"] = "modern",
) -> str:
    """Render Markdown inside the stable web-ui HTML contract v1 surface.

    This emits semantic HTML only. It does not fetch or embed web-ui CSS and
    therefore preserves this module's single-file, standard-library-only
    runtime contract. Consumers may load their pinned web-ui assets separately.

    ``theme`` is case-sensitive and limited to the currently frozen v1 theme values.
    ``title`` is escaped as text. Markdown body conversion follows
    ``markdown_to_html`` and its documented supported subset.
    """
    if theme not in {"modern", "github-like"}:
        raise ValueError("theme must be 'modern' or 'github-like'")
    body = markdown_to_html(content)
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>',
        f'<body data-ui-theme="{theme}">',
        '<main class="ui-page">',
    ]
    # The title is optional by contract; the body wrapper is always emitted.
    if title is not None:
        parts.append(f'<h1 class="ui-title">{html_module.escape(title)}</h1>')
    parts.extend([
        '<section class="ui-panel">',
        body,
        "</section>",
        "</main>",
        "</body>",
        "</html>",
    ])
    return "\n".join(parts)

def html_to_markdown(html: str) -> str:
    """Conservatively convert common HTML tags to Markdown.

    This public compatibility entry point intentionally delegates to the
    legacy parser engine. Keeping the engine separate lets DOM conversion
    reuse the same implementation without creating a future recursion loop.
    """
    return _html_to_markdown_impl(html)


def _escape_html_text(text: str) -> str:
    return html_module.escape(text, quote=False)


def _angle_autolink_html(url: str) -> str:
    """Render a safe stashed angle autolink; unsafe URLs degrade to text."""
    safe_url = _sanitize_url_scheme(url)
    text = html_module.escape(url)
    if not safe_url:
        return text
    href = html_module.escape(safe_url, quote=True)
    return f'<a href="{href}">{text}</a>'


def _parse_task_item(item: str) -> tuple[bool, str] | None:
    """Return ``(checked, rest)`` for a GFM task marker, else ``None``.

    Only the item body is inspected (list marker already stripped).
    ``[ ]`` is unchecked; ``[x]`` / ``[X]`` are checked. A following
    description needs whitespace after ``]``; ``- [x]done`` is not a task.
    """
    match = _TASK_ITEM_RE.match(item)
    if not match:
        return None
    checked = match.group(1) in "xX"
    rest = match.group(2) or ""
    return checked, rest


def _task_checkbox_html(checked: bool) -> str:
    if checked:
        return '<input type="checkbox" disabled checked />'
    return '<input type="checkbox" disabled />'


def _unquote_blockquote_line(line: str) -> str | None:
    match = _BLOCKQUOTE_PREFIX_RE.match(line)
    if not match:
        return None
    return match.group(2)


def _blockquote_alert_info(line: str) -> dict[str, str] | None:
    match = _BLOCKQUOTE_ALERT_RE.match(line)
    if not match:
        return None
    raw_kind = match.group(1)
    fold = match.group(2) or ""
    title = (match.group(3) or "").strip()
    github_shaped = (
        raw_kind in _GITHUB_ALERT_KIND_SET and not fold and not title
    )
    if github_shaped:
        return {
            "flavor": "github",
            "kind": raw_kind,
            "title": raw_kind,
            "fold": "",
        }
    return {
        "flavor": "obsidian",
        "kind": raw_kind.lower(),
        "title": title,
        "fold": fold,
    }


def _qiita_note_kind(line: str) -> str | None:
    match = _QIITA_NOTE_OPEN_RE.match(line)
    if not match:
        return None
    return (match.group(1) or "info").lower()


def _zenn_message_kind(line: str) -> str | None:
    match = _ZENN_MESSAGE_OPEN_RE.match(line)
    if not match:
        return None
    return (match.group(1) or "message").lower()


def _is_alert_block_open(line: str) -> bool:
    return bool(
        _blockquote_alert_info(line)
        or _qiita_note_kind(line) is not None
        or _zenn_message_kind(line) is not None
        or _details_open_summary(line) is not None
    )


def _details_open_summary(line: str) -> str | None:
    """Return the summary text if ``line`` opens a ``:::details`` block."""
    match = _DETAILS_OPEN_RE.match(line)
    if not match:
        return None
    return (match.group(1) or "").strip()


def _footnote_slug(ident: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", ident).strip("-")
    return slug or "note"


def _collect_footnote_definitions(lines: list[str]) -> tuple[list[str], dict[str, str]]:
    """Strip ``[^id]:`` definitions (except inside fences); first id wins.

    Indented (2+ spaces or a tab) lines immediately after a definition are
    continuations. A blank line or a non-indented line ends the note.
    """
    defs: dict[str, str] = {}
    kept: list[str] = []
    i = 0
    in_fence: str | None = None
    while i < len(lines):
        line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            mark = fence.group(1)
            if in_fence is None:
                in_fence = mark
            elif line.startswith(in_fence):
                in_fence = None
            kept.append(line)
            i += 1
            continue
        if in_fence:
            kept.append(line)
            i += 1
            continue
        match = _FOOTNOTE_DEF_RE.match(line)
        if match:
            ident = match.group(1)
            parts = [match.group(2)]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    break
                if _FOOTNOTE_DEF_RE.match(nxt):
                    break
                cont = _FOOTNOTE_CONT_RE.match(nxt)
                if not cont:
                    break
                parts.append(cont.group(1).strip())
                i += 1
            if ident not in defs:
                defs[ident] = " ".join(p for p in parts if p).strip()
            continue
        kept.append(line)
        i += 1
    return kept, defs


def _footnote_ref_html(ident: str, number: int, *, with_id: bool) -> str:
    slug = html_module.escape(_footnote_slug(ident), quote=True)
    label = html_module.escape(str(number))
    if with_id:
        return (
            f'<sup class="footnote-ref">'
            f'<a href="#fn-{slug}" id="fnref-{slug}">{label}</a>'
            f"</sup>"
        )
    return (
        f'<sup class="footnote-ref">'
        f'<a href="#fn-{slug}">{label}</a>'
        f"</sup>"
    )


def _footnotes_section_html(
    order: list[str],
    defs: dict[str, str],
    render_inline,
) -> str:
    items: list[str] = ['<section class="footnotes">', "<ol>"]
    for ident in order:
        slug = html_module.escape(_footnote_slug(ident), quote=True)
        note = render_inline(defs.get(ident, ""))
        items.append(
            f'<li id="fn-{slug}">{note}'
            f' <a href="#fnref-{slug}" class="footnote-backref">↩</a></li>'
        )
    items.append("</ol>")
    items.append("</section>")
    return "\n".join(items)


def _consume_details(
    lines: list[str],
    start: int,
    summary: str,
    render_inline,
) -> tuple[str, int]:
    """Collect a ``:::details`` block into ``<details><summary>``.

    Body lines become paragraphs (blank lines split them). Inner ATX /
    lists / nested ``:::details`` stay paragraph text — the first ``:::``
    closer ends the block.
    """
    i = start + 1
    body_lines: list[str] = []
    while i < len(lines) and not _COLON_CONTAINER_CLOSE_RE.match(lines[i]):
        body_lines.append(lines[i])
        i += 1
    if i < len(lines) and _COLON_CONTAINER_CLOSE_RE.match(lines[i]):
        i += 1

    paragraphs: list[list[str]] = [[]]
    for raw in body_lines:
        if not raw.strip():
            if paragraphs[-1]:
                paragraphs.append([])
            continue
        paragraphs[-1].append(raw)

    parts = ["<details>", f"<summary>{render_inline(summary)}</summary>"]
    for para in paragraphs:
        if not para:
            continue
        text = " ".join(s.strip() for s in para)
        parts.append(f"<p>{render_inline(text)}</p>")
    parts.append("</details>")
    return "\n".join(parts), i


def _alert_aside_html(
    *,
    flavor: str,
    kind: str,
    title: str,
    body_markdown: str,
    fold: str = "",
    render_inline,
) -> str:
    kind_slug = kind.lower()
    kind_token = html_module.escape(kind.upper(), quote=True)
    flavor_token = html_module.escape(flavor, quote=True)
    css_kind = html_module.escape(kind_slug, quote=True)
    attrs = [
        f'class="markdown-alert markdown-alert-{css_kind}"',
        f'data-alert="{kind_token}"',
        f'data-alert-flavor="{flavor_token}"',
    ]
    if fold == "+":
        attrs.append('data-alert-fold="open"')
    elif fold == "-":
        attrs.append('data-alert-fold="closed"')
    display_title = title if title else kind.upper()
    parts = [
        f"<aside {' '.join(attrs)}>",
        f'<p class="markdown-alert-title">{render_inline(display_title)}</p>',
    ]
    body = body_markdown.strip("\n")
    if body.strip():
        body_html = markdown_to_html(body).rstrip("\n")
        if body_html:
            parts.append(body_html)
    parts.append("</aside>")
    return "\n".join(parts)


def _consume_blockquote_alert(
    lines: list[str],
    start: int,
    info: dict[str, str],
    render_inline,
) -> tuple[str, int]:
    i = start + 1
    body_lines: list[str] = []
    while i < len(lines):
        unquoted = _unquote_blockquote_line(lines[i])
        if unquoted is None:
            break
        body_lines.append(unquoted)
        i += 1
    html = _alert_aside_html(
        flavor=info["flavor"],
        kind=info["kind"],
        title=info["title"],
        body_markdown="\n".join(body_lines),
        fold=info["fold"],
        render_inline=render_inline,
    )
    return html, i


def _consume_colon_alert(
    lines: list[str],
    start: int,
    *,
    flavor: str,
    kind: str,
    render_inline,
) -> tuple[str, int]:
    i = start + 1
    body_lines: list[str] = []
    while i < len(lines) and not _COLON_CONTAINER_CLOSE_RE.match(lines[i]):
        body_lines.append(lines[i])
        i += 1
    if i < len(lines) and _COLON_CONTAINER_CLOSE_RE.match(lines[i]):
        i += 1
    title = kind.upper()
    html = _alert_aside_html(
        flavor=flavor,
        kind=kind,
        title=title,
        body_markdown="\n".join(body_lines),
        render_inline=render_inline,
    )
    return html, i


def _split_table_row(line: str) -> list[str]:
    """Split a GFM pipe row into cells.

    Leading/trailing pipes are optional. A ``\\|`` sequence stays one cell
    (the backslash is dropped). This is the same split ``table()`` output
    round-trips through; it is not a full GFM cell lexer.
    """
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    before_last = stripped[:-1] if stripped.endswith("|") else stripped
    trailing_slashes = len(before_last) - len(before_last.rstrip("\\"))
    if stripped.endswith("|") and trailing_slashes % 2 == 0:
        stripped = stripped[:-1]
    cells: list[str] = []
    cell: list[str] = []
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) and stripped[index + 1] in {"\\", "|"}:
            cell.append(stripped[index + 1])
            index += 2
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell = []
        else:
            cell.append(char)
        index += 1
    cells.append("".join(cell).strip())
    return cells


def _looks_like_table_row(line: str) -> bool:
    return "|" in line.strip()


def _is_table_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = _split_table_row(line)
    if not cells:
        return False
    return all(_TABLE_SEP_CELL_RE.match(cell.replace(" ", "")) for cell in cells)


def _is_table_start(lines: list[str], index: int) -> bool:
    """True when ``lines[index]`` is a header row followed by a ``| --- |`` delimiter.

    List markers, headings, fences, thematic breaks, and ``>`` quotes are
    not treated as headers, so a malformed ``- a | b`` line stays a list.
    A pipe row with no delimiter after it stays a paragraph (safe degrade).
    """
    if index + 1 >= len(lines):
        return False
    header = lines[index]
    if not header.strip() or not _looks_like_table_row(header):
        return False
    if (
        _HEADING_RE.match(header)
        or _FENCE_RE.match(header)
        or _HR_RE.match(header)
        or _unquote_blockquote_line(header) is not None
        or _LIST_ITEM_RE.match(header)
        or _is_alert_block_open(header)
    ):
        return False
    return _is_table_separator(lines[index + 1])


def _table_html(
    headers: list[str],
    rows: list[list[str]],
    render_inline,
) -> str:
    width = len(headers)

    def row_html(tag: str, cells: list[str]) -> str:
        padded = list(cells[:width]) + [""] * (width - min(len(cells), width))
        inner = "".join(f"<{tag}>{render_inline(cell)}</{tag}>" for cell in padded)
        return f"<tr>{inner}</tr>"

    parts = ["<table>", "<thead>", row_html("th", headers), "</thead>", "<tbody>"]
    for row in rows:
        parts.append(row_html("td", row))
    parts.append("</tbody>")
    parts.append("</table>")
    return "\n".join(parts)


def _consume_table(
    lines: list[str],
    start: int,
    render_inline,
) -> tuple[str, int]:
    headers = _split_table_row(lines[start])
    i = start + 2
    rows: list[list[str]] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip() or not _looks_like_table_row(line):
            break
        if (
            _HEADING_RE.match(line)
            or _FENCE_RE.match(line)
            or _HR_RE.match(line)
            or _unquote_blockquote_line(line) is not None
            or _is_alert_block_open(line)
        ):
            break
        rows.append(_split_table_row(line))
        i += 1
    return _table_html(headers, rows, render_inline), i


def _consume_blockquote(
    lines: list[str],
    start: int,
    render_inline,
) -> tuple[str, int]:
    """Collect consecutive ``>`` lines into a ``<blockquote>``.

    Blank ``>`` / ``> `` lines split paragraphs. Inner ATX headings, lists,
    nested quotes, and tables are **not** re-parsed as blocks -- they stay
    paragraph text -- so GitLab ``>>>`` openers cannot collapse into alerts.
    A later ``> [!TYPE]`` line ends this quote so the alert handler can win.
    """
    i = start
    body_lines: list[str] = []
    while i < len(lines):
        unquoted = _unquote_blockquote_line(lines[i])
        if unquoted is None:
            break
        if i > start and _blockquote_alert_info(lines[i]):
            break
        body_lines.append(unquoted)
        i += 1

    paragraphs: list[list[str]] = [[]]
    for raw in body_lines:
        if not raw.strip():
            if paragraphs[-1]:
                paragraphs.append([])
            continue
        paragraphs[-1].append(raw)

    parts = ["<blockquote>"]
    for para in paragraphs:
        if not para:
            continue
        text = " ".join(s.strip() for s in para)
        parts.append(f"<p>{render_inline(text)}</p>")
    parts.append("</blockquote>")
    return "\n".join(parts), i


def markdown_to_html(content: str) -> str:
    """Conservatively convert a Markdown *subset* to HTML.

    Handles ATX headings, fenced code, paragraphs, inline code, bold/italic,
    strikethrough (``~~text~~`` → ``<del>``), links, images, angle-bracket
    http(s) autolinks, thematic breaks, simple indentation-based nested
    bullet/numbered lists, nested GFM task lists, ordinary ``>`` blockquotes, simple GFM pipe tables,
    GitHub / Qiita / Zenn / Obsidian alerts, Zenn-style ``:::details``
    collapsible sections, and a small GFM/Pandoc-like footnote subset.

    Alerts render to a shared ``<aside>`` shape. Pair with
    ``default_stylesheet()`` (or ``alert_stylesheet()``) if you want CSS::

        <style>{default_stylesheet()}</style>
        <aside class="markdown-alert markdown-alert-note"
               data-alert="NOTE" data-alert-flavor="github">
        <p class="markdown-alert-title">NOTE</p>
        <p>…body…</p>
        </aside>

    Classification:

    - ``> [!NOTE]`` (uppercase GitHub kinds, no same-line title, no fold)
      is ``data-alert-flavor="github"``.
    - Other ``> [!type]`` markers (lowercase, extra types, optional title,
      ``+``/``-`` fold) are ``obsidian``. GitLab's lowercase five-kind
      form therefore parses as Obsidian; its ``>>>`` multiline alerts are
      not recognized.
    - ``:::note`` / ``:::note info|warn|alert`` … ``:::`` is ``qiita``.
    - ``:::message`` / ``:::message alert`` … ``:::`` is ``zenn``.
    - ``:::details Summary`` … ``:::`` becomes ``<details><summary>``.
      Nested inlines in the summary and body are parsed; nested blocks
      stay paragraph text. Raw HTML ``<details>`` stays escaped.
    - Ordinary ``>`` lines that are not an alert opener become
      ``<blockquote>`` (multi-line; blank ``>`` lines split paragraphs).
      Nested block constructs inside the quote are not parsed.
    - A header row followed by a ``| --- |`` delimiter row becomes
      ``<table>``. Cell text is escaped, then the same inline renderer
      used for paragraphs is applied (bold / italic / code / links / images
      / strikethrough / angle autolinks / footnotes). Pipe rows without
      that delimiter stay paragraphs.
    - ``~~text~~`` becomes ``<del>text</del>``. Unmatched ``~~`` stays
      literal; ``~~a~~b~~`` takes the first pair. Nested bold/italic
      inside or around a pair is applied.
    - Unordered ``-`` / ``*`` / ``+`` items whose body is ``[ ]`` /
      ``[x]`` / ``[X]`` (optional description after whitespace) become
      ``<li>`` with ``<input type="checkbox" disabled>`` (``checked``
      for x/X). The box is not interactive. Task items and ordinary
      bullets in the same list stay one ``<ul>`` with mixed ``<li>``
      shapes. ``1. [ ]`` stays ordinary ordered-list text.
    - ``<https://...>`` / ``<http://...>`` become ``<a href="...">``.
      Bare URLs, ``mailto:``, and ordinary ``<tag>`` (including
      ``<script>``) are not autolinks; non-URL angle brackets stay
      escaped. ``[text](url)`` links still win when both forms appear.
    - ``[^id]`` plus a ``[^id]: note`` definition become a superscript
      link and a trailing ``<section class="footnotes">``. Undefined
      refs stay literal. Duplicate ids: first definition wins. Unused
      defs are dropped. Only indented (2+ spaces / tab) continuation
      is kept; unindented wrapping is a new paragraph.

    Unknown GitHub/Qiita/Zenn kinds are not generated (``alert()`` raises);
    unknown Obsidian types still parse as Obsidian callouts (matching
    Obsidian's custom-type support).
    """
    source_lines = content.splitlines()
    lines, footnote_defs = _collect_footnote_definitions(source_lines)
    footnote_order: list[str] = []
    footnote_ref_seen: set[str] = set()
    out: list[str] = []
    i = 0
    in_list: str | None = None

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append(f"</{in_list}>")
            in_list = None

    def render_inline(text: str) -> str:
        placeholders: list[str] = []

        def stash(snippet: str) -> str:
            placeholders.append(snippet)
            return f"\x00PH{len(placeholders) - 1}\x00"

        def replace_footnote(match: re.Match[str]) -> str:
            ident = match.group(1)
            if ident not in footnote_defs:
                return match.group(0)
            if ident not in footnote_order:
                footnote_order.append(ident)
            number = footnote_order.index(ident) + 1
            with_id = ident not in footnote_ref_seen
            if with_id:
                footnote_ref_seen.add(ident)
            return stash(_footnote_ref_html(ident, number, with_id=with_id))

        text = _INLINE_IMAGE_RE.sub(
            lambda m: stash(markdown_image_to_html(m.group(0))),
            text,
        )
        text = _INLINE_LINK_RE.sub(
            lambda m: stash(markdown_link_to_html(m.group(0))),
            text,
        )
        text = re.sub(
            r"`([^`]+)`",
            lambda m: stash(f"<code>{_escape_html_text(m.group(1))}</code>"),
            text,
        )
        text = _ANGLE_URL_RE.sub(
            lambda m: stash(_angle_autolink_html(m.group(1))),
            text,
        )
        text = _FOOTNOTE_REF_RE.sub(replace_footnote, text)
        text = _escape_html_text(text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
        text = _STRIKETHROUGH_RE.sub(r"<del>\1</del>", text)
        for index, snippet in enumerate(placeholders):
            text = text.replace(f"\x00PH{index}\x00", snippet)
        return text

    def consume_list(start: int) -> tuple[str, int]:
        """Consume one contiguous Markdown list, preserving simple nesting.

        Nesting is indentation-based and deliberately small: list items may
        contain child ul/ol lists, but arbitrary block content inside an item
        remains out of scope.
        """

        def match_list_line(index: int):
            if index >= len(lines):
                return None
            return re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[index])

        def kind_for(marker: str) -> str:
            return "ol" if marker.endswith(".") and marker[:-1].isdigit() else "ul"

        def render_item(kind: str, item: str) -> str:
            task = _parse_task_item(item) if kind == "ul" else None
            if task is None:
                return render_inline(item)
            checked, rest = task
            box = _task_checkbox_html(checked)
            body = render_inline(rest)
            return f"{box} {body}" if body else box

        def consume_level(index: int, indent: int, kind: str) -> tuple[list[str], int]:
            parts = [f"<{kind}>"]
            while index < len(lines):
                match = match_list_line(index)
                if match is None:
                    break
                current_indent = len(match.group(1).expandtabs(4))
                current_kind = kind_for(match.group(2))
                if current_indent < indent:
                    break
                if current_indent != indent or current_kind != kind:
                    break

                item = match.group(3)
                index += 1
                children: list[str] = []
                while index < len(lines):
                    child = match_list_line(index)
                    if child is None:
                        break
                    child_indent = len(child.group(1).expandtabs(4))
                    if child_indent <= indent:
                        break
                    child_kind = kind_for(child.group(2))
                    child_parts, index = consume_level(index, child_indent, child_kind)
                    children.extend(child_parts)

                body = render_item(kind, item)
                if children:
                    parts.append(f"<li>{body}")
                    parts.extend(children)
                    parts.append("</li>")
                else:
                    parts.append(f"<li>{body}</li>")

            parts.append(f"</{kind}>")
            return parts, index

        first = match_list_line(start)
        if first is None:
            return "", start
        indent = len(first.group(1).expandtabs(4))
        kind = kind_for(first.group(2))
        parts, end = consume_level(start, indent, kind)
        return "\n".join(parts), end

    def paragraph_interrupt(index: int) -> bool:
        line = lines[index]
        if not line.strip():
            return True
        if (
            _HEADING_RE.match(line)
            or _FENCE_RE.match(line)
            or _HR_RE.match(line)
            or _is_alert_block_open(line)
            or _unquote_blockquote_line(line) is not None
            or _is_table_start(lines, index)
        ):
            return True
        if re.match(r"^(\s*)[-*+]\s+", line) or re.match(r"^(\s*)\d+\.\s+", line):
            return True
        return False

    while i < len(lines):
        line = lines[i]
        fence = _FENCE_RE.match(line)
        if fence:
            close_list()
            fence_mark = fence.group(1)
            info = fence.group(2).strip()
            lang = info.split()[0] if info else ""
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith(fence_mark):
                body.append(lines[i])
                i += 1
            code = _escape_html_text("\n".join(body))
            cls = f' class="language-{html_module.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code}\n</code></pre>")
            i += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            close_list()
            level = len(heading.group(1))
            title = render_inline(heading.group(2).strip())
            out.append(f"<h{level}>{title}</h{level}>")
            i += 1
            continue

        if _HR_RE.match(line):
            close_list()
            out.append("<hr />")
            i += 1
            continue

        alert_info = _blockquote_alert_info(line)
        if alert_info:
            close_list()
            html, i = _consume_blockquote_alert(lines, i, alert_info, render_inline)
            out.append(html)
            continue

        qiita_kind = _qiita_note_kind(line)
        if qiita_kind is not None:
            close_list()
            html, i = _consume_colon_alert(
                lines,
                i,
                flavor="qiita",
                kind=qiita_kind,
                render_inline=render_inline,
            )
            out.append(html)
            continue

        zenn_kind = _zenn_message_kind(line)
        if zenn_kind is not None:
            close_list()
            html, i = _consume_colon_alert(
                lines,
                i,
                flavor="zenn",
                kind=zenn_kind,
                render_inline=render_inline,
            )
            out.append(html)
            continue

        details_summary = _details_open_summary(line)
        if details_summary is not None:
            close_list()
            html, i = _consume_details(lines, i, details_summary, render_inline)
            out.append(html)
            continue

        if _unquote_blockquote_line(line) is not None:
            close_list()
            html, i = _consume_blockquote(lines, i, render_inline)
            out.append(html)
            continue

        if _is_table_start(lines, i):
            close_list()
            html, i = _consume_table(lines, i, render_inline)
            out.append(html)
            continue

        ul = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        ol = re.match(r"^(\s*)\d+\.\s+(.*)$", line)
        if ul or ol:
            close_list()
            html, i = consume_list(i)
            out.append(html)
            continue

        if not line.strip():
            close_list()
            i += 1
            continue

        close_list()
        para = [line]
        i += 1
        while i < len(lines) and not paragraph_interrupt(i):
            para.append(lines[i])
            i += 1
        rendered_para: list[str] = []
        for index, raw in enumerate(para):
            rendered_para.append(render_inline(raw.strip()))
            if index + 1 < len(para):
                rendered_para.append("<br />" if raw.endswith("  ") else " ")
        out.append(f"<p>{''.join(rendered_para)}</p>")

    close_list()
    if footnote_order:
        out.append(_footnotes_section_html(footnote_order, footnote_defs, render_inline))
    return "\n".join(out) + ("\n" if out else "")

_ALERT_STYLESHEET = """\
.markdown-alert {
  padding: 0.75em 1em;
  margin: 1em 0;
  border-left: 0.25em solid #57606a;
  background: #f6f8fa;
}
.markdown-alert-title {
  font-weight: 700;
  margin: 0 0 0.35em;
}
.markdown-alert-note,
.markdown-alert-info,
.markdown-alert-message { border-left-color: #0969da; }
.markdown-alert-tip { border-left-color: #1a7f37; }
.markdown-alert-important { border-left-color: #8250df; }
.markdown-alert-warning,
.markdown-alert-warn { border-left-color: #9a6700; }
.markdown-alert-caution,
.markdown-alert-alert { border-left-color: #cf222e; }
.markdown-alert[data-alert-flavor="github"] { background: #f6f8fa; }
.markdown-alert[data-alert-flavor="obsidian"] { border-radius: 0.25em; }
.markdown-alert[data-alert-flavor="qiita"] { border-left-width: 0.35em; }
.markdown-alert[data-alert-flavor="zenn"] { background: #fff8f0; }
"""

_DEFAULT_STYLESHEET_REST = """\
table { border-collapse: collapse; margin: 1em 0; }
th, td { border: 1px solid #d0d7de; padding: 0.4em 0.8em; }
th { background: #f6f8fa; font-weight: 600; }
blockquote {
  margin: 1em 0;
  padding: 0 1em;
  border-left: 0.25em solid #d0d7de;
  color: #656d76;
}
pre, code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
pre {
  padding: 0.8em;
  overflow: auto;
  background: #f6f8fa;
  border-radius: 0.25em;
}
h1, h2, h3, h4, h5, h6 { margin-top: 1.25em; margin-bottom: 0.5em; }
del { text-decoration: line-through; }
li input[type="checkbox"] { margin: 0 0.35em 0 0; vertical-align: middle; }
details {
  margin: 1em 0;
  border: 1px solid #d0d7de;
  border-radius: 0.25em;
  padding: 0.5em 0.8em;
}
summary { cursor: pointer; font-weight: 600; }
.footnotes {
  margin-top: 2em;
  padding-top: 0.75em;
  border-top: 1px solid #d0d7de;
  font-size: 0.9em;
}
.footnotes ol { padding-left: 1.5em; }
sup.footnote-ref { font-size: 0.75em; line-height: 0; }
.footnote-backref { text-decoration: none; }
"""


def alert_stylesheet() -> str:
    """Return compact CSS for ``.markdown-alert`` HTML from ``markdown_to_html``.

    Covers the shared ``.markdown-alert`` / ``.markdown-alert-title`` hooks,
    kind colors (``note`` / ``tip`` / ``warning`` / Qiita ``warn`` / Zenn
    ``alert``, …), and ``data-alert-flavor`` distinctions. No external
    URLs or font files. Embed next to converted HTML::

        <style>{alert_stylesheet()}</style>
    """
    return _ALERT_STYLESHEET


def default_stylesheet() -> str:
    """Return compact CSS for ``markdown_to_html`` output, including alerts.

    Includes :func:`alert_stylesheet` plus defaults for tables, blockquotes,
    fenced/inline code, headings, strikethrough (``del``), task-list
    checkboxes, ``details``/``summary``, and ``.footnotes``. Stdlib string
    only; no external URLs.
    Typical embedding::

        html = "<style>" + default_stylesheet() + "</style>\\n" + markdown_to_html(src)
    """
    return _ALERT_STYLESHEET + _DEFAULT_STYLESHEET_REST


def is_probably_url(value: str) -> bool:
    """Return True if ``value`` looks like an http(s) URL."""
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
