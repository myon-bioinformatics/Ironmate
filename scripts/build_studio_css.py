"""Regenerate the studio stylesheets from PySaiyanWeBoo (pysaiyanweboo).

    uv run --group test python scripts/build_studio_css.py          # rewrite style.css, tools/tools.css, brand/gallery.css, slides/slides.css
    uv run --group test python scripts/build_studio_css.py --check  # exit 1 when a committed file is stale

Every sheet is ``pysaiyanweboo.write_bundle`` output: ``core_css()`` (tokens, base, components) + the ``ironmate`` palette
(``pysaiyanweboo.theme_css``) + the rules below, which are only this studio's layout: header and brand, the three-column
workspace, the board and its handles, the shelf cards, the inspector. Buttons, inputs, selects, textareas and
tables take the component look through ``class="ui-elements"`` on ``<body>``; nothing generic lives here.
The files are committed (the studio is served as static files and image_studio.py is stdlib-only), and
``tests/test_studio_css.py`` (``pysaiyanweboo.check_bundle``) fails when they drift.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "studio"

# The brand, as --ui-* tokens: light paper, deep green ink, teal accent (tests run pysaiyanweboo.check_theme on it). Header and primary button keep
# their own (dark green / lime) colours in the studio rules, because they are the two brand surfaces.
IRONMATE = {
    "--ui-bg": "#edf0ec",
    "--ui-panel": "#ffffff",
    "--ui-fg": "#213a3c",
    "--ui-muted": "#566a61",   # pysaiyanweboo.check_theme: every text token reads at WCAG AA on paper and panel
    "--ui-border": "#cfd8cf",
    "--ui-accent": "#076c68",
    "--ui-danger": "#ad4337",
    "--ui-radius": "7px",
}
INK = "#163b3b"
LIME = "#bdf06c"

STUDIO_RULES = f"""/* studio layout */
body{{font-size:13px;line-height:1.5;margin:0}}
header{{min-height:76px;background:{INK};color:#fff;padding:18px 26px;display:flex;align-items:center;justify-content:space-between;gap:20px}}
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
.shelf-details strong{{display:block;font-size:12px;color:{INK};white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
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
.table-wrap{{overflow-x:auto}}
table{{background:var(--ui-panel);font-size:13px}}
th,td{{padding:16px;min-width:180px}}
th{{background:#e4eee8}}
footer{{padding:30px;text-align:center;color:var(--ui-muted);font-size:12px;border-top:1px solid var(--ui-border)}}
@media(max-width:760px){{main{{padding:30px 16px}}.workspace{{grid-template-columns:1fr}}.controls,.preview{{padding:18px}}header{{padding:18px}}h2{{font-size:25px}}.exports{{gap:8px}}}}
"""

GALLERY_RULES = """/* brand gallery layout */
body{line-height:1.7;margin:0}
a{color:var(--ui-accent);text-underline-offset:4px}
header{display:flex;align-items:center;gap:18px;background:#d8e6a3;padding:24px max(24px,calc((100vw - 1100px)/2))}
header p{margin:0}header a{font-weight:bold;font-size:22px}
main{max-width:1100px;margin:auto;padding:28px 24px}
h1{font-size:clamp(26px,5vw,44px)}h2{font-size:19px}
img{image-rendering:pixelated;max-width:100%;object-fit:contain}
.designs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin:30px 0}
.designs section{padding:22px;background:var(--ui-panel);border:1px solid var(--ui-border)}
.designs img{display:block;margin:auto}
.home{padding:24px;background:#dfe8df}
.print-logo{display:none}
@media(max-width:700px){.designs{grid-template-columns:repeat(2,minmax(0,1fr))}.designs section{padding:14px}.designs img{width:100%;height:auto}}
@media print{header,.designs,.home{display:none}.print-logo{display:block}body{background:white;color:black}}
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


NOTE = "scripts/build_studio_css.py"
BRAND = ("ironmate", IRONMATE)


def bundles() -> dict[Path, dict]:
    """Each sheet's write_bundle / check_bundle arguments: the ironmate palette on core_css plus that page's layout.
    slides.css is loaded after style.css, so it carries only its own rules (no second copy of the core)."""
    return {
        STUDIO / "style.css": {"brand": BRAND, "extra_css": STUDIO_RULES},
        STUDIO / "tools" / "tools.css": {"brand": BRAND, "extra_css": TOOLS_RULES},
        STUDIO / "brand" / "gallery.css": {"brand": BRAND, "extra_css": GALLERY_RULES},
        STUDIO / "slides" / "slides.css": {"theme": None, "extra_css": SLIDES_RULES},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when a committed stylesheet is stale")
    args = parser.parse_args(argv)
    import pysaiyanweboo  # PySaiyanWeBoo, pinned in pyproject's test group

    problems = []
    for target, options in bundles().items():
        if args.check:
            problems += pysaiyanweboo.check_bundle(target, **options)
        else:
            fields = pysaiyanweboo.write_bundle(target, note=NOTE, **options)
            print(f"{target.relative_to(ROOT)} pysaiyanweboo {fields['commit'][:8]}")
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
