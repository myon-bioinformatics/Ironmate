# Public vendor placement in CI

Push and PR CI verifies the checked-in `vendor.lock.json` against on-disk bytes,
recreates every locked file from its pinned upstream commit, verifies again, and
runs the Python test suite. No workflow promotes or updates lock entries in CI;
the lock is the sole provenance record for vendored sources and LICENSE files.

`vendor.lock.json` is the acquisition contract: exact commit, Git blob and SHA-256
for every enrolled source and LICENSE. Each entry's `ref` is the same 40-hex
commit SHA as `commit`. Tests assert schema, hashes, and ref/commit alignment for
every file.

The pinned parent `vendor_sync.py` is checked out only in CI (not vendored in
this repository). Checkout credentials are not persisted.

ALM agents can use the same mechanism in a disposable checkout:

```bash
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout --detach a9df23dec720f125772a24b77b413552d60060ba
python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json
python -S .vendor-sync-tools/vendor_sync.py materialize --manifest vendor.lock.json
python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json
```

Run the existing Python suite with its test-only dependencies after verification.
The shared tool rejects edited baseline copies before contacting upstream.

Cross-repository rollout: myon-bioinformatics/myon-bioinformatics#35. JUnit
failure identity remains tracked separately in myon-bioinformatics/myon-bioinformatics#22.

## What a green run covers

The primary Python job checks and materializes the lock, then runs unit tests and
default pytest. A separate Marp integration job exercises real PPTX conversion.
`failure-identity` correlates JUnit artifacts across jobs.

Vendor evidence is staged with the pinned parent `vendor_stage.py` (`locked` kind).
Membership comes from the lock only; legacy per-file provenance JSON sidecars are
retired. `vendor-evidence.json` records member SHA-256 values. Staging runs on
failure as well.

Pages/Docker continue shipping checked-in bytes; CI does not write back to main.
The existing `paths` trigger means upstream-only changes wait for a matching
consumer change.

The shared profile MIT LICENSE is locked at `443b8a94bbc6801332e0abd9f2e56da68173b38d`
and included in staged evidence.

The PR observation consumer enrolls the parent's canonical `gh_ops.py` with
adjacent GHI. Its baseline is recorded in `vendor.lock.json`.

The catalog audit compares the checked-in lock before candidate enrollment.
Candidates are checked in a separate disposable root and never replace the
adopted lock or vendor bytes. Explicit catalog skips are not enrollment targets.
The pinned parent registry still contains retired git_inspector/vendor_sync
entries; the existing CI projection removes only those two entries until the
parent registry correction is adopted. This does not certify parent-main parity.
