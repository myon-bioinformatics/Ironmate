# README.md

# Ironmate

共有ツールとして独立させる前の、Pythonツールの試作・検証環境です。
単一ファイル・標準ライブラリ中心の小さな候補を検証し、需要と責務が
明確になったものだけを独立させます。ローカルLLMやGPUは必須ではありません。

## 第一段階の整理

旧キャラクター型アシスタント、モデルのロード・量子化・REPL、ローカル
キャラクター資産を整理しました。ASCII・Markdownのコアは独立済みの
[ascii_artist](https://github.com/myon-bioinformatics/ascii_artist) と
[markdown](https://github.com/myon-bioinformatics/markdown) が提供元です。
Gradio画面は [mcp-toolcall-lab](https://github.com/myon-bioinformatics/mcp-toolcall-lab)
の任意起動デモ `mcp_toolcall_lab.gradio_galleria` へ移管します。
[移管先PR #104](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/104) の取り込みを、この削除PRの前提とします。

削除・移管・維持の対象と理由は [整理記録](docs/cleanup-stage-one.md) に記載しています。
今回の範囲は既存構成の整理です。新しい候補配置や自動化の作り込みは別段階です。

## 残す検証経路

- `repository_metadata*.py` と `python_artifact_provenance.py`：既存consumerが使う共有契約。
- GitHub／ニコニコのadapter、catalog、MCP：既存の試作・統合検証。
- `vendor/`：提供元の固定版。共通処理は再実装しません。
- `tests/`、GitHub Actions、JUnit、親の共通証跡、Pages：継続利用する検証基盤。

```bash
python -m pip install -r tests/requirements.txt
# CIと同じ固定版のテスト用依存（初回のみ）
git clone https://github.com/myon-bioinformatics/xprobe.git build/shared
git -C build/shared checkout 7e7015b2df69ad446b968f6fa49711b5b1dbdd3f
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout 974da5eb9593df652b132e4b0f1a679f67422566
python -m pytest -q -m "not heavy" --junitxml=build/test-results/pytest-local.xml
python -S scripts/build_repository_diagnostics.py
```

メタデータMCPサーバーを起動する場合のみ、`requirements-mcp.txt` をインストールし
`python ironmate_mcp.py` を実行します。モデルのダウンロードはありません。

不具合は再現条件・実行したSHA・JUnit／証跡とともに提供元へ還元します。
問題のない候補はIronmateで保持でき、すべてを直ちに独立させる必要はありません。

## Vendored utilities

Ironmate keeps exact source snapshots under `vendor/` instead of treating these
helpers as runtime package dependencies. `vendor.lock.json` records the source
commit, Git blob and SHA-256 for each source and license, including markdown,
ascii_artist, NVD, git_inspector, gh_identity and parent-owned gh_ops.
The current checked-in NVD source is `a3d8f1835e4a82bc6e50682d6a79e22a851c4c91`
(blob `9daa3938dfa4226198e94273c18af5362c1ccb8b`); the previous README named a
different snapshot. The ASCII source header is now preserved verbatim and its
LICENSE is included, as described by the original provenance preparation.

Ordinary Python CI updates that allowlist once, validates every selected source
and available LICENSE, projects compatible provenance records, and tests the
same downloaded snapshot. Source headers describe their upstream artifact
baseline; they do not become the consumer HEAD or the downstream fetch commit.
See [vendor automation](docs/vendor-automation.md) for CI and ALM commands.
The existing NUL replacement and producer/consumer behavior remain covered by
regression tests.


---

## MCP Stub UI

The static MCP Stub Explorer at `docs/mcp-stub.html` consumes the shared
`myon-bioinformatics/web-ui` semantic contract and the Modern theme.

Presentation is supplied by pinned `web-ui` CSS at commit
`adb23d7ba6ea94672b76457573f6655a081ee054`. Ironmate continues to own
repository-search semantics, evidence export, history, and MCP-specific behavior.

This migration is presentation-only: the existing MCP Stub search, history,
export, and repository-source behavior are intentionally unchanged.

The existing **Technology stack** summary is also preserved; it now lives inside
the primary `stub-result` pane alongside repository details rather than in a
separate top-level panel. Its `#stats` target and `renderStats()` behavior are unchanged.

CI captures deterministic Chromium screenshots for:

- desktop `1440x900`
- mobile `390x844`

The screenshots are uploaded as the `ironmate-mcp-stub-screenshots` artifact.
Open the relevant **Test MCP stub** Actions run and use its Artifacts section to
inspect the desktop/mobile evidence. Run artifacts are evidence for that commit;
they are not a permanent release asset.


---

## web-ui v1 consumer integration

Ironmate now exercises the frozen web-ui v1 contract through both vendored
sibling libraries rather than only through hand-written Stub markup.

`scripts/build_web_ui_consumer_examples.py` composes:

- `vendor/markdown.py::markdown_to_web_ui_v1()`
- `vendor/ascii_artist.py::to_web_ui_v1_html()`
- pinned web-ui CSS at `adb23d7b`

The libraries emit semantic HTML only. Ironmate remains responsible for loading
the pinned presentation assets, which keeps the upstream libraries stdlib-only
and dependency-free.

GitHub Pages generates these integration examples at deploy time:

- `/consumer-v1/index.html`
- `/consumer-v1/markdown.html`
- `/consumer-v1/ascii.html`

CI compiles the vendored modules and builder, validates the semantic classes and
text escaping, and captures deterministic Chromium evidence in the
`ironmate-web-ui-consumer-screenshots` artifact.

This also records the exact upstream revisions in generated HTML comments, so a
render can be traced back to the web-ui, markdown, and ascii_artist commits that
produced it.

When advancing the web-ui pin, update the MCP Stub stylesheet pin and the
consumer-example `WEB_UI_SHA` together in the same PR so both presentation
lanes remain on one contract revision.


---

## GitHub source adapter

`github_adapter.py` is Ironmate's reference read-only source adapter. It separates
**Parse → Build URL → Fetch → Normalize/inspect** so URL construction and fixture
tests remain useful even when a runner cannot reach GitHub.

Public resources can be inspected anonymously; a token passed by the caller is
optional rate-limit headroom rather than a requirement for URL construction.
Bearer credentials are attached only to HTTPS requests for `api.github.com`
and are stripped if a redirect leaves that host. Consumers
may also call `inspect_public(..., fetch=False)` to produce canonical GitHub
HTML and REST API URLs without any network request.

The adapter is intentionally small and stdlib-only. Future API/MCP adapters
should use this shape as a reference rather than copying GitHub-specific request
logic into each consumer. Live GitHub availability is not a normal CI
requirement.


### Catalog integration and Pages verification

`github_catalog.py` now reuses `github_adapter.fetch_json()` for GitHub
transport instead of maintaining a second request implementation. The catalog
keeps its existing output vocabulary (`detected`, `not_found`,
`fetch_failed`) at the consumer boundary; the adapter deliberately keeps the
smaller transport outcome plus raw HTTP/error evidence.

The GitHub Pages deploy remains the live integration lane. A deploy builds the
catalog through the shared adapter and publishes the generated files under
`docs/api/`. Normal adapter tests stay offline and deterministic; Pages is
where the public GitHub fetch path is exercised. After deployment, verify that
`api/catalog.min.json` is present and that repository metadata such as
`api/repos/Ironmate.json` is refreshed for the deployed revision.


### Live read-only example

Public resources can be inspected without a token when network access is intentionally requested:

```python
from github_adapter import inspect_public

result = inspect_public("openai/openai-python", fetch=True)
print(result["fetch"]["status"])
```

Normal CI remains fixture/offline-driven; this live form is for manual/browser validation. A token is optional rate-limit headroom, not a requirement for public resources.


## Live PR observation consumer

`github_pr.py` consumes the parent repository's canonical `gh_ops.py` for one-shot PR
observations, saved-snapshot diffs and explicitly requested PR comments. It runs
with `python -S` and uses `GITHUB_TOKEN` / `GH_TOKEN` when provided.

```bash
python -S github_pr.py observe OWNER/REPO 42 --min-checks 6 --snapshot pr-42.json
# Repeat to compare with the last successful observation and replace its snapshot.
python -S github_pr.py observe OWNER/REPO 42 --min-checks 6 --snapshot pr-42.json
python -S github_pr.py diff before.json after.json  # offline
python -S github_pr.py comment OWNER/REPO 42 --body-file note.md          # preview
python -S github_pr.py comment OWNER/REPO 42 --body-file note.md --write  # post once
```

Output is JSON. `observe` returns `observation`, `diff` and `snapshot_saved`;
the first observation has `diff: null`. `ok: true` means observation succeeded;
inspect `observation.checks.state` for CI status. Zero/fewer-than-minimum checks
are pending, never green. Choose the expected minimum for the target repository.
A head change during collection is rejected as stale. Failed/stale observations
preserve the previous snapshot, while a complete pending/failed CI observation
can replace it. The snapshot contains the producer's observation schema, so it
can also be read by upstream `pr-diff`. Invalid/wrong-PR saved snapshots fail
before HTTP. Create the parent directory first and serialize invocations sharing
one path; replacement is atomic, but this is not a concurrent state store.
Snapshots may contain private repository metadata; keep them in an appropriate
local location rather than a public Pages directory.

Comment results preserve `posted` / `verified` and the producer's uncertainty
message. Exit codes are 0 for a successful operation (including preview), 1 for
an unsuccessful result, and 2 for input/I/O/transport errors. Posting is never
automatically retried; after an uncertain write, inspect GitHub before deciding
to retry. The API returns the producer comment result unchanged and the CLI
preserves the UTF-8 body including its trailing newline.

This consumer performs no scheduling, notifications, semantic Blocking/Should
classification or automatic comment/merge action. The static metadata MCP
remains a separate interface. Source/LICENSE bytes are recorded in
`vendor.lock.json` and participate in the existing locked/update CI lanes;
GitHub REST collection and diff logic stay in the upstream producer.

## GitHub comment one-liner

`github_comment.py` posts a comment to an issue or pull request and prints the
comment URL, in one command. It writes through the GitHub CLI (`gh api`), so
authentication stays with `gh`; the module never reads a token. The body goes to
GitHub as JSON on stdin, so newlines, quotes and Markdown arrive unchanged.
Unlike `github_adapter.py` (read-only), this module writes, so it is kept separate.

```bash
python github_comment.py OWNER/REPO 1 --body-file reply.md          # prints the comment URL
cat reply.md | python github_comment.py OWNER/REPO 1 --body-file -  # from stdin
python github_comment.py OWNER/REPO 1 --body "text" --json          # {"id": ..., "url": ...}
python github_comment.py OWNER/REPO 1 --body-file reply.md --dry-run  # show, do not post
```

Exit codes: 0 posted (or shown), 1 `gh` failed (its message on stderr), 2 bad arguments.

## Python artifact provenance contract

`python_artifact_provenance.py` is a stdlib-only static contract for standalone or vendored
single-file Python artifacts. It is intentionally separate from repository metadata JSON/JSONL.

The canonical `__all__` declaration must be one literal top-level list or tuple of strings.
Top-level functions, classes, and assigned constants count as artifact implementations.
Imported names and names defined only inside control-flow blocks such as `if` or `try` do
not count as implementations for this static check, so re-exporting them is rejected.
Public top-level functions/classes must be exported, while underscore-prefixed helpers must
remain internal.

Dynamic or nested mutation is outside the contract. In particular, slice assignment such as
`__all__[:] = [...]` and mutations hidden inside control flow are not interpreted as a
canonical declaration. Top-level `+=`, `.extend(...)`, and `.append(...)` are rejected
rather than guessed.


## Cross-repository anti-patterns

Ironmate also keeps a discovery index for recurring CI/design failures across
the sibling repositories:

- [docs/antipatterns.md](docs/antipatterns.md)

The owning repositories remain the source of truth for their detailed catalogs;
Ironmate links and summarizes shared IDs so the same failure class is searchable
across repository boundaries.


---

## NVD security metadata adapter

`vendor/nvd_nist_known_vulns.py` is an unchanged snapshot of upstream
`myon-bioinformatics/nvd_nist_known_vulns` merge `a3d8f18`. Upstream now owns
both production and generic `nvd-cve-summary/1` JSONL consumption
(`parse_jsonl`, `read_jsonl`, and `select_cpe_records`), so Ironmate no
longer maintains a parallel `security_nvd.py` implementation.

Ironmate keeps only its repository-specific boundary in `repository_metadata.py`:
the explicit `ironmate-security-cpe/1` repository-to-CPE mapping and conversion
of upstream selection results into repository metadata. It does **not** infer a
CPE from a Python package or repository name. Missing mapping or incomplete query
completion remains `not_measured`, while a completed zero-CVE query is
`measured` with count zero. Normal tests are offline and pin the vendored Git
blob, so CI does not call NVD. NVD evidence remains complementary to package-native
advisory sources such as Dependabot.

### Unreviewed diagnostics

`scripts/unreviewed.py` treats an item as reviewed only when a comment or review body contains a standalone `from: <reviewer>` line. Author identity alone is intentionally insufficient: bot-authored Action/error responses such as `claude[bot]` failures do not count as reviews unless that tag line is present.


### Repository metadata portability

Repository metadata uses the stdlib-only Python producer and canonical JSON/JSONL contract documented in [docs/repository-metadata-portability.md](docs/repository-metadata-portability.md). UI/runtime consumers read generated records rather than reimplementing GitHub metadata collection.

## Shared screenshot checks

The screenshot job checks all six named PNGs with browser-test-kit at
`6a2e32a4bbe49be5268e6b30040d665a89eecf66`, checked out separately in CI.
See the [shared screenshot guide](https://github.com/myon-bioinformatics/browser-test-kit/blob/6a2e32a4bbe49be5268e6b30040d665a89eecf66/docs/screenshot-evidence.md).
Missing/invalid PNGs fail the lane. Existing Stub and consumer artifacts, plus
`ironmate-repository-diagnostics-screenshots`, preserve available captures even
after failure, with 14-day retention. This lane measures Chromium desktop/mobile
viewports; Firefox/WebKit remain unmeasured.

The screenshot lane now seals a current-run multi-image receipt via pinned
browser-test-kit, requires all six PNGs and their recorded SHA-256/size, and
checks the explicit tested head SHA plus run ID/attempt. Output is cleared before
capture. Failed receipts are preserved but cannot cover required success. CI also
mutates isolated copies of the real bundle to prove rejection of missing images,
wrong hashes, stale run IDs and failed receipts. These are integrity/run checks;
they add no screen-content or pixel-regression assertions.

Public source placement and automatic Python CI updates: [vendor automation](docs/vendor-automation.md).

Consumer Pages attribution displays the acquisition commit recorded in vendor
provenance (ASCII: `50585862`), rather than the artifact header base SHA
(`7c21bacf`). The deployment rebuilds these labels from checked-in baseline files.
