"""Reusable CLI building blocks. Python 3.10+, standard library only.

Importing this module never parses argv or starts a subprocess.
External tools keep their own option semantics; pass their argv unchanged.
"""
from __future__ import annotations

import argparse
import base64
from difflib import get_close_matches
from collections.abc import Sequence as SequenceABC
from dataclasses import asdict, dataclass, field
import json
import math
import os
import re
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread
from typing import Any, Iterable, Mapping, Sequence, TextIO


__version__ = "0.0.0"

__all__ = [
    "Argument", "make_parser", "parse_args", "add_output_arguments",
    "add_execution_arguments", "add_node_arguments", "require_when",
    "positive_seconds", "Command", "CommandResult", "run_command",
    "render_output", "write_output", "pytest_command", "trim_output",
    "pytest_summary", "build_env", "NodeNotFoundError", "is_node_target",
    "resolve_node", "node_command", "run_node", "node_or_command",
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


class _SuggestingArgumentParser(argparse.ArgumentParser):
    """Offer a closest *option* on unknown-argument errors, without accepting it."""

    def parse_args(self, args=None, namespace=None):
        # Keep structured argv: error text loses token and -- boundaries.
        tokens = list(sys.argv[1:] if args is None else args)
        parsed, extras = self.parse_known_args(tokens, namespace)
        if extras:
            message = argparse._("unrecognized arguments: %s") % " ".join(extras)
            message += self._unknown_option_hint(tokens, extras)
            # argparse honors exit_on_error here starting with 3.12.5.
            # Earlier releases always call error(), even when it is false.
            if sys.version_info >= (3, 12, 5) and not self.exit_on_error:
                raise argparse.ArgumentError(None, message)
            self.error(message)
        return parsed

    def _unknown_option_hint(self, tokens, extras):
        boundary = tokens.index("--") if "--" in tokens else len(tokens)
        wrapper_tokens = tokens[:boundary]
        options = {option: action.help == argparse.SUPPRESS
                   for action in self._actions for option in action.option_strings
                   if option.startswith("--")}
        for token in extras:
            if token == "--":
                break
            if token not in wrapper_tokens:
                continue
            name = token.partition("=")[0]
            if ("-" not in self.prefix_chars or name in options
                    or re.fullmatch(r"--[A-Za-z0-9][A-Za-z0-9_-]*", name) is None):
                continue
            # Rank hidden options too, so their typos do not fall back to a
            # weaker public match. Never display the hidden winner.
            suggestions = get_close_matches(name, list(options), n=1, cutoff=0.7)
            if suggestions:
                candidate = suggestions[0]
                return "" if options[candidate] else f" (did you mean {candidate!r}?)"
        return ""


def make_parser(arguments: Iterable[Argument] = (), *, suggest_unknown: bool = False,
                **kwargs: Any) -> argparse.ArgumentParser:
    """Create a parser; optional unknown-option hints never change parsing."""
    if type(suggest_unknown) is not bool:
        raise TypeError("suggest_unknown must be bool")
    kwargs.setdefault("allow_abbrev", False)
    parser_class = _SuggestingArgumentParser if suggest_unknown else argparse.ArgumentParser
    parser = parser_class(**kwargs)
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
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="text renders a human document; json writes one JSON document (default: text)",
    )
    parser.add_argument("--output", type=Path, help="UTF-8 output file; default: stdout")


def add_execution_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="describe argv without executing")
    parser.add_argument(
        "--timeout",
        type=positive_seconds,
        default=None,
        metavar="SECONDS",
        help="positive finite seconds before the child is stopped",
    )
    parser.add_argument("--cwd", type=Path, help="working directory for the child process")


def add_node_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node", metavar="PATH", help="Node.js executable path")
    parser.add_argument("--node-flag", action="append", default=[], dest="node_flags",
                        metavar="FLAG", help="repeatable flag before the script target")


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
    output_limited: bool = False


def _decode(value: bytes | None) -> str:
    return (value or b"").decode("utf-8", errors="replace")


