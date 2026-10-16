"""One-command Markdown -> Marp PPTX -> Open XML inspection.

No promise of Mermaid rendering unless a configured Marp renderer supports it.
"""
import json
import csv
import tomllib
from zipfile import ZipFile
from vendor.markdown import markdown_table_to_rows
import os
from pathlib import Path
import sys
import tempfile

from vendor.cli_args import Argument, make_parser
import shutil
import subprocess
from mermaid_svg import render_mermaid
from pptx_inspect import inspect
from pptx_ooxml import append_objects, copy_with_replacements, ordered_slide_members, require_package, slide_size
from pptx_spec import pattern_objects


def enrich(source, patterns, *, destination=None, dry_run=False):
    """Append only; copy every non-target ZIP member without modification.

    Coordinates are inches. Callers choose a free region; overlap with existing
    objects is not resolved. Dry-run builds the same native objects in memory.
    """
    if not isinstance(patterns, list) or not patterns:
        raise ValueError('at least one pattern is required')
    if not dry_run and (destination is None or Path(source).resolve() == Path(destination).resolve() or os.path.lexists(destination)):
        raise ValueError('destination must be a new file distinct from source')
    with ZipFile(source) as original:
        if len(original.namelist()) != len(set(original.namelist())):
            raise ValueError('duplicate ZIP members unsupported')
        members = ordered_slide_members(original)
        width, height = slide_size(original)
        pending = {member: original.read(member) for member in members}
    changed, report = {}, []
    for index, spec in enumerate(patterns):
        objects = pattern_objects(spec, index=index, slide_count=len(members), slide_width=width, slide_height=height)
        member = members[spec['slide'] - 1]
        payload, ids = append_objects(pending[member], objects)
        pending[member] = payload
        changed[member] = payload
        report.append(dict(pattern=spec['pattern'], slide=spec['slide'], added_shapes=len(objects), shape_ids=ids))
    if not dry_run:
        dst = Path(destination)
        with tempfile.TemporaryDirectory(prefix='.pptx-enrich-', dir=dst.parent) as staging:
            staged = Path(staging) / 'complete.pptx'
            copy_with_replacements(source, staged, changed)
            require_package(staged)
            os.link(staged, dst)
    return dict(dry_run=dry_run, patterns=report, added_shapes=sum(item['added_shapes'] for item in report))


def load_patterns(path):
    """Read TOML and resolve CSV references relative to its directory."""
    path = Path(path)
    with path.open('rb') as stream:
        patterns = tomllib.load(stream).get('patterns')
    if not isinstance(patterns, list) or not patterns:
        raise ValueError('at least one pattern is required')
    for spec in patterns:
        if isinstance(spec, dict) and isinstance(spec.get('csv'), str):
            spec['csv'] = str(path.parent / spec['csv'])
    return patterns


def convert(source, output, *, marp="marp", allow_local_files=False):
    source, output = Path(source), Path(output)
    if source.suffix.lower() != ".md":
        raise ValueError("input must be a .md file")
    if output.suffix.lower() != ".pptx":
        raise ValueError("output must be a .pptx file")
    if source.resolve() == output.resolve() or output.exists():
        raise ValueError("output must be a new file distinct from input")
    executable = shutil.which(marp)
    if executable is None:
        raise RuntimeError("Marp CLI not installed; install and pin @marp-team/marp-cli separately")
    command = [executable, str(source), "--pptx", "--output", str(output)]
    if allow_local_files:
        command.append("--allow-local-files")
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Marp conversion failed (exit {result.returncode}): {result.stderr.strip()}")
    if not output.is_file():
        raise RuntimeError("Marp returned success but produced no PPTX")
    try:
        slides = require_package(output)
    except Exception as exc:
        raise RuntimeError("Marp output is not a readable PPTX") from exc
    return {"source": str(source), "output": str(output), "slides": slides, "backend": "marp"}


def read_markdown_input(*, source=None, text=None, stdin=None):
    """Resolve Markdown from file, inline text, or stdin without altering CLI semantics."""
    if (source is None) == (text is None):
        raise ValueError("provide exactly one Markdown source")
    if text is not None:
        return text, "inline"
    if source == "-":
        return (sys.stdin if stdin is None else stdin).read(), "stdin"
    return Path(source).read_text(encoding="utf-8"), str(source)



