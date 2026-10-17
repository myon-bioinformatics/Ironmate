# Image Studio 検証記録

記録: 2026-10-17

Ironmate main `680b35f6daeee52dff1ccf5998e313203ac7f210` に対する追加試作。
図形・文字・絵文字・ローカル画像を合成し、ヒートマップの色段階とモザイクの粒度を探索する。
既存の3-Way Surveyの結果・閾値・生データは変更していない。

## 実際の出力

- [デスクトップ画面](desktop.png) / [390px幅の画面](mobile.png)
- [作成したPNG](demo.png) / [SVG](demo.svg) / [再編集用JSON](demo-scene.json)
- [実ブラウザの検証結果](browser-result.json) / [対象ソースのSHA-256](source-sha256.json)

![スタンプと行列から作成したPNG](demo.png)

これは架空の数値を用いた合成例で、Aoiの野球分析結果ではない。
ユーザー提供の画像をリポジトリへ転載していない。

## 参照した先行実装

| 対象 | 確認SHA | 参照箇所 |
|---|---|---|
| Flutter Navigation Basic | `13905a4d90f97daa73069d6fbff43acd6a65a760` | `lib/features/photo_studio/domain/studio_document.dart`, `photo_studio_state.dart`, `studio_geometry.dart`, `emoji_stamp.dart` |
| Aoi / DRAgoWing | `62ad1e49154121cf237d52de352404c4400e6a55` | `dragowing/figures.py::heatmap_figure`, 描画・書出し経路 |

状態をレイヤーとして保持すること、表示色と元の数値を分離することを参照した。
DartのコードやPlotly本体を取り込まず、PythonとJSの独立実装にした。
Plotlyのグラフ描画を再現するのではなく、単一heatmap traceの数値を合成画像用に取り込む。
先頭行を上として描くため、Plotly側の軸の設定が異なる場合には上下順も同じとは限らない。

## 数値・画像の回帰検証

`python -m pytest -q tests/test_image_studio.py`: **16 passed**。

- Python/JSの色変換: 負数、範囲外、定数行列、欠測、連続／量子化の37条件で一致。
- 元の浮動小数値・null・軸ラベル・sourceを保存し、色段階変更で数値が変化しない。
- 非長方形、bool、非有限値、安全整数範囲外、極端に大きな整数を拒否する。
- 7×5 RGBA画像のセル幅1/3/128、色段階256/4/2の4条件でPythonとJSの全画素が一致。
- ブロック平均ではalphaを考慮。透明な青と不透明な赤の平均は半透明の赤であり、紫にはしない。
- 端の余りセルを保持し、PNG encode/decode後のRGBAも一致。
- SVG内の文字列をエスケープし、外部URL画像、無効な寸法・角度、重複IDを拒否する。
- Undo後の別編集でRedo枝が消えること、状態を参照共有で破壊しないことを確認。
- ローカルHTTPは固定した4ファイルだけを配信し、プロジェクト内の他ファイルやPOSTを受け付けない。
- Python CLIは既存の出力ファイルを明示なしに上書きしない。

## 実ブラウザ・PPTX検証

Python 3.12.14 / Node 24.19.0 / Chromium 133.0.6943.0 / Linux x86_64。
ブラウザの自動操作にはtest-only Playwrightを利用。
日本語・絵文字用のNotoフォントを検証環境へ導入して目視確認した。
この環境の絵文字は単色。利用端末の絵文字フォントにより見た目は変わる。

`node tests/image_studio_browser.cjs`: 成功。
テストはPythonサーバーを自分で起動し、終了時に停止する。CDNや外部画像には接続しない。

| 検証 | 結果 |
|---|---|
| 図形の配置・内側からの移動・右下ハンドルでの拡縮 | 成功 |
| 選択レイヤーのカスタムスタンプ化、繰り返し配置 | 成功 |
| 絵文字の配置、Undo/Redoでのレイヤー数復帰 | 成功 |
| ヒートマップの色段階変更 | 元のz値が完全一致 |
| モザイクのセル幅を変更してから1へ戻す | 保持した元画像のPNGを再利用 |
| キャッシュ上限を超える20画像の加工 | 全画像が設定どおりの処理済み画素を表示 |
| JSON保存→別編集→読込 | シーンが完全一致、同一環境でPNGバイト一致 |
| オフラインでのPNG出力 | オンライン時のPNGとバイト一致 |
| 選択ハンドル | SVG・PNGには含まれない |
| 390px幅 | 横方向のページはみ出しなし |
| PNG→固定PptxGenJS 4.0.1→PPTX | media内のPNGが出力PNGとバイト一致 |
| JavaScript例外・外部HTTP通信 | 0件 |

キャッシュ容量を超える画像の表示試験で、必要な処理済み画像を各描画へ渡す方式に修正した。
単にキャッシュから落ちた画像を元画像で表示することがないように回帰試験を追加した。
これは画素の滑らかさ・自然画像の復元精度・高速性の証明ではない。
PPTXは画像として挿入した検証であり、スタンプがPPTXネイティブ図形になったわけではない。

## 既存機能・CI

既存のPython・PPTX統合workflowへstudioのパスを追加した。
実ブラウザ検証は既存のPPTX統合ジョブの後半で行い、既存テストの前に失敗して
PPTX検証を省略する配置にはしていない。既存artifactの中へブラウザ証跡も保存する。
workflow権限、配布設定、JUnit集計経路は変更しない。

actionlint 1.7.7、Python compile、Node構文検査、git diff --checkは成功。
ローカルの既存suiteに必要な親ツールとxprobeは、workflowと同じ固定SHAを用意して確認した。

`python -m pytest -q -m 'not heavy'`: **790 passed / 13 skipped / 7 deselected**。
13 skipは既存のオプションMarp/Chromiumレーンであり、新規Python/JS検証のskipはない。
Marp/PPTX実機能のCIと新規ブラウザ検証はGitHub Actionsの統合ジョブでも確認する。
