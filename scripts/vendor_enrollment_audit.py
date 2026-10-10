"""Audit every parent catalog recommendation using the canonical vendor verifier.

Produces a proposed lock (never modifies vendor.lock.json) and an explicit
per-tool enrollment/skip/error report. Run in a disposable checkout with
the pinned parent vendor_sync.py on PYTHONPATH.
"""
import argparse
import json
from pathlib import Path

import vendor_sync


def audit(catalog_path, lock_path, output):
    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    locked = json.loads(Path(lock_path).read_text(encoding="utf-8"))
    if catalog.get("schema") != "vendor-catalog/1" or locked.get("schema") != "vendor-lock/1":
        raise ValueError("unexpected catalog or lock schema")
    existing = {(x["repository"], x["source"]) for x in locked["files"]}
    destinations = {x["destination"].casefold() for x in locked["files"]}
    proposed = list(locked["files"])
    rows = []
    for tool in catalog["tools"]:
        repository, commit = tool["repository"], tool["commit"]
        source = tool.get("source", repository.split("/")[1] + ".py")
        decision = tool.get("consumers", {}).get(
            "myon-bioinformatics/Ironmate",
            tool.get("default_enrollment", {"enrollment": "enrolled", "reason": "default_single_file_policy"}))
        row = {"repository": repository, "source": source, "recommended_commit": commit,
               "catalog_enrollment": decision["enrollment"], "reason": decision["reason"]}
        if (repository, source) in existing:
            row["status"] = "already_locked"
            rows.append(row)
            continue
        if repository == "myon-bioinformatics/Ironmate":
            row["status"] = "skipped_self_vendor"
            rows.append(row)
            continue
        # Even skipped recommendations are audited; their policy remains recorded.
        candidates = []
        try:
            for item in (source, "LICENSE"):
                if (repository, item) in existing:
                    continue
                verified = vendor_sync.inspect_source(repository, commit, item)
                destination = "vendor/" + (source.split("/")[-1] if item != "LICENSE"
                                          else repository.split("/")[-1] + "-LICENSE")
                if destination.casefold() in destinations:
                    raise ValueError("destination collision: " + destination)
                candidates.append({**verified, "ref": "refs/heads/main", "destination": destination})
            for item in candidates:
                destinations.add(item["destination"].casefold())
                proposed.append(item)
            row["status"] = "verified_candidate"
            row["files"] = [x["destination"] for x in candidates]
        except (OSError, ValueError, KeyError) as exc:
            row["status"] = "verification_failed"
            row["error"] = str(exc)
        rows.append(row)
    vendor_sync.validate({"schema": "vendor-lock/1", "files": proposed})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(json.dumps({"schema": "vendor-enrollment-audit/1",
        "tools": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "proposed-vendor.lock.json").write_text(json.dumps(
        {"schema": "vendor-lock/1", "files": proposed}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default="vendor-catalog.json")
    parser.add_argument("--lock", default="vendor.lock.json")
    parser.add_argument("--output", default="build/vendor-enrollment-audit")
    args = parser.parse_args(argv)
    rows = audit(args.catalog, args.lock, args.output)
    print(json.dumps({status: sum(r["status"] == status for r in rows)
                      for status in sorted({r["status"] for r in rows})}, sort_keys=True))


if __name__ == "__main__":
    main()