def run(*, source=None, text=None, output, marp="marp", mmdc=None, background="#FFFFFF", svg_foreground=None, enrich_patterns=None):
    output = Path(output)
    if (source is None) == (text is None):
        raise ValueError("provide exactly one Markdown source")
    if enrich_patterns is not None:
        if output.suffix.lower() != ".pptx" or os.path.lexists(output):
            raise ValueError("output must be a new .pptx file")
        # Keep the Marp intermediate private until all native edits succeed.
        with tempfile.TemporaryDirectory(prefix="ironmate-enrich-", dir=output.parent) as directory:
            intermediate = Path(directory) / "marp.pptx"
            result = run(source=source, text=text, output=intermediate, marp=marp,
                         mmdc=mmdc, background=background, svg_foreground=svg_foreground)
            edit_report = enrich(intermediate, enrich_patterns, destination=output)
        result["conversion"]["output"] = str(output)
        result["enrichment"] = edit_report
        result["inspection"] = inspect(output)
        return result
    if mmdc is not None:
        raw, _ = read_markdown_input(source=source, text=text)
        if not raw.strip():
            raise ValueError("Markdown must not be empty")
        with tempfile.TemporaryDirectory(prefix="ironmate-svg-") as directory:
            working = Path(directory)
            prepared, images = render_mermaid(raw, working, mmdc=mmdc, background=background, foreground=svg_foreground)
            input_path = working / "input.md"
            input_path.write_text(prepared, encoding="utf-8")
            conversion = convert(input_path, output, marp=marp, allow_local_files=True)
            conversion["mermaid_svg_count"] = len(images)
    elif text is not None:
        if not text.strip():
            raise ValueError("Markdown must not be empty")
        with tempfile.TemporaryDirectory(prefix="ironmate-md-") as directory:
            input_path = Path(directory) / "input.md"
            input_path.write_text(text, encoding="utf-8")
            conversion = convert(input_path, output, marp=marp)
            conversion["source"] = "inline"
    else:
        conversion = convert(source, output, marp=marp)
    report = inspect(output)
    return {"conversion": conversion, "inspection": report}


