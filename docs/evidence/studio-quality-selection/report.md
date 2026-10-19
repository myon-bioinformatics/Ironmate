# 拡大候補選択と110ケースの品質評価の照合

2026-10-19。基点はmain `b91fbcb52885c10d5d7cb69ff42f6718103d66ca`。
[110ケースの元実験](../studio-quality/report.md) と
[既存の拡大候補選択](../../image-comparison.md) を同じ基準画像で接続した。
[全候補・指標別の同点集合・Pareto集合・処理負荷](results.json) を保存する。
人間の好みや知覚品質の正解は測っていない。選択は基準を見たoracleであり、未知画像へ固定する方針の学習・独立評価ではない。

## 再現

```sh
# ネットワーク、ブラウザ、追加画像ライブラリ不要。新しい/空の出力先を指定。
python -S scripts/quality_selection_experiment.py --out build/quality-selection
python -m pytest -q tests/test_studio_candidate_selection.py tests/test_image_compare.py tests/test_quality_experiment.py tests/test_studio_shape_metrics.py tests/test_studio_image_quality.py tests/test_studio_alignment.py
# 元の256px拡大例でEnergy Diceを優先し、未補正の前景欠けを0に制約する。
python -S image_compare.py \
  --reference docs/evidence/studio-delivery/tradeoff-original/reference.png \
  --nearest docs/evidence/studio-delivery/tradeoff-original/nearest.png \
  --smooth docs/evidence/studio-delivery/tradeoff-original/smooth.png \
  --quality --select-by energy_dice --max-missing-foreground 0 --out build/quality-choice
```

既存のMAE/RMSE/Balanced選択式と同点処理を共通関数に抽出し、両実験から再利用。
既存の4役割・11候補・PNG・通常のJSON形式は維持する。`--quality` 時だけ診断と
`quality_selected.png` を追加。元画像は変更しない。CLIの詳細は[利用説明](../../image-comparison.md)。

## 比較範囲と重複する指標

110ケースのPNGを読み戻し、寸法・基準と候補のRGBA hashを照合する。
元の前景指標とRGBA類似度を再計算し、記録との一致を確認してから位置合わせとAPIコストを再利用。
新たにRGB MAE/RMSE、Balanced、未補正の前景欠け・過剰画素、位置合わせ操作自体の切り落としを計算した。
比較群はscenario・seed・寸法・基準RGBA hashで分割。probeを加えた基準は別群となる。

同一基準の396組の比較には恒等変換も含め、元実験と同じ母集団で照合した。
選択/Paretoからは明示的な恒等変換を除外する。probe群は1候補だけなので候補間優劣は判断できない。
膨張や縮小往復が結果的に元画像と一致するケースは削除せず、同点集合を記録する。

| 指標の組合せ | 関係 | この実験での扱い |
|---|---|---|
| IoU / Dice | 同じ二値マスクでは `Dice=2*IoU/(1+IoU)` | 順位逆転0。別の独立証拠として数えない |
| RGB MAE / RGBA類似度 | 全画素が不透明なら `RGBA=1-3*MAE/1020` | 110ケースでは同順位。透明画素の隠れたRGBが異なる反例をテスト |
| Alpha IoU | 全110ケースで1 | 不透明画像の変化検出には使えない |
| IoU / Energy Dice / Near Field | 面積、基準エッジ重み、1px近傍許容の違い | 個別の選択結果と逆転を残す |
| Raw IoU / Aligned IoU | 位置ずれを含む比較 / 探索で位置を変えた比較 | 欠損・移動量を併記し、代替しない |

RGB MAEとRGBA類似度の同順位は今回の不透明画像についての関係である。
透明画像で白背景へ合成したRGB誤差は、元RGBAのチャンネル誤差と同じではない。

IoUとの厳密な逆転は符号付き効用差の積 `< -1e-12`、同点・微小差・未定義は別計数。
MAE/RMSEは小さいほど良い向きに変換して比較する。396組は相互独立な標本ではない。

| 比較先 | IoUとの順位逆転数 |
|---|---:|
| RGB MAE（低い順） / RGBA類似度（高い順） | 各37 |
| RGB RMSE（低い順） | 35 |
| Balanced（高い順） | 34 |
| Energy Dice | 32 |
| Near Field | 7 |
| Aligned IoU | 10 |
| 未補正の前景欠け画素数（少ない順） | 48 |

