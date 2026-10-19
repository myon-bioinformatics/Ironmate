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

## 形状・色・欠損を併記して選ぶ（任意）

```sh
python -S image_compare.py --reference truth.png --nearest nearest.png --smooth smooth.png \
  --quality --select-by energy_dice --max-missing-foreground 0 --out variants-quality
```

`--quality` は既存候補を変更せず、`report.json` の `quality` に同一基準画像での
IoU、Dice、Energy Dice、Near Field、RGBA類似度、未補正の前景欠け・過剰画素数、
位置合わせの移動量と切り落としを追加する。形状定義は110ケースの実験と同じ
白背景への合成・白からの距離>32、基準固定の前方エッジ重み、探索半径2である。
既定のMAE/RMSE用レポートと4役割のPNGは従来どおり。
診断は候補合計1MPまで（従来の拡大候補生成は16MPまで）。追加依存は不要。

`--select-by` は `rgb_mae` / `rgb_rmse` / `balance_score` / `iou` /
`energy_dice` / `near_field` / `rgba_similarity` から選ぶ。省略時は従来のBalanced。
選択した元候補を `quality_selected.png` に保存し、選択indexを標準出力にも返す。
`--max-missing-foreground N` は未補正の前景欠け画素数の上限。
前景マスクでの欠けであり、情報消失の正確な数や可逆性を保証するものではない。
条件を満たさない場合は `selected_index: null` と除外理由を記録し、選択PNGを作らない。
Energy Diceの未定義値も同様に除外し、別指標へ自動で切り替えない。
これらのフラグは `--quality` を必要とする。

`studio_candidate_selection.select_quality()` は共通API。
同じ寸法と基準RGBAのSHA-256を持つ候補だけを受け付ける。
`max_source_clipped_nonfill` で変換時の既知の切り落としも制約にできる。
由来が不明な候補はこの制約から除外する。通常の入力PNGから変換履歴を推測せず、
`source_clipped_nonfill` は `null`。位置合わせ操作の切り落としとは別に扱う。

全指標について同点集合も残す。MAE/RMSE/Balancedの同点処理は既存の副誤差→index、
他の指標はindex順。全同点時の先頭選択は画質優位を意味しない。
`quality.summary.legacy` はMAE/RMSEの既存Pareto集合、`quality_pareto` は
MAE・RMSE・IoU・Energy Dice・Near Fieldの明示した5軸。
DiceはIoUと同順位であり、今回の不透明画像のRGBA類似度はMAEと同順位なので、
既定の5軸には加えない。透明画像ではRGBAと表示RGB誤差が異なるため、必要なら
`pareto_indices(rows, axes=...)` で軸を明示する。
欠損を隠し得るAligned IoUや処理時間は既定の画質Paretoに含めない。
未定義の軸がある候補はPareto計算から除外し、そのindexを明示する。

[110ケースとの照合・拡大と縮小の再現実験](evidence/studio-quality-selection/report.md)
には指標の重複、順位逆転、位置合わせ時の欠損、観測処理時間を分けて記録した。
基準付きの探索的選択であり、人間による知覚評価や未知画像の普遍的な最高画質判定ではない。
