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
| `HOST_FSTRING_FOREIGN_BRACES` | markdown #64, ascii_artist #5; aggregated in mcp-toolcall-lab | A Python f-string embeds brace-heavy JavaScript/CSS/JSON as if it were plain text, so foreign-language braces are parsed as host interpolation and CI can fail at import/collection time | Keep the embedded program in a plain literal/template, replace only explicit sentinels (for example `__REPO__` / `__BASE__`), and compile/import generator scripts in CI |

## Incident: repository-diagnostics horizontal rollout

During the first repository-diagnostics rollout from Ironmate/mcp-toolcall-lab
into `markdown` and `ascii_artist`, the builder used a Python triple-quoted
f-string containing a complete JavaScript block. The JavaScript function/object
braces were parsed by Python's f-string machinery, producing a `SyntaxError`
while tests were being collected. The page itself never had a chance to run.

The same implementation pattern failed in two repositories, which makes it a
cross-repository anti-pattern rather than a one-off CI typo.

The corrected pattern is deliberately simple:

```python
template = """<script>
(function () {
  const payload = {status: "ok"};
})();
</script>"""

html = template.replace("__REPO__", repository).replace("__BASE__", asset_base)
```

When only a few values need substitution, keep the host-language interpolation
surface narrow instead of turning the entire embedded language into an
interpolated string.

## Maintenance rule

When a failure repeats across repositories:

1. reuse the same stable ID where the failure class is genuinely the same;
2. add a regression/compile/import test in the affected repository when practical;
3. update the owning repository's catalog;
4. add or refresh the Ironmate index link/summary so the lesson is discoverable
   without knowing which repository first observed it.