## 110ケースからの候補選択

恒等変換を除いたshapes・seed 20261018・128pxの抜粋。
単一の画質順位を作らず、既存の選択を同じ候補プールへ適用した。

| 候補 | RGB MAE | RGB RMSE | Balanced | IoU | Energy Dice | Near Field | RGBA類似度 | 未補正の前景欠け |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| +1px移動 | 2.934774 | 18.225269 | 95.850972 | 0.938076 | 0.870158 | 0.984024 | 0.991368 | 141 |
| 3×3ぼかし | 2.032654 | 8.619097 | 97.911421 | 0.942143 | 0.882496 | 0.985536 | 0.994022 | 0 |
| 輪郭膨張 | 1.774801 | 14.244853 | 96.858891 | 0.919567 | 0.869461 | 0.979892 | 0.994780 | 0 |

MAE/RGBAは膨張、RMSE/Balanced/IoU/Energy/Near Fieldはぼかしを選ぶ。
既存のMAE/RMSE Paretoにも5軸の品質Paretoにも、ぼかしと膨張の両方が残る。
64pxではMAE/RMSE/Balanced/Near Fieldはぼかし、IoU/Energyは+1px移動を選ぶ。
同じ画像種別でも寸法や目的で選択が変わり、一律に最良な変換は決められない。

## 実際の拡大候補11段階への適用

既存の256px基準・最近傍・平滑補間PNGをそのまま読み、混合率0〜1の11候補を再生成。
MAE/RMSE用の元の選択・全候補の数値・Pareto集合は保存済み結果と一致する。

| 選択方針 | 平滑補間率 | RGB MAE | RGB RMSE | IoU | Energy Dice | Near Field | 未補正の前景欠け |
|---|---:|---:|---:|---:|---:|---:|---:|
| MAE / RGBA | 0.0 | 14.497630 | 36.023626 | 0.892017 | 0.867378 | 0.949509 | 90 |
| IoU / Energy / Near Field | 0.3 | 15.056666 | 33.237604 | 0.892722 | 0.887132 | 0.950000 | 0 |
| 中間 | 0.5 | 15.440592 | 31.883027 | 0.879580 | 0.885771 | 0.943435 | 0 |
| Balanced | 0.8 | 16.094147 | 30.737891 | 0.859701 | 0.885771 | 0.933413 | 0 |
| RMSE | 0.9 | 16.307892 | 30.612404 | 0.856215 | 0.885771 | 0.931655 | 0 |

この拡大例ではMAE/RMSE Paretoも5軸Paretoも0.0〜0.9が残る。
「中間」「Balanced」が形状指標でも最高とは限らず、形状優先0.3もMAE優先0.0より色誤差が増える。
制約付き選択は元の候補を選ぶだけであり、画像を再描画したり原画の細部を推定したりしない。

## 縮小・平滑化の追加比較

110ケースの `shrink_expand` は1/4縮小後の最近傍復元、`enlarge_crop` は5/4拡大と中央切り出しである。
これらを一般的な純粋縮小の評価と呼ばない。別に3種類の既存sourceから次を固定して実験した。

- seed 20261018のpixel-art / shapes / gradientを既存のfloor最近傍で64pxへ準備。
- その既知基準を2×2ブロック複製で128px化し、同じ3×3 clampぼかしを加える。
- 同じ128px入力をfloor最近傍または2×2面積平均（整数floor）で64pxに縮小。
- この2候補を既存のpremultiplied混合で11段階にし、固定64px基準へ比較。

この人工的なブロック構造という前提を含む。自然画像、任意倍率、ブラウザの補間方式への一般化はしない。
0=最近傍縮小、1=面積平均縮小であり、この表の混合率を拡大の平滑率と混同しない。

| 種類 | MAE優先 | RMSE優先 | Balanced | IoU / Near Field | Energy Dice | MAE/RMSE Pareto | 5軸Pareto |
|---|---:|---:|---:|---|---|---|---|
| pixel-art | 0.8 | 1.0 | 1.0 | 全11候補同点 | 全11候補同点 | 0.8, 1.0 | 0.8, 1.0 |
| shapes | 1.0 | 1.0 | 1.0 | 1.0 | 0.2 | 1.0 | 0.2, 0.3, 0.5, 0.7, 0.8, 0.9, 1.0 |
| gradient | 0.8 | 0.8 | 0.8 | 全11候補同点 | 全11候補同点 | 0.8 | 0.8 |

