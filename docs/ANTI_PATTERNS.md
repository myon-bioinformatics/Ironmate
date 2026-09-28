# Anti-patterns

This document records reusable failure modes observed during repository maintenance.
The goal is prevention, not a chronology of individual mistakes.

## Editing and verification

### Do not globally replace escaped newlines

**Observed:** a broad `split("\\\\n").join("\\n")`-style repair fixed literal separators between
source lines but also converted intentional `\\n`, `\\r`, and `\\t` inside Python string
literals. The test module then failed during collection with an unterminated string.

**Rule:** repair the smallest syntactic region possible. Treat source-code separators and data
inside string literals as different domains. Parse or compile the resulting source before push.

### A commit message is not evidence that a fix landed

**Observed:** several commits claimed to repair newline/YAML damage while the target blob was
unchanged or the intended bytes were still absent.

**Rule:** after every automated edit, re-fetch the exact branch/head and inspect the actual blob or
diff. For escape-sensitive changes, inspect the literal source representation, not only rendered
text. Empty commits or unchanged content must never be reported as a completed fix.

### Do not let a wrong implementation validate a wrong fixture

**Observed:** the workflow corruption detector accidentally required two backslashes before `n`.
Its regression fixture made the same escaping mistake, so the test was green while the real #42
one-backslash corruption was not detected.

**Rule:** derive regression fixtures from the original failure bytes independently of the
implementation. Include nearby negative controls when representation is ambiguous. For this case:
one backslash + `n` is the corruption; two backslashes + `n` is different data.

### Count escaping at the data boundary, not by visual intuition

**Observed:** JavaScript strings, Python source, raw regex strings, and YAML text each added a
different escaping layer. Reading `\\\\n` visually led to repeated off-by-one-backslash fixes.

**Rule:** state which layer is being represented (tool-call string, source text, regex, or runtime
data), then verify the resulting bytes/text at that boundary. Add positive and negative executable
examples.

## Test design

### A pytest test is not a pre-collection syntax guard

**Observed:** a repository-wide `py_compile` test was useful, but a syntax error in another
`test_*.py` can stop pytest collection before that test executes.

**Rule:** use compile smoke tests as repository hygiene, not as proof of pre-collection protection.
When CI needs a true preflight, run syntax compilation before pytest. Keep the hygiene test useful
for local and cross-repository reuse.

### Account for lazy short-circuiting in test doubles

**Observed:** a test expected a warning from a later PR review endpoint, but an earlier issue
comment already contained `from: bot`. `any(...)` short-circuited, so the later endpoint was
never called.

**Rule:** design each fake so execution must reach the behavior under test. Test independent
surfaces independently when short-circuiting is part of the implementation contract.

### Bound tests that exercise loop protection

**Observed:** pagination cycle detection is specifically intended to prevent infinite traversal.

**Rule:** the fake used to test a loop guard must have its own small call bound and fail if exceeded.
A regression in production cycle detection must turn into a fast test failure, not a hung test job.

## Hygiene guards

### Do not make a regression guard broader than the failure class

**Observed:** an initial workflow guard rejected every non-comment line containing literal `\\n`.
That would also reject legitimate shell/JSON data such as `printf 'a\\nb'`.

**Rule:** detect the structural corruption that actually occurred, and keep legitimate data as a
negative fixture. Prefer a narrow guard with an executable reproduction over a broad heuristic.

### Prefer tracked files, but define archive behavior

**Observed:** recursive `rglob("*.py")` can include untracked local/generated files; relying only on
`git ls-files` fails in source archives or environments without Git.

**Rule:** prefer `git ls-files '*.py'` in a checkout. Provide a documented, tested fallback for
source archives, with explicit exclusions for generated/cache directories.

## API diagnostics

### Do not infer review state from bot identity alone

**Observed:** an Action/error comment authored by a reviewer bot can exist even when no review was
completed.

**Rule:** review state requires the explicit standalone `from: <reviewer>` contract. Author/login
identity alone is not evidence of a completed review.

### Do not send credentials across an unverified redirect/origin

**Observed risk:** pagination links and redirects are remote input. Following arbitrary absolute
URLs while retaining Authorization can leak credentials.

**Rule:** validate same-origin links before authenticated requests and reject cross-origin
redirects. Test the rejection path directly.

---

Relevant implementation history: PRs #37–#44, especially the `unreviewed.py` and repository
hygiene work in #42–#44.
