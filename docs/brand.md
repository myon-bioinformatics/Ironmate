# Ironmate のロゴ6案

共通の核は **I’m のアポストロフィを🔰に置き換えること**です。faviconでも I と m を残します。**正式版は未決定**です。6案を用途に応じて使い分け、以下の割り当ても暫定とします。

| 案 | 素材 | 想定用途・今回の配置 |
| --- | --- | --- |
| ① Pixel Mono | `studio/brand/mono.svg` | SVGロゴ・白黒資料。ギャラリーの印刷時に表示 |
| ② Dark Green | `studio/brand/dark-green.svg`、`icon-192.png` | GitHub向け画像。faviconに暫定採用 |
| ③ Famicom Retro | `studio/brand/famicom.svg`、`readme.svg` | README先頭に暫定採用 |
| ④ GameBoy Style | `studio/brand/gameboy.svg` | 6案ギャラリーのヘッダーに暫定採用 |
| ⑤ Heatmap Pixel | `studio/brand/heatmap.svg`、`hero.svg` | 3画面のヘッダーとブラウザツールのHeroに暫定採用 |
| ⑥ Pixel 3D | `studio/brand/pixel-3d.svg` | ホーム画面追加アイコン・ランチャーに暫定採用 |

GitHubアカウントのプロフィール画像は変更していません。実機へのホーム画面追加は利用者が行います。今回はサイト側のアイコン指定とmanifestを整えています。

## 共通ルール

16×16の整数グリッドを共通字形とし、文字も矩形で描きます。フォント・絵文字フォントに依存しません。SVGは `shape-rendering="crispEdges"`、PNGは整数倍の最近傍拡大です。ICOは16・32・48pxのPNGを格納します。

🔰内部のヒートマップは離散セルで、グラデーションは使いません。ファミコン・GameBoyの枠と3Dの影も整数座標で描き、曲線・ぼかしを使いません。

## 差し替え・再生成

- favicon：`studio/index.html` と `studio/tools/index.html` の `rel="icon"`。`icon.svg` は現在Dark Greenの互換名です。
- ヘッダー：同HTML内の `.brand img`。Slide StudioはImage Studioから生成するため同時に反映します。
- Hero：`studio/tools/index.html` の `.brand-hero`。
- README：先頭の画像リンク。
- ホーム画面：`manifest.webmanifest` と `apple-touch-icon.png`（180px）。Android向け192px・512pxと、マスク用512pxの不透明PNGを用意。
- ギャラリー：`/brand/`。6案を閲覧・保存でき、印刷時はモノクロを表示。

リポジトリのルートで `python -S scripts/build_brand.py` を実行します。Python標準ライブラリと既存の `grid_png.py` だけを使用します。

公開対象は `image_studio.py` の明示的なallowlistで指定し、6案のSVGをギャラリー向けに配布します。README専用SVGと生成スクリプトは配布しません。

## 検証

- 関連Pythonテスト：29 passed、1 skipped（既存のスライドシェル再生成は `npm ci` 未実施のため）。
- Chromium：静的ビルドの `/Ironmate/`、`/Ironmate/tools/`、`/Ironmate/slides/`、`/Ironmate/brand/` を1440px・390px幅で確認。8ケースでロゴ表示、favicon 200、ブランド枠の収まりを確認。manifestのブラウザ解析・ホーム画面アイコンの取得も成功。コンソールエラーなし。
- ローカルPythonサーバー：SVG・PNG・ICOのContent-Typeと配信バイト列を既存テストで確認。
- 16px・32px・48pxの実寸表示と整数倍拡大を目視確認。

[ブラウザ確認結果](evidence/brand/browser-results.json) ／ [390pxの画面](evidence/brand/mobile.png)

![6案とREADME・Heroの暫定配置](evidence/brand/preview.png)

## ホーム画面追加

ブラウザの「ホーム画面に追加」を使用します。Android向けmanifestにはアプリ名、アイコン、開始URL、スコープと3ツールへのショートカットを指定しています。iPhone向けは `apple-touch-icon` を全画面に指定しています。faviconは②、ホーム画面アイコンは⑥です。

マスク用アイコンの全前景画素が中央80%円内に収まること、透過画素がないことを検証しています。実機での追加操作は未検証であり、manifestによる指定がオフライン動作を提供するものではありません。

参照：[Web App Manifest icons](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/icons)、[Apple Web Clipアイコン](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html)。

[6案ギャラリーのスマホ表示](evidence/brand/gallery-mobile.png)
