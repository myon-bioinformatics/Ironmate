<!-- image-digest.md -->
# 画像の要約ページ（image_digest）

多数の画像と、それぞれの合否（status）から、軽い 1 枚の HTML とレビュー用の Markdown 要約を作る。
行と列は何でもよい（ページ × 環境、ケース × 端末、スライド × テーマなど）。browser-test-kit の
published-app の実行のように、全体の成果物が大きくてダウンロードしにくいときに、全体を 1 ページで見渡すためのもの。

```sh
python -S image_digest.py input.json --out digest/            # 画像パスは input.json からの相対パス
python -S image_digest.py input.json -o digest/               # -o と --output は --out と同じ
node image_digest.cjs input.json digest/                       # Node から（処理は Python が持つ）
node image_digest.cjs input.json --out digest/ --tile 64x128   # Python と同じフラグ
node image_digest.cjs --help
```

直せない入力は終了コード 2 です。`--json` を付けると、その失敗は stderr の JSON 1 個になり、成功時の stdout は変わりません。引数が足りないときは待たずに使い方を出します。

Node の API（`buildDigest`）の型は `image_digest.d.cts` にある。ほかの Node API（`flow_export.cjs`、
`flow_workspace.cjs`、`studio/ingress.cjs`）も同じ名前の `.d.cts` を持ち、本体は JavaScript のまま。

Node ラッパーは親由来の `vendor/py_launch.cjs` で Python を起動する。API の `python` を省略したときは
各呼び出しで 3.9 以上の短いバージョン確認のあと、順に `IRONMATE_PYTHON` → `PYTHON` → `python3` →
`python`（Windows では `py -3`）を試す。API の `python` または設定済み `IRONMATE_PYTHON` はフォールバックしない。
起動失敗は `image digest Python process failed: …`（ライブラリ）または CLI 終了コード `2`。
詳細は [flow export の Node 起動](flow-export.md) と同じ。

入力は `ironmate-image-digest-input/1`:

```json
{"schema": "ironmate-image-digest-input/1", "title": "Published app run",
 "rows": ["home", "hub"], "cols": ["Linux-chromium-desktop", "macOS-webkit-iphone"],
 "meta": {"build": "d161b0cd4967", "link": "https://github.com/.../actions/runs/1"},
 "cells": [{"row": "home", "col": "Linux-chromium-desktop", "image": "shots/home.png", "status": "pass"},
           {"row": "home", "col": "macOS-webkit-iphone", "image": "shots/home-i.png", "status": "fail",
            "notes": ["320px:overlap"]}]}
```

出力:

- `digest.html`: サムネイルを data URI で埋め込んだ 1 ファイル。JavaScript なしで、どこでも開ける。
- `summary.md`: 行ごとの合格数と「見るべきところ」の表。PR コメントやジョブの要約にそのまま貼れる。
- `digest.json`（`ironmate-image-digest/1`）: 使ったサムネイル寸法、バイト数、status ごとの件数。

サムネイルは 64x128 px（`--tile` で変更可）から始め、`--max-bytes`（既定 1MB）に収まるまで
縦横を半分（画素数 1/4）にする。下限は 16x32。status は色分けと件数にだけ使い、画素から合否を推測しない。
セルのない組み合わせは「not run」と明示する。画像パスは入力ディレクトリ内の相対パスに限る。

## 入力・出力契約

- `base` は存在する入力ディレクトリ。CLI は入力 JSON の親ディレクトリ（`--base` で変更可）、
  stdin と Node API は明示指定する。画像の実体パスを解決し、ファイル自身・親ディレクトリの
  symlink を経由して入力ディレクトリ外へ出る参照は拒否する。入力内を指す symlink は許可する。
- 画像は通常ファイルの PNG（8-bit gray / gray+alpha / RGB / RGBA、非インターレース）。
  1 ファイル 32MiB **以下**、総画素数 16,777,216（4096×4096）以下。サイズを読み込み前に確認し、
  読み込み自体も 32MiB+1 byte に制限する。画像が無いセルは `image` を省略または `null` にできる。
