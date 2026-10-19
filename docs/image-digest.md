# 画像の要約ページ（image_digest）

多数の画像と、それぞれの合否（status）から、軽い 1 枚の HTML とレビュー用の Markdown 要約を作る。
行と列は何でもよい（ページ × 環境、ケース × 端末、スライド × テーマなど）。browser-test-kit の
published-app の実行のように、全体の成果物が大きくてダウンロードしにくいときに、全体を 1 ページで見渡すためのもの。

```sh
python -S image_digest.py input.json --out digest/            # 画像パスは input.json からの相対パス
node image_digest.cjs input.json digest/                       # Node から（処理は Python が持つ）
```

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
