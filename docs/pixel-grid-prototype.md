# ドット絵試作：第1弾の契約と次の段階

Ironmate #77の「試作・検証・候補として保管」に沿った候補。
ユーザーの目標は、まず絵文字で機械生成と加工を試し、将来は写真変換や
認識できるオリジナルキャラクターの表現へ進むことである。
第1弾は品質を完成と判定するものではなく、再現可能な色番号グリッドを作る。

## 実装した範囲

`pixel_grid.py` は単一ファイル・stdlib-onlyで、import時に入出力しない。
`render(mask, palette, effect, size)` が `ironmate-pixel-grid/1` を返す（`resampling: procedural_mask`）。
`filename(artifact)` は `{形}_{色ID}_{加工}_{サイズ}.png`（例：`triangle_C01_shadow_32.png`）。

| 軸 | 現在 |
| --- | --- |
| 形 | triangle / diamond / cloud / circle / rock（手続き生成） |
| 配色 | 色ID `C01`〜`C10`（main/shadowから派生） |
| 加工 | normal / shadow / highlight / outline（いずれか1つ） |
| サイズ | 形ごとの範囲内の任意の整数（下表） |
| 正規データ | 色番号の二次元配列＋固定RGBA palette（0=透明） |
| 出力 | 絵文字 / JSON / SVG / PNG |

`SIZES = (8, 16, 32, 64, 128)` は photo_grid.py と共有する代表サイズとして残す。
pixel_grid では8を下限としない形がある（cloud・diamondは8では描かない）。

### 色ID

- IDは `C` ＋2桁の連番（`C01`〜`C10`）。一度割り当てたIDは別の色に再利用しない。
  色名（grass等）は `PALETTE_LABELS` の参考ラベルで、CLI・JSON・ファイル名には使わない。
- 定義は `PALETTE_BASE[ID] = (main, shadow)`。色番号は 0=透明、1=main、2=shadow、3=highlight、4=outline。
- highlight・outlineはRGBの各成分を整数で四捨五入（0.5は切り上げ）して派生する：
  - highlight = round((3 × main + 2 × 255) / 5)（mainを白へ40%寄せる）
  - outline = round(shadow / 2)（shadowを黒へ50%寄せる）
- C05（main #FFFFFF）はhighlightがmainと同じ色になる。

| ID | main | shadow | ラベル |
| --- | --- | --- | --- |
| C01 | #5BBD3E | #418A2D | grass |
| C02 | #63B3FF | #3F75CC | water |
| C03 | #FF6A00 | #CC3D00 | lava |
| C04 | #A84DFF | #7520B8 | poison |
| C05 | #FFFFFF | #CFD8E6 | snow |
| C06 | #E0C072 | #B08D45 | sand（仮） |
| C07 | #9EA4AB | #6D737B | stone（仮） |
| C08 | #A8693A | #744423 | wood（仮） |
| C09 | #FFD23F | #C99A17 | gold（仮） |
| C10 | #FF86C0 | #C9568F | blossom（仮） |

C01〜C05はユーザー指定の値。C06〜C10は10色にするための仮の値で、目視評価は未実施。

### 形（手続き生成）

固定seedの拡大ではなく、サイズごとに図形を計算し直す。外周1セルは透明margin。

| 形 | 生成方法 | サイズ範囲 |
| --- | --- | --- |
| triangle | 1行ごとに左右1セルずつ広げる（頂点1または2セル、高さ≒幅/2） | 5〜256 |
| diamond | セル中心の L1距離 ≤ 半径 | 9〜256 |
| circle | セル中心の距離 ≤ 半径 | 6〜256 |
| rock | 指数2.6の超楕円（高さ0.7×幅）、下側を平らにカット | 7〜256 |
| cloud | 平らな底の上に3つの円（左右r=0.16W、中央r=0.2W）、各列の穴を埋める | 16〜256 |

品質規則（`mask_problem`）に合わない場合は、半径・幅を少し小さくする等の決まった順の候補を試し、
最初に合格したものを使う。どれも合格しなければ `ValueError`。範囲外のサイズも `ValueError`。

### 品質規則

