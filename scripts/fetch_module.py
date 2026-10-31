#!/usr/bin/env python3
"""Compatibility entrypoint for the pinned Aoi fetch_module implementation.

Canonical bytes/LICENSE are recorded in vendor.lock.json. Ironmate retains its
build/cdn-cache default; Aoi's direct vendor entrypoint keeps its own default.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vendor import fetch_module as _implementation


def __getattr__(name):
    return getattr(_implementation, name)


def ensure(package, cache="build/cdn-cache", version=None):
    return _implementation.ensure(package, cache, version)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # The caller's later --cache (including argparse abbreviations) wins.
    return _implementation.main(["--cache", "build/cdn-cache", *args])


if __name__ == "__main__":
    raise SystemExit(main())
