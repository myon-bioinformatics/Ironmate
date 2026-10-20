# GitHub Pages版のブラウザツール

- Image Studio: https://myon-bioinformatics.github.io/Ironmate/
- ドット絵・画像一覧・Base64容量: https://myon-bioinformatics.github.io/Ironmate/tools/
- ポートフォリオ: https://myon-bioinformatics.github.io/#ironmate

追加のJavaScriptパッケージや外部CDNは使いません。HTML/CSS/JavaScriptと、Python版から生成した公開プリセットだけを配信します。画像・JSONはブラウザ内で処理し、アップロードしません。

## Dockerでビルド・起動

```sh
docker build -f Dockerfile.pages --target runtime -t ironmate-pages .
docker run --rm -p 127.0.0.1:8080:8080 ironmate-pages
# http://localhost:8080/Ironmate/ または http://localhost:8080/Ironmate/tools/
```

GitHub Pages用の公開ファイルだけを取り出す場合：

```sh
docker build -f Dockerfile.pages --target artifact --output type=local,dest=build/studio-site .
```

Python標準ライブラリだけで同じ静的ファイルを作ることもできます：

```sh
python -S image_studio.py --build-site build/studio-site
# 出力先は新規または空のディレクトリ
```

`studio-pages.yml`はDockerで静的ファイルを生成し、コンテナ上の`/Ironmate/`を実ブラウザで検証してから公開します。公開環境でDockerやPythonが動いているわけではありません。権限・公開先・既存StudioのURLは維持します。

## 対応範囲

| 機能 | Pagesでの動作 | ローカル版との境界 |
| --- | --- | --- |
| Image Studio | 既存の図形・画像・文字・ヒートマップ・モザイク、履歴、クリップボード、PNG/SVG/JSON/Base64 | 既存の入力・画素・容量制限を維持 |
| ドット絵 | 5形×4加工×5サイズ、10配色ID、色番号のクリック編集、JSON読込、最近傍拡縮、配色変更、1状態のundo | プリセット元サイズは16/23/31/32/64。出力グリッドは1〜256セル／辺。Pythonの任意サイズ手続き生成・写真減色・スパース走査・プローブ縮小は移植していない |
| ドット絵出力 | PNG/SVG/JSON/Base64。1/2/8/16倍 | PNGはRGBAを直接deflateし、透明画素の隠れたRGBと色表を保持。Python版との圧縮byte一致は保証しない。PNGにはCompressionStream対応ブラウザが必要 |
| 画像一覧 | PNG/JPEG/WebP最大20枚、列数変更、一覧PNG、画像埋込HTML | 1枚8MiB・合計32MiB・1画像4MP。デコード後に画素数を検査し、長辺512px以下のサムネイルを保持。元画像byte・メタデータ保持、合否・MAE/RMSE算出は対象外 |
| Base64容量 | File.sizeから`4*ceil(bytes/3)`を計算。PNG data URIなら22文字加算 | 圧縮率や縮小率の推定ではない。ファイルを読み込まずサイズだけ使う |
| PPTX/PDF・外部API | 実行環境を必要とする範囲を画面に明記 | pptx_pipeline.py / pptx_replace.py / pptx_preview.py等を手元で実行。#145のpypdf取得はブラウザ用の実装ではない |

画像一覧のデコードはブラウザ実装に依存します。アニメーション、EXIF・色管理の完全保持、OS間のフォント一致は対象外です。ファイル選択をキャンセルした場合や不正なJSONを選択した場合は、現在の作業を保持します。ページを閉じると作業は失われるので明示的に保存してください。

## 検証

```sh
python -m pytest -q tests/test_pages_tools.py tests/test_studio_delivery.py tests/test_image_studio.py
# Dockerを上記の8080番ポートで起動した後、テスト専用Playwrightで実行：
IRONMATE_PLAYWRIGHT_MODULE="$PWD/build/pages-test/node_modules/playwright" node tests/pages_browser.cjs
```

全100プリセットの色番号を既存Python実装と照合します。最近傍拡縮は奇数・非正方形を含めてPythonと比較します。ブラウザ検証は既存Studioからの導線、PNG/SVG/JSON/Base64出力、PNG→Pythonでの完全復元、サイズ変更・undo、不正JSONの拒否、画像一覧、ファイル名のHTMLエスケープ、Base64容量、390px幅の画面を確認します。

公開allowlistに入力画像・作業JSON・リポジトリの証跡・Pythonソースを含めません。生成物は約300KBのHTML/JS/CSSとプリセットです。
