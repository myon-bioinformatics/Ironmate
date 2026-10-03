# Public vendor placement in CI

Ordinary push/PR CI restores locked files and updates the explicit public source
allowlist once in `resolve-vendor`. Each Python test job downloads the same
verified snapshot. Existing documentation-only change detection is retained.
Dispatch defaults to `update`; `vendor-mode: locked` reproduces the baseline.
No dedicated token, enable variable, scheduled update PR or main writeback is
required. Source acquisition uses anonymous HTTP/public Git in the pinned shared
stdlib tool. Checkout credentials are not persisted.

`vendor.lock.json` is the acquisition contract: exact commit, Git blob and SHA-256
for every source and available upstream LICENSE. Existing provenance JSON field
names stay compatible with current readers. The consumer's explicit stdlib
projection script verifies all source/license bytes before rewriting those
records from the lock; it does not infer aliases or import candidates. Tests
cross-check identity and hashes against the lock rather than a second static pin.
The projection is idempotent and rejected source/license bytes leave metadata
untouched. Upstream embedded artifact headers are preserved verbatim.

Source repositories that have LICENSE files carry their exact LICENSE bytes.
The shared profile repository currently has no LICENSE file at either the pinned
source revisions or shared tool pin; no sibling license is falsely attributed to
it. Its existing inspector copy remains an explicit source entry. License policy
for that source is a separate upstream decision.

The source/license/lock and compatibility records are retained in Actions both
before and after testing with `if: always()` and missing-file errors. Failures
remain nonzero. Public Actions artifacts can be downloaded by signed-in users;
raw reports are not added to Pages. Existing runtime dependencies, unrelated
browser/Docker workflows and deployment settings are preserved.

ALM agents can use the same mechanism in a disposable checkout:

```bash
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout --detach 90bc069c33901bd4b5373eb02311026e0acf2e2e
python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json
python -S .vendor-sync-tools/vendor_sync.py materialize --manifest vendor.lock.json
python -S .vendor-sync-tools/vendor_sync.py update --manifest vendor.lock.json
python -S .vendor-sync-tools/vendor_sync.py check --manifest vendor.lock.json
python -S scripts/sync_vendor_provenance.py
```

Run the existing Python suite with its test-only dependencies after projection.
The shared tool rejects edited baseline copies before contacting upstream.
Cross-repository rollout: myon-bioinformatics/myon-bioinformatics#35. Existing
JUnit work remains tracked separately in #22.
