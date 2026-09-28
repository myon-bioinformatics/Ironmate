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

## Maintenance rule

When a failure repeats across repositories:

1. reuse the same stable ID where the failure class is genuinely the same;
2. add a regression/compile/import test in the affected repository when practical;
3. update the owning repository's catalog;
4. add or refresh the Ironmate index link/summary so the lesson is discoverable
   without knowing which repository first observed it.
