#!/usr/bin/env python3
"""Fetch a pure-Python wheel from PyPI and import it without pip or uv.

The JSON API selects the latest release (or ``--version``). A ``py3-none-any``
or ``py2.py3-none-any`` wheel is cached only after its sha256 matches the
digest PyPI publishes. The wheel zip can sit on ``sys.path`` (zipimport).

Runtime dependencies are refused. Extras are not selected. An environment
marker is evaluated first, so a requirement such as
``typing_extensions>=4.0; python_version < "3.11"`` is inactive on
Python 3.11 and newer. A marker this module cannot evaluate is treated as
active. Transitive dependencies are not installed.

    python scripts/fetch_module.py resolve pypdf
    python scripts/fetch_module.py fetch pypdf --cache build/cdn-cache
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

INDEX = os.environ.get("FETCH_MODULE_INDEX", "https://pypi.org/pypi")
PURE = re.compile(r"-py3-none-any\.whl$|-py2\.py3-none-any\.whl$")
_RELEASE = re.compile(r"\d+(?:\.\d+)*")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.]*")
_OPS = ("===", "==", "~=", "!=", "<=", ">=", "<", ">", "not in", "in")
_ENV_KEYS = {
    "implementation_name",
    "implementation_version",
    "os_name",
    "platform_machine",
    "platform_release",
    "platform_system",
    "platform_version",
    "python_full_version",
    "platform_python_implementation",
    "python_version",
    "sys_platform",
    "extra",
}


def _get(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"https only: {url}")
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _format_full_version(info) -> str:
    version = f"{info.major}.{info.minor}.{info.micro}"
    if info.releaselevel != "final":
        version += info.releaselevel[0] + str(info.serial)
    return version


def marker_environment(overrides: dict | None = None) -> dict:
    """Marker values for this interpreter. ``extra`` stays empty (no extra selected)."""
    env = {
        "implementation_name": sys.implementation.name,
        "implementation_version": _format_full_version(sys.implementation.version),
        "os_name": os.name,
        "platform_machine": platform.machine(),
        "platform_release": platform.release(),
        "platform_system": platform.system(),
        "platform_version": platform.version(),
        "python_full_version": platform.python_version(),
        "platform_python_implementation": platform.python_implementation(),
        "python_version": ".".join(platform.python_version_tuple()[:2]),
        "sys_platform": sys.platform,
        "extra": "",
    }
    if overrides:
        for key, value in overrides.items():
            env[key] = "" if value is None else str(value)
    return env


def _canonicalize(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _version_key(value: str):
    """Plain release key, or None. Trailing zeros do not affect equality."""
    text = value.strip()
    if not _RELEASE.fullmatch(text):
        return None
    parts = [int(part) for part in text.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _version_class(value: str) -> str:
    text = value.strip()
    if _version_key(text) is not None:
        return "release"
    if re.search(r"\d", text):
        return "complex"
    return "other"


def _compare(left: str, op: str, right: str, *, left_extra: bool, right_extra: bool) -> bool:
    if left_extra or right_extra:
        left, right = _canonicalize(left), _canonicalize(right)
    if op == "===":
        return left == right
    if op == "in":
        return str(left) in str(right)
    if op == "not in":
        return str(left) not in str(right)
    left_class, right_class = _version_class(left), _version_class(right)
    if left_class == "complex" or right_class == "complex":
        raise ValueError(f"unsupported version marker operand: {left!r} {op} {right!r}")
    if left_class == "release" and right_class == "release":
        if op == "~=":
            return _compatible(left, right)
        order = (_version_key(left) > _version_key(right)) - (_version_key(left) < _version_key(right))
        return {
            "==": order == 0,
            "!=": order != 0,
            "<": order < 0,
            "<=": order <= 0,
            ">": order > 0,
            ">=": order >= 0,
        }[op]
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op == "~=":
        return False
    return False


def _compatible(left: str, right: str) -> bool:
    release = tuple(int(part) for part in right.strip().split("."))
    if len(release) < 2:
        return False
    prefix = release[:-1]
    left_release = tuple(int(part) for part in left.strip().split("."))
    if left_release[: len(prefix)] != prefix:
        return False
    return _version_key(left) >= _version_key(right)


def _tokenize(marker: str) -> list[tuple[str, str]]:
    tokens = []
    i, n = 0, len(marker)
    while i < n:
        if marker[i].isspace():
            i += 1
            continue
        if marker[i] in "'\"":
            quote = marker[i]
            end = marker.find(quote, i + 1)
            if end < 0 or "\\" in marker[i + 1 : end]:
                raise ValueError(f"unsupported marker string: {marker!r}")
            tokens.append(("str", marker[i + 1 : end]))
            i = end + 1
            continue
        if marker[i] == "(":
            tokens.append(("lp", "("))
            i += 1
            continue
        if marker[i] == ")":
            tokens.append(("rp", ")"))
            i += 1
            continue
        for op in _OPS:
            if marker.startswith(op, i):
                nxt = i + len(op)
                if nxt == n or marker[nxt].isspace() or marker[nxt] in "'\"()":
                    tokens.append(("op", op))
                    i = nxt
                    break
        else:
            for word in ("and", "or"):
                if marker.startswith(word, i):
                    nxt = i + len(word)
                    if nxt == n or not (marker[nxt].isalnum() or marker[nxt] in "_."):
                        tokens.append(("word", word))
                        i = nxt
                        break
            else:
                match = _IDENT.match(marker, i)
                if not match:
                    raise ValueError(f"unsupported marker syntax: {marker[i:]!r}")
                tokens.append(("ident", match.group(0)))
                i = match.end()
                continue
            continue
    return tokens


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]):
        self.tokens = tokens
        self.i = 0

    def peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, kind=None, value=None):
        token = self.peek()
        if token is None or (kind and token[0] != kind) or (value and token[1] != value):
            raise ValueError("unsupported marker syntax")
        self.i += 1
        return token

    def parse(self):
        node = self.or_expr()
        if self.peek() is not None:
            raise ValueError("unsupported marker syntax")
        return node

    def or_expr(self):
        nodes = [self.and_expr()]
        while self.peek() == ("word", "or"):
            self.take()
            nodes.append(self.and_expr())
        return ("or", nodes) if len(nodes) > 1 else nodes[0]

    def and_expr(self):
        nodes = [self.item()]
        while self.peek() == ("word", "and"):
            self.take()
            nodes.append(self.item())
        return ("and", nodes) if len(nodes) > 1 else nodes[0]

    def item(self):
        if self.peek() == ("lp", "("):
            self.take()
            node = self.or_expr()
            self.take("rp")
            return node
        left = self.atom()
        op = self.take("op")[1]
        return ("cmp", op, left, self.atom())

    def atom(self):
        token = self.peek()
        if token is None:
            raise ValueError("unsupported marker syntax")
        if token[0] == "ident":
            return ("var", self.take()[1])
        if token[0] == "str":
            return ("str", self.take()[1])
        raise ValueError("unsupported marker syntax")


def _eval(node, env: dict) -> bool:
    kind = node[0]
    if kind == "or":
        return any(_eval(child, env) for child in node[1])
    if kind == "and":
        return all(_eval(child, env) for child in node[1])
    op, left, right = node[1], node[2], node[3]
    left_value, left_extra = _atom(left, env)
    right_value, right_extra = _atom(right, env)
    return _compare(left_value, op, right_value, left_extra=left_extra, right_extra=right_extra)


def _atom(node, env: dict) -> tuple[str, bool]:
    if node[0] == "str":
        return node[1], False
    name = node[1]
    if name not in _ENV_KEYS:
        raise ValueError(f"unknown marker variable: {name}")
    if name not in env:
        raise ValueError(f"missing marker variable: {name}")
    return str(env[name]), name == "extra"


def marker_applies(marker: str, env: dict | None = None) -> bool:
    """True when ``marker`` matches. ``env`` None uses this interpreter."""
    environment = marker_environment() if env is None else dict(env)
    environment.setdefault("extra", "")
    return _eval(_Parser(_tokenize(marker)).parse(), environment)


def _split_marker(requirement: str) -> str | None:
    if ";" not in requirement:
        return None
    return requirement.split(";", 1)[1].strip()


def runtime_requirements(info: dict, env: dict | None = None) -> list[str]:
    """Requirements that apply here. An inactive marker is not a runtime dependency."""
    environment = marker_environment(env)
    active = []
    for raw in info.get("requires_dist") or []:
        marker = _split_marker(raw)
        if marker is None:
            active.append(raw)
            continue
        try:
            applies = marker_applies(marker, environment)
        except ValueError:
            applies = True
        if applies:
            active.append(raw)
    return active


def resolve(package: str, version: str | None = None, *, allow_deps: bool = False, env: dict | None = None) -> dict:
    path = f"{package}/{version}/json" if version else f"{package}/json"
    meta = json.loads(_get(f"{INDEX}/{path}"))
    info = meta["info"]
    deps = runtime_requirements(info, env)
    if deps and not allow_deps:
        raise SystemExit(f"{package} {info['version']} has runtime dependencies (not supported): {deps}")
    wheels = [item for item in meta["urls"] if item["packagetype"] == "bdist_wheel" and PURE.search(item["filename"])]
    if not wheels:
        raise SystemExit(f"{package} {info['version']} has no pure-Python wheel (compiled wheels are not supported)")
    chosen = wheels[0]
    if Path(chosen["filename"]).name != chosen["filename"]:
        raise SystemExit(f"unsafe wheel filename: {chosen['filename']}")
    return {
        "package": package,
        "version": info["version"],
        "filename": chosen["filename"],
        "url": chosen["url"],
        "sha256": chosen["digests"]["sha256"],
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(spec: dict, cache: Path) -> Path:
    """Reuse a cached wheel when its sha256 matches; otherwise download and verify."""
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / spec["filename"]
    if dest.exists() and _sha256(dest) == spec["sha256"]:
        return dest
    data = _get(spec["url"])
    got = hashlib.sha256(data).hexdigest()
    if got != spec["sha256"]:
        raise SystemExit(f"sha256 mismatch: {spec['filename']} {got} != {spec['sha256']}")
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    return dest


def extract(wheel: Path, out: Path) -> Path:
    """Extract importable files, omitting ``*.dist-info`` and ``*.data``."""
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            top = name.split("/", 1)[0]
            if top.endswith((".dist-info", ".data")) or ".." in name.split("/"):
                continue
            archive.extract(name, out)
    return out


def ensure(package: str, cache: str | os.PathLike = "build/cdn-cache", version: str | None = None):
    """Put the fetched wheel at the front of ``sys.path`` and import ``package``."""
    import importlib

    wheel = fetch(resolve(package, version), Path(cache))
    sys.path.insert(0, str(wheel))
    return importlib.import_module(package)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["resolve", "fetch"])
    parser.add_argument("package")
    parser.add_argument("--version")
    parser.add_argument("--cache", default="build/cdn-cache")
    parser.add_argument("--extract", help="extract the wheel into this directory instead of printing its path")
    parser.add_argument("--github-output", action="store_true")
    args = parser.parse_args(argv)
    spec = resolve(args.package, args.version)
    if args.command == "resolve":
        if args.github_output:
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
                for key in ("version", "filename", "sha256"):
                    handle.write(f"{key}={spec[key]}\n")
        print(json.dumps(spec, indent=1))
        return 0
    wheel = fetch(spec, Path(args.cache))
    print(extract(wheel, Path(args.extract)) if args.extract else wheel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