def _command_result_with_bytes(command: Command, returncode: int | None, stdout: bytes | None,
                               stderr: bytes | None, executed: bool, *,
                               timed_out: bool = False,
                               output_limited: bool = False) -> tuple[CommandResult, bytes, bytes]:
    out, err = stdout or b"", stderr or b""
    return (
        CommandResult(command.argv, returncode, _decode(out), _decode(err), executed,
                      timed_out, output_limited),
        out,
        err,
    )


def _run_bounded_with_bytes(command: Command, data: bytes | None, *, cwd: str | os.PathLike[str] | None,
                            timeout: float | None, env: Mapping[str, str] | None,
                            limit: int) -> tuple[CommandResult, bytes, bytes]:
    """Read two pipes concurrently with a shared byte cap; stop noisy children."""
    process = subprocess.Popen(
        command.argv, cwd=cwd, env=env, stdin=subprocess.PIPE if data is not None else None,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
    )
    lock = Lock()
    limited = Event()
    captured = [bytearray(), bytearray()]
    remaining = [limit]

    def reader(stream, index):
        try:
            while True:
                # BufferedReader.read(size) may wait for size/EOF even after a
                # smaller flushed write. read1() returns available pipe bytes
                # from one underlying read so cap+1 is detected promptly.
                chunk = stream.read1(min(4096, remaining[0] + 1) if not limited.is_set() else 4096)
                if not chunk:
                    break
                with lock:
                    if limited.is_set():
                        continue
                    size = min(len(chunk), remaining[0])
                    captured[index].extend(chunk[:size])
                    remaining[0] -= size
                    if size < len(chunk):
                        limited.set()
                        try:
                            process.kill()
                        except ProcessLookupError:
                            pass
        finally:
            stream.close()

    def writer():
        try:
            if data is not None and process.stdin is not None:
                process.stdin.write(data)
                process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass

    workers = [Thread(target=reader, args=(process.stdout, 0), daemon=True),
               Thread(target=reader, args=(process.stderr, 1), daemon=True)]
    if data is not None:
        workers.append(Thread(target=writer, daemon=True))
    for worker in workers:
        worker.start()
    timed_out = False
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
    for worker in workers:
        worker.join()
    return _command_result_with_bytes(
        command,
        None if timed_out or limited.is_set() else process.returncode,
        bytes(captured[0]), bytes(captured[1]),
        True,
        timed_out=timed_out,
        output_limited=limited.is_set(),
    )


def run_command(command: Command, *, cwd: str | os.PathLike[str] | None = None,
                timeout: float | None = None, dry_run: bool = False,
                env: Mapping[str, str] | None = None,
                stdin: str | bytes | None = None,
                max_output_bytes: int | None = None) -> CommandResult:
    """Capture UTF-8 text (replacement on invalid bytes), never use a shell.

    Nonzero exits are results. Launch failures raise OSError. Timeout returns
    partial output and no exit code. env, if provided, replaces the environment.
    Input accepts explicit UTF-8 text or raw bytes (including NUL records).
    No newline is appended. Output is buffered; streaming, binary output and
    process-tree cleanup are outside this contract. When max_output_bytes is set,
    stdout/stderr share a byte cap and the child is stopped on overflow.
    """
    result, _, _ = _run_command_with_bytes(
        command, cwd=cwd, timeout=timeout, dry_run=dry_run, env=env,
        stdin=stdin, max_output_bytes=max_output_bytes,
    )
    return result


