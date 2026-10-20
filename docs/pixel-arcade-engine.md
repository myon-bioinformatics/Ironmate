# スパース走査と4種プローブの試作

`pixel_arcade_engine.py`（標準ライブラリ、Python 3.11以上）を、既存の
`ironmate-pixel-grid/1` と `grid_tools` に接続する。既定の最近傍変換は変更しない。

## 可逆操作とフレーム

```python
import grid_tools as g

original = g.make('circle', 'C02', 'outline', 16)
scanner = g.sparse(original, quota_per_frame=4)
frames = scanner.iter_shift_frames(1, 0)
first_frame = next(frames)  # 最大4ドットだけ更新。sleepや実時間の待機はない
scanner.quota_per_frame = 8  # 次のフレームから処理量を変更
for frame in frames:
    current_artifact = scanner.grid.to_artifact()
scanner.grid.rollback_all()
assert scanner.grid.to_artifact() == original
```

一括実行は `scanner.shift_formation_step_by_step(1, 0)`。
戻り値の `frames_for_one_step` はバッチ数、`relative_speed_vs_55` は試作の
比較用比率であり、実行時間の測定値ではない。空グリッドは0フレーム。
途中で打ち切るときは `frames.close()` 後に `rollback_all()` できる。
進行中のiteratorを残したまま他の画素操作やrollbackを混在させない。

- `iter_active_coords()` は `(flat_index, x, y)` を返す。LSB取り出しと
  `mask &= mask - 1` により、yield数は有効ドット数と一致する。
- スキャナの移動は上下左右の隣接1セルのみ。進行方向順の逆順スワップで、
  隣接した多色ドットも1セルずつ移す。斜め・複数セル移動は拒否する。
- 辺への接触は `check_sentinel_collision()`、指定領域との接触は
  `check_sentinel_collision(precomputed_mask)`。検査時に画素・座標を走査しない。
- 移動先が範囲外になる場合は、進行方向の辺マスクとのANDで事前に拒否する。
  外周の他の辺へ接触しているだけなら移動できる。部分移動後の黙った切り捨てはしない。
- スワップは色値XORと占有マスクXORの差分を記録し、逆順に適用して復元する。
  色値が同じスワップは履歴に含めない。`rollback_all()` は履歴件数を返す。
- adapterは入力・出力をコピーし、色番号、未使用色、重複色、メタデータを保持する。
  `pixels` は読み取り専用のtupleスナップショット。外部からの配列変更で履歴を壊さない。

Python整数は多倍長なので、AND・LSB処理・bit_countは整数のワード数にも依存する。
したがって「厳密なO(1)の境界検査」「待ち時間ゼロ」「走査全体が厳密にO(N_active)」
とは呼ばない。初期マスク作成は全セルを読み、フレーム開始時は有効indexのリストを確保する。
履歴は実際に変更されたスワップ数に比例して増える。

## 4種プローブによる2倍縮小

```bash
python -S -m grid_tools make circle --size 32 --resize 16 --resize-method probes --to png -o small.png
python -S -m grid_tools load small.png --to base64 --data-uri
```

```python
small = g.downscale_2x(original)
assert small == g.resize(original, 8, method='probes')
assert g.restore(g.encode(small), backend='stdlib') == small
```

偶数幅・偶数高さ（各2以上）のみ対応する。奇数の右端・下端を黙って捨てない。
`resize(..., method='probes')` は両軸とも正確に半分のサイズに限る。
この経路は常に標準ライブラリで計算し、既存の `backend` 選択には依存しない。
出力の `resampling` は `pacman_probes_2x_lossy`。

| プローブ | 座標の規則 |
| --- | --- |
| アカベイ（`akabei`） | `akabei_ref` を直接参照 |
| ピンキー（`pinky`） | `(x + (dx << 2), y + (dy << 2))` |
| アオスケ（`aosuke`） | 2セル先をpivotとして `(pivot << 1) - akabei_ref` |
| グズタ（`guzuta`） | 前回保持した特徴点までのマンハッタン距離が8以上なら追跡、8未満ならcornerへ退避 |

入力プロトタイプから、以下の点を安全なグリッド処理向けに補正した。

- 色番号は順序のないラベルなので、方向推定は番号の大小でなく占有状態で求める。
  代表色は局所の非背景色を投票し、アカベイ/ピンキー/アオスケの一致票を加える。
  同数なら局所の行順で先に現れた色を採用する。paletteの番号を置き換えても見える結果は同じ。
- 局所に1ドットだけある場合でも、左上セルが空だからという理由で消さない。
- alpha=0の色番号はすべて背景、alpha=1〜255は有効。色番号0も不透明なら有効である。
  透明色がないpaletteには、縮小が透明セルを生成した場合だけ末尾へ透明色を追加する。
- cornerは仮想的な背景アンカーであり、元画像のcornerを消したり、その色を背景と推測したりしない。
  実際の距離も確認し、前回の特徴点がcorner座標だった場合と退避を混同しない。

グズタの間引きは、局所2×2が3ドット以上、特徴点まで8未満、ピンキー/アオスケが背景、
出力座標が奇数パリティのときに行う。これはラスタ走査順に依存する試験的なヒューリスティックであり、
任意の絵で線の連結性・対称性・読みやすさを保証しない。4×2の密集入力で最近傍の
`[1, 1]` を `[1, 0]` に間引く例と、孤立ドットを保持する例をテストする。

## 復元できる範囲

スワップ→rollbackは元の画素・占有マスク・artifactを完全復元できる。
縮小後のartifact→PNG/Base64→artifactは既存仕様で往復できる
（重複RGBAの色番号は従来どおり最初の番号に寄る）。SVGでは見えるRGBAを比較する。

**縮小自体は不可逆**。出力だけから元の細部を復元できない。
既存の最近傍拡大はそのまま利用できるが、失われた細部を再構成するものではない。
この試作は4種プローブによる拡大補間や、縮小前の画像を隠して保持する仕組みを追加しない。

```bash
python -m pytest -q tests/test_pixel_arcade_engine.py tests/test_grid_tools.py -m 'not heavy'
```
