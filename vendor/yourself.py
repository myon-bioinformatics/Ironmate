"""Read-only environment facts, using the standard library only.

No network requests, package installation or project-file content reads.
Fixed version commands are available only through explicit opt-in diagnostics.
Import is inert. Directory observations are shallow and explicitly requested.
"""

import json
import os
import platform
import re
import shutil
import subprocess
import stat
import sys
from pathlib import Path

__version__ = "0.3.0"
__all__ = ["collect", "directory_summary", "to_json", "to_markdown",
           "command_inventory", "workspace_facts", "listener_ports", "diagnose", "main"]


def directory_summary(path, *, sample_size=10):
    """Count immediate entry types and return a sorted, bounded name sample.

    No recursion or file-content reads. Symlinks are counted without following
    them. Invalid roots raise; individual entry errors are reported. Paths and
    names can be sensitive; callers choose whether to include this observation.
    """
    if isinstance(sample_size, bool) or not isinstance(sample_size, int) or sample_size < 0:
        raise ValueError("sample_size must be a non-negative integer")
    path = Path(path)
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("path must be a directory, not a symlink")
    counts = {"files": 0, "directories": 0, "symlinks": 0, "other": 0}
    names = []
    errors = []
    with os.scandir(path) as entries:
        for entry in entries:
            # Keep only the lexicographically smallest sample, not all names.
            if sample_size:
                names.append(entry.name)
                names.sort()
                del names[sample_size:]
            try:
                if entry.is_symlink():
                    kind = "symlinks"
                elif entry.is_dir(follow_symlinks=False):
                    kind = "directories"
                elif entry.is_file(follow_symlinks=False):
                    kind = "files"
                else:
                    kind = "other"
                counts[kind] += 1
            except OSError as error:
                errors.append({"name": entry.name, "reason": type(error).__name__})
    return {"path": str(path.absolute()), "counts": counts, "sample": names,
            "errors": sorted(errors, key=lambda item: item["name"])}


def collect(*, directory=None, sample_size=10, include_host=False):
    """Observe OS/runtime facts; optional host name and shallow directory data.

    No environment variable dump, username, IP, Git identity or inferred project
    facts. Host name is opt-in to keep the default report easy to share.
    Stable key order; values reflect the current environment, not a fixed fixture.
    """
    facts = {"schema_version": 1,
             "os": {"system": platform.system(), "release": platform.release(),
                    "machine": platform.machine()},
             "runtime": {"implementation": platform.python_implementation(),
                         "version": platform.python_version(),
                         "bits": 64 if sys.maxsize > 2 ** 32 else 32},
             "host": {"name": platform.node()} if include_host else None,
             "directory": None}
    if directory is not None:
        facts["directory"] = directory_summary(directory, sample_size=sample_size)
    return facts


def to_json(facts):
    """Serialize facts as deterministic Unicode JSON; reject non-finite numbers."""
    return json.dumps(facts, ensure_ascii=False, sort_keys=True, indent=2,
                      allow_nan=False) + "\n"


def _cell(value):
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "".join("\\u%04x" % ord(c) if ord(c) < 32 or ord(c) == 127 else c
                   for c in text).replace("|", "&#124;").replace("`", "&#96;")


def to_markdown(facts):
    """Render collect() facts as a concise Markdown report without raw controls."""
    rows = ["# Environment", "", "| Fact | Observed value |", "| --- | --- |"]
    for section in ("os", "runtime", "host"):
        for key, value in (facts.get(section) or {}).items():
            rows.append("| " + _cell(section + "." + key) + " | " + _cell(value) + " |")
    directory = facts.get("directory")
    if directory is not None:
        rows.extend(["", "## Directory (immediate entries only)", "",
                     "Path: " + _cell(directory["path"]), "",
                     "Counts: " + _cell(directory["counts"]), "",
                     "Sample: " + _cell(directory["sample"]), "",
                     "Errors: " + _cell(directory["errors"])])
    if "commands" in facts:
        rows.extend(["", "## Tools", "", "| Tool | Observation |", "| --- | --- |"])
        for tool in facts["commands"]:
            observed = tool["version"] or ("available; " + tool["status"] if tool["available"] else "not found")
            rows.append("| " + _cell(tool["name"]) + " | " + _cell(observed) + " |")
    for key in ("os_release", "workspace", "listeners"):
        if facts.get(key) is not None:
            rows.extend(["", key + ": " + _cell(facts[key])])
    return "\n".join(rows) + "\n"


