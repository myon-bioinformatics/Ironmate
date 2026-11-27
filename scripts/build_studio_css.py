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
markup is ``PSWB_PHONE`` and their modules ride in studio.js as one classic script, each written here from the pinned commit.
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


def bundles() -> dict[Path, dict]:
    """One stylesheet for every studio page: PySaiyanWeBoo's green theme on core_css, the components pswb_parts() uses, then
    the pages' layout, PySaiyanWeBoo's ``studio-pages.css`` (scoped by ``<body data-page="...">``; the slides page is
    ``data-page="studio slides"``)."""
    import pysaiyanweboo
    sheets = [*dict.fromkeys(sheet for name in PSWB for sheet in pysaiyanweboo.COMPONENTS[name]["css"]), "studio-pages.css"]
    return {STUDIO / "style.css": {"theme": THEME, "extra_css": "\n".join(map(pysaiyanweboo.css_source, sheets))}}


PSWB = ("stage", "pager", "chrome")  # 🧩 PySaiyanWeBoo components: the 📱 page's stage and pager, the studios' chrome


def chrome_specs() -> dict[str, dict]:
    """🧰 The studios' chrome (PySaiyanWeBoo's): 🏠 the portfolio, 💾 one save whose panel lists every format, 📂 one open, ⚙️ the 📱
    layout, ☰ the other pages, ⋯ the temporary shelf. A row with a key is answered by the page (``ui-chrome-action`` in studio.js)."""
    rows = lambda pairs: [{"label": label, "key": key} for label, key in pairs]
    save = [("🖼 PNG", "png"), ("🖼 PNG ×2", "png-2"), ("🖼 PNG ×4", "png-4"), ("🖼 PNG ×8", "png-8"), ("📐 SVG", "svg"),
            ("📦 JSON（再編集用）", "json"), ("🕘 作業履歴", "workspace"), ("🔤 Base64 / 渡す", "base64")]
    opened = [("📦 JSON", "open-json"), ("🕘 作業履歴", "open-workspace")]
    github = {"label": "🐙 GitHub リポジトリ", "href": "https://github.com/myon-bioinformatics/Ironmate"}
    music = {"label": "🎵 作曲", "href": "https://myon-bioinformatics.github.io/PySaiyanWeBoo/examples/composition-studio.html"}

    def spec(title, text, places, phone, save, opened):
        return {"id": "ironmate", "home": "https://myon-bioinformatics.github.io/#ironmate", "board": {"title": title, "items": [{"text": text}]},
                "places": [*places, music, github], "settings": [{"label": "📱 スマホ版", "href": phone}], "screen": rows([("📋 クリップボード・シェルフ", "shelf")]),
                "tools": {"💾": {"label": "保存", "label_en": "Save", "links": rows(save)}, "📂": {"label": "開く", "label_en": "Open", "links": rows(opened)}}}
    return {"studio": spec("IMAGE", "図形・文字・スタンプ・写真を重ねて PNG / SVG に。データはこの端末の中だけ。",
                           [{"label": "📽️ スライド・PPTX作成", "href": "./slides/"}, {"label": "🟦 画像一覧・素材", "href": "./tools/"}], "./slides/phone/", save, opened),
            "slides": spec("SLIDES", "スライドを作って PPTX に。文字と図形は PowerPoint でも編集できます。",
                           [{"label": "🖼️ Image Studio", "href": "../"}, {"label": "🟦 画像一覧・素材", "href": "../tools/"}], "./phone/",
                           [("📽️ PPTX", "pptx"), ("📦 全スライド JSON", "deck-json"), *save], [("📦 全スライド JSON", "open-deck"), *opened])}


def classic_script(modules: str) -> str:
    script = re.sub(r"^export (?=function |const )", "", modules, flags=re.M)
    assert not re.search(r"^\s*(import|export)\b", script, flags=re.M), "a module PySaiyanWeBoo ships now imports or exports otherwise"
    return script


def pswb_parts() -> dict[str, str]:
    """🧩 What the 📱 page takes from PySaiyanWeBoo: the 🖼️ stage (``{slide}`` marks where the slide goes), the 🧭 pager (one page; the
    browser keeps it in step with the deck) and the components' modules as one classic script, because the pages' CSP allows script
    files and no inline module: ``export`` dropped, wrapped, and ``pagerSet`` / ``pagerIndex`` left on ``globalThis.PySaiyanWeBoo``."""
    import pysaiyanweboo
    words = {"first": "最初のページ", "prev": "前のページ", "next": "次のページ", "last": "最後のページ", "page": "ページ"}
    modules = "".join(pysaiyanweboo.js_source(m) for name in PSWB for m in pysaiyanweboo.COMPONENTS[name]["js"])
    classic = classic_script(modules)
    commit = pysaiyanweboo.source_commit() or "unknown"
    return {"stage": pysaiyanweboo.stage_html("{slide}", label="スライド", id="phone-stage"),
            "pager": pysaiyanweboo.pager_html(1, label="ページ移動", words=words, keys=True, id="phone-pager"),
            "js": (f"/* ⬇️ pysaiyanweboo {commit[:8]} ({', '.join(PSWB)}): written by {NOTE} from the pinned commit; --check fails when it drifts */\n"
                   f"(() => {{\n{classic}globalThis.PySaiyanWeBoo = {{ pagerSet, pagerIndex, bindChrome }};\n"
                   f"if (typeof document !== \"undefined\") bindChrome(); // 🧰 a page with a chrome gets its menus\n}})();\n/* ⬆️ pysaiyanweboo */\n"),
            "chrome": {name: pysaiyanweboo.chrome_html(spec) for name, spec in chrome_specs().items()}}


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
    parts = pswb_parts()
    lines = lambda html: "".join(f"\n        {part!r}" for part in re.split(r"(?<=>)(?=<)", html))
    block = (f"# ⬇️ pysaiyanweboo: {NOTE} writes PSWB_PHONE from the pinned commit (--check fails when it drifts)\n"
             f"PSWB_PHONE = {{\n    \"stage\": ({lines(parts['stage'])}),\n    \"pager\": ({lines(parts['pager'])}),\n}}\n"
             f"PSWB_CHROME = {{  # 🧰 the studios' chrome, one a page (image_studio.public_assets swaps the slide page's in)\n"
             + "".join(f"    {name!r}: ({lines(html)}),\n" for name, html in parts["chrome"].items()) + "}\n# ⬆️ pysaiyanweboo\n")
    begin, end = "    <!-- PSWB chrome", "<!-- End PSWB chrome -->\n"   # the image studio's own copy inside STUDIO_HTML
    src = replace_region(src, begin, end, f"{begin}: generated by {NOTE} -->{parts['chrome']['studio']}{end}")
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
                print(f"{bundle_py.relative_to(ROOT)} (STYLE_CSS, PSWB_PHONE, PSWB_CHROME, studio.js) pysaiyanweboo {fields['commit'][:8]}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