1. 透明margin、4連結、穴・列の途切れなし（cloud以外は行の途切れもなし）。
2. 左右対称。circle・diamondは上下対称も必要。
3. 輪郭のぎざぎざなし：上端・下端（列ごと）と左端（行ごと）の各輪郭を単調な区間に分け、
   - 2セル以上の段差が平らな区間と隣り合わない（2×2の階段を作らない）
   - 隣り合う同じ種類の区間（段差の大きさ、平らな区間の長さ）の比が2倍以内
   （区間の両端は切れているので比較しない）。cloudの左端は、puffの切れ込みより下だけを見る。
4. 形として読めること：triangleは頂点2セル以下で底辺が最大、diamondは頂点2セル以下・充填率0.65以下、
   circleは外接四角形が正方形で角が空き充填率0.68〜0.9、rockは横長・角が空き・底辺が幅の半分以上、
   cloudは上端に2つ以上の切れ込み・底辺が幅の半分以上・頂上が1セルの尖りでないこと。

サイズ範囲は3〜256の全サイズを走査して決めた。下限は「それ以上の全サイズが合格する最小値」。
下限未満で合格するサイズ（diamondの5・7、cloudの14）もあるが、範囲を連続にするため採用しない。
上限256は出力サイズの方針上の上限で、品質規則の限界ではない。
範囲内では5つの形が同じサイズで互いに異なることも確認している（16〜64）。

### 加工

色番号の置換で表す。影＝形の下1/3を2、明部＝上1/3を3、
輪郭＝4近傍に透明がある形の内側のセルを4。silhouetteは変えない。

同じ入力は同じ出力。乱数・ネットワーク・外部モデルは使わない。
絵文字は各色に最も近い絵文字を選ぶ近似表示で、正確な色・透過はJSONで判定する。

## 検証と評価

自動テストでは範囲内の全サイズ（heavy）の品質規則、奇数・代表サイズでの寸法・色範囲・決定性、
加工前後のsilhouette維持、影/明部の位置、輪郭境界、入力拒否、
CLI JSONと副作用のないimportを検証する。
既存pytestからJUnitを生成できるため、専用の証跡生成処理は増やさない。

目視評価では「単色でも形が分かるか」「影が形を説明しているか」
「小型で特徴が残るか」「palette変更後も明暗を読み取れるか」を確認する。
人の品質評価は未実施。テスト成功を美的品質の合格に置き換えない。
候補はこのrepoで保持し、他consumerの需要・契約が明確になってから独立させる。

## 今後の段階（未実装）

1. **出力とサイズ別設計**：JSON gridからPNG/SVGへ出力（`grid_svg.py`・`grid_png.py`で試作済み）。
   16/32/64それぞれのseedまたは輪郭規則を用意し、単なる拡大との差を比較する。
   観察用拡大は最近傍でセル境界を維持する。
2. **キャラクター部品**：胴体・頭・目・口・手足・装備をlayerで合成。
   anchor、重なり順、左右対称と例外、poseを明示する。
   「ロボット」「丸い顔」などのオリジナル形状で識別性を評価する。
   地形向け5マスクの色変更だけでキャラクター品質を達成したとは扱わない。
3. **写真変換**：画像decode→向き補正→crop/背景処理→低解像度化→減色→
   任意dither→グリッド→出力。入力写真はユーザーが選んだものを使用する。
   背景除去や目・輪郭の意味的修正は、単なる減色とは別の処理・評価になる。
4. **写真からキャラクター化**：crop/減色したbaselineと、部品へ特徴を移す方式を比較。
   顔の可読性・輪郭・色数・不要な孤立点を人が評価する。自動で高品質になるとは約束しない。