def _run_command_with_bytes(command: Command, *, cwd: str | os.PathLike[str] | None = None,
                            timeout: float | None = None, dry_run: bool = False,
                            env: Mapping[str, str] | None = None,
                            stdin: str | bytes | None = None,
                            max_output_bytes: int | None = None) -> tuple[CommandResult, bytes, bytes]:
    """Like run_command, but also return captured stdout/stderr as raw bytes for the CLI."""
    if type(dry_run) is not bool:
        raise TypeError("dry_run must be bool")
    if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout must be positive and finite")
    if stdin is not None and not isinstance(stdin, (str, bytes)):
        raise TypeError("stdin must be str, bytes, or None")
    data = stdin.encode("utf-8") if isinstance(stdin, str) else stdin
    if max_output_bytes is not None and (type(max_output_bytes) is not int or max_output_bytes < 0):
        raise ValueError("max_output_bytes must be a nonnegative integer or None")
    if dry_run:
        return _command_result_with_bytes(command, None, b"", b"", False)
    if max_output_bytes is not None:
        return _run_bounded_with_bytes(
            command, data, cwd=cwd, timeout=timeout, env=env, limit=max_output_bytes,
        )
    try:
        completed = subprocess.run(command.argv, cwd=cwd, timeout=timeout, env=env,
                                   input=data, capture_output=True, shell=False, check=False)
    except subprocess.TimeoutExpired as exc:
        return _command_result_with_bytes(command, None, exc.stdout, exc.stderr, True, timed_out=True)
    return _command_result_with_bytes(command, completed.returncode, completed.stdout,
                                      completed.stderr, True)


def render_output(value: Any, *, format: str = "text") -> str:
    if format not in ("text", "json"):
        raise ValueError("format must be text or json")
    if isinstance(value, CommandResult):
        if format == "text":
            return value.stdout if value.executed else json.dumps(list(value.argv), ensure_ascii=False) + "\n"
        value = asdict(value)
        if not value["output_limited"]:
            del value["output_limited"]  # preserve the existing JSON contract
    if format == "json":
        return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    text = str(value)
    return text if text.endswith("\n") else text + "\n"


def write_output(value: Any, *, format: str = "text",
                 output: str | os.PathLike[str] | None = None,
                 stream: TextIO | None = None,
                 overwrite: bool = True) -> None:
    """Render before writing; exclusive hard-link publication for new output."""
    text = render_output(value, format=format)
    if output is None:
        (sys.stdout if stream is None else stream).write(text)
    else:
        if type(overwrite) is not bool:
            raise TypeError("overwrite must be bool")
        destination = Path(output)
        if overwrite:
            destination.write_text(text, encoding="utf-8", newline="\n")
        else:
            # On Windows, x-mode alone may follow a dangling symlink.
            # Stage complete bytes then publish with an exclusive hard link.
            # Filesystems without hard links fail closed; never unlink the target.
            if os.path.lexists(destination):
                raise FileExistsError("destination already exists: " + str(destination))
            with tempfile.TemporaryDirectory(prefix=".cli-args-", dir=destination.parent) as work:
                staged = Path(work) / "complete.txt"
                staged.write_text(text, encoding="utf-8", newline="\n")
                os.link(staged, destination)


class NodeNotFoundError(FileNotFoundError):
    """Raised when Node.js cannot be located or does not meet the minimum version."""


_NODE_PROBE_CACHE: dict[str, str] = {}
_NODE_MIN_MAJOR = 24
_NODE_VERSION = re.compile(r"(?:^|\s)v?(?P<major>\d+)(?:\.\d+)*", re.IGNORECASE)


def is_node_target(path: str | os.PathLike[str]) -> bool:
    """True when ``path`` names a JavaScript entry file by extension."""
    return Path(os.fspath(path)).suffix.lower() in (".js", ".cjs", ".mjs")


def _reject_windows_batch_wrapper(path: str) -> None:
    lowered = path.lower()
    if lowered.endswith(".cmd") or lowered.endswith(".bat"):
        raise NodeNotFoundError("cli_args: node batch wrappers (.cmd/.bat) are not supported: "
                                + path)


