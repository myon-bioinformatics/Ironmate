"""Build-free flow diagrams: JSON to static HTML, fragment or GitHub Mermaid."""
from __future__ import annotations
import argparse
from html import escape
import json
from pathlib import Path
import sys

MAX_INPUT = 256 * 1024
THEMES = ("modern", "github-like")

def _label(value, required=True, length=240):
    if not isinstance(value, str) or len(value) > length:
        raise ValueError("labels must be bounded strings")
    if any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("control characters or unpaired surrogates in label")
    if required and not value.strip():
        raise ValueError("empty label")
    return value

def _cards(value, kind):
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise ValueError(f"{kind} must contain 1..8 cards")
    result = []
    for card in value:
        if not isinstance(card, dict) or "title" not in card or set(card) - {"title", "note"}:
            raise ValueError("cards require title and optional note only")
        result.append({"title": _label(card["title"], length=120),
                       "note": _label(card.get("note", ""), required=False)})
    return result

def validate(spec):
    if not isinstance(spec, dict) or set(spec) - {"title", "sources_label", "sources", "steps"}:
        raise ValueError("expected flow object")
    return {"title": _label(spec.get("title", ""), length=120),
            "sources_label": _label(spec.get("sources_label", "Sources"), length=120),
            "sources": _cards(spec.get("sources"), "sources"),
            "steps": _cards(spec.get("steps"), "steps")}

def _card_html(card):
    title = '<strong class="ui-flow-card-title">' + escape(card["title"]) + '</strong>'
    note = ('<span class="ui-flow-card-note">' + escape(card["note"]) + '</span>') if card["note"] else ""
    return '<div class="ui-flow-card">' + title + note + '</div>'

def flow_html(spec):
    data = validate(spec)
    sources = "".join('<li class="ui-flow-source">' + _card_html(c) + '</li>' for c in data["sources"])
    steps = "".join('<li class="ui-flow-step">' + _card_html(c) + '</li>' for c in data["steps"])
    return ('<figure class="ui-flow" aria-label="' + escape(data["title"], quote=True) + '">'
            '<figcaption class="ui-flow-caption">' + escape(data["title"]) + '</figcaption>'
            '<ul class="ui-flow-sources" aria-label="' + escape(data["sources_label"], quote=True) + '">'
            + sources + '</ul><div class="ui-flow-arrow" aria-hidden="true">↓</div>'
            '<ol class="ui-flow-steps">' + steps + '</ol></figure>')

def _mermaid_label(value):
    entities = {'"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;",
                "[": "#91;", "]": "#93;", "\\": "#92;", "\n": "#10;"}
    return "".join(entities.get(char, char) for char in value)

def flow_mermaid(spec):
    data = validate(spec)
    lines = ["```mermaid", "flowchart TB",
             '    subgraph input["' + _mermaid_label(data["sources_label"]) + '"]',
             "        direction LR"]
    for i, card in enumerate(data["sources"]):
        label = _mermaid_label(card["title"])
        if card["note"]:
            label += "<br/>" + _mermaid_label(card["note"])
        lines.append(f'        S{i}["{label}"]')
    lines.append("    end")
    for i, card in enumerate(data["steps"]):
        label = _mermaid_label(card["title"])
        if card["note"]:
            label += "<br/>" + _mermaid_label(card["note"])
        lines.append(f'    T{i}["{label}"]')
    for i in range(len(data["sources"])):
        lines.append(f"    S{i} --> T0")
    for i in range(1, len(data["steps"])):
        lines.append(f"    T{i-1} --> T{i}")
    return "\n".join(lines + ["```", ""])

def flow_document(spec, *, asset_base=".", theme="github-like", embed_css=False):
    if theme not in THEMES:
        raise ValueError("unknown theme")
    if not isinstance(asset_base, str) or not asset_base or any(
        c in asset_base for c in ('<', '>', '"', "'", "\\", "?", "#", "\n", "\r")
    ) or ":" in asset_base or asset_base.startswith("//"):
        raise ValueError("asset_base must be a local path")
    assets = ["css/tokens.css", "css/base.css", "css/components.css",
              "css/flow.css", f"css/themes/{theme}.css"]
    if embed_css:
        root = Path(__file__).resolve().parents[1]
        styles = "\n".join((root / name).read_text(encoding="utf-8") for name in assets)
        if "</style" in styles.lower():
            raise ValueError("unsafe stylesheet")
        css = "<style>" + styles + "</style>"
    else:
        prefix = asset_base.rstrip("/")
        css = "".join('<link rel="stylesheet" href="' + escape(prefix + "/" + name, quote=True) + '">' for name in assets)
    data = validate(spec)
    return ('<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + escape(data["title"]) + '</title>' + css + '</head>'
            '<body data-ui-theme="' + theme + '"><main class="ui-page">'
            + flow_html(data) + '</main></body></html>\n')

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format", choices=("html", "mermaid", "fragment"), default="html")
    parser.add_argument("--theme", choices=THEMES, default="github-like")
    parser.add_argument("--asset-base", default=".")
    parser.add_argument("--embed-css", action="store_true")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT:
            raise ValueError("flow JSON is too large")
        spec = json.loads(raw.decode("utf-8"))
        if args.format == "mermaid":
            output = flow_mermaid(spec)
        elif args.format == "fragment":
            output = flow_html(spec) + "\n"
        else:
            output = flow_document(spec, asset_base=args.asset_base,
                                   theme=args.theme, embed_css=args.embed_css)
    except (UnicodeError, ValueError, OSError) as exc:
        parser.exit(2, f"flow diagram: {exc}\n")
    sys.stdout.write(output)

if __name__ == "__main__":
    main()
