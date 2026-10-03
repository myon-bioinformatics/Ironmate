# Public vendor placement in CI

Ordinary push/PR CI restores locked files and updates the explicit public source
allowlist once in `resolve-vendor`. The primary Python test job, including its
matrix variants, downloads the same verified snapshot. Existing documentation-only change detection is retained.
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
it. Its existing inspector copy remains an explicit source entry. The owner has authorized MIT licensing in shared PR #39
(https://github.com/myon-bioinformatics/myon-bioinformatics/pull/39). After it is
merged, add that exact upstream LICENSE to this lock and artifact allowlist.

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
JUnit work remains tracked separately in myon-bioinformatics/myon-bioinformatics#22.

## What a green run covers

The primary Python job tests the updated snapshot. A separate `test-locked` job
now tests the checked-in baseline on one representative Python version on every
selected push/PR run. It verifies local bytes, removes the allowlisted files,
materializes their exact upstream commits, verifies again and projects provenance
before running the existing Python suite. It never downloads the candidate
snapshot or runs update. Locked evidence uses a `locked-` artifact prefix and is
retained on failure; it is separate from candidate JUnit collection.

Pages/Docker continue shipping checked-in bytes; no source is written back to
main. Green `test-locked` covers that baseline on its one Python version, not the
whole candidate matrix. `vendor-mode: locked` remains available for a full primary
matrix baseline run, but no dispatch is required for routine baseline coverage.

The resolve job's summary lists changed source/LICENSE paths and old/new commits.
It describes the candidate only; baseline test results belong to `test-locked`.
A failed update remains red even if the independent baseline job succeeds.

Updates happen only when the existing workflow/change filters select the run.
There is no upstream-only scheduler. Separate push and pull-request events are
separate runs and can each resolve upstream once.

The pinned shared tool's public-Git rate-limit fallback applies to `update`.
Locked `materialize` currently fails nonzero on raw HTTP 403/429; it does not
silently accept the baseline or bypass digest verification.

The small projection adapter is consumer-owned because existing provenance
schemas differ. Acquisition and verification stay in the shared pinned tool;
unifying projection needs an explicit schema contract rather than guessed aliases.

The `screenshot` job deliberately builds and captures the checked-in baseline,
matching Pages deployment inputs. It does not validate the updated pytest snapshot.
The existing `paths` trigger means upstream-only changes wait for a matching
consumer change (or dispatch).

Pages attribution now displays the upstream **acquisition commit** from provenance,
not the artifact header’s `base_sha`. For ASCII this changes `7c21bacf` to
`50585862` on the baseline. The Pages workflow is unchanged, but merging this PR
rebuilds that attribution in the public consumer examples.

A legacy provenance `date` becomes the UTC resolution date when its source commit
changes during CI. It is retained when the commit is unchanged; it is not the
upstream commit timestamp or a claim that the checkout was committed that day.
