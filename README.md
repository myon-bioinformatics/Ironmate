# Ironmate

Pythonを中心に、文書・画像などの**内容や属性の変換・置換**を検証するプロジェクトです。
PPTXの文字・色・矢印属性の置換を今後の対象とし、画素／パレットに基づくドット表現を試作しています。
要件は [Issue #80](https://github.com/myon-bioinformatics/Ironmate/issues/80)、
ドット表現の試作は [PR #79](https://github.com/myon-bioinformatics/Ironmate/pull/79) で追跡します。
Markdown→PPTX変換と既存PPTXの属性編集CLIは試作実装済みです。写真変換は第1段階（Base64→色番号グリッド）のみ試作済みで、キャラクター部品合成は未実装です。実装済みのドット表現の範囲は次節を参照してください。

## PPTX変換・編集

MarkdownからPPTXを生成する入口は **`pptx_pipeline.py`** に統一しています。旧`marp_pptx.py`は削除済みで、互換CLIは提供しません。引数の構築には固定vendorの`vendor/cli_args.py`を使用します。

```sh
python pptx_pipeline.py slides.md -o slides.pptx
python pptx_pipeline.py --text '# タイトル' -o slides.pptx
printf '# タイトル\n' | python pptx_pipeline.py - -o slides.pptx
# MermaidのSVG事前変換を行う場合のみ追加:
python pptx_pipeline.py diagrams.md --mmdc node_modules/.bin/mmdc -o diagrams.pptx
```

Marp CLIは事前インストールが必要で、コマンドが勝手にNode/npmを導入することはありません。標準の変換はローカルファイル参照を許可せず、`--mmdc`を使う場合のみ、信頼できる入力を対象にローカル参照を有効化します。出力JSONには変換とPPTX検査の結果が入ります。

既存PPTXの文字・色・属性を変更する場合は、独立した`pptx_replace.py`を使用します。詳細は[試作契約・検証状況](docs/pptx-cli-prototype.md)を参照してください。

## ドット絵の試作候補

`pixel_grid.py`で、5種類の形（手続き生成）・10配色（色ID `C01`〜`C10`）・4加工を、
形ごとの範囲内の任意サイズ（奇数も可）で再現可能な色番号グリッドにします。
きれいに描けないサイズは生成せずエラーにします。

| 形 | 最小〜最大サイズ |
| --- | --- |
| triangle | 5〜256 |
| diamond | 9〜256 |
| cloud | 16〜256 |
| circle | 6〜256 |
| rock | 7〜256 |

```bash
python -S pixel_grid.py --mask cloud --palette C01 --effect shadow --size 23
python -S pixel_grid.py --mask circle --palette C02 --size 31 --format png --scale 8 > circle.png
```

[第1弾の契約・検証・今後の設計](docs/pixel-grid-prototype.md)。

`photo_grid.py`は、Base64（生の文字列または`data:image/...;base64,`）または画像ファイルを
読み、同じ`ironmate-pixel-grid/1`形式（固定RGBA＋色番号グリッド）にします。

| 入力形式（Base64包み・ファイルとも） | 標準ライブラリのみ | Pillowあり |
| --- | --- | --- |
| PNG（8bitのgray/gray+alpha/RGB/RGBA、非interlace） | 対応 | 対応（標準decoderを使用） |
| JPEG/JPG | 非対応（Pillowが必要というエラー） | 対応 |
| WebP | 非対応（Pillowが必要というエラー） | 対応 |
| SVG | 非対応（入力としては扱わない） | 非対応 |

| 出力形式（`--format`） | 実装 |
| --- | --- |
| JSON（既定） | 標準ライブラリ |
| SVG | 標準ライブラリ（`grid_svg.py`） |
| PNG | 標準ライブラリ（`grid_png.py`、8bit RGBA、整数倍の最近傍拡大） |
| Base64 | 標準ライブラリ（PNG出力と同じbytesをBase64化。`--data-uri`で`data:image/png;base64,...`） |

WebP出力・PPTXネイティブ図形出力はありません。SVGは出力専用です。

Pillowは必須依存ではありません。

```bash
base64 -w0 photo.png > photo.b64
python -S photo_grid.py photo.b64 --size 32 --colors 8
python photo_grid.py photo.b64 --size 16 --palette C01 --fit contain
python -S photo_grid.py photo.b64 --size 32 --format svg --scale 8 -o photo.svg
python -S pixel_grid.py --mask cloud --format svg > cloud.svg
python -S grid_svg.py grid.json -o grid.svg   # 既存のgrid JSONからSVG
python -S photo_grid.py photo.png --size 32 --format png --scale 4 -o dots.png
python -S pixel_grid.py --mask cloud --format png --scale 8 > cloud.png
python -S grid_png.py grid.json --scale 8 -o grid.png
python -S pixel_grid.py --mask cloud --format base64 --data-uri -o cloud.b64
python -S photo_grid.py cloud.b64 --size 16 --palette C01   # 元のgridに戻る
```

[写真入力の契約と制限](docs/pixel-grid-prototype.md#写真入力の最初の到達点base64からドットグリッドへ)。

## 責務

- 共通GitHub操作・vendor管理は [親リポジトリ](https://github.com/myon-bioinformatics/myon-bioinformatics) と [gh_identity](https://github.com/myon-bioinformatics/gh_identity) を参照します。
- 旧GitHubカタログ、MCPサーバー、repository metadata／diagnostics、成果物provenance生成の試作は廃止しました。すべての旧APIが移管先に互換実装されているという意味ではありません。
- source／niconico実装とテストの移管先は [mcp-toolcall-lab PR #108](https://github.com/myon-bioinformatics/mcp-toolcall-lab/pull/108) です。先に移管先をマージしてから、この削除をマージします。API／MCPの差分吸収の設計は同repo #107で扱います。
- `vendor/` と `vendor.lock.json` はconsumerの固定コピーです。共有ツール53ファイル（LICENSEを含む）を親の管理方式で登録し、固定ハッシュ検証を行います。
- `scripts/sync_vendor_provenance.py` は既存CIのvendor証跡をlockから投影する補助処理として残します。旧ルートの `provenance.py` とは別物です。

紹介・メタデータは [ポートフォリオ](https://myon-bioinformatics.github.io/#ironmate) に集約します。Ironmate専用のmetadata stub Pagesは廃止し、このrepoで公開する実動デモが必要になった時に再検討します。

詳しくは [整理とvendor調査](docs/cleanup-stage-two.md)、[vendor CI](docs/vendor-automation.md) を参照してください。

## ローカルテスト

```sh
python -m pip install -r tests/requirements.txt
git clone https://github.com/myon-bioinformatics/xprobe.git build/shared
git -C build/shared checkout 7e7015b2df69ad446b968f6fa49711b5b1dbdd3f
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.git .vendor-sync-tools
git -C .vendor-sync-tools checkout 974da5eb9593df652b132e4b0f1a679f67422566
python -m pytest -q -m 'not heavy'
```

xprobeと親のvendorツールはテスト用の別checkoutです。実行時依存として自動取得しません。
PPTX機能の実行には `python-pptx` が必要です。Marp変換時のみ別途インストール済みのMarp CLIが必要です。
