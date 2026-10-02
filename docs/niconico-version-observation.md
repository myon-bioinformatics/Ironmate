# Snapshot version observations

Issue #39's residual automatic version acquisition is implemented by
`niconico_adapter.fetch_version()` and `paged_search()`.

## Specification check

On 2026-10-02 the [official guide](https://site.nicovideo.jp/search-api-docs/snapshot)
was fetched directly and checked before implementation. Its latest revision is
still 2026-04-15 (`contentType` addition). No changes to the version endpoint,
timestamp format, HTTP classification, or pacing contract were found.

`fetch_version()` uses the existing provider-specific GET transport and accepts
only a real calendar timestamp in the documented `YYYY-MM-DDTHH:mm:ss+09:00`
form. Failed observations retain transport status/timing but have no
`last_modified`; missing/invalid timestamps are `error` / `invalid_version`.

## Search/export entry point

```python
from niconico_adapter import paged_search

result = paged_search(
    q="synthetic query", targets="title", sort="-startTime",
    context="MySearchApp", user_agent="MySearchApp/1.0", limit=100,
)
if result["complete"]:
    records_to_export = result["records"]
```

The function observes version → requested pages → version, retains both
observations, and delegates completion to the existing `completion_state()`.
Each normalized record retains the exact page query as `source_url`. A snapshot
change, failed observation, malformed/stalled page, provider offset limit, or
optional `max_pages` cap prevents completion. Completeness starts at the
requested `offset` (default zero); a caller exporting the whole query uses zero.

An initial version failure aborts before searching (`page.status=not_started`,
empty final observation). Once searching starts, a final observation is made
even after page failure. There are no automatic retries. HTTP 400 remains
`invalid_request`, and 503 remains `maintenance`. Every subsequent request waits
at least the prior response's elapsed time, or 300 seconds after a 503. The
returned `retry_delay_seconds` tells the caller how long to wait before its next
request after this operation. `opener` and `sleeper` are injectable for offline
tests. These pacing guarantees apply to sequential calls; callers coordinating
concurrent operations must also coordinate their request schedule.

This does not publish to catalog/Pages, add live CI, or change shared provider
status vocabulary. Publication requires the separate terms/boundary review
already recorded in #39.
