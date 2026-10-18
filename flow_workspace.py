"""Retain original flow JSON, apply web-ui patches, and regenerate exports.

This is structural JSON editing, independent of Image Studio pixel operations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from xml.etree import ElementTree as ET

from flow_export import FORMATS, MAX_INPUT, read_spec, render_flow
from grid_output import write_output

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / 'vendor/web_ui'
SCHEMA = 'ironmate-flow/1'
MAX_PATCH_DOCUMENT = 320 * 1024
MAX_WORKSPACE = 2 * 1024 * 1024


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def import_flow(raw):
    """Keep the exact UTF-8 source text, including spacing and omitted defaults."""
    spec = read_spec(raw)
    return dict(schema=SCHEMA, original_json=raw.decode('utf-8'), spec=spec)


def validate_workspace(workspace):
    """Return detached state; neither source nor working spec aliases the caller."""
    if not isinstance(workspace, dict) or set(workspace) != {'schema', 'original_json', 'spec'}:
        raise ValueError('expected schema, original_json and spec')
    if workspace['schema'] != SCHEMA or not isinstance(workspace['original_json'], str):
        raise ValueError('unsupported flow workspace')
    read_spec(workspace['original_json'].encode('utf-8'))
    spec = read_spec(_json_bytes(workspace['spec']))
    return dict(schema=SCHEMA, original_json=workspace['original_json'], spec=spec)


def read_workspace(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_WORKSPACE:
        raise ValueError('workspace must be UTF-8 bytes, at most 2MiB')
    return validate_workspace(json.loads(raw.decode('utf-8')))


def workspace_bytes(workspace):
    raw = _json_bytes(validate_workspace(workspace)) + b'\n'
    if len(raw) > MAX_WORKSPACE:
        raise ValueError('workspace exceeds 2MiB')
    return raw


def patch_workspace(workspace, operations):
    """Use the byte-identical upstream CLI in an isolated module search path.

    No process-global sys.path/module aliases and no local patch implementation.
    All validation and rendering complete before callers receive replacement state.
    """
    result = validate_workspace(workspace)
    document = _json_bytes(dict(spec=result['spec'], patch=operations))
    if len(document) > MAX_PATCH_DOCUMENT:
        raise ValueError('patch document exceeds 320KiB')
    patched = subprocess.run(
        [sys.executable, '-I', '-S', '-c',
         'import sys,runpy; sys.path.insert(0,sys.argv[1]); '
         'sys.argv=["flow_patch"]; runpy.run_module("tool.flow_patch",run_name="__main__")',
         str(UPSTREAM)],
        input=document, capture_output=True, timeout=10, check=False)
    if patched.returncode:
        raise ValueError(patched.stderr.decode('utf-8', errors='replace').strip() or 'flow patch failed')
    result['spec'] = read_spec(patched.stdout)
    return result


def render_workspace(workspace, format='svg', **options):
    return render_flow(validate_workspace(workspace)['spec'], format, **options)


def patch_and_render(workspace, operations, format='svg', **options):
    """Transactional in-memory result: return both only after successful drawing."""
    updated = patch_workspace(workspace, operations)
    image = render_workspace(updated, format, **options)
    return updated, image


def _read(path, limit):
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('input exceeds byte budget')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('import', 'patch', 'render', 'original', 'spec'):
        command = commands.add_parser(name)
        command.add_argument('input', type=Path)
        command.add_argument('-o', '--output', type=Path)
        command.add_argument('--force', action='store_true')
        if name == 'patch':
            command.add_argument('patch', type=Path, help='web-ui array of path/value operations')
        if name == 'render':
            command.add_argument('--format', choices=FORMATS, default='svg')
            command.add_argument('--scale', type=float, default=1)
            command.add_argument('--background')
            command.add_argument('--mmdc', default='mmdc')
            command.add_argument('--chrome')
            command.add_argument('--puppeteer-config', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'import':
            data = workspace_bytes(import_flow(_read(args.input, MAX_INPUT)))
        else:
            workspace = read_workspace(_read(args.input, MAX_WORKSPACE))
            if args.command == 'patch':
                operations = json.loads(_read(args.patch, MAX_PATCH_DOCUMENT).decode('utf-8'))
                data = workspace_bytes(patch_workspace(workspace, operations))
            elif args.command == 'render':
                data = render_workspace(workspace, args.format, scale=args.scale, background=args.background,
                                        mmdc=args.mmdc, chrome=args.chrome, puppeteer_config=args.puppeteer_config)
            elif args.command == 'original':
                data = workspace['original_json'].encode('utf-8')
            else:
                data = _json_bytes(workspace['spec']) + b'\n'
        if args.output:
            write_output(str(args.output), data, args.force)
        else:
            sys.stdout.buffer.write(data)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        parser.exit(2, f'flow workspace: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