shapesでは1.0のRMSE=8.887700・Energy=0.891583に対し、0.2のRMSE=11.304897・Energy=0.947728。
面積誤差と基準エッジ重みが異なる目的を持つため、5軸ParetoはMAE/RMSE Paretoより広がる。
全同点の指標で選ばれるindex 0は、indexによる機械的な決定であり画質改善ではない。

## 欠損と位置合わせ

Studio demo・128×72・+1px移動はAligned IoU=1だが、変換時に非白72画素が切れ、逆変換で元に戻らない。
位置合わせが一致しても情報が保持されたとは判定しない。

| フィールド | 意味 |
|---|---|
| `missing_foreground` / `extra_foreground` | 未補正座標での前景マスクの欠け / 過剰。色・しきい値の変化も含む |
| `source_clipped_nonfill` / `source_inverse_exact` | 既知の前方移動recipeの切り落とし / 元基準との厳密な逆変換一致 |
| `registration_clipped_nonfill` / `registration_inverse_exact` | 比較用の位置合わせ操作が候補自体を切り落とすか / 候補へ戻せるか |
| `crop_discarded_canvas_pixels` | 拡大キャンバスからcropで捨てた画素位置数。異なる元情報が何個失われたかは意味しない |

元実験のcropの`clipped_nonfill=0`は移動専用カウンターである。
今回の`source_clipped_nonfill`は移動以外では`null`とし、「欠損なし」の証拠にしない。
通常のPNG入力の過去の変換履歴も不明なので`null`。
`max_source_clipped_nonfill=0`制約は不明な候補を除外する。Aligned IoUで制約を解除しない。
Energy Dice=1でもgradientの端の切り落としを見逃す元実験の例も残っている。

## 処理時間・メモリと選択の関係

元実験のtransform CPUは1回測定、3つのAPI群は独立にwarmup後の3回中央値とtracemallocを記録。
既存値はそのまま再利用し、重複するAPI群の時間・メモリを合算しない。
今回の`diagnostic_cpu_ms`は入力変換・マスク・重み・誤差・位置合わせ・欠損を含む呼び出し全体の1回CPUで、
元のAPI群の測定範囲とは違う。sweep CPUは候補生成とRGB誤差を含み、変換単体と呼ばない。
追加の縮小は端点の変換CPUを別記し、混合候補全体の変換時間へ推定加算しない。
このためsweepの`transform_cpu_ms`は`null`で、cost Paretoは未定義indexを明示する。

shapes・128pxの元観測は、移動17.248ms、ぼかし91.685ms、膨張13.596ms。
前景指標群はそれぞれ2.454 / 2.432 / 2.778ms、ピーク割当はいずれも1,082,584 bytes。
Balancedが選ぶぼかしは、この観測では膨張より変換CPUが大きい。
記録された変換CPUとIoUでは396組中122組の順位逆転があるが、単発測定の順位を性能保証にしない。

品質ParetoはMAE/RMSE/IoU/Energy/Near Fieldの5軸。
別に、観測transform CPUを加えた6軸のcost Paretoを記録し、遅い候補を削除せず残す。
shapes・128pxでは品質Paretoの2候補に対し、cost Paretoは6候補となる。
計算コストの重みを画質へ暗黙に混ぜず、利用者が目的と上限を指定する方式にした。

## 回帰テストの契約と限界

既存の数値・役割・PNG挙動、110件のhash/指標照合、396組の逆転数、透明画像による重複指標の反例、
基準違いの拒否、欠損制約、未定義Energy、同点・厳密Pareto、保存済みの72画素欠損を確認する。
4つの11候補sweepを毎回再生成し、画素hash・各指標・選択・Paretoを保存記録と照合する。
CPUの閾値や新規測定時間の順位は固定しない。

画像コーパス、背景しきい値、倍率、変換は限定的。人間の知覚評価、タスク精度、未知画像での最良選択は未検証。
既存の変換を維持しつつ、基準付き実験で「どの指標・制約で何を選んだか」を再現可能にする変更である。
