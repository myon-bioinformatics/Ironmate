# ブラウザ別スクリーンショットの比較シート

`browser_matrix.py` は、browser-test-kit の `platform-apps` が保存したスクリーンショットを読み、
「ページ × 環境（OS・ブラウザ・プロファイル）」の比較シートを作る。Python 標準ライブラリと
Ironmate の PNG コーデックだけを使う。

```sh
python -S browser_matrix.py app-results --out matrix                     # 既定: width-384 の画面
python -S browser_matrix.py app-results --out matrix-initial --shot initial --reference macOS-webkit-desktop
```

入力は任意の深さの `.../<page>/<OS>-<browser>-<profile>/<shot>.png`。browser-test-kit の artifact を
展開したままのツリーをそのまま渡せる。同じページと環境の組み合わせが 2 枚ある場合は止まる。

## 出力

- `sheet.png`: 行がページ、列が環境。スクリーンショットのない組み合わせは灰色。
- `tiles/<page>/<env>.png` と `index.html`: 同じ並びをラベル付きの表で見る。
- `report.json`（`ironmate-browser-matrix/1`）: 各セルの元ファイル・SHA-256・元の寸法と、基準環境との差。

## 差の意味

端末ごとに devicePixelRatio が違う（iPhone 3 倍、Pixel 2.625 倍）ため、各画像を共通の幅に面積サンプリングで縮め、
共通の高さに切り詰めるか白で埋めてから比べる。タイルの寸法と間隔は 8 px の倍数に限る（browser-test-kit の撮影幅と同じ 8 px グリッド）。差は、タイル同士の RGB の MAE / RMSE（0〜255）。
「このエンジンではページの描かれ方が違う」という画面単位の手がかりで、画素単位の回帰判定ではない。
基準環境は既定で `Linux-chromium-desktop`（なければ環境名で最初のもの）。

モバイル表示はエミュレーションで、実機の画面ではない。公開サイトは実行のたびに変わりうるので、
どの build を見たかは browser-test-kit の記録（`target.provenance`）で確かめる。
