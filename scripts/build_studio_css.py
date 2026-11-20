"""Regenerate the studio stylesheet and the PySaiyanWeBoo parts from PySaiyanWeBoo (pysaiyanweboo).

    uv run --group test python scripts/build_studio_css.py          # rewrite STYLE_CSS and the pysaiyanweboo parts in ironlib/studio_bundle.py
    uv run --group test python scripts/build_studio_css.py --check  # exit 1 when either is stale

The sheet is ``pysaiyanweboo.write_bundle`` output: ``core_css()`` (tokens, base, components) with PySaiyanWeBoo's ``green`` theme
(``CANDIDATE_THEMES``) + the rules below, which are only this studio's layout: header and brand, the three-column
workspace, the board and its handles, the shelf cards, the inspector. Buttons, inputs, selects, textareas and
tables take the component look through ``class="ui-elements"`` on ``<body>``; nothing generic lives here.
The file is committed (the studio is served as static files and image_studio.py is stdlib-only), and
``tests/test_studio.py`` (``pysaiyanweboo.check_bundle``) fails when it drifts.

The 📱 page's 🖼️ stage and 🧭 pager are PySaiyanWeBoo components too (``pswb_parts()``): their stylesheets join the sheet, their
markup is ``PSWB_PHONE`` and their modules ride in studio.js as one classic script, each written here from the pinned commit.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio"

# The palette is PySaiyanWeBoo's "green" theme (CANDIDATE_THEMES; first built by hand here, now owned there, so
# `data-ui-theme` can switch it like any other theme). The header is the theme's ink (var(--ui-fg)); the primary
# button keeps the studio's lime, the one brand surface the themes do not carry.
THEME = "green"
LIME = "#bdf06c"

STUDIO_RULES = f"""/* studio layout */
body{{font-size:13px;line-height:1.5;margin:0}}
header{{min-height:76px;background:var(--ui-fg);color:#fff;padding:18px 26px;display:flex;align-items:center;justify-content:space-between;gap:20px}}
.brand{{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:2px;font-size:19px;white-space:nowrap}}
.brand span{{font-weight:400;font-size:10px;display:block;letter-spacing:3px;margin:5px 0 0;color:#99c5bc}}
.brand img{{flex:none;image-rendering:pixelated}}
.top-actions{{display:flex;flex-wrap:wrap;gap:7px}}
.top-actions>a{{color:#c7f58a;align-self:center;padding:7px 3px;text-underline-offset:3px}}
button,.button{{display:inline-flex;align-items:center;justify-content:center;gap:5px;text-decoration:none;min-height:38px;padding:10px 12px}}
.button{{font:inherit;cursor:pointer;background:var(--ui-panel);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}}
button:hover,.button:hover{{border-color:var(--ui-accent);background:#ecf5ef}}
.primary{{background:{LIME};border-color:{LIME};font-weight:700}}
header button,header .button,header select{{border-color:#406261;background:#244a49;color:#fff}}
header .primary{{background:#c7f58a;color:#183b34;border-color:#c7f58a}}
input[type=file]{{display:none}}
main{{display:grid;grid-template-columns:250px minmax(0,1fr) 238px;min-height:calc(100vh - 76px)}}
aside{{padding:24px 20px;background:#fafbf8}}
aside.tools{{border-right:1px solid var(--ui-border)}}
aside.inspector{{border-left:1px solid var(--ui-border)}}
h1{{font-size:25px;line-height:1.55;letter-spacing:-1px;margin:12px 0}}
h2{{font-size:15px;line-height:1.6;margin:8px 0}}
.eyebrow{{font-size:10px;letter-spacing:2px;font-weight:800;color:var(--ui-muted);margin:0 0 12px}}
.hint,.note{{font-size:11px;color:var(--ui-muted);line-height:1.85}}
.note{{margin-top:18px}}
.tool-grid,.two{{display:grid;grid-template-columns:1fr 1fr;gap:7px}}
.tool-grid{{margin:24px 0 18px}}
.active{{background:#d8eee3!important;border-color:#59937d!important;color:#0a544d!important;font-weight:700}}
label{{display:block;font-size:11px;margin:12px 0 7px}}
input,textarea,select{{display:block;width:100%;font-size:13px;padding:9px;margin-top:5px}}
select{{width:auto;max-width:100%;padding:8px}}
input[type=color]{{height:35px;padding:3px}}
input[type=range]{{padding:0}}
input[type=checkbox]{{display:inline;width:auto;margin:0 7px 0 0}}
.check{{display:flex;align-items:center}}
.wide{{width:100%;margin:6px 0}}
.emojis{{display:flex;flex-wrap:wrap;gap:4px}}
.emojis button{{font-size:21px;padding:5px 7px;border:none;background:transparent}}
.kaomojis button{{font-size:13px;padding:7px 4px}}
.section{{border-top:1px solid var(--ui-border);padding-top:20px;margin-top:22px}}
.workspace{{padding:30px;min-width:0}}
.canvas-heading{{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:5px 0 24px}}
.canvas-heading h2{{font-size:22px;font-weight:500;letter-spacing:-.5px}}
.canvas-heading span{{font-size:11px;white-space:nowrap;color:var(--ui-muted)}}
.board{{position:relative;aspect-ratio:16/9;background:repeating-conic-gradient(#e4e9e2 0 25%,#f7f9f4 0 50%) 0/20px 20px;box-shadow:0 12px 45px #244d3c15;outline:none;touch-action:none}}
.board svg{{width:100%;height:100%;display:block;user-select:none}}
.board g[data-layer]{{cursor:move}}
.board .selection{{pointer-events:none}}
.board .handle{{pointer-events:all;cursor:nwse-resize}}
.canvas-footer{{display:flex;justify-content:space-between;gap:10px;font-size:10px;line-height:1.5;color:var(--ui-muted);margin:16px 0}}
.examples{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-top:1px solid var(--ui-border);padding-top:24px;margin-top:30px}}
.examples label{{margin:0;max-width:76px}}
.example-view{{margin:16px 0 0}}
.example-view img{{display:block;max-width:100%;height:auto;border:1px solid var(--ui-border)}}
.examples input[type=color]{{width:45px}}
.examples input[type=number]{{width:68px}}
.examples .check{{max-width:none}}
.layers{{max-height:240px;overflow:auto;margin-bottom:12px}}
.layers button{{width:100%;justify-content:space-between;margin-bottom:5px;text-align:left}}
.layers small{{color:var(--ui-muted);font-size:9px}}
output{{float:right;color:var(--ui-accent)}}
.inspector h2{{font-size:14px;margin-bottom:20px}}
dialog{{border:1px solid var(--ui-border);border-radius:14px;max-width:480px;padding:30px;color:var(--ui-fg)}}
dialog::backdrop{{background:#123d3b66}}
dialog textarea{{max-width:100%;word-break:break-all}}
#error-text{{white-space:pre-wrap;line-height:1.8}}
#shelf-dialog,#base64-dialog{{width:min(600px,92vw);max-width:600px}}
.shelf-actions{{display:flex;gap:10px;margin:12px 0}}
.shelf-list{{max-height:320px;overflow-y:auto;margin:15px 0;display:flex;flex-direction:column;gap:10px}}
.shelf-card{{display:flex;align-items:center;justify-content:space-between;background:#f4f7f4;border:1px solid var(--ui-border);border-radius:8px;padding:10px 14px;gap:12px}}
.shelf-card-info{{display:flex;align-items:center;gap:12px;overflow:hidden}}
.shelf-thumb{{width:48px;height:48px;object-fit:contain;background:repeating-conic-gradient(#e4e9e2 0 25%,#f7f9f4 0 50%) 0/10px 10px;border:1px solid var(--ui-border);border-radius:4px;flex-shrink:0}}
.shelf-details{{font-size:11px;overflow:hidden}}
.shelf-details strong{{display:block;font-size:12px;color:var(--ui-fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.shelf-details span{{color:var(--ui-muted)}}
.shelf-card-actions{{display:flex;gap:6px;flex-shrink:0}}
#base64-text{{font:11px var(--ui-font-mono);resize:vertical}}
#base64-dialog form{{display:inline}}
#base64-dialog p{{font-size:12px;line-height:1.8}}
@media(min-width:1600px){{.workspace{{padding:44px}}}}
@media(max-width:1150px){{main{{grid-template-columns:210px minmax(0,1fr)}}.inspector{{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}}.inspector>.eyebrow{{display:none}}.inspector>.section{{margin:0;border:0;padding:0}}.workspace{{padding:22px}}}}
@media(max-width:680px){{header{{padding:14px;display:block}}.top-actions{{margin-top:15px}}.top-actions button,.top-actions .button{{padding:7px;font-size:11px}}main{{display:flex;flex-direction:column}}.workspace{{order:-1;padding:18px}}.canvas-heading h2{{font-size:17px}}.canvas-heading{{margin-bottom:16px}}.canvas-footer{{display:block}}.canvas-footer span{{display:block;margin:5px 0}}.tools{{display:block}}.tools h1,.tools>.hint{{display:none}}.tool-grid{{margin:8px 0;grid-template-columns:repeat(3,1fr)}}.inspector{{display:block}}.inspector>.section{{margin-top:20px}}.examples{{margin-top:20px;padding-top:15px}}.board{{width:100%}}aside{{padding:18px}}.tools>.section{{margin-top:15px}}}}
"""

TOOLS_RULES = f"""/* tools page layout */
body{{font-size:15px;line-height:1.65;margin:0}}
a{{color:var(--ui-accent);text-underline-offset:4px}}
header{{padding:24px 4vw;border-bottom:1px solid var(--ui-border);display:flex;justify-content:space-between;gap:24px;align-items:center;flex-wrap:wrap}}
.brand{{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.1em;text-decoration:none;color:inherit}}
.brand img{{flex:none;image-rendering:pixelated}}
.brand-hero{{display:block;max-width:100%;height:auto;image-rendering:pixelated}}
nav,.jump,.exports,.digest-options{{display:flex;flex-wrap:wrap;gap:16px;align-items:center}}
nav{{font-size:13px}}
main{{max-width:1240px;margin:auto;padding:48px 28px}}
.eyebrow,.section-heading span{{font-size:12px;letter-spacing:.15em;font-weight:800;color:var(--ui-muted)}}
h1{{font-size:clamp(38px,7vw,76px);letter-spacing:-.04em;line-height:1.12;margin:20px 0 28px}}
h2{{font-size:30px;letter-spacing:-.03em;margin:10px 0 25px}}
.lead{{font-size:18px;color:var(--ui-muted)}}
.jump{{margin:30px 0}}
.jump a{{background:var(--ui-panel);border:1px solid var(--ui-border);padding:10px 16px;border-radius:30px;text-decoration:none}}
section{{scroll-margin-top:20px;border-top:1px solid var(--ui-border);margin-top:52px;padding-top:28px}}
.workspace{{display:grid;grid-template-columns:310px minmax(0,1fr);gap:28px}}
.controls,.preview{{background:var(--ui-panel);padding:24px;border:1px solid var(--ui-border);border-radius:18px}}
.controls{{display:flex;flex-direction:column;gap:14px}}
label{{display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:650}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
button,select,input,textarea{{max-width:100%;min-width:0}}
button,select,input[type=number],textarea{{padding:10px 12px}}
button{{font-weight:650}}
button:hover{{background:#eaf3ed}}
.primary{{background:var(--ui-accent);border-color:var(--ui-accent);color:#fff}}
.primary:hover{{background:#12554d}}
.hint{{color:var(--ui-muted);font-size:12px;font-weight:400;margin:0}}
.preview{{display:flex;flex-direction:column;gap:16px;justify-content:center;align-items:stretch}}
.preview canvas{{display:block;width:min(100%,480px);height:auto;image-rendering:pixelated;margin:auto;border:1px solid var(--ui-border);background:repeating-conic-gradient(#e1e8e3 0% 25%,#fff 0% 50%) 0 0/20px 20px;cursor:crosshair;touch-action:manipulation}}
textarea{{width:100%;font-size:11px;overflow-wrap:anywhere}}
#grid-info{{font-size:13px;color:var(--ui-muted)}}
#message{{border-left:3px solid var(--ui-accent);padding:8px 16px;min-height:42px;background:#e2eee7}}
#message[data-error=true]{{border-color:var(--ui-danger);color:#983c30}}
.image-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-top:24px}}
.image-list figure{{margin:0;padding:14px;background:var(--ui-panel);border:1px solid var(--ui-border);border-radius:10px;overflow:hidden}}
.image-list img{{width:100%;height:160px;object-fit:contain}}
.image-list figcaption{{font-size:12px;overflow-wrap:anywhere}}
.digest-options{{margin:25px 0}}
@media print{{body:has(#brand:target) header,body:has(#brand:target) footer,main:has(#brand:target)>:not(#brand),#brand:target p,#brand:target h2,#brand:target a:not(:first-child){{display:none}}}}
.table-wrap{{overflow-x:auto}}
table{{background:var(--ui-panel);font-size:13px}}
th,td{{padding:16px;min-width:180px}}
th{{background:#e4eee8}}
footer{{padding:30px;text-align:center;color:var(--ui-muted);font-size:12px;border-top:1px solid var(--ui-border)}}
@media(max-width:760px){{main{{padding:30px 16px}}.workspace{{grid-template-columns:1fr}}.controls,.preview{{padding:18px}}header{{padding:18px}}h2{{font-size:25px}}.exports{{gap:8px}}}}
"""

SLIDES_RULES = """/* slide studio panel (loaded after style.css) */
.slide-controls{padding:14px 24px;background:#e6f0e9;border-bottom:1px solid var(--ui-border)}
.slide-toolbar,.slide-template{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.slide-toolbar select{width:auto;min-width:180px}
.slide-controls details{margin:14px 0}
.slide-controls summary{cursor:pointer;font-weight:650}
.slide-template{align-items:flex-end;margin-top:10px}
.slide-template label{min-width:180px;max-width:420px;flex:1}
.slide-template input,.slide-template textarea,.slide-template select{width:100%}
.slide-hint{font-size:12px;color:var(--ui-muted);margin:6px 0}
#deck-status{font-size:13px;margin:8px 0}
#deck-status[data-error=true]{color:var(--ui-danger)}
.slide-controls button{min-height:38px}
@media(max-width:700px){.slide-controls{padding:14px}.slide-toolbar{gap:8px}.slide-template{display:grid;grid-template-columns:1fr}.slide-template label{max-width:none}.slide-toolbar label{max-width:100%}.slide-toolbar select{max-width:100%}}
"""

PHONE_RULES = """/* 📱 phone slides: the slide is pinned on top (PySaiyanWeBoo's .ui-stage) and the emoji controls scroll under it (landscape: beside it) */
body{margin:0;background:#dfe8df}
input[type=file]{display:none}
.button{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;cursor:pointer;text-decoration:none;background:var(--ui-panel);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}
.phone{display:flex;flex-direction:column;height:100dvh;max-width:960px;margin:0 auto}
.ui-stage{background:#fff;border:0;box-shadow:0 8px 24px rgba(0,0,0,.16);touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
.phone-svg svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.phone-pick{position:absolute;box-sizing:border-box;border:2px dashed #126fef;pointer-events:none}
.phone-pick[hidden],.phone-edit[hidden]{display:none}
.phone-grip{position:absolute;right:-16px;bottom:-16px;width:32px;height:32px;display:grid;place-items:center;border-radius:50%;background:#126fef;color:#fff;font-size:16px;pointer-events:auto;touch-action:none}
.phone-edit{flex:1 1 100%;box-sizing:border-box;margin:0;min-height:88px;padding:8px;font-size:16px;line-height:1.5;border:2px solid #126fef;resize:vertical}
.phone-deck{flex:1;min-height:0;overflow:auto;display:flex;flex-wrap:wrap;align-items:flex-start;align-content:flex-start;gap:16px;padding:16px}
.phone-tools{flex:1 1 328px;min-width:0;display:flex;flex-direction:column;gap:8px}
.phone-row{display:flex;flex-wrap:wrap;gap:8px}
.phone-tools button,.phone-tools .button{min-width:48px;min-height:48px;padding:0 8px;font-size:24px;line-height:1;touch-action:manipulation}
.phone-tools button:disabled{opacity:.32}
.phone-status{flex:1 1 128px;margin:0;align-self:center;min-height:24px;font-size:16px;overflow-wrap:anywhere}
.phone-status[data-error=true]{color:var(--ui-danger)}
@media(orientation:landscape) and (max-height:560px){.phone{flex-direction:row;max-width:none}.ui-stage{max-width:72vw}.phone-deck{flex-direction:column;flex-wrap:nowrap}.phone-tools,.phone-status{flex:none}}
"""


NOTE = "scripts/build_studio_css.py"


PAGES = (("studio", "STUDIO_RULES"), ("tools", "TOOLS_RULES"), ("slides", "SLIDES_RULES"),
         ("phone", "PHONE_RULES"))


def scoped(css: str, page: str) -> str:
    """Prefix every selector with ``:where([data-page~="page"])`` (zero specificity, so the cascade is unchanged).

    The rules are flat (selectors, declarations, ``@media`` blocks, comments); ``body`` keeps its place:
    ``body{...}`` becomes ``body:where(...){...}`` and ``.x{...}`` becomes ``:where(...) .x{...}``.
    """
    guard = f':where([data-page~="{page}"])'

    def selector(text: str) -> str:
        text = text.strip()
        if text.startswith(("html", ":root")):
            return text
        if text == "body" or (text.startswith("body") and not (text[4:5].isalnum() or text[4:5] in "-_")):
            return "body" + guard + text[4:]
        return guard + " " + text

    out, i = [], 0
    while i < len(css):
        if css.startswith("/*", i):
            end = css.index("*/", i) + 2
            out.append(css[i:end]); i = end
        elif css[i].isspace():
            out.append(css[i]); i += 1
        elif css.startswith("@media", i):
            open_at = css.index("{", i)
            depth, j = 1, open_at + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(css[j], 0); j += 1
            out.append(css[i:open_at + 1] + scoped(css[open_at + 1:j - 1], page) + "}"); i = j
        else:
            open_at = css.index("{", i); close = css.index("}", open_at)
            out.append(",".join(selector(part) for part in css[i:open_at].split(",")) + css[open_at:close + 1]); i = close + 1
    return "".join(out)


def bundles() -> dict[Path, dict]:
    """One stylesheet for every studio page: PySaiyanWeBoo's green theme on core_css, the components pswb_parts() uses, then
    each page's layout scoped by ``<body data-page="...">`` (the slides page is ``data-page="studio slides"``)."""
    import pysaiyanweboo
    sheets = dict.fromkeys(sheet for name in PSWB for sheet in pysaiyanweboo.COMPONENTS[name]["css"])
    rules = "\n".join(scoped(globals()[name], page) for page, name in PAGES)
    return {STUDIO / "style.css": {"theme": THEME, "extra_css": "\n".join([*map(pysaiyanweboo.css_source, sheets), rules])}}


PSWB = ("stage", "pager")  # 🧩 the PySaiyanWeBoo components the 📱 page uses


def pswb_parts() -> dict[str, str]:
    """🧩 What the 📱 page takes from PySaiyanWeBoo: the 🖼️ stage (``{slide}`` marks where the slide goes), the 🧭 pager (one page; the
    browser keeps it in step with the deck) and the components' modules as one classic script, because the pages' CSP allows script
    files and no inline module: ``export`` dropped, wrapped, and ``pagerSet`` / ``pagerIndex`` left on ``globalThis.PySaiyanWeBoo``."""
    import pysaiyanweboo
    words = {"first": "最初のページ", "prev": "前のページ", "next": "次のページ", "last": "最後のページ", "page": "ページ"}
    modules = "".join(pysaiyanweboo.js_source(m) for name in PSWB for m in pysaiyanweboo.COMPONENTS[name]["js"])
    classic = re.sub(r"^export function ", "function ", modules, flags=re.M)
    assert not re.search(r"^\s*(import|export)\b", classic, flags=re.M), "a module PySaiyanWeBoo ships now imports or exports otherwise"
    commit = pysaiyanweboo.source_commit() or "unknown"
    return {"stage": pysaiyanweboo.stage_html("{slide}", label="スライド", id="phone-stage"),
            "pager": pysaiyanweboo.pager_html(1, label="ページ移動", words=words, keys=True, id="phone-pager"),
            "js": (f"/* ⬇️ pysaiyanweboo {commit[:8]} ({', '.join(PSWB)}): written by {NOTE} from the pinned commit; --check fails when it drifts */\n"
                   f"(() => {{\n{classic}globalThis.PySaiyanWeBoo = {{ pagerSet, pagerIndex }};\n}})();\n/* ⬆️ pysaiyanweboo */\n")}


def with_parts(src: str) -> str:
    """studio_bundle.py's source with the pysaiyanweboo regions (``PSWB_PHONE`` and the classic script in STUDIO_JS) rewritten."""
    parts = pswb_parts()
    lines = lambda html: "".join(f"\n        {part!r}" for part in re.split(r"(?<=>)(?=<)", html))
    block = (f"# ⬇️ pysaiyanweboo: {NOTE} writes PSWB_PHONE from the pinned commit (--check fails when it drifts)\n"
             f"PSWB_PHONE = {{\n    \"stage\": ({lines(parts['stage'])}),\n    \"pager\": ({lines(parts['pager'])}),\n}}\n# ⬆️ pysaiyanweboo\n")
    for begin, end, body in (("# ⬇️ pysaiyanweboo", "# ⬆️ pysaiyanweboo\n", block), ("/* ⬇️ pysaiyanweboo", "/* ⬆️ pysaiyanweboo */\n", parts["js"])):
        i = src.index(begin)
        j = src.index(end, i) + len(end)
        src = src[:i] + body + src[j:]
    return src


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed stylesheet is stale")
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
                    problems.append(f"{bundle_py.relative_to(ROOT)}: the pysaiyanweboo parts (PSWB_PHONE, studio.js) are stale; run {NOTE}")
            else:
                fields = pysaiyanweboo.write_bundle(tmp_css, note=NOTE, **options)
                new_css = tmp_css.read_text(encoding="utf-8")
                bundle_py.write_text(with_parts(src[:start] + new_css + src[end:]), encoding="utf-8")
                print(f"{bundle_py.relative_to(ROOT)} (STYLE_CSS, PSWB_PHONE, studio.js) pysaiyanweboo {fields['commit'][:8]}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