# Fixed observation-only commands: no shell, arbitrary argv, service startup,
# builds, package installation, Docker daemon access, or compiler invocation.
_COMMANDS = {
    'python': ('--version',), 'git': ('--version',), 'docker': ('--version',),
    'node': ('--version',), 'cmake': ('--version',), 'ninja': ('--version',),
    'gcc': ('--version',), 'g++': ('--version',), 'clang': ('--version',),
    'rg': ('--version',),
    # Some CLIs (Flutter/Dart/npm/goma) can bootstrap/update or initialize state.
    # Discover their presence, but do not run them as an environment probe.
    'flutter': None, 'dart': None, 'npm': None, 'pytest': None,
    'goma': None, 'gomacc': None,
    'gh': None, 'uv': None, 'pip': None, 'pipx': None,
    'npx': None, 'pnpm': None, 'yarn': None, 'playwright': None,
    'actionlint': None, 'jq': None, 'curl': None,
    'ffmpeg': None, 'magick': None, 'tsc': None,
}
_MARKERS = ('pyproject.toml', 'requirements.txt', 'package.json', 'pubspec.yaml',
            'Dockerfile', 'compose.yaml', 'docker-compose.yml', 'CMakeLists.txt',
            'BUILD.gn', 'WORKSPACE', '.goma')


