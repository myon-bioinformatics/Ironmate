"""Explicit legacy-provenance projection from the verified shared vendor lock.

No source acquisition, importing candidate modules, tokens or repository writes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BINDINGS = [['vendor/ascii_artist.provenance.json',
  'vendor/ascii_artist.py',
  {'blob_sha': 'blob_sha',
   'sha256': 'sha256',
   'source_commit': 'commit',
   'source_path': 'source',
   'source_repository': 'repository'}],
 ['vendor/git_inspector.provenance.json',
  'vendor/git_inspector.py',
  {'blob_sha': 'blob_sha',
   'sha256': 'sha256',
   'source_commit': 'commit',
   'source_path': 'source',
   'source_repository': 'repository'}],
 ['vendor/markdown.provenance.json',
  'vendor/markdown.py',
  {'blob_sha': 'blob_sha',
   'commit': 'commit',
   'path': 'source',
   'repository': 'repository_url',
   'sha256': 'sha256'}]]
EXPECTED = {('myon-bioinformatics/myon-bioinformatics', 'LICENSE', 'vendor/myon-bioinformatics-LICENSE'),
 ('myon-bioinformatics/ascii_artist', 'LICENSE', 'vendor/ascii_artist-LICENSE'),
 ('myon-bioinformatics/ascii_artist', 'ascii_artist.py', 'vendor/ascii_artist.py'),
 ('myon-bioinformatics/markdown', 'LICENSE', 'vendor/markdown-LICENSE'),
 ('myon-bioinformatics/markdown', 'markdown.py', 'vendor/markdown.py'),
 ('myon-bioinformatics/myon-bioinformatics', 'git_inspector.py', 'vendor/git_inspector.py'),
 ('myon-bioinformatics/nvd_nist_known_vulns',
  'LICENSE',
  'vendor/nvd_nist_known_vulns-LICENSE'),
 ('myon-bioinformatics/nvd_nist_known_vulns',
  'nvd_nist_known_vulns.py',
  'vendor/nvd_nist_known_vulns.py')}


def records(root):
    lock = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))
    if lock["schema"] != "vendor-lock/1":
        raise ValueError("unsupported vendor lock")
    files = lock["files"]
    if len(files) != len(EXPECTED) or {(e["repository"], e["source"], e["destination"]) for e in files} != EXPECTED:
        raise ValueError("unexpected source or destination")
    by_destination = {e["destination"]: e for e in files}
    for e in files:
        if e["ref"] != "refs/heads/main" or not re.fullmatch(r"[0-9a-f]{40}", e["commit"]):
            raise ValueError("invalid source identity")
        data = (root / e["destination"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != e["blob_sha"] or hashlib.sha256(data).hexdigest() != e["sha256"]:
            raise ValueError("locked bytes mismatch: " + e["destination"])
    return by_destination


def project(root):
    entries = records(root)  # Verify every source/LICENSE before writing any metadata.
    pending = {}
    for path, destination, fields in BINDINGS:
        record = json.loads((root / path).read_text(encoding="utf-8"))
        entry = entries[destination]
        old_commit = record.get("commit")
        for target, source in fields.items():
            record[target] = "https://github.com/" + entry["repository"] if source == "repository_url" else entry[source]
        if "date" in record and old_commit != record["commit"]:
            record["date"] = datetime.now(timezone.utc).date().isoformat()
        if "license" in record:
            license_entry = next((e for e in entries.values() if e["repository"] == entry["repository"] and e["source"] == "LICENSE"), None)
            if license_entry is None:
                raise ValueError("missing LICENSE entry for " + entry["repository"])
            record["license"] = {"source_path": "LICENSE", "vendored_path": license_entry["destination"],
                                 "blob_sha": license_entry["blob_sha"], "sha256": license_entry["sha256"]}
        pending[path] = record
    # All per-file formats are mapped above.
    for path, record in pending.items():
        (root / path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")



def summarize(root, baseline, output, outcome):
    """Describe recorded lock drift; this report never certifies a failed update."""
    old = json.loads(baseline.read_text(encoding="utf-8"))["files"]
    new = json.loads((root / "vendor.lock.json").read_text(encoding="utf-8"))["files"]
    previous = {entry["destination"]: entry for entry in old}
    changed = [entry["destination"] for entry in new
               if any(entry[key] != previous[entry["destination"]][key]
                      for key in ("blob_sha", "sha256"))]
    lines = ["## Public vendor snapshot", "", "Update outcome: **" + outcome + "**.",
             "A failed update remains a failed job; recorded bytes are not a successful candidate.",
             "Primary Python tests use this run's snapshot. Pages/Docker ship the checked-in baseline.",
             "This summary is not a baseline test result.", "",
             "Changed source/LICENSE paths: `" + json.dumps(changed) + "`", "",
             "| Destination | Checked-in commit | Recorded snapshot commit | Bytes changed |",
             "| --- | --- | --- | --- |"]
    for entry in new:
        path = entry["destination"]
        lines.append("| `" + path + "` | `" + previous[path]["commit"] + "` | `" +
                     entry["commit"] + "` | " + ("yes" if path in changed else "no") + " |")
    with output.open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary-baseline", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--update-outcome", choices=("success", "failure", "skipped", "cancelled", ""), default="")
    args = parser.parse_args()
    if bool(args.summary_baseline) != bool(args.summary_output):
        parser.error("--summary-baseline and --summary-output must be used together")
    try:
        if args.summary_baseline:
            summarize(ROOT, args.summary_baseline, args.summary_output, args.update_outcome)
        else:
            project(ROOT)
    except (ValueError, KeyError, OSError) as error:
        print("vendor-provenance: " + str(error), file=sys.stderr)
        raise SystemExit(2)
