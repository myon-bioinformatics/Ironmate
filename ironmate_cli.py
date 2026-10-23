"""Exit status and stderr contract for Ironmate command-line tools.

Humans and non-human callers share one contract:

- ``--help`` / ``-h`` explains the command and exits 0.
- ``--json`` does not change a successful payload. On a fixable failure it
  writes one JSON object to stderr.
- Exit 0 means success. Exit 2 means the caller can fix the invocation
  (usage, validation, missing path, refused overwrite). Exit 1 is an
  unexpected defect: the traceback is printed and not replaced.
- Fixable failures name the tool, the problem, and a hint. They are not
  swallowed and they are not turned into an empty success.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile

EXIT_OK = 0
EXIT_BUG = 1
EXIT_USAGE = 2

FIXABLE = (ValueError, OSError, UnicodeError, json.JSONDecodeError, zipfile.BadZipFile)


def wants_json(argv):
    """True when ``--json`` is an argv token. ``None`` reads ``sys.argv``."""
    tokens = sys.argv[1:] if argv is None else list(argv)
    return '--json' in tokens


def hint_for(exc):
    """A next step for a fixable failure. ``None`` when the message already says it."""
    message = str(exc)
    if '--help' in message or 'use --force' in message or 'npm ci' in message or message.startswith('hint:'):
        return None
    if isinstance(exc, FileNotFoundError):
        return 'pass a path that exists and is readable'
    if isinstance(exc, FileExistsError):
        return 'pass --force to replace an existing file, or choose a new path'
    if isinstance(exc, IsADirectoryError):
        return 'pass a file path, not a directory'
    if isinstance(exc, PermissionError):
        return 'the process cannot read or write that path'
    if isinstance(exc, json.JSONDecodeError):
        return 'the input must contain one JSON value'
    if isinstance(exc, UnicodeError):
        return 'the input must be UTF-8 text'
    lowered = message.lower()
    if 'not installed' in lowered or 'no such file' in lowered:
        return 'install the named program, or pass its path if it is not on PATH'
    return 'rerun with --help'


def fail_text(tool, message, *, hint=None, json_mode=False):
    """One stderr record: a line pair, or one JSON object."""
    text = str(message).strip() or 'failed'
    if json_mode:
        payload = {'ok': False, 'tool': tool, 'error': text, 'exit': EXIT_USAGE}
        if hint:
            payload['hint'] = hint
        return json.dumps(payload, ensure_ascii=False) + '\n'
    lines = f'{tool}: {text}\n'
    if hint:
        lines += f'hint: {hint}\n'
    return lines


def emit_error(tool, exc, *, json_mode=False, hint=None):
    """Write a fixable failure to stderr and return exit status 2."""
    if hint is None:
        hint = hint_for(exc)
    sys.stderr.write(fail_text(tool, exc, hint=hint, json_mode=json_mode))
    return EXIT_USAGE


def guard(tool, fn, *, json_mode=False, extra=()):
    """Run ``fn``. Fixable failures become exit 2. Anything else propagates."""
    try:
        return fn()
    except FIXABLE + tuple(extra) as exc:
        return emit_error(tool, exc, json_mode=json_mode)


class ToolParser(argparse.ArgumentParser):
    """ArgumentParser that reports usage problems with the shared contract."""

    def __init__(self, *args, tool=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool = tool or self.prog
        self.json_mode = False

    def add_json_flag(self):
        self.add_argument(
            '--json', action='store_true',
            help='on a fixable failure, write one JSON object to stderr; success output is unchanged',
        )

    def parse_args(self, args=None, namespace=None):
        self.json_mode = wants_json(args)
        return super().parse_args(args, namespace)

    def error(self, message):
        self.exit(EXIT_USAGE, fail_text(self.tool, message, hint='rerun with --help', json_mode=self.json_mode))


def bind_json_errors(parser, argv, tool):
    """Point an existing parser's ``error`` at this contract. Returns the parser."""
    parser.tool = tool
    parser.json_mode = wants_json(argv)

    def error(message, _parser=parser):
        _parser.exit(EXIT_USAGE, fail_text(tool, message, hint='rerun with --help', json_mode=_parser.json_mode))

    parser.error = error
    return parser
