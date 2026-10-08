#!/usr/bin/env python3
"""Stage a vendor artifact from canonical evidence, without hand-maintained membership."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

LEGACY = (
    "vendor/ascii_artist.provenance.json",
    "vendor/git_inspector.provenance.json",
    "vendor/markdown.provenance.json",
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("candidate", "locked"), required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    tool = root / ".vendor-sync-tools/vendor_sync.py"
    cmd = [sys.executable, "-S", str(tool), "evidence", "--manifest", "vendor.lock.json"]
    if args.kind == "candidate":
        cmd += ["--runtime-evidence", "vendor-promotion.json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    evidence = json.loads(proc.stdout)
    if evidence.get("schema") != "vendor-evidence/1":
        raise ValueError("unsupported evidence schema")
    members = evidence[args.kind] + evidence["runtime"] + list(LEGACY)
    destination = (root / args.output).resolve()
    if not destination.is_relative_to(root) or destination == root:
        raise ValueError("output must be a subdirectory")
    if destination.exists():
        raise ValueError("artifact staging destination already exists")
    for member in members:
        path = Path(member)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("unsafe evidence member")
        source = (root / path).resolve()
        if not source.is_relative_to(root) or not source.is_file():
            raise ValueError("missing or unsafe evidence member: " + member)
    destination.mkdir(parents=True)
    for member in members:
        target = destination / member
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / member, target)
    (destination / "vendor-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