def command_inventory(names=None, *, versions=False, timeout=2):
    """Find fixed tool names; version execution is explicit opt-in.

    Runs only fixed version argv with shell=False, stdin disabled, no cwd
    override and a timeout. Reports numeric versions, never command output,
    paths, environment values, stdout or stderr. PATH executables must be trusted;
    a malicious/replaced binary cannot be made read-only by its argv.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30:
        raise ValueError('timeout must be a finite number in (0, 30]')
    if isinstance(names, str):
        raise TypeError('names must be a sequence, not a string')
    names = tuple(_COMMANDS) if names is None else tuple(names)
    if any(not isinstance(n, str) or n not in _COMMANDS for n in names):
        raise ValueError('unsupported command name')
    rows = []
    for name in sorted(set(names)):
        executable = sys.executable if name == 'python' else shutil.which(name)
        item = {'name': name, 'available': bool(executable), 'version': None,
                'status': 'not_found' if not executable else 'not_requested'}
        args = _COMMANDS[name]
        if executable and versions:
            if args is None:
                item['status'] = 'presence_only'
            else:
                try:
                    observed = subprocess.run([executable, *args], shell=False,
                                              stdin=subprocess.DEVNULL,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              timeout=timeout, check=False)
                    # Only a numeric version escapes the observation boundary.
                    output = (observed.stdout + b'\n' + observed.stderr)[:8192]
                    version = re.search(rb'(?<![\w.])v?(\d+(?:\.\d+){1,3})(?![\w.])', output)
                    if observed.returncode:
                        item['status'] = 'nonzero_exit'
                    elif version:
                        item['version'] = version.group(1).decode('ascii')
                        item['status'] = 'measured'
                    else:
                        item['status'] = 'unrecognized_version'
                except subprocess.TimeoutExpired:
                    item['status'] = 'timeout'
                except OSError:
                    item['status'] = 'execution_error'
        rows.append(item)
    return rows


def workspace_facts(path):
    """Observe project marker presence and disk capacity without content reads.

    No Git identity, dependency parsing or recursive inventory. Marker files are
    lstat-ed only; symlinks do not count as files. Disk facts are byte counts.
    """
    root = Path(path)
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise ValueError('workspace must be a directory, not a symlink')
    markers, errors = [], []
    for name in _MARKERS:
        try:
            mode = (root / name).lstat().st_mode
            if stat.S_ISREG(mode) or (name == '.goma' and stat.S_ISDIR(mode)):
                markers.append(name)
        except FileNotFoundError:
            continue
        except OSError as error:
            errors.append({'marker': name, 'reason': type(error).__name__})
    try:
        disk = shutil.disk_usage(root)
        storage = {'total_bytes': disk.total, 'used_bytes': disk.used,
                   'free_bytes': disk.free}
    except OSError as error:
        storage = None
        errors.append({'marker': 'storage', 'reason': type(error).__name__})
    return {'markers': markers, 'storage': storage, 'errors': errors}


def listener_ports(*, proc_root='/proc'):
    """Read Linux proc TCP LISTEN ports only, never connect or expose addresses.

    Unsupported platforms return measured=False. No port scan, PID ownership,
    UDP inference, remote connections or network commands. Restricted proc data
    is represented as an error; an empty observed table is distinct.
    """
    if platform.system() != 'Linux':
        return {'measured': False, 'tcp_ports': [], 'errors': ['unsupported_platform']}
    ports, errors, observed = set(), [], 0
    for name in ('tcp', 'tcp6'):
        try:
            with (Path(proc_root) / 'net' / name).open('r', encoding='ascii') as stream:
                next(stream, None)
                for line in stream:
                    fields = line.split()
                    if len(fields) < 4 or fields[3] != '0A':
                        continue
                    try:
                        port = int(fields[1].rsplit(':', 1)[1], 16)
                    except (ValueError, IndexError):
                        errors.append('malformed_' + name)
                        continue
                    if 0 <= port <= 65535:
                        ports.add(port)
                    else:
                        errors.append('malformed_' + name)
            observed += 1
        except (OSError, UnicodeError) as error:
            errors.append(name + ':' + type(error).__name__)
    return {'measured': observed > 0, 'tcp_ports': sorted(ports),
            'errors': sorted(set(errors))}


def diagnose(*, directory=None, include_host=False, versions=False,
             ports=False, commands=None, timeout=2):
    """Compact AI environment context; no environment changes or repairs.

    Defaults to tool presence only. Version commands and proc listener reads
    each require their own opt-in. Workspace inspection requires a directory.
    Does not import project code, read configs, inspect Git or contact a daemon.
    """
    facts = collect(include_host=include_host)
    facts['commands'] = command_inventory(commands, versions=versions, timeout=timeout)
    facts['workspace'] = workspace_facts(directory) if directory is not None else None
    facts['listeners'] = listener_ports() if ports else None
    facts['os_release'] = None
    if platform.system() == 'Linux':
        try:
            release = platform.freedesktop_os_release()
            facts['os_release'] = {k: release[k] for k in ('ID', 'VERSION_ID') if k in release}
        except OSError:
            pass
    return facts


def main(argv=None):
    """Direct single-file entry point; no-argument use observes current workspace."""
    import argparse
    parser = argparse.ArgumentParser(description="Read-only AI environment introduction")
    parser.add_argument("--directory", default=".")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--versions", action="store_true")
    parser.add_argument("--minimal", action="store_true",
                        help="OS/runtime only; omit workspace and tool observations")
    args = parser.parse_args(argv)
    try:
        facts = collect() if args.minimal else diagnose(
            directory=args.directory, versions=args.versions)
    except (OSError, ValueError) as error:
        print(type(error).__name__, file=sys.stderr)
        return 2
    print(to_json(facts) if args.format == "json" else to_markdown(facts), end="")
    partial = bool(facts.get("workspace") and facts["workspace"]["errors"])
    partial |= any(row["status"] in ("timeout", "execution_error", "nonzero_exit",
                                    "unrecognized_version")
                   for row in facts.get("commands", []))
    return 2 if partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