写真の低解像度化は最初から最近傍だけに固定せず、BOX/LANCZOS等を比較する。
表示用の整数倍拡大はNEAREST。減色は固定paletteまたはquantize、ditherは
無しをbaselineにして細部・ノイズとの関係を比較する。
Pillowにはこれらの操作がある。ただしJPEG/PNG等のdecodeを含む写真adapterは
任意の依存として分離する判断が必要で、コアにPillowを必須化する変更は行っていない。
一次資料：[Pillow Image reference](https://pillow.readthedocs.io/en/stable/reference/Image.html)。

## 第1弾で決めないこと

キャラクター完成品・写真adapter・Web画面・PNG/SVG・大量ファイル保存・
animationはまだない。Gradioが必要になった場合は既存mcp-toolcall-lab環境への
接続を検討し、Ironmateの旧キャラクター/LLM基盤を復活させない。

## 配色置換の目的とOffice CLIへの接続

目的は、同じ形・配置を再利用し、色や文字などの指定した属性を機械的に
置換することである。絵文字は最初の確認手段であり、CSSは必要としない。
参考の素材アイデア集には純粋な配色変更のほか、内部模様や部品の変更も
含まれる。それらは別の加工として扱い、色変更だけの成果と混同しない。

まず雲型で、茂み・水・溶岩・雪の配色を比較できる。
次の例では色番号グリッドが完全に同じで、RGBAテーブルだけが変わる。
用途名は見立てであり、素材としての識別性は別途目視評価する。

```python
from pixel_grid import render

variants = {
    name: render("cloud", name, "shadow", 16)
    for name in ("C01", "C02", "C03", "C05")
}
baseline = variants["C01"]["pixels"]
assert all(item["pixels"] == baseline for item in variants.values())
assert len({tuple(item["colors"]) for item in variants.values()}) == 4
```

Office CLIは今後の別の試作で、まず既存PPTXの文字と塗り色の置換を対象にする。
このPRにはPPTX編集・出力機能は含めない。PPTXはPresentationMLの複数partと
relationshipを持つパッケージなので、ZIP内の全XMLを無条件に文字列置換する
方式ではなく、対象part・図形・属性を特定して編集する方針とする。
将来のWord/Excel対応でも、形式ごとのXML構造を扱うadapterを分ける。

最初のOffice試作で確認する項目：

- 対象のslideと図形を指定し、変更予定・一致件数をdry-runで表示する。
- 文字が複数runに分かれる場合の扱いを定義し、対象外の文字や書式を保持する。
- 直接RGB指定とテーマ参照色を区別し、図形単体の色変更とテーマ変更を分ける。
- 入力とは別ファイルへ出力し、対象外partの内容とrelationshipを保持する。
- ZIP/XMLの再読込・変更差分の検証に加え、レンダリングして表示を確認する。

ドット絵は色番号グリッド、Officeは文書内の図形・文字を入力にするが、
「構造を保持して指定した属性を置換する」という検証の考え方を共通にする。
画像として配置する場合の配色変更と、編集可能な図形の塗り色変更は別処理になる。

一次資料：[Microsoft Learn — PresentationML](https://learn.microsoft.com/en-us/office/open-xml/presentation/overview)、
[Working with slide masters](https://learn.microsoft.com/en-us/office/open-xml/presentation/working-with-slide-masters)。

### 優先順位と依存の方針

- 最初はPPTXの色・文字・背景の変換に集中する。「文字をすべて黒に」
  「背景を白に」「指定の灰色だけを置換」を別々の操作として扱う。
  文字色と背景色に同じRGBが使われていても、対象の役割で選択する。
- CSSは出力の必須基盤にしない。一方、外部HTML/CSSを読む際は入力仕様を
  理解して吸収する。取得済みデータの解析とネットワーク取得を分離し、
  CSS対応を理由に外部資源の取得を無条件に増やさない。
  CSSの「#」に関する具体的な不足機能は、対象コード・入力例を確認してから
  別案件として定義する。この試作でHTML/CSS readerを拡張したとは扱わない。
- XML parserを自作することは目的にしない。既存の標準機能を利用し、
  Officeの対象選択・変換・検証のノウハウを蓄積する。
- stdlib-onlyや単一ファイルをOffice機能全体に強制しない。
  python-pptxは必要な操作と互換性を確認して採用できる候補であり、
  現段階では依存に追加しない。
- openpyxlは導入しない。表データはCSV/TSVや利用可能な既存サービスで
  目的を満たせるか先に判断する。Excel固有の新規作成・編集は、
  それらで満たせない需要が具体化したものに絞る。

共通化候補は「対象・属性・変更前の条件・変更後の値・変更件数・検証結果」。
ドットのpaletteとOfficeの書式を同じ内部構造へ無理に統合せず、
まず各形式で小さく実証し、同じ規則が使える箇所を後から抽出する。
正規表現やMarkdown等の既存ツールも、契約が合う部分で再利用を検討する。

追加の参考画像では、python-pptxによるテキスト・色・リンク付き図形の作成、
スライド順序とページ番号の変更、変更前の図形情報をハッシュ化する例を確認した。
写真から読み取れるコードの参考であり、元PPTXの正常性を検証したものではない。
図形種別・位置・寸法・文字だけのハッシュでは色等の保持を確認できないため、
検証対象は実際の変更内容に応じて定義する。

### 写真入力の最初の到達点：Base64からドットグリッドへ

写真側の最初のゴールは、Base64で渡された画像を読み、指定した解像度の
ドットグリッドとして出力すること。圧縮率の改善やCSSでの表示は要件にしない。

Base64はバイナリを文字で受け渡す表現であり、画素や色の配列そのものではない。
JPEG/PNGのBase64文字列に任意の置換をしても、意図したドット化にはならない。
処理を次の段階に分ける。

1. Base64を検証・復号して、元の画像ファイルのbytesへ戻す。
2. 画像形式に対応したdecoderで幅・高さ・画素を取り出す。
3. 指定解像度または縮小率で代表色を求め、必要なら固定paletteへ割り当てる。
4. 色番号グリッドと配色をJSONへ出し、絵文字を確認用に使う。

第1段階はPython標準のbase64で扱えるが、第2段階のJPEG/PNG展開とは別である。
Pillowの採用は未決定とし、既存の利用可能なdecoderや共有ツールも確認する。
依存を避けるためにJPEG等のdecoderを独自実装する方針にはしない。
画素配列を直接受け取って第3段階以降を先に検証することもできるが、
その結果を写真のBase64入力対応済みとは呼ばない。

入力上限・画素数上限、不正Base64・未対応形式の扱いと、向き・縦横比・
透過の規則は実装時に定義する。外部URLの自動取得は必要としない。
CSSの読み取りに関する既存の横断資産は、必要になった時点で参照し、
この写真変換コアの必須依存にはしない。

一次資料：[Python base64](https://docs.python.org/3/library/base64.html)。

#### 試作実装（`photo_grid.py`、Python 3.11以上）

| 段階 | 規則 |
| --- | --- |
| Base64 | 生Base64または`data:<type>;base64,`。空白・改行は除去。英数字`+/`と末尾`=`2個まで以外、長さが4の倍数でない入力は拒否。復号後8 MiBまで |
| decode | adapter契約は`bytes -> (width, height, RGBA行のbytes)`。PNG署名なら`decode_png`（zlib+struct、CRC検査、8bit gray/gray+alpha/RGB/RGBA、非interlaceのみ）。それ以外は`decode_pillow`（Pillowがある場合のみ。EXIF向き補正あり）。上限4096×4096画素 |
| crop/fit | 既定`crop`は短辺に合わせた中央の正方形を切り出す。`contain`は縦横比を保って全体を収め、余白を透明にする。canvasは8/16/32/64/128 |
| 縮小 | 面積平均（端の画素は重なった面積で重み付け）。alphaで重み付けし、透明画素の色は混ぜない |
| 減色 | 既定はmedian cut（1〜16色、既定8色、同値時の選び方を固定）。`--palette`ではpixel_grid.pyの固定paletteの番号1〜4へ最近色（RGB二乗距離、同距離は小さい番号）で割り当てる |
| 透過 | 平均alphaが128未満のセルは色番号0（`#00000000`）。それ以外は不透明色として出力 |

入力形式：Base64（生・data URI）または画像ファイル。拡張子ではなく先頭bytesで判別する（`_sniff`）。
- PNG（8bit gray/gray+alpha/RGB/RGBA、非interlace）：標準ライブラリ（zlib＋struct）。
- palette・16bit・interlaceのPNG：標準decoderは拒否し、Pillowがあれば自動でPillowへ切り替える。
- JPEG/JPG・WebP：Pillowがある場合のみ（DCT・VP8/VP8Lの展開は標準ライブラリにない）。Pillowを
  開く形式を限定するため、他の形式がJPEG等を名乗っても読まない。WebPアニメーションは先頭フレーム。
- SVG（ベクター、描画器が必要）・GIF・BMP・TIFF・ICO・HEIC/AVIF：Pillowの有無に関係なく
  「… input is not supported」で拒否する。
形式ごとの理由と挙動はREADMEの表を参照。`tests/test_image_formats.py` が表の挙動を検証する。

#### PNG出力（`grid_png.py`）

`to_png(artifact, scale=1)` は同じgrid JSONから8bit RGBA・非interlace・filter 0・zlib level 9の
PNGを標準ライブラリ（zlib+struct）で書く。時刻・テキストchunkを入れないため同じ入力は同じbytes。
`scale`（1〜64）は整数倍の最近傍拡大で、出力は4096×4096画素まで。色番号0はそのRGBA（通常は透明）で書く。
`photo_grid.py`・`pixel_grid.py`の`--format png`（遅延import）または`grid_png.py`のCLIで使う。
標準PNG decoderでの読み戻しが元の色と一致することをテストで確認している。

#### Base64出力（可逆性）

`--format base64`（`photo_grid.py`・`pixel_grid.py`、`grid_png.to_base64`）は、`--format png`と
同じbytesをBase64で出す。`--data-uri`で`data:image/png;base64,`付き。`--scale`と`-o`に従う。
出力はそのまま`photo_grid.py`の入力にできる。

- scale 1で、同じ`--size`を指定して読み戻すと元のgrid（palette＋色番号）と一致する。
  pixel_grid.pyのgridは同じ`--palette`、photo_grid.pyのgridは`--colors`を元の不透明色数にする。
- scale>1のPNGは、元の`--size`を指定すれば同じgridに戻る（各セルがscale×scaleの同色ブロックのため）。
  異なる`--size`では別のgridになる。
- median cutの出力は、どのセルにも使われない色をpaletteから除く（色番号は詰め直す）。
  そのため photo_grid.py の出力は `--colors`=不透明色数で読み戻すと一致する。
- 外部で作ったgridは、色番号0が透明・不透明色がRGB昇順・全色使用・重複なしの場合に一致する。
  それ以外（0が透明でない、未使用色、半透明色alpha 1〜254）はセルの色は保てても番号やalphaは一致しない。
  非正方形や8/16/32/64/128以外の寸法のgridは、PNG/Base64には書けるがphoto_grid.pyの入力では
  正方形canvasへcropされるため同じgridには戻らない。

Base64入力の規則：標準アルファベットと`=`padding必須（URL-safeの`-_`・padding省略は拒否）。
空白・CRLF改行・先頭のBOMは無視。`data:`のschemeとtypeは大文字小文字を区別しない。
data URIのtypeは省略か`image/png`・`image/jpeg`・`image/jpg`・`image/webp`のみで、
復号したbytesの形式と一致しない場合はエラー（例：`data:text/plain;base64,`、`data:image/svg+xml;base64,`）。

#### SVG出力（`grid_svg.py`）

`to_svg(artifact, scale=8)` は `ironmate-pixel-grid/1` のJSON（pixel_grid.py・photo_grid.py共通）から
SVGを標準ライブラリだけで書く。Base64→decode→grid→SVGを1コマンドで行える
（`photo_grid.py --format svg [-o out.svg]`、既定はJSONのまま）。

- `viewBox`はグリッド単位、`--scale`（1〜64、既定8）はwidth/heightのみ変える。`shape-rendering="crispEdges"`。
- 同じ色の横方向の連続を1つの`<rect>`にまとめる（`--no-merge`で1セル1つ）。塗られる範囲は同じ。
- 色番号0とalpha 0の色は出力しない。`fill="#rrggbb"`、alpha<255は`fill-opacity`。
- metadataは`<title>`/`<desc>`にXMLエスケープして入れる。同じ入力なら同じSVG。
- WebP出力、PPTXネイティブ図形出力は行わない。

同じ入力・同じ指定なら同じJSONになる。乱数・ネットワークは使わない。
PNGのdecoderは対象を8bitの基本形式に絞った小さなadapterで、パレットPNG・16bit・
interlace・APNG・色空間chunk（gAMA/iCCP等）は扱わない（前3つは明示的にエラー）。
JPEG等のdecoderは独自実装せず、Pillowへ任せる方針を維持する。
Pillow版と標準版は同じadapter契約なので、後から差し替え・追加できる。

制限：ditherなし、縮小方式は面積平均のみ（BOX/LANCZOS等との比較は未実施）、
出力はJSON/SVG/PNG（WebP出力はなし）、背景除去・顔などの意味的補正なし。
標準版は純Pythonなので大きな画像は遅い（1000×1000で約1秒の目安）。
見た目の品質は評価していない。