def _probe_node_once(path: str) -> str:
    cached = _NODE_PROBE_CACHE.get(path)
    if cached is not None:
        return cached
    _reject_windows_batch_wrapper(path)
    try:
        completed = subprocess.run(
            (path, "--version"), capture_output=True, timeout=5, shell=False, check=False,
        )
    except FileNotFoundError as exc:
        raise NodeNotFoundError("cli_args: node executable not found: " + path) from exc
    except OSError as exc:
        raise NodeNotFoundError("cli_args: node version probe failed: " + path) from exc
    except subprocess.TimeoutExpired as exc:
        raise NodeNotFoundError("cli_args: node version probe timed out: " + path) from exc
    output = _decode(completed.stdout) + _decode(completed.stderr)
    match = _NODE_VERSION.search(output)
    if completed.returncode != 0 or match is None:
        raise NodeNotFoundError("cli_args: node version probe failed: " + path)
    major = int(match.group("major"))
    if major < _NODE_MIN_MAJOR:
        raise NodeNotFoundError(
            f"cli_args: node version must be {_NODE_MIN_MAJOR} or newer (found {major}): " + path)
    _NODE_PROBE_CACHE[path] = path
    return path


def _node_executable(node: str | os.PathLike[str] | None, *, probe: bool) -> str:
    """Return a Node argv[0] token; probe runs ``node --version`` when enabled."""
    explicit = node is not None
    if not explicit and "CLI_ARGS_NODE" in os.environ:
        node = os.environ["CLI_ARGS_NODE"]
        explicit = True
    if explicit:
        path = _token(node)
        return _probe_node_once(path) if probe else path

    if not probe:
        env_node = os.environ.get("NODE")
        if env_node:
            return _token(env_node)
        discovered = shutil.which("node")
        return discovered if discovered else "node"

    candidates: list[str] = []
    env_node = os.environ.get("NODE")
    if env_node:
        candidates.append(_token(env_node))
    discovered = shutil.which("node")
    if discovered:
        candidates.append(discovered)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            return _probe_node_once(candidate)
        except NodeNotFoundError:
            continue
    raise NodeNotFoundError("cli_args: node executable not found")


def resolve_node(node: str | os.PathLike[str] | None = None) -> str:
    """Locate a Node 24+ executable.

    Explicit ``node``, ``CLI_ARGS_NODE``, or a caller-supplied ``--node`` value must
    work as given; auto-discovery tries ``NODE`` then ``shutil.which('node')``.
    """
    return _node_executable(node, probe=True)


def node_command(target: str | os.PathLike[str], *args: str | os.PathLike[str],
                 node: str | os.PathLike[str] | None = None,
                 node_flags: Sequence[str | os.PathLike[str]] = (),
                 probe: bool = True) -> Command:
    """Build ``[node, *node_flags, target, *args]`` without reinterpreting passthrough argv."""
    executable = _node_executable(node, probe=probe)
    flags = _tokens(node_flags)
    script = _token(target)
    trailing = tuple(_token(value) for value in args)
    return Command((executable, *flags, script, *trailing))


def run_node(target: str | os.PathLike[str], *args: str | os.PathLike[str],
             node: str | os.PathLike[str] | None = None,
             node_flags: Sequence[str | os.PathLike[str]] = (),
             **run_command_kwargs: Any) -> CommandResult:
    dry_run = run_command_kwargs.get("dry_run", False)
    if type(dry_run) is not bool:
        raise TypeError("dry_run must be bool")
    return run_command(
        node_command(target, *args, node=node, node_flags=node_flags, probe=not dry_run),
        **run_command_kwargs,
    )


def node_or_command(argv: Sequence[str | os.PathLike[str]], *,
                    node: str | os.PathLike[str] | None = None,
                    node_flags: Sequence[str | os.PathLike[str]] = (),
                    probe: bool = True) -> Command:
    """Wrap ``argv[0]`` with Node when it names a ``.js`` / ``.cjs`` / ``.mjs`` file."""
    tokens = _tokens(argv)
    if not tokens:
        return Command(tokens)
    if is_node_target(tokens[0]):
        return node_command(tokens[0], *tokens[1:], node=node, node_flags=node_flags,
                            probe=probe)
    return Command(tokens)


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


