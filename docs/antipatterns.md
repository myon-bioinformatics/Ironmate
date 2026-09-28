# Cross-repository anti-pattern index

Ironmate acts as a discovery/catalog hub for sibling repositories. This page links
their anti-pattern catalogs and records failure classes that matter across more
than one repository.

The source catalogs remain owned by each project; this page is an index, not a
replacement for them.

## Catalog links

- [markdown anti-pattern catalog](https://github.com/myon-bioinformatics/markdown/blob/main/docs/antipatterns.md)
- [ascii_artist anti-pattern catalog](https://github.com/myon-bioinformatics/ascii_artist/blob/main/docs/antipatterns.md)
- [mcp-toolcall-lab anti-pattern catalog](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/main/docs/antipatterns.md)

## Cross-repository stable IDs

| ID | Observed in | Failure class | Preferred contract |
| --- | --- | --- | --- |
| `HOST_FSTRING_FOREIGN_BRACES` | [markdown #64](https://github.com/myon-bioinformatics/markdown/pull/64), [ascii_artist #5](https://github.com/myon-bioinformatics/ascii_artist/pull/5); aggregated in mcp-toolcall-lab | A Python f-string embeds brace-heavy JavaScript/CSS/JSON as if it were plain text, so foreign-language braces are parsed as host interpolation and CI can fail at import/collection time | Keep the embedded program in a plain literal/template, replace only explicit sentinels (for example `__REPO__` / `__BASE__`), and compile/import generator scripts in CI |

## Incident: repository-diagnostics horizontal rollout

The shared `HOST_FSTRING_FOREIGN_BRACES` failure was observed in the
repository-diagnostics rollout to `markdown` and `ascii_artist`: embedded
JavaScript braces inside a Python f-string caused import/collection-time
`SyntaxError` failures before page tests could run.

See the owning catalogs for the detailed incident and regression guidance:
[markdown](https://github.com/myon-bioinformatics/markdown/blob/main/docs/antipatterns.md),
[ascii_artist](https://github.com/myon-bioinformatics/ascii_artist/blob/main/docs/antipatterns.md),
and [mcp-toolcall-lab](https://github.com/myon-bioinformatics/mcp-toolcall-lab/blob/main/docs/antipatterns.md).

## PR #37–#44 verification and hygiene lessons

The adapter/diagnostics work exposed a cluster of related maintenance failures. Keep these as
one incident family rather than creating a second anti-pattern catalog.

| Boundary | Example | Rule |
| --- | --- | --- |
| Tool-call string → source text | a replacement intended for literal `\\n` also changed `\\n` / `\\r` / `\\t` inside Python strings | Edit the smallest syntactic region; compile/parse before push |
| Source text → regex | the detector accidentally required two backslashes while the #42 corruption had one | State the representation layer and test the original failure bytes |
| Fixture → implementation | the fixture repeated the same escaping error as the detector, producing a false green | Derive regression fixtures independently; include adjacent negative controls |
| Commit → repository tree | commits/messages claimed fixes that did not change the intended blob | Re-fetch the exact head and inspect the actual diff/blob after every automated edit |
| Lazy iterator → endpoint fake | `any(...)` found an early reviewer tag, so a later expected 404/warning was never reached | Make the fake force the behavior under test; separate independent surfaces |
| pytest collection → compile hygiene | a pytest compile test cannot protect against syntax errors that stop collection first | Run syntax compilation before pytest; retain repository hygiene tests as a second line |
| Loop guard → regression test | removing pagination-cycle protection could otherwise hang CI | Give the fake its own small call bound so regressions fail quickly |
| Narrow incident → broad guard | rejecting every literal `\\n` would reject legitimate shell/JSON data | Guard the structural failure class and retain legitimate negative fixtures |
| Checkout → source archive | `git ls-files` is precise but Git may be absent; `rglob` can include generated files | Prefer tracked files and use a tested fallback with explicit exclusions |
| Bot identity → review state | an Action/error comment can be bot-authored without a completed review | Require the standalone `from: <reviewer>` contract; author identity alone is insufficient |
| Authenticated URL → redirect | remote pagination/redirect URLs can cross origins | Validate same-origin URLs before sending credentials and test rejection directly |

For escape-sensitive changes, do not rely on how a string looks in one rendered layer. The positive
fixture for #42 is **one backslash + `n`** between YAML list entries; **two backslashes + `n`**
and legitimate data such as `printf 'a\\nb'` are negative fixtures.

Relevant history: PRs #37–#44, especially #42–#44.

## Maintenance rule

When a failure repeats across repositories:

1. reuse the same stable ID where the failure class is genuinely the same;
2. add a regression/compile/import test in the affected repository when practical;
3. update the owning repository's catalog;
4. add or refresh the Ironmate index link/summary so the lesson is discoverable
   without knowing which repository first observed it.