def review(*, source=None, text=None, directory, marp='marp', mmdc=None,
           background='#FFFFFF', svg_foreground=None, enrich_patterns=None,
           sha=None, run_id=None):
    """One-command source preview + final PPTX structural inspection.

    Never claims that Marp HTML/PDF includes later native PPTX edits.
    Only a completed bundle publishes final.pptx; existing paths are preserved.
    """
    import base64
    import hashlib
    import html as html_escape
    import uuid
    from pptx_preview import render_preview_html
    target = Path(directory)
    if os.path.lexists(target) or not target.parent.is_dir():
        raise ValueError('review directory must be new with an existing parent')
    raw, _ = read_markdown_input(source=source, text=text)
    if not raw.strip():
        raise ValueError('Markdown must not be empty')
    executable = shutil.which(marp)
    if executable is None:
        raise RuntimeError('Marp CLI not installed')
    if sha is None:
        sha = subprocess.run(['git', '-C', str(Path(__file__).resolve().parent), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, check=True, timeout=10).stdout.strip()
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        raise ValueError('review SHA must be a full lowercase Git SHA')
    run_id = run_id or uuid.uuid4().hex
    target.mkdir()  # Exclusive, before any render work.
    report = {'stage': 'source', 'source_sha256': hashlib.sha256(raw.encode()).hexdigest(),
              'tested_sha': sha, 'run_id': run_id, 'is_final_pptx_render': False,
              'native_pptx_edits_reflected': False,
              'scope': 'Marp source preview + separate final PPTX structural inspection'}
    try:
        # Keep the final PPTX private until previews and PDF validation succeed.
        with tempfile.TemporaryDirectory(prefix='.review-', dir=target) as scratch:
            private = Path(scratch) / 'final.pptx'
            prepared = raw
            if mmdc is not None:
                prepared, images = render_mermaid(raw, target, mmdc=mmdc,
                                                 background=background, foreground=svg_foreground)
                # Keep SVG previews portable instead of retaining temporary paths.
                for image in images:
                    uri = 'data:image/svg+xml;base64,' + base64.b64encode(image.read_bytes()).decode()
                    prepared = prepared.replace('./' + image.name, uri)
            md = target / 'source.md'
            md.write_text(prepared, encoding='utf-8')
            report['stage'] = 'pptx'
            # Keep the existing PPTX path's original asset-resolution behavior.
            result = run(source=source, text=text, output=private, marp=marp, mmdc=mmdc,
                         background=background, svg_foreground=svg_foreground, enrich_patterns=enrich_patterns)
            report['stage'] = 'html'
            html = target / 'preview.html'
            proc = subprocess.run([executable, str(md), '--template', 'bare', '-o', str(html)],
                                  capture_output=True, text=True, timeout=120, check=False)
            if proc.returncode != 0 or not html.is_file():
                raise RuntimeError('Marp HTML conversion failed')
            # Resolve ordinary relative assets against the original source folder.
            # HTML portability still depends on those assets; PDF/PNG are standalone.
            base = (Path(source).resolve().parent if source is not None else Path.cwd()).as_uri() + '/'
            markup = html.read_text(encoding='utf-8')
            if '<head>' not in markup:
                raise ValueError('Marp output has no HTML head')
            markup = markup.replace('<head>', '<head><base href="' + html_escape.escape(base, quote=True) + '">', 1)
            html.write_text(markup, encoding='utf-8')
            report['stage'] = 'preview'
            preview = render_preview_html(html, target, expected_slides=len(result['inspection']['slides']),
                                          sha=sha, run_id=run_id)
            if hashlib.sha256((Path(source).read_text(encoding='utf-8') if source is not None else text).encode()).hexdigest() != report['source_sha256']:
                raise ValueError('Markdown source changed during review')
            final = target / 'final.pptx'
            result['conversion']['output'] = str(final)
            result['inspection']['source'] = str(final)
            (target / 'inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            final_hash = hashlib.sha256(private.read_bytes()).hexdigest()
            os.link(private, final)
            report.update(stage='complete', preview=preview, final_pptx_sha256=final_hash)
    except Exception as exc:
        report.update(failed_stage=report['stage'], stage='failed', error_type=type(exc).__name__)
        raise RuntimeError(f"review failed at {report['failed_stage']} ({type(exc).__name__}); see review.json") from None
    finally:
        (target / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def table_pattern(path, *, pattern="table", slide=1, region=(.5, 1.2, 9, 4), columns=None):
    """Turn CSV or the first live Markdown table into a native table/diagram.

    Diagram mapping: first cell is title; remaining cells become header: value
    body lines. No inference, scoring, or new Markdown parser.
    """
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            data = list(csv.reader(stream))
        if len(data) < 2 or not data[0] or any(len(row) != len(data[0]) for row in data):
            raise ValueError("CSV requires header and rectangular body rows")
        headers, rows = data[0], data[1:]
    elif path.suffix.lower() == ".md":
        headers, rows = markdown_table_to_rows(path.read_text(encoding="utf-8-sig"))
        if not headers or not rows:
            raise ValueError("Markdown must contain a live GFM table with body rows")
    else:
        raise ValueError("table input must be .csv or .md")
    if pattern not in ("table", "cards", "regions", "flow"):
        raise ValueError("table pattern must be table, cards, regions or flow")
    spec = dict(pattern=pattern, slide=slide, **dict(zip(("x","y","width","height"),region)))
    if pattern == "table":
        spec["rows"] = [headers, *rows]
    else:
        spec["items"] = [dict(title=row[0], body="\n".join(f"{key}: {value}" for key,value in zip(headers[1:],row[1:]))) for row in rows]
        if columns is not None:
            spec["columns"] = columns
    return spec


def main(argv=None):
    """Single supported Markdown-to-PPTX CLI, with optional SVG preprocessing."""
    parser = make_parser([
        Argument(("source",), {"nargs": "?", "help": "Markdown file path or - for stdin"}),
        Argument(("--text",), {"help": "Inline Markdown source"}),
        Argument(("-o", "--output"), {"type": Path}),
        Argument(("--review",), {"type": Path, "help": "New directory: final PPTX inspection plus Marp HTML/PDF/PNG preview"}),
        Argument(("--review-sha",), {"help": "Tested Git SHA; defaults to repository HEAD"}),
        Argument(("--review-run-id",), {}),
        Argument(("--marp",), {"default": "marp"}),
        Argument(("--mmdc",), {"help": "Optional Mermaid SVG pre-renderer"}),
        Argument(("--background",), {"default": "#FFFFFF"}),
        Argument(("--svg-foreground",), {}),
        Argument(("--table",), {"type": Path, "help": "CSV or Markdown table; TOML not required"}),
        Argument(("--table-pattern",), {"choices": ("table","cards","regions","flow"), "default": "table"}),
        Argument(("--table-slide",), {"type": int, "default": 1}),
        Argument(("--table-region",), {"type": float, "nargs": 4, "default": (.5,1.2,9,4), "metavar": ("X","Y","WIDTH","HEIGHT")}),
        Argument(("--table-columns",), {"type": int}),
        Argument(("--enrich",), {"type": Path, "help": "TOML patterns applied as native OOXML shapes after Marp"}),
    ], description=__doc__)
    args = parser.parse_args(argv)
    if (args.source is None) == (args.text is None):
        parser.error("provide exactly one of source or --text")
    if (args.output is None) == (args.review is None):
        parser.error("provide exactly one of --output or --review")
    if args.review is None and (args.review_sha is not None or args.review_run_id is not None):
        parser.error("review metadata requires --review")
    inline = args.text if args.text is not None else sys.stdin.read() if args.source == "-" else None
    if inline is not None and not inline.strip():
        parser.error("Markdown content must not be empty")
    if args.table is not None and args.enrich is not None:
        parser.error("use --table or optional --enrich configuration, not both")
    patterns = None
    if args.table is not None:
        patterns = [table_pattern(args.table, pattern=args.table_pattern, slide=args.table_slide,
                                  region=args.table_region, columns=args.table_columns)]
    if args.enrich is not None:
        patterns = load_patterns(args.enrich)
    common = dict(source=None if inline is not None else args.source, text=inline,
                  marp=args.marp, mmdc=args.mmdc, background=args.background,
                  svg_foreground=args.svg_foreground, enrich_patterns=patterns)
    if args.review is not None:
        result = review(directory=args.review, sha=args.review_sha, run_id=args.review_run_id, **common)
    else:
        result = run(output=args.output, **common)
    if args.source == "-" and args.review is None:
        result["conversion"]["source"] = "stdin"
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
