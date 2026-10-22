# pillow_min.py

`pillow_min.py` は、PNG と APNG を扱うための Pillow の代替です。標準モジュールだけで書いた1ファイルで、Python 3.9 以上で動きます。正本はこのリポジトリにあり、利用側は vendor-lock で取り込みます（Issue #153）。

## 対象範囲

利用側が実際に呼んでいる Pillow 13 の API を、同じ結果になるように実装しています。

| 区分 | API |
|---|---|
| 読み込み | `Image.open`（パス・bytes・ファイル風オブジェクト）、`n_frames` / `is_animated` / `seek` / `tell`、`info` |
| 画像の作成 | `Image.new` / `frombytes` / `putdata` / `putpixel` / `putpalette` / `getpalette` |
| 変換・参照 | `convert`（L / LA / RGB / RGBA へ）、`crop`、`split`、`point`、`histogram`、`getbbox`、`getextrema`、`getpixel`、`tobytes`、`width` / `height` / `size` / `mode` |
| 書き出し | `save`（PNG のみ。モード 1 / L / LA / P / I;16 / RGB / RGBA、`transparency` / `bits` / `compress_level`） |
| 差分 | `ImageChops.difference` / `lighter` / `darker` |
| 独自の補助 | `open_bytes`（RGBA で返す）、`decode_png_rgba`、`iter_apng_frames`、`encode_png`、`decode_base64`、`Image.to_base64`、`diff_metrics`、`paeth`、`unfilter_scanlines` |

PNG はすべての色タイプとビット深度（1 / 2 / 4 / 8 / 16bit）、インターレース（Adam7）、tRNS、短いパレットに対応します。開いたときのモードは Pillow と同じです（例：16bit グレーは `I;16`、16bit グレー＋アルファは `RGBA`、1bit グレーは `1`）。

## Pillow の挙動に合わせている点

結果を Pillow と一致させるため、次の挙動もそのまま再現しています。

- 16bit グレー（`I;16`）を 8bit に変換するときは、縮小せず 255 で頭打ちにします。
- tRNS の透過キーは下位 8bit だけを比較します。2bit・4bit グレーでは、拡大後の値とキーをそのまま比べます。
- グレースケール変換は Pillow と同じ固定小数点の式（L24）を使います。
- `Image.new` に整数の色を渡すと、複数バンドのモードではリトルエンディアンで展開します。RGBA の既定色は透明な黒です。
- APNG のフレーム合成は Pillow の dispose / blend の手順どおりです。OVER の合成はマスク付き貼り付けの式で計算します。「直前に戻す」の結果は、Pillow と同様に前のフレームの画素を読んだかどうかで変わります。
- サイズ上限は Pillow と同じです。`MAX_IMAGE_PIXELS`（既定 89,478,485 画素）を超えると `DecompressionBombWarning`、その2倍を超えると `DecompressionBombError` です。この値はモジュール属性で、呼び出し時に読み直します。

## Pillow と意図的に違う点

| 項目 | Pillow | pillow_min |
|---|---|---|
| 形式 | JPEG・WebP・GIF なども読める | PNG と APNG だけ。ほかは `UnsupportedImageError` |
| 壊れたファイル | 一部のチャンクの CRC を見ない。末尾の余分なデータや途中までのファイルを読めることがある | すべてのチャンクの CRC を検証し、末尾の余分なデータと途中で切れたファイルは開くときにエラー |
| エラーの型 | `OSError` の派生（`UnidentifiedImageError` など） | `ImageDecodeError` は `ValueError` と `OSError` の両方の派生。どちらで捕まえても動く。メッセージの文面は異なる |
| 16bit グレーの APNG を OVER で合成 | `conversion from I;16 to RGBA not supported` で失敗 | 合成できる（マスクは不透明として扱う） |
| インターレースの APNG の2枚目以降 | Pillow 13 の不具合で失敗（`decoderconfig` がフレームごとに伸びる） | 読める |
| 巻き戻し（`seek` で前のフレームへ） | OVER 合成でパレットのアルファが書き換わり、新しく開いた場合と変換結果がずれることがある | 新しく開いて同じフレームへ移動した場合と同じ結果 |
| 変換後の `info['transparency']` | 変換先によっては RGB のキーなどに書き換えて残す | 別モードへ変換したら削除する |
| 未対応の API | — | APNG の書き出し（`save_all`）、P / 1 / I;16 への変換、`resize` / `paste` / `ImageDraw`、`I;16` の `histogram` / `point`、テキスト・dpi・gamma・ICC の `info` |
| 速度 | C 実装 | 純 Python。1280×720 の読み込みは 0.1〜1 秒（Paeth フィルタが多いほど遅い）。`image_diff` 相当の差分処理は 0.3 秒前後 |

## 検証

- `tests/test_pillow_min_parity.py`：Pillow を参照実装にした、シード固定のランダム照合です（Pillow は dev 依存だけで、`pillow_min` 本体は import しません）。全色タイプ・ビット深度・フィルタ・インターレース・範囲外の透過キーの読み込み、Pillow が書いた APNG と手作りの APNG（部分フレーム、全 dispose / blend、既定画像あり／なし、fdAT の分割）の各フレームを照合します。フレームは「各フレームを読みながら進む」場合と「直接移動する」場合の両方で比べます。ほかに Image / ImageChops の各操作、`save` の往復、上限の扱いも照合します。
- `tests/test_pillow_min.py`：#152 で追加した単体テストです。
- browser-test-kit の `scripts/image_diff.py` を pillow_min に切り替えて、Pillow 版と比べました。ランダムな 300 組（全 PNG 形式、APNG、zip メンバー、clip / viewport、tolerance、壊れた入力を含む）で、終了コードと標準出力がすべて一致しました。壊れた入力でのエラーの文面だけが異なります。