- 行・列は重複しない 1〜120 文字のラベル（制御文字不可）。セルは最大 2000 件、同じ行・列の重複不可。
  `status` は `[a-z][a-z0-9_-]{0,23}`（省略時 `unknown`）。`pass` だけを合格数へ加算する。
  `notes` は各 200 文字以下で先頭 6 件を HTML、先頭 2 件を Markdown の不合格理由に表示する。
  Markdown 表の改行は空白へまとめ、区切り・HTML・装飾用文字をエスケープする。
- 各画像の実体は 1 回だけ読み込み・デコードする。元画像から各候補寸法の PNG を作り、
  縮小の反復で再利用する。候補は縦横半減、下限 16×32。全画像のフル解像度画素を保持しない。
- 出力先は新規または空のディレクトリ。通常ファイル、空でないディレクトリ、symlink
  （リンク切れを含む）は `write()` が `ValueError` で拒否する。CLI はエラー時に終了コード 2、
  Node API は例外となる。入力は実行中に変更しないスナップショットを使う。
- `build(spec, base, max_bytes=..., tile=(64, 128))` は `(HTML, Markdown, info)` を返す。
  `write(out, *build(...))` は 3 ファイルを保存する。Node は
  `buildDigest(spec, {base, out, maxBytes, tile: "64x128"})` で保存し、同じ `info` を返す。
- `info` は `schema`, `tile: [width,height]`, `bytes`（HTML の UTF-8 byte 数）、`fits`,
  `rows`, `cols`（行・列数）、`passed`, `statuses`（明示セルの status ごとの件数）。
  省略セルは `statuses` に含めない。最小寸法でも収まらなければ出力は生成し `fits: false` とする。
  上限は保証されないので、アップロード前に呼出側で `fits` を確認する。

## browser-test-kit からの接続

`scripts/app_digest.py` の観測・合否判定は browser-test-kit 側に残し、描画入力だけを次のように変換できる。

| browser-test-kit | image_digest 入力 |
| --- | --- |
| 予定ページ一覧 | `rows`（未実行ページも残す） |
| `planned_envs(runners)` | `cols`（未実行環境も残す） |
| `(adapter, OS-channel/browser-profile)` | `cell.row`, `cell.col` |
| `find_shots(root, shot)` の PNG | `cell.image`（入力 root からの相対パス） |
| 観測の `verdict` | `cell.status`（画素から推測しない） |
| レイアウト・クリックの失敗理由 | `cell.notes` |
| ビルド SHA、run URL | `meta.build`, `meta.link`（https のみ） |

画像だけがある場合は `status: "unknown"` と `notes: ["no record"]`、観測だけがある場合は
画像無しのセルにする。画像も観測も無い組合せはセルを省略し「not run」にする。
セルごとにビルドが異なる場合は各セルの notes に短い build 表示を加え、全体の build と区別する。

現行 btk は `btk-app-digest/1` の `pages` / `envs` を使うため、そのままの JSON 置換ではない。
移行アダプターで `rows` / `cols` から名前を変換するか、呼出側を新 schema に対応させる。
また `app_digest_comment.py` は `<!-- platform-apps-digest -->` と Markdown 60,000 bytes 以下を要求する。
Python では `summary_markdown(validate(spec), marker='<!-- platform-apps-digest -->')` で既存 marker を維持できる。
Node の既定 marker は `<!-- ironmate-image-digest -->` なので、投稿前にアダプターで調整する。
`max_bytes` は HTML の上限であり、Markdown の投稿上限とは別に検査する。

呼出例（btk 側で作った上記 schema の `spec` を渡す）:

```python
from image_digest import build, summary_markdown, validate, write

page, _, info = build(spec, results_root)
summary = summary_markdown(validate(spec), marker='<!-- platform-apps-digest -->')
write(out, page, summary, info)
# info['fits'] と len(summary.encode('utf-8')) <= 60_000 を投稿・配布前に確認する。
```

この PR は Ironmate 側の契約と安全性を整備する。btk の既存描画を置き換える変更は含まない。