def trim_output(text: str, *, head: int = 40, tail: int = 40) -> str:
    """Keep the first ``head`` and last ``tail`` lines with an explicit omission marker.

    A log cut with ``head``/``tail`` silently looks complete; here the gap is a line
    ``... N line(s) omitted ...`` so a reader (or an agent) knows output is missing.
    Text that already fits is returned unchanged; a trailing newline is kept.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    for value in (head, tail):
        if type(value) is not int or value < 0:
            raise ValueError("head and tail must be nonnegative integers")
    lines = text.splitlines(keepends=True)
    if len(lines) <= head + tail:
        return text
    omitted = len(lines) - head - tail
    kept_tail = lines[len(lines) - tail:] if tail else []
    gap = f"... {omitted} line(s) omitted ...\n"
    body = "".join(lines[:head])
    if body and not body.endswith(("\n", "\r")):
        body += "\n"
    return body + gap + "".join(kept_tail)


_PYTEST_FINAL = re.compile(
    r"^=*\s*((?:\d+ (?:failed|passed|skipped|deselected|xfailed|xpassed|warnings?|errors?|rerun)(?:, )?)+"
    r"|no tests ran)( in [\d.]+s(?: \([^)]*\))?)\s*=*$")
_PYTEST_DECIDING = re.compile(r"^(?:FAILED|ERROR|XPASS|INTERNALERROR)\b|^E\s+\S|^ERROR collecting\b")


def pytest_summary(output: str, *, max_lines: int = 60) -> dict[str, Any]:
    """The lines that decide a pytest run, from its captured output.

    Returns ``counts`` from the final ``N failed, M passed in Xs`` line (``summary``),
    ``failed``/``errors`` from the ``-ra`` short summary (``FAILED``/``ERROR`` lines),
    ``coverage`` (pytest-cov ``TOTAL`` row and the ``Required test coverage`` verdict)
    and ``deciding_lines``: those lines plus the first ``E`` line of each failure and
    ``INTERNALERROR``, in order, at most ``max_lines`` (``truncated`` says so).
    """
    if not isinstance(output, str):
        raise TypeError("output must be str")
    if type(max_lines) is not int or max_lines < 1:
        raise ValueError("max_lines must be a positive integer")
    summary, counts, failed, errors, deciding = None, {}, [], [], []
    coverage: dict[str, Any] = {"total": None, "required": None, "required_met": None}
    seen_e = False
    for raw in output.splitlines():
        line = raw.rstrip()
        final = _PYTEST_FINAL.match(line.strip())
        keep = False
        if final:
            summary = (final.group(1) + final.group(2)).strip()
            counts = {}
            for number, word in re.findall(r"(\d+) (\w+)", final.group(1)):
                key = {"warning": "warnings", "error": "errors"}.get(word, word)
                counts[key] = counts.get(key, 0) + int(number)
            keep = True
        elif line.startswith("TOTAL") and re.search(r"\d+%$", line):
            coverage["total"] = " ".join(line.split())
            keep = True
        elif "Required test coverage of" in line:
            coverage["required"] = re.sub(r"^FAIL\s+", "", line.strip())
            coverage["required_met"] = "reached" in line and "not reached" not in line
            keep = True
        elif _PYTEST_DECIDING.match(line):
            if line.startswith("FAILED"):
                failed.append(line[7:].strip())
            elif line.startswith("ERROR ") and not line.startswith("ERROR collecting"):
                errors.append(line[6:].strip())
            if line.startswith("E "):
                keep = not seen_e
                seen_e = True
            else:
                keep = True
        elif line.startswith("___") and line.endswith("___"):
            seen_e = False  # next failure section: keep its first E line
        if keep:
            deciding.append(line)
    return {"summary": summary, "counts": counts, "failed": failed, "errors": errors, "coverage": coverage,
            "deciding_lines": deciding[:max_lines], "truncated": len(deciding) > max_lines}


def build_env(extra: Mapping[str, str] | Sequence[str] | None = None, *,
              inherit: bool = True, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """Construct an environment dictionary for run_command.

    If inherit is True (default), starts with base (default: os.environ).
    extra can be a Mapping or an ordered sequence of "KEY=VALUE" strings.
    Rejects scalar or unordered iterables, non-string keys/values, NUL bytes,
    empty keys, keys containing "=", and malformed "KEY=VALUE" entries.
    """
    if type(inherit) is not bool:
        raise TypeError("inherit must be bool")
    if base is None:
        base_map = dict(os.environ) if inherit else {}
    else:
        if not isinstance(base, Mapping):
            raise TypeError("base must be a Mapping or None")
        base_map = dict(base) if inherit else {}

    def validate_entry(key, value):
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("environment keys and values must be strings")
        if "\0" in key or "\0" in value:
            raise ValueError("environment keys and values must not contain NUL")
        if not key or "=" in key:
            raise ValueError("environment keys must be nonempty and must not contain '='")

    # Validate caller-supplied base entries too, including the extra=None path.
    # The process's inherited environment is already valid for its platform.
    if base is not None:
        for key, value in base_map.items():
            validate_entry(key, value)
    result = dict(base_map)
    if extra is None:
        return result

    if isinstance(extra, Mapping):
        for k, v in extra.items():
            validate_entry(k, v)
            result[k] = v
        return result

    if (isinstance(extra, (str, bytes, bytearray, os.PathLike))
            or not isinstance(extra, SequenceABC)):
        raise TypeError("extra environment entries must be a Mapping or ordered sequence of KEY=VALUE strings")

    for item in extra:
        if not isinstance(item, str):
            raise TypeError("environment entries must be strings in KEY=VALUE format")
        if "\0" in item:
            raise ValueError("environment entries must not contain NUL")
        if "=" not in item:
            raise ValueError(f"invalid environment entry '{item}': missing '='")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError(f"invalid environment entry '{item}': empty key")
        result[key] = value

    return result


class _CliRequestError(Exception):
    """Invalid stdin JSON or request fields (exit 2)."""


CLI_STDIN_MAX_BYTES = 4 * 1024 * 1024
"""Maximum UTF-8 bytes read from stdin by ``cli_args.py run`` / ``render``."""

CLI_RUN_DEFAULT_MAX_OUTPUT_BYTES = 4 * 1024 * 1024
"""Default combined stdout/stderr byte cap for Node ``cli_args.cjs`` (always sent as ``max_output``)."""

CLI_RUN_MAX_OUTPUT_BYTES = 8 * 1024 * 1024
"""Maximum ``max_output`` the Node bridge accepts; larger child output needs another host path."""

CLI_RUN_RESPONSE_MAX_BYTES = 96 * 1024 * 1024
"""Declared UTF-8 byte cap for ``cli_args.py run`` JSON stdout (Node ``response_max_bytes``)."""

CLI_RENDER_RESPONSE_MAX_BYTES = 96 * 1024 * 1024
"""Declared UTF-8 byte cap for ``cli_args.py render`` stdout (Node ``--response-max-bytes``)."""

CLI_HOST_RESPONSE_MARGIN_BYTES = 512
"""Node ``maxBuffer`` is ``response_max_bytes +`` this margin (never rely on a JSON size formula)."""

_CLI_STDIN_MAX_BYTES = CLI_STDIN_MAX_BYTES
_RUN_REQUEST_KEYS = frozenset({
    "argv", "timeout", "cwd", "env", "input", "max_output", "dry_run", "response_max_bytes",
})


def cli_host_max_buffer_bytes(response_max_bytes: int) -> int:
    """``maxBuffer`` for ``py_launch`` when Python enforces ``response_max_bytes`` before writing."""
    if type(response_max_bytes) is not int or response_max_bytes < 0:
        raise ValueError("response_max_bytes must be a nonnegative integer")
    return response_max_bytes + CLI_HOST_RESPONSE_MARGIN_BYTES


class _CliResponseTooLargeError(Exception):
    """Serialized CLI stdout would exceed the declared response_max_bytes cap (exit 1)."""


def _check_response_max_bytes(encoded: bytes | bytearray, response_max_bytes: int | None) -> None:
    if response_max_bytes is None:
        return
    if type(response_max_bytes) is not int or response_max_bytes < 0:
        raise _CliRequestError("response_max_bytes must be a nonnegative integer")
    if len(encoded) > response_max_bytes:
        raise _CliResponseTooLargeError(
            f"response exceeds response_max_bytes ({response_max_bytes} bytes, got {len(encoded)})",
        )


def _emit_cli_stdout_bytes(encoded: bytes | bytearray, response_max_bytes: int | None) -> None:
    _check_response_max_bytes(encoded, response_max_bytes)
    binary_out = getattr(sys.stdout, "buffer", None)
    if binary_out is not None:
        binary_out.write(encoded)
        binary_out.flush()
    else:
        sys.stdout.write(encoded.decode("utf-8"))
        sys.stdout.flush()


def _emit_cli_stdout(text: str, response_max_bytes: int | None) -> None:
    _emit_cli_stdout_bytes(text.encode("utf-8"), response_max_bytes)


def _emit_cli_json_stdout(value: Any, response_max_bytes: int | None) -> None:
    """Serialize JSON to stdout incrementally so oversized values abort before a full buffer."""
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2, allow_nan=False)
    buffer = bytearray()
    for piece in encoder.iterencode(value):
        chunk = piece.encode("utf-8")
        if response_max_bytes is not None and len(buffer) + len(chunk) > response_max_bytes:
            raise _CliResponseTooLargeError(
                f"response exceeds response_max_bytes ({response_max_bytes} bytes, "
                f"got more than {response_max_bytes})",
            )
        buffer.extend(chunk)
    newline = b"\n"
    if response_max_bytes is not None and len(buffer) + len(newline) > response_max_bytes:
        raise _CliResponseTooLargeError(
            f"response exceeds response_max_bytes ({response_max_bytes} bytes, "
            f"got {len(buffer) + len(newline)})",
        )
    buffer.extend(newline)
    _emit_cli_stdout_bytes(buffer, response_max_bytes)


def _reject_json_non_finite(constant: str) -> Any:
    raise _CliRequestError("JSON must not contain NaN or Infinity")


def _read_stdin_text() -> str:
    raw = sys.stdin.buffer.read(_CLI_STDIN_MAX_BYTES + 1)
    if len(raw) > _CLI_STDIN_MAX_BYTES:
        raise _CliRequestError("stdin exceeds size limit")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _CliRequestError("stdin must be UTF-8") from exc


def _command_result_cli_json(result: CommandResult, stdout_raw: bytes, stderr_raw: bytes) -> dict[str, Any]:
    payload = asdict(result)
    payload["stdout_b64"] = base64.standard_b64encode(stdout_raw).decode("ascii")
    payload["stderr_b64"] = base64.standard_b64encode(stderr_raw).decode("ascii")
    return payload


def _parse_run_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _CliRequestError("request must be a JSON object")
    unknown = sorted(set(payload) - _RUN_REQUEST_KEYS)
    if unknown:
        raise _CliRequestError("unknown request keys: " + ", ".join(unknown))
    if "argv" not in payload:
        raise _CliRequestError("argv is required")
    argv = payload["argv"]
    if not isinstance(argv, list):
        raise _CliRequestError("argv must be a JSON array")
    try:
        command = Command(tuple(argv))
    except (TypeError, ValueError) as exc:
        raise _CliRequestError(str(exc)) from exc
    timeout = payload.get("timeout")
    if timeout is not None:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise _CliRequestError("timeout must be a positive finite number")
    cwd = payload.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        raise _CliRequestError("cwd must be a string")
    env = payload.get("env")
    env_map: dict[str, str] | None = None
    if env is not None:
        if not isinstance(env, dict):
            raise _CliRequestError("env must be a JSON object")
        try:
            env_map = build_env(env, inherit=True)
        except (TypeError, ValueError) as exc:
            raise _CliRequestError(str(exc)) from exc
    stdin = payload.get("input")
    if stdin is not None and not isinstance(stdin, str):
        raise _CliRequestError("input must be a string or null")
    max_output = payload.get("max_output")
    if max_output is not None and (type(max_output) is not int or max_output < 0):
        raise _CliRequestError("max_output must be a nonnegative integer")
    dry_run = payload.get("dry_run", False)
    if type(dry_run) is not bool:
        raise _CliRequestError("dry_run must be a boolean")
    response_max_bytes = payload.get("response_max_bytes")
    if response_max_bytes is not None and (type(response_max_bytes) is not int or response_max_bytes < 0):
        raise _CliRequestError("response_max_bytes must be a nonnegative integer")
    return {
        "command": command,
        "cwd": cwd,
        "timeout": timeout,
        "env": env_map,
        "stdin": stdin,
        "max_output_bytes": max_output,
        "dry_run": dry_run,
        "response_max_bytes": response_max_bytes,
    }


def _load_stdin_json() -> Any:
    raw = _read_stdin_text()
    if not raw.strip():
        raise _CliRequestError("stdin must contain JSON")
    try:
        return json.loads(raw, parse_constant=_reject_json_non_finite)
    except json.JSONDecodeError as exc:
        raise _CliRequestError("invalid JSON: " + exc.msg) from exc


def _cli_run() -> int:
    request = _parse_run_request(_load_stdin_json())
    try:
        result, stdout_raw, stderr_raw = _run_command_with_bytes(
            request["command"],
            cwd=request["cwd"],
            timeout=request["timeout"],
            dry_run=request["dry_run"],
            env=request["env"],
            stdin=request["stdin"],
            max_output_bytes=request["max_output_bytes"],
        )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    body = json.dumps(
        _command_result_cli_json(result, stdout_raw, stderr_raw),
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
    ) + "\n"
    _emit_cli_stdout(body, request["response_max_bytes"])
    return 0


def _cli_render(format: str, response_max_bytes: int | None) -> int:
    payload = _load_stdin_json()
    if format == "json":
        _emit_cli_json_stdout(payload, response_max_bytes)
        return 0
    try:
        rendered = render_output(payload, format=format)
    except ValueError as exc:
        raise _CliRequestError(str(exc)) from exc
    _emit_cli_stdout(rendered, response_max_bytes)
    return 0


def _main(argv: Sequence[str] | None = None) -> int:
    help_formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(
        prog="cli_args.py",
        description=(
            "Machine-facing entry points for run_command and render_output.\n"
            "exit 0: request handled; child status is JSON returncode, not this exit.\n"
            "exit 1: child could not be started, or the response exceeded its byte cap.\n"
            "exit 2: usage error, invalid JSON, or a rejected request field (one stderr line)."
        ),
        formatter_class=help_formatter,
        exit_on_error=False,
    )
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    subparsers = parser.add_subparsers(dest="command", required=False)
    subparsers.add_parser(
        "run",
        help="run a command from a JSON request on stdin",
        description=(
            "Read one JSON object from stdin. argv (array of strings) is required.\n"
            "Optional keys: timeout, cwd, env, input, max_output, dry_run, response_max_bytes.\n"
            "Unknown keys and wrong types are exit 2. dry_run must be a JSON boolean.\n"
            "When the request is handled this process exits 0 and the child status is returncode."
        ),
        formatter_class=help_formatter,
    )
    render_parser = subparsers.add_parser(
        "render",
        help="render a JSON value from stdin",
        description="Read one JSON value from stdin and write render_output to stdout.",
        formatter_class=help_formatter,
    )
    render_parser.add_argument("--format", choices=("text", "json"), default="text")
    render_parser.add_argument(
        "--response-max-bytes",
        type=int,
        default=None,
        help="reject stdout larger than this UTF-8 byte cap (Node bridge sets CLI_RENDER_RESPONSE_MAX_BYTES)",
    )
    try:
        args = parser.parse_args(None if argv is None else list(argv))
    except argparse.ArgumentError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.command is None:
        parser.print_usage(sys.stderr)
        print("cli_args.py: error: command required (run or render)", file=sys.stderr)
        return 2
    try:
        if args.command == "run":
            return _cli_run()
        return _cli_render(args.format, args.response_max_bytes)
    except _CliRequestError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except _CliResponseTooLargeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc) or exc.__class__.__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
