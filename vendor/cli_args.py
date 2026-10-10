"""Reusable CLI building blocks. Python 3.10+, standard library only.

Importing this module never parses argv or starts a subprocess.
External tools keep their own option semantics; pass their argv unchanged.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence, TextIO

__all__ = [
    "Argument", "make_parser", "parse_args", "add_output_arguments",
    "add_execution_arguments", "require_when", "positive_seconds",
    "Command", "CommandResult", "run_command", "render_output",
    "write_output", "pytest_command",
]


@dataclass(frozen=True)
class Argument:
    """Native argparse names and kwargs, without a separate option language."""

    names: tuple[str, ...]
    kwargs: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        names = _tokens(self.names)
        if not names:
            raise ValueError("at least one argument name is required")
        object.__setattr__(self, "names", names)


def make_parser(arguments: Iterable[Argument] = (), **kwargs: Any) -> argparse.ArgumentParser:
    """Create a parser; option abbreviation is disabled unless requested."""
    kwargs.setdefault("allow_abbrev", False)
    parser = argparse.ArgumentParser(**kwargs)
    for argument in arguments:
        parser.add_argument(*argument.names, **argument.kwargs)
    return parser


def parse_args(arguments: Iterable[Argument] = (), argv: Sequence[str] | None = None,
               **kwargs: Any) -> argparse.Namespace:
    tokens = None if argv is None else _tokens(argv)
    return make_parser(arguments, **kwargs).parse_args(tokens)


def positive_seconds(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected positive finite seconds") from exc
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("expected positive finite seconds")
    return number


def add_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, help="UTF-8 output file; default: stdout")


def add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="describe argv without executing")
    parser.add_argument("--timeout", type=positive_seconds, default=None, metavar="SECONDS")
    parser.add_argument("--cwd", type=Path)


def require_when(parser: argparse.ArgumentParser, args: argparse.Namespace, *,
                 when: bool, required: Sequence[str]) -> None:
    """Require non-None destinations when a condition holds. False/0 are values."""
    if when:
        required_names = _tokens(required)
        missing = [name for name in required_names if getattr(args, name, None) is None]
        if missing:
            parser.error("required for this mode: " + ", ".join(missing))


def _token(value: Any) -> str:
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        raise TypeError("argv tokens must be strings or text paths")
    if "\0" in value:
        raise ValueError("argv tokens must not contain NUL")
    return value


def _tokens(values: Sequence[str | os.PathLike[str]]) -> tuple[str, ...]:
    """Validate an ordered finite token sequence; reject scalar/unordered iterables."""
    if (isinstance(values, (str, bytes, bytearray, os.PathLike))
            or not isinstance(values, SequenceABC)):
        raise TypeError("argv token collections must be ordered sequences, not scalar or unordered iterables")
    return tuple(_token(value) for value in values)


@dataclass(frozen=True)
class Command:
    """Immutable argv builder. Order is explicit; no shell quoting or splitting."""

    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        tokens = _tokens(self.argv)
        if not tokens or not tokens[0]:
            raise ValueError("a non-empty executable is required")
        object.__setattr__(self, "argv", tokens)

    def positional(self, *values: str | os.PathLike[str]) -> Command:
        return Command(self.argv + tuple(_token(value) for value in values))

    def flag(self, name: str, enabled: bool = True) -> Command:
        if not isinstance(enabled, bool):
            raise TypeError("enabled must be bool")
        return self.positional(name) if enabled else self

    def option(self, name: str, value: str | os.PathLike[str] | None, *,
               attached: bool = False) -> Command:
        """None omits an option; empty strings remain real values.

        attached=True creates --name=value, useful for leading-hyphen values
        only when the destination command supports that spelling.
        """
        if value is None:
            return self
        name, value = _token(name), _token(value)
        return self.positional(name + "=" + value) if attached else self.positional(name, value)

    def repeated(self, name: str, values: Sequence[str | os.PathLike[str]]) -> Command:
        command = self
        for value in _tokens(values):
            command = command.option(name, value)
        return command

    def multiple(self, name: str, values: Sequence[str | os.PathLike[str]]) -> Command:
        tokens = _tokens(values)
        return self.positional(name, *tokens) if tokens else self

    def passthrough(self, values: Sequence[str], *, separator: bool = False) -> Command:
        """Preserve argv. Add -- only if the destination supports it."""
        tokens = _tokens(values)
        return self.positional(*(("--",) if separator else ()), *tokens)


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    executed: bool
    timed_out: bool = False


def _decode(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", errors="replace")


def run_command(command: Command, *, cwd: str | os.PathLike[str] | None = None,
                timeout: float | None = None, dry_run: bool = False,
                env: Mapping[str, str] | None = None) -> CommandResult:
    """Capture UTF-8 text (replacement on invalid bytes), never use a shell.

    Nonzero exits are results. Launch failures raise OSError. Timeout returns
    partial output and no exit code. env, if provided, replaces the environment.
    Output is buffered; streaming, binary output and process-tree cleanup are
    outside this initial contract.
    """
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be positive and finite")
    if dry_run:
        return CommandResult(command.argv, None, "", "", False)
    try:
        result = subprocess.run(command.argv, cwd=cwd, timeout=timeout, env=env,
                                capture_output=True, shell=False, check=False)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(command.argv, None, _decode(exc.stdout), _decode(exc.stderr),
                             True, True)
    return CommandResult(command.argv, result.returncode, _decode(result.stdout),
                         _decode(result.stderr), True)


def render_output(value: Any, *, format: str = "text") -> str:
    if format not in ("text", "json"):
        raise ValueError("format must be text or json")
    if isinstance(value, CommandResult):
        if format == "text":
            return value.stdout if value.executed else json.dumps(list(value.argv), ensure_ascii=False) + "\n"
        value = asdict(value)
    if format == "json":
        return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    text = str(value)
    return text if text.endswith("\n") else text + "\n"


def write_output(value: Any, *, format: str = "text",
                 output: str | os.PathLike[str] | None = None,
                 stream: TextIO | None = None) -> None:
    """Render before writing; files are UTF-8/LF, overwritten, parents are not created."""
    text = render_output(value, format=format)
    if output is None:
        (sys.stdout if stream is None else stream).write(text)
    else:
        Path(output).write_text(text, encoding="utf-8", newline="\n")


def pytest_command(paths: Sequence[str] = (), *, quiet: bool = False,
                   tb: str | None = None, summary: bool = False,
                   extra: Sequence[str] = (), python: str | None = None) -> Command:
    """Optional preset: pytest is an external runtime dependency, never imported."""
    if tb is not None and tb not in ("auto", "long", "short", "line", "native", "no"):
        raise ValueError("unsupported pytest traceback style")
    path_tokens = _tokens(paths)
    return (Command((sys.executable if python is None else python, "-m", "pytest"))
            .flag("-q", quiet).option("--tb", tb).flag("-ra", summary)
            .passthrough(extra).positional(*path_tokens))
