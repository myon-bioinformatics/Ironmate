"""Regenerate the studio stylesheet, components and heatmap colors from PySaiyanWeBoo.

    uv run --group test python scripts/build_studio_css.py
    uv run --group test python scripts/build_studio_css.py --check  # exit 1 when generated parts are stale

The sheet is ``pysaiyanweboo.write_bundle`` output: ``core_css()`` (tokens, base, components) with PySaiyanWeBoo's ``green`` theme
(``CANDIDATE_THEMES``) + PySaiyanWeBoo's ``studio-pages.css``, this studio's layout: header and brand, the three-column
workspace, the board and its handles, the shelf cards, the inspector. Buttons, inputs, selects, textareas and
tables take the component look through ``class="ui-elements"`` on ``<body>``; nothing generic lives here.
The file is committed (the studio is served as static files and image_studio.py is stdlib-only), and
``tests/test_studio.py`` (``pysaiyanweboo.check_bundle``) fails when it drifts.

The 📱 page's 🖼️ stage and 🧭 pager are PySaiyanWeBoo components too (``pswb_parts()``): their stylesheets join the sheet, their
markup is ``PSWB_PARTS`` and their modules ride in studio.js as one classic script, each written here from the pinned commit.
The heatmap color module, the dot-art grid and the slide deck (check, JSON, template, page operations) also come from the same
pin and are embedded in studio.js.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from textwrap import indent

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio"

# The palette is PySaiyanWeBoo's "green" theme (CANDIDATE_THEMES; first built by hand here, now owned there, so
# `data-ui-theme` can switch it like any other theme). The pages' layout is PySaiyanWeBoo's too (``studio-pages.css``, first
# written here): its colours are the theme's tokens, so every palette, light or dark, draws the pages.
THEME = "green"

NOTE = "scripts/build_studio_css.py"

# Ironmate-specific controls not provided by the shared layout.
SLIDE_EDITOR_CSS = """#phone-inspector:not([hidden]){display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;min-width:0}
#phone-inspector label:not([hidden]){display:flex;align-items:center;gap:6px}
#phone-inspector input:not([type=checkbox]),#phone-inspector select{min-width:0;width:100%;font-size:16px}
#phone-grid:not([hidden]){display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:6px;flex:0 0 auto;width:100%}
#phone-grid>div{min-width:0}
#phone-grid .ui-stage,#phone-grid button{width:100%;max-width:100%;margin:0;position:relative;top:auto}
#phone-grid .ui-stage{outline:2px solid var(--ui-accent)}
#phone-grid button{padding:0;display:block}
@media(min-width:960px){#phone-grid:not([hidden]){width:calc(100vw - 376px);max-height:100dvh;overflow:auto}}"""


def bundles() -> dict[Path, dict]:
    """One stylesheet for every studio page: PySaiyanWeBoo's green theme on core_css, the components pswb_parts() uses, then
    the pages' layout, PySaiyanWeBoo's ``studio-pages.css`` (scoped by ``<body data-page="...">``; the slides page is
    ``data-page="studio slides"``)."""
    import pysaiyanweboo
    sheets = [*dict.fromkeys(sheet for name in PSWB for sheet in pysaiyanweboo.COMPONENTS[name]["css"]), "current-item.css", "studio-pages.css"]
    return {STUDIO / "style.css": {"theme": THEME, "extra_css": "\n".join([*map(pysaiyanweboo.css_source, sheets), SLIDE_EDITOR_CSS])}}


PSWB = ("stage", "pager", "labels-switch", "toolbar")  # 🧩 the PySaiyanWeBoo components the 📱 page uses


def classic_script(modules: str) -> str:
    script = re.sub(r"^export (?=(?:async )?function |const )", "", modules, flags=re.M)
    assert not re.search(r"^\s*(import|export)\b", script, flags=re.M), "a module PySaiyanWeBoo ships now imports or exports otherwise"
    return script


def toolbar(pysaiyanweboo, page: str) -> str:
    """🧰 A studio's toolbar (``studio_bundle.studio_toolbar(page)``: "slides" or "image") as PySaiyanWeBoo's ``toolbar_html``; the
    slide editor's file row ends with 💻 ⇄ 📱 (Image Studio's is in its top bar)."""
    sys.path.insert(0, str(ROOT))
    from ironlib import studio_bundle
    groups, inside, after = studio_bundle.studio_toolbar(page)
    if page == "slides":
        return pysaiyanweboo.toolbar_html(groups, label="道具", id="phone-toolbar", candidates_id="phone-candidates",
                                          inside={"file": pysaiyanweboo.labels_switch_html(id="labels-switch")}, after=after)
    return "        " + pysaiyanweboo.toolbar_html(groups, label="道具", id="studio-toolbar", candidates_id="studio-candidates",
                                                 inside=inside, after=after) + "\n"


def pswb_parts() -> dict[str, str]:
    """🧩 What the 📱 page takes from PySaiyanWeBoo: the 🖼️ stage (``{slide}`` marks where the slide goes), the 🧭 pager (one page; the
    browser keeps it in step with the deck) and the components' modules as one classic script, because the pages' CSP allows script
    files and no inline module: ``export`` dropped, wrapped, and ``pagerSet`` / ``pagerIndex`` left on ``globalThis.PySaiyanWeBoo``."""
    import pysaiyanweboo
    words = {"first": "最初のページ", "prev": "前のページ", "next": "次のページ", "last": "最後のページ", "page": "ページ"}
    modules = "".join(map(pysaiyanweboo.js_source, dict.fromkeys(m for name in PSWB for m in pysaiyanweboo.COMPONENTS[name]["js"])))  # each file once
    classic = classic_script(modules)
    commit = pysaiyanweboo.source_commit() or "unknown"
    return {"stage": pysaiyanweboo.stage_html("{slide}", label="スライド", id="phone-stage"),
            "pager": pysaiyanweboo.pager_html(1, label="ページ移動", words=words, keys=True, id="phone-pager"),
            "labels": pysaiyanweboo.labels_switch_html(id="labels-switch"),
            "slides-toolbar": toolbar(pysaiyanweboo, "slides"),
            "image-toolbar": toolbar(pysaiyanweboo, "image"),
            "js": (f"/* ⬇️ pysaiyanweboo {commit[:8]} ({', '.join(PSWB)}): written by {NOTE} from the pinned commit; --check fails when it drifts */\n"
                   f"(() => {{\n{classic}globalThis.PySaiyanWeBoo = {{ pagerSet, pagerIndex, bindLabels, bindToolbar }};\n}})();\n/* ⬆️ pysaiyanweboo */\n")}


def replace_region(src: str, begin: str, end: str, body: str) -> str:
    start = src.index(begin)
    stop = src.index(end, start) + len(end)
    return src[:start] + body + src[stop:]


def with_parts(src: str) -> str:
    """Rewrite the PySaiyanWeBoo regions in studio_bundle.py."""
    import pysaiyanweboo

    html = pysaiyanweboo.pixel_editor_html()
    src = re.sub(r'PIXEL_EDITOR_HTML = r""".*?"""', lambda _: 'PIXEL_EDITOR_HTML = r"""' + html + '"""', src, count=1, flags=re.S)
    begin, end = "/* PSWB pixel-editor.js */", "/* End PSWB pixel-editor.js */"
    editor = classic_script(pysaiyanweboo.js_source("pixel-editor.js"))
    src = replace_region(src, begin, end, f"{begin}\n{editor}{end}")
    begin, end = "/* PSWB current-item.js */", "/* End PSWB current-item.js */"
    current_item = classic_script(pysaiyanweboo.js_source("current-item.js"))
    src = replace_region(src, begin, end, f"{begin}\n{current_item}{end}")
    for name in ("async-task.js", "records.js"):
        begin, end = f"/* PSWB {name} */", f"/* End PSWB {name} */"
        module = pysaiyanweboo.js_source(name).rstrip("\n")
        src = replace_region(src, begin, end, f"{begin}\n{module}\n{end}")
    parts = pswb_parts()
    lines = lambda html: "".join(f"\n        {part!r}" for part in re.split(r"(?<=>)(?=<)", html))
    block = (f"# ⬇️ pysaiyanweboo: {NOTE} writes PSWB_PARTS from the pinned commit (--check fails when it drifts)\n"
             f"PSWB_PARTS = {{\n    \"stage\": ({lines(parts['stage'])}),\n    \"pager\": ({lines(parts['pager'])}),\n"
             f"    \"labels\": ({lines(parts['labels'])}),\n    \"slides-toolbar\": ({lines(parts['slides-toolbar'])}),\n    \"image-toolbar\": ({lines(parts['image-toolbar'])}),\n}}\n# ⬆️ pysaiyanweboo\n")
    src = replace_region(src, "# ⬇️ pysaiyanweboo", "# ⬆️ pysaiyanweboo\n", block)
    src = replace_region(src, "/* ⬇️ pysaiyanweboo", "/* ⬆️ pysaiyanweboo */\n", parts["js"])
    begin, end = "  /* PSWB heatmap-color.js", "  /* End PSWB heatmap-color.js */\n"
    commit = pysaiyanweboo.source_commit() or "unknown"
    heatmap_js = indent(classic_script(pysaiyanweboo.js_source("heatmap-color.js")), "  ")
    src = replace_region(src, begin, end, f"{begin} @ {commit}. Generated by {NOTE}. */\n{heatmap_js}{end}")
    begin, end = "  /* PSWB pixel-grid.js", "  /* End PSWB pixel-grid.js */\n"   # 🟦 IronmateTools: the dot-art grid, Base64 length, PNG chunks
    grid_js = indent(classic_script(pysaiyanweboo.js_source("pixel-grid.js")), "  ")
    src = replace_region(src, begin, end, f"{begin} @ {commit}. Generated by {NOTE}. */\n{grid_js}{end}")
    begin, end = "  /* PSWB slide-deck.js", "  /* End PSWB slide-deck.js */\n"   # 📽️ IronmateSlides: the deck's check, JSON, template and page operations
    deck_js = indent(classic_script(pysaiyanweboo.js_source("slide-deck.js")), "  ")
    return replace_region(src, begin, end, f"{begin} @ {commit}. Generated by {NOTE}. */\n{deck_js}{end}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed studio assets are stale")
    args = parser.parse_args(argv)
    import tempfile
    import pysaiyanweboo  # PySaiyanWeBoo, pinned in pyproject's test group

    bundle_py = ROOT / "ironlib/studio_bundle.py"
    src = bundle_py.read_text(encoding="utf-8")
    marker = 'STYLE_CSS = r"""'
    start = src.index(marker) + len(marker)
    end = src.index('"""', start)
    problems = []
    for target, options in bundles().items():
        with tempfile.TemporaryDirectory() as tmp:
            tmp_css = Path(tmp) / target.name
            tmp_css.write_text(src[start:end], encoding="utf-8")
            if args.check:
                problems += pysaiyanweboo.check_bundle(tmp_css, **options)
                if with_parts(src) != src:
                    problems.append(f"{bundle_py.relative_to(ROOT)}: the PySaiyanWeBoo parts are stale; run {NOTE}")
            else:
                fields = pysaiyanweboo.write_bundle(tmp_css, note=NOTE, **options)
                new_css = tmp_css.read_text(encoding="utf-8")
                bundle_py.write_text(with_parts(src[:start] + new_css + src[end:]), encoding="utf-8")
                print(f"{bundle_py.relative_to(ROOT)} (STYLE_CSS, PSWB_PARTS, studio.js) pysaiyanweboo {fields['commit'][:8]}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
