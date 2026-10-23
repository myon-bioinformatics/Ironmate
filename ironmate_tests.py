"""Show how to run Ironmate tests, and run one named fast command.

JSON is the default so a non-human caller can take the argv list and run it.
A failing child process keeps its status. This does not hide stderr or turn
a failure into success.

    python -S ironmate_tests.py list
    python -S ironmate_tests.py list --text
    python -S ironmate_tests.py run studio-ingress
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

from ironmate_cli import ToolParser, guard
from vendor.cli_args import pytest_command

PYTHON_MARK = 'not heavy and not network'
NODE = (
    {'id': 'py-launch-wrappers', 'argv': ['node', '--test', 'tests/py_launch_wrappers.test.cjs'], 'needs': []},
    {'id': 'studio-ingress', 'argv': ['node', '--test', 'tests/studio_ingress.test.cjs'], 'needs': []},
    {'id': 'studio-workspace', 'argv': ['node', '--test', 'tests/studio_workspace.test.cjs'], 'needs': []},
    {'id': 'image-digest', 'argv': ['node', '--test', 'tests/image_digest.test.cjs'], 'needs': ['DIGEST_PNG']},
    {'id': 'flow-export-browser', 'argv': ['node', 'tests/flow_export_browser.cjs'], 'needs': ['browser']},
    {'id': 'image-studio-browser', 'argv': ['node', 'tests/image_studio_browser.cjs'], 'needs': ['browser']},
    {'id': 'pages-browser', 'argv': ['node', 'tests/pages_browser.cjs'], 'needs': ['browser']},
    {'id': 'slides-browser', 'argv': ['node', 'tests/slides_browser.cjs'], 'needs': ['browser']},
    {'id': 'studio-clipboard', 'argv': ['node', 'tests/studio_clipboard.cjs'], 'needs': ['browser']},
    {'id': 'studio-quality-browser', 'argv': ['node', 'tests/studio_quality_browser.cjs'], 'needs': ['browser']},
    {'id': 'studio-scale-browser', 'argv': ['node', 'tests/studio_scale_browser.cjs'], 'needs': ['browser']},
    {'id': 'studio-shelf-browser', 'argv': ['node', 'tests/studio_shelf_browser.cjs'], 'needs': ['browser']},
    {'id': 'studio-tradeoff-browser', 'argv': ['node', 'tests/studio_tradeoff_browser.cjs'], 'needs': ['browser']},
)


def python_pytest_argv():
    """Current interpreter plus the default fast pytest selection."""
    return list(pytest_command((), quiet=True, extra=('-m', PYTHON_MARK)).argv)


def locked_pytest_argv():
    """Same selection through the locked dev environment, as documented for humans."""
    return ['uv', 'run', '--locked', 'python', '-m', 'pytest', '-q', '-m', PYTHON_MARK]


def catalog():
    return {
        'ok': True,
        'python': {'pytest': python_pytest_argv(), 'locked': locked_pytest_argv()},
        'node': list(NODE),
    }


def _find(entry_id):
    for entry in NODE:
        if entry['id'] == entry_id:
            return entry
    known = ', '.join(entry['id'] for entry in NODE)
    raise ValueError(f'unknown test id {entry_id!r}; known ids: {known}')


def _run_entry(entry):
    if entry['needs']:
        raise ValueError(
            f"{entry['id']} needs {', '.join(entry['needs'])}; run it directly: " + ' '.join(entry['argv'])
        )
    program = entry['argv'][0]
    if shutil.which(program) is None:
        raise ValueError(f'{program} is not installed')
    completed = subprocess.run(entry['argv'], check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    return 0


def main(argv=None):
    parser = ToolParser(prog='ironmate_tests.py', description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    listed = commands.add_parser('list', help='print python and node test commands')
    listed.add_argument('--json', action='store_true', help='print the catalog as JSON (this is the default)')
    listed.add_argument('--text', action='store_true', help='print one argv per line')
    run = commands.add_parser('run', help='run one fast node test id and keep its exit status')
    run.add_argument('id', help='id from list, for example studio-ingress')
    args = parser.parse_args(argv)

    def work():
        if args.command == 'list':
            if args.text and args.json:
                parser.error('pass only one of --text or --json')
            data = catalog()
            if args.text:
                print(' '.join(data['python']['pytest']))
                print(' '.join(data['python']['locked']))
                for entry in data['node']:
                    needs = f"  # needs {', '.join(entry['needs'])}" if entry['needs'] else ''
                    print(' '.join(entry['argv']) + needs)
            else:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        return _run_entry(_find(args.id))

    return guard('ironmate_tests.py', work, json_mode=False)


if __name__ == '__main__':
    raise SystemExit(main())
