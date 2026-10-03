# Python failure evidence (#58)

The Python 3.12 non-heavy lane emits `junit-py3.12/pytest-3.12.xml`.
The existing unittest step remains before pytest. Pytest runs after a unittest
failure if compilation succeeded and the run was not cancelled; unittest failure
still makes the job fail. Neither suite uses `continue-on-error` or a shell success
fallback. Uploads and the dependent collector run with `always()`; a missing report
is an incomplete collection, not a successful empty result.

`tests/test_junit_failure_identity.py` runs real isolated child pytest twice,
with and without JUnit. Each child returns **1**: two parameterized assertion
failures, one setup error, one pass and one skip. The outer regression succeeds
only when return code, classifications and redaction match. The locked baseline
runs the same regression without producing an additional collected artifact.

In the normal lane, `junit-controlled-py3.12` holds `junit.xml`,
`child-exit.json` and locally checked `failures.jsonl`. Raw XML contains synthetic
message, setup, stdout/stderr and parameter sentinels. Compact identity retains
only test/class and failure/error; pass/skip and sentinels are absent.
The test and collector use xprobe commit
`7e7015b2df69ad446b968f6fa49711b5b1dbdd3f`, verified against blob
`dbc5b7d55005d6288c072a7612584d6170c216f4` before import. The checkout is
under ignored `build/shared`, a test-only dependency outside the vendor lock.

The canonical reusable collector is pinned to
`myon-bioinformatics/myon-bioinformatics/.github/workflows/reusable-junit-identity.yml@4dfda95d6573250477f991a0421fa6acb9bc0258`.
Its exact expected report list is the two paths above from the same run;
`failure-identity` contains its compact corpus and collection receipt.
`commit_sha` is null because canonical metadata is not connected.
Raw JUnit stays in Actions artifacts (14 days), never Pages or the shared corpus.
Collector success does not change a failed test job's conclusion.

## Local reproduction

Install `requirements-mcp.txt` and `tests/requirements.txt`, then from the checkout:

```sh
git clone https://github.com/myon-bioinformatics/xprobe.git build/xprobe-source
git -C build/xprobe-source show 7e7015b2df69ad446b968f6fa49711b5b1dbdd3f:xprobe.py > build/xprobe.py
mkdir -p build/shared
cp build/xprobe.py build/shared/xprobe.py
python -m pytest -q tests/test_junit_failure_identity.py
```

For artifact reproduction set `IRONMATE_FAILURE_EVIDENCE=build/controlled-failure`
and run the normal pytest command from the workflow. The destination must not
already exist: prior evidence is rejected rather than mixed.

Completion requires same-head green CI, child exit receipt 1, and a complete
collector receipt with three compact child failure/error cases and no sentinels.
Measured run/head evidence is recorded in the PR. This covers JUnit integration;
automated learning, replay and source-chat linkage remain outside this change.
Provider APIs, screenshot, Pages and runtime requirements are unchanged;
#57 remains a separate identity migration.
