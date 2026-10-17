# PNG拡大候補を複数の軸で比べる

`image_compare.py` は、同じ寸法の基準PNG・最近傍拡大PNG・平滑補間PNGを受け取り、
既存の2画像の混合率を振って候補を保存する。Python標準ライブラリとIronmateのPNG codecだけを使う。
Image StudioのUIや配信ファイルには追加依存を持ち込まない。

```sh
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png --out variants
# MAEを75%、RMSEを25%として評価する例
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png --mae-weight 0.75 --out variants-mae75
```

基準画像は必須。未知の原画像を採点できるという意味ではなく、基準付き実験の候補比較用である。
入力はPNG 32MiB・4MPまで、寸法が異なる入力は拒否する。
既存stdlib codecの範囲（8-bit gray/gray+alpha/RGB/RGBA、非インターレース）に限る。
混合率は既定0.0〜1.0の11段階。`--steps`は2〜100の偶数で、全候補の合計は16MPまで。
出力先は新しいディレクトリまたは空ディレクトリだけを許可する。入力を変更しない。

## 出力と評価定義

- `variant-00.png` など: 全候補。元の最近傍／平滑補間も端点として残す。
- `mae_priority.png`: 平均絶対誤差（MAE）が最小の候補。
- `rmse_priority.png`: 二乗平均平方根誤差（RMSE）が最小の候補。
- `midpoint.png`: 混合率0.5。中間だから最良とは限らない。
- `balanced.png`: 明示した重みのスコアが最高の候補。
- `report.json`: 全候補の誤差、入力ハッシュ、選択理由・重み・Pareto集合。複数の役割が同じ画像を指す場合もある。

RGBを白背景へ合成してから、全画素×3チャンネルを0〜255の同じスケールで測る。
alphaのMAE、完全一致する元RGBA画素数も別に出す。完全透明の隠れたRGBが違うと、
表示誤差は0でも元RGBAの完全一致にはならない。従来の完全一致・残差評価を置き換えない。
混合はpremultiplied alphaの8-bit sRGBで整数丸めする。線形光での補間ではなく、未知の細部は追加しない。

補助スコアは `100 × (1 − (w × MAE + (1 − w) × RMSE) / 255)`。既定の `w=0.5` は
両誤差を同じ重みで扱うという方針で、知覚的な正解や普遍的な最良値ではない。
重みを変えると選ばれる候補も変わり得る。候補ごとのmin/maxに合わせて正規化し直さない。
Pareto集合は、MAE・RMSEの両方で劣る候補を除いたもの。総合スコアとは別に全候補を保持する。
同点は、各誤差または候補indexの明示した順序で決定する。

## 先行ロジックとの関係

PythDRagoras `83a53f60d1b5dec70df841a1104d4c78fbe4a494` の `rule_search.py` は、
precision/recallを残したままMCCで順位付けし、候補を探索前に決め、別データで確認する。
Aoi `62ad1e49154121cf237d52de352404c4400e6a55` の
`sakanalytics/league_laboratory.py`・`pythdragoras/score_sensitivity.py` も、複数軸・変化量・条件を区別して残す。
今回取り入れたのは、全候補の保持・複数軸・選択条件の固定・別seed評価の方法。
二値分類のMCC/precision/recallを画素誤差へ直接転用していない。

web-ui `9ab07c0e09cd06209dd795f7a8f9a595da302c36` の `scripts/check_visual_regression.py` は
PNG寸法とSHA-256による完全一致を扱う。画素誤差・候補補間は提供していないため、
既存のIronmate `photo_grid.decode_png`・`grid_png.to_png`・`grid_output.write_output` を再利用した。
他repoのコードやPython/JS依存を新たにコピーしていない。
将来共通化する場合も、PNG寸法・基準の有無・alpha/背景・誤差定義を契約にし、
web-uiの完全一致検査を緩めるものとして扱わない。

[実験記録](evidence/studio-delivery/tradeoff-report.md) に、元の比較と別seedの成功・悪化を両方保存する。
