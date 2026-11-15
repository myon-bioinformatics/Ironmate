"""Local image composition studio and exact cell-average mosaic helpers (stdlib).

    python -S image_studio.py
    python -S image_studio.py --heatmap matrix.json -o scene.json
    python -S image_studio.py --render scene.json --format svg --scale 4 -o image.svg
    python -S image_studio.py --build-site build/site

The server serves only fixed public UI assets on loopback; it never accepts uploads
or writes files. Browser exports are explicit downloads. Existing grid tools own
PNG encoding; numeric source data is kept separate from its display colors.
The web editor runs without Python. Scene CLI rendering uses Node.js; PNG/Base64
also use installed Chrome through Node 26 built-in WebSocket (no runtime npm package).
"""
from __future__ import annotations

import argparse, base64, json, math, os, shutil, struct, subprocess, sys, tempfile
from functools import lru_cache; from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer; from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = 'ironmate-image-studio/1'
PALETTE = ('#440154', '#3B528B', '#21918C', '#5EC962', '#FDE725')


def heat_color(value, low, high, levels=0):
    """Viridis-like five-stop display scale; source value is never modified."""
    if value is None:
        return None
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (value, low, high)) or low > high:
        raise ValueError('finite value and ordered range required')
    if type(levels) is not int or (levels != 0 and not 2 <= levels <= 256):
        raise ValueError('levels must be 0 (continuous) or 2..256')
    t = 0.5 if high == low else max(0, min(1, (value - low) / (high - low)))
    if levels:
        t = math.floor(t * (levels - 1) + 0.5) / (levels - 1)
    p = t * (len(PALETTE) - 1)
    i = min(len(PALETTE) - 2, int(p))
    a, b = (bytes.fromhex(c[1:]) for c in PALETTE[i:i + 2])
    return '#' + ''.join(f'{math.floor(x + (y-x)*(p-i) + 0.5):02X}' for x, y in zip(a, b))


def heatmap_scene(source):
    """Import a numeric matrix or ONE Plotly heatmap trace; row zero is at top.

    This imports data, not Plotly layout/axis rendering. Keep source metadata so
    the scene is an editable composition, never a replacement research result.
    """
    if isinstance(source, list):
        trace = {'z': source}
    elif isinstance(source, dict) and isinstance(source.get('data'), list):
        traces = [t for t in source['data'] if isinstance(t, dict) and t.get('type') == 'heatmap']
        if len(traces) != 1:
            raise ValueError('exactly one heatmap trace required')
        trace = traces[0]
    else:
        trace = source
    if not isinstance(trace, dict):
        raise ValueError('matrix or heatmap object required')
    z = trace.get('z')
    if (not isinstance(z, list) or not z or not isinstance(z[0], list) or not z[0]
            or len(z) * len(z[0]) > 4096 or any(not isinstance(r, list) or len(r) != len(z[0]) for r in z)):
        raise ValueError('rectangular matrix of 1..4096 cells required')
    finite = [v for row in z for v in row if v is not None]
    def safe(v):
        if type(v) is int:
            return abs(v) <= 2**53-1
        return type(v) is float and math.isfinite(v) and (not v.is_integer() or abs(v) <= 2**53-1)
    if any(not safe(v) for v in finite):
        raise ValueError('finite JavaScript-safe numbers or null required')
    low, high = trace.get('zmin'), trace.get('zmax')
    low = min(finite, default=0) if low is None else low
    high = max(finite, default=1) if high is None else high
    if not safe(low) or not safe(high):
        raise ValueError('finite JavaScript-safe color range required')
    heat_color(low, low, high)
    x, y = trace.get('x', list(range(len(z[0])))), trace.get('y', list(range(len(z))))
    if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(z[0]) or len(y) != len(z):
        raise ValueError('axis label counts do not match matrix')
    return {'schema': SCHEMA, 'width': 1280, 'height': 720, 'background': '#FFFFFF',
            'layers': [{'id': 'heatmap', 'kind': 'heatmap', 'name': 'Heatmap', 'x': 80, 'y': 90,
                        'w': 1120, 'h': 520, 'rotation': 0, 'opacity': 1,
                        'z': z, 'xlabels': x, 'ylabels': y, 'low': low, 'high': high,
                        'levels': 0, 'labels': True}], 'source': source}


def mosaic(artifact, cell=8, levels=256):
    """Area means of original RGBA blocks, alpha-weighted RGB, partial edges kept.

    Return a full-size indexed grid. Repeat calls on the ORIGINAL to change the
    resolution; mosaicing a mosaic does not restore lost information.
    """
    from grid_tools import canonical
    art = canonical(artifact)
    if type(cell) is not int or not 1 <= cell <= 512 or type(levels) is not int or not 2 <= levels <= 256:
        raise ValueError('cell 1..512, levels 2..256 required')
    colors = [tuple(bytes.fromhex(c[1:])) for c in art['colors']]
    width, height = art['width'], art['height']
    if width * height > 4194304:
        raise ValueError('mosaic input must be at most 4MP')
    pixels = [[0] * width for _ in range(height)]
    palette, index = [], {}
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            block = [colors[art['pixels'][j][i]] for j in range(y, min(y+cell, height)) for i in range(x, min(x+cell, width))]
            alpha = sum(p[3] for p in block)
            rgba = [math.floor(sum(p[c]*p[3] for p in block)/alpha + 0.5) if alpha else 0 for c in range(3)]
            rgba = [math.floor(math.floor(v/255*(levels-1)+0.5)/(levels-1)*255+0.5) for v in rgba]
            rgba.append(math.floor(alpha/len(block)+0.5))
            color = '#' + ''.join(f'{v:02X}' for v in rgba)
            if color not in index:
                index[color] = len(palette)
                palette.append(color)
            for j in range(y, min(y+cell, height)):
                pixels[j][x:min(x+cell, width)] = [index[color]] * min(cell, width-x)
    return {'schema': 'ironmate-pixel-grid/1', 'width': width, 'height': height, 'colors': palette, 'pixels': pixels}


_SLIDES_PANEL_HTML = """\
<section class="slide-controls" aria-label="スライド編集">
  <div class="slide-toolbar">
    <strong>スライド作成</strong
    ><select id="slide-select" aria-label="スライド"></select
    ><button id="slide-add">＋ 白紙</button
    ><button id="slide-duplicate">スライド複製</button
    ><button id="slide-up">前へ移動</button
    ><button id="slide-down">後へ移動</button
    ><button id="slide-delete">スライド削除</button
    ><button id="deck-save">全スライドJSON保存</button
    ><label class="button"
      >全スライドを開く<input
        id="deck-open"
        type="file"
        accept=".json,application/json" /></label
    ><button id="deck-pptx" class="primary">PPTXを書き出す</button>
  </div>
  <details open>
    <summary>タイトル・本文とフォント見本</summary>
    <div class="slide-template">
      <label
        >タイトル<input
          id="slide-title"
          placeholder="タイトルを入力"
          value="スライドのタイトル" /></label
      ><label
        >本文<textarea
          id="slide-body"
          rows="2"
          placeholder="本文を入力。幅で自動折り返し。改行も使用できます。"
        >
ここに本文を入力します。
テキストはPowerPointでも編集できます。</textarea></label
      ><label
        >文字の見本<select id="font-sample">
          <option value="">見本を選ぶ</option>
          <option value="日本語の文章と ABC abc 0123456789">
            日本語・英数字
          </option>
          <option value="あいうえお　アイウエオ　漢字の見本">
            ひらがな・カタカナ・漢字
          </option>
          <option value="The quick brown fox jumps over the lazy dog.">
            英文
          </option>
        </select></label
      ><button id="slide-template">タイトル＋本文を追加</button
      ><button id="slide-arrow">編集できる矢印を追加</button
      ><button id="slide-bold">選択した文字の太字を切替</button>
    </div>
  </details>
  <p id="deck-status" role="status">
    文字・図形をImage
    Studioと同じ操作で配置できます。全スライドは同じ寸法で作成します。
  </p>
  <p class="slide-hint">
    文字はボックス幅で折り返します。文字サイズは自動縮小しません。長文では高さ・位置も調整してください。
    最大20枚・JSON合計32MiB。テキスト・通常図形・三角の矢羽根はPPTXの編集可能な要素になります。時計・ヒートマップ・単色スタンプ・🔰の矢印は、レイヤー単位の画像として保存します。フォントは表示先の端末に依存します。
  </p>
</section>
"""


_TOOLS_HTML = """\
<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; manifest-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; connect-src 'none'; object-src 'none'; base-uri 'none'"
    />
    <link rel="manifest" href="../brand/manifest.webmanifest" />
    <link rel="apple-touch-icon" sizes="180x180" href="../brand/apple-touch-icon.png" />
    <meta name="theme-color" content="#003D32" />
    <meta name="apple-mobile-web-app-title" content="Ironmate" />
    <title>Ironmate — ブラウザツール</title>
    <link rel="icon" href="../brand/favicon.ico" sizes="16x16 32x32 48x48" />
    <link rel="icon" type="image/svg+xml" href="../brand/icon.svg" sizes="any" />
    <link rel="stylesheet" href="../style.css" />
    <script defer src="catalog.js"></script>
    <script defer src="../studio.js"></script>
  </head>
  <body class="ui-elements" data-ui-theme="green" data-page="tools">
    <header>
      <a class="brand" href="../"><img src="../brand/heatmap.svg" width="48" height="48" alt="I’m — 🔰がアポストロフィのIronmateロゴ" /> IRONMATE</a>
      <nav aria-label="サイト">
        <a href="../brand/">ロゴ6案 ↗</a><a href="../">Image Studio ↗</a
        ><a href="https://myon-bioinformatics.github.io/#ironmate"
          >ポートフォリオ ↗</a
        ><a href="https://github.com/myon-bioinformatics/Ironmate">ソース ↗</a>
      </nav>
    </header>
    <main>
      <p class="eyebrow">BROWSER WORKBENCH / 02</p>
      <h1>素材をつくる。<br />並べて、持ち出す。</h1>
      <p class="lead">
        インストール不要。画像もJSONも、このブラウザの中で処理します。
      </p>
      <img class="brand-hero" src="../brand/hero.svg" width="560" height="160" alt="Ironmate — I’mとヒートマップのセルを組み合わせたロゴ" />
      <div class="jump">
        <a href="#pixels">01 ドット絵</a><a href="#digest">02 画像一覧</a
        ><a href="#capacity">03 Base64容量</a><a href="#features">できること</a>
      </div>
      <p id="message" role="status" aria-live="polite">準備しています…</p>
      <section id="pixels">
        <div class="section-heading">
          <span>01 / PIXEL GRID</span>
          <h2>色番号から、ドット絵へ。</h2>
        </div>
        <div class="workspace">
          <div class="controls">
            <label>形<select id="mask"></select></label>
            <div class="pair">
              <label>元サイズ<select id="size"></select></label
              ><label>加工<select id="effect"></select></label>
            </div>
            <label>配色ID<select id="palette"></select></label
            ><button id="generate" class="primary">プリセットから生成</button>
            <p class="hint">
              Python版でビルドした5形・4加工・10配色。元サイズは16 / 23 / 31 /
              32 / 64。配色IDは色そのものとは独立した識別子です。
            </p>
            <label class="file"
              >グリッドJSONを開く<input
                id="grid-file"
                type="file"
                accept=".json,application/json"
            /></label>
            <div class="pair">
              <label
                >幅<input
                  id="width"
                  type="number"
                  min="1"
                  max="256"
                  value="32" /></label
              ><label
                >高さ<input
                  id="height"
                  type="number"
                  min="1"
                  max="256"
                  value="32"
              /></label>
            </div>
            <button id="resize">最近傍でサイズ変更</button>
            <p class="hint">
              縮小では細部が失われます。配色変更は5役割のグリッドのみ。
            </p>
            <button id="recolor">選択した配色IDを適用</button>
            <div class="pair">
              <label>描く色番号<select id="ink"></select></label
              ><label
                >出力倍率<select id="scale">
                  <option>1</option>
                  <option>2</option>
                  <option selected>8</option>
                  <option>16</option>
                </select></label
              >
            </div>
            <button id="undo-grid">ひとつ戻す</button>
          </div>
          <div class="preview">
            <canvas
              id="grid"
              width="32"
              height="32"
              aria-label="ドット絵。クリックすると選択した色番号で描画"
              tabindex="0"
            ></canvas>
            <p id="grid-info"></p>
            <div class="exports">
              <button id="grid-json">JSON保存</button
              ><button id="grid-svg">SVG</button
              ><button id="grid-png">PNG</button
              ><button id="grid-base64">Base64</button>
            </div>
            <label
              >PNG data URI<textarea
                id="base64-output"
                rows="3"
                readonly
              ></textarea>
            </label>
            <p class="hint">
              PNGは色表・寸法のironmateメタデータ付き。JSONは色番号を保持します。SVG・PNGは同じセルを描画しますが、Python版との圧縮byte一致は対象外です。
            </p>
          </div>
        </div>
      </section>
      <section id="digest">
        <div class="section-heading">
          <span>02 / IMAGE DIGEST</span>
          <h2>比較のための、一枚。</h2>
        </div>
        <p>
          最大20枚のPNG / JPEG /
          WebPを選び、並べたPNGと、画像を埋め込んだHTMLを保存できます。
        </p>
        <div class="digest-options">
          <label class="file"
            >画像を選ぶ<input
              id="images"
              type="file"
              multiple
              accept="image/png,image/jpeg,image/webp" /></label
          ><label
            >列数<select id="columns">
              <option>2</option>
              <option selected>3</option>
              <option>4</option>
              <option>5</option>
            </select></label
          ><button id="digest-png" disabled>一覧PNG</button
          ><button id="digest-html" disabled>一覧HTML</button>
        </div>
        <p class="hint">
          1枚8MiB、合計32MiB、1画像4MPまで。表示用に長辺512px以下へ縮小します。ファイル名だけをラベルとして使い、合否・MAE等は計算しません。
        </p>
        <div id="image-list" class="image-list"></div>
      </section>
      <section id="capacity">
        <div class="section-heading">
          <span>03 / BASE64</span>
          <h2>送る前に、容量を確認。</h2>
        </div>
        <label
          >任意のファイルを選ぶ<input id="capacity-file" type="file"
        /></label>
        <p id="capacity-result">
          ファイル本体は読み込まず、サイズから標準Base64文字数を計算します。
        </p>
      </section>
      <section id="features">
        <div class="section-heading">
          <span>CAPABILITIES</span>
          <h2>用途に合わせた入口。</h2>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>機能</th>
                <th>ブラウザで利用</th>
                <th>ローカルCLIで利用</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>図形・文字・画像・時計・矢印・ヒートマップ・モザイク</td>
                <td><a href="../">Image Studio</a></td>
                <td>image_studio.py</td>
              </tr>
              <tr>
                <td>レイヤー・履歴・クリップボード・PNG/SVG/JSON/Base64</td>
                <td><a href="../">Image Studio</a></td>
                <td>image_studio.py / studio_ingress.py</td>
              </tr>
              <tr>
                <td>ドット絵・配色・最近傍拡縮</td>
                <td><a href="#pixels">この画面</a>（プリセットサイズ）</td>
                <td>pixel_grid.py / grid_tools.py（任意の対応サイズ）</td>
              </tr>
              <tr>
                <td>画像一覧</td>
                <td><a href="#digest">この画面</a>（画像・名前・一覧）</td>
                <td>
                  image_digest.py / browser_matrix.py（行列・測定レポート）
                </td>
              </tr>
              <tr>
                <td>Base64容量</td>
                <td><a href="#capacity">正確な文字数</a></td>
                <td>ironlib/size_estimate.py（縮小候補の検証も可）</td>
              </tr>
              <tr>
                <td>PPTX作成・属性置換・PDFプレビュー</td>
                <td><a href="../slides/">複数スライドのPPTX作成</a></td>
                <td>pptx_pipeline.py / pptx_replace.py / ironlib/pptx_preview.py</td>
              </tr>
              <tr>
                <td>GitHub・MCP・外部API</td>
                <td>
                  <a href="https://myon-bioinformatics.github.io/"
                    >ポートフォリオの関連プロジェクト</a
                  >
                </td>
                <td>認証やサーバーが必要な処理はCLIで実行</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="hint">
          GitHub
          Pagesは静的配信です。Docker・Python・Nodeの処理はビルド時または手元の環境で実行します。入力画像や作業JSONは公開ビルドに入りません。
        </p>
      </section>
    </main>
    <footer>
      IRONMATE /
      ブラウザ内の作業は自動保存されません。持ち出すときはダウンロードしてください。
    </footer>
  </body>
</html>
"""

_BRAND_HTML = """\
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; img-src 'self'; manifest-src 'self'; base-uri 'none'; object-src 'none'" />
  <title>Ironmate — ロゴ6案</title>
  <link rel="stylesheet" href="../style.css" />
  <link rel="icon" type="image/svg+xml" href="icon.svg" sizes="any" />
  <link rel="icon" href="favicon.ico" sizes="16x16 32x32 48x48" />
  <link rel="manifest" href="manifest.webmanifest" />
  <link rel="apple-touch-icon" sizes="180x180" href="apple-touch-icon.png" />
  <meta name="theme-color" content="#003D32" />
</head>
<body class="ui-elements" data-ui-theme="green" data-page="brand">
  <header><img src="gameboy.svg" width="64" height="64" alt="GameBoy StyleのIronmateロゴ" /><div><a href="../">Ironmate</a><p>ロゴ6案 / 暫定配置</p></div></header>
  <main>
    <h1>同じI’m、6つの表情。</h1>
    <p>初心者マークをアポストロフィに。正式版は決めず、用途ごとに使い分けます。</p>
    <div class="designs">
      <section><img src="mono.svg" alt="Pixel Mono" width="192" height="192" /><h2>① Pixel Mono</h2><p>白黒資料・印刷向け</p><a href="mono.svg" download>SVGを保存</a></section>
      <section><img src="dark-green.svg" alt="Dark Green" width="192" height="192" /><h2>② Dark Green</h2><p>GitHub向け素材・favicon</p><a href="dark-green.svg" download>SVGを保存</a></section>
      <section><img src="famicom.svg" alt="Famicom Retro" width="192" height="192" /><h2>③ Famicom Retro</h2><p>READMEの先頭</p><a href="famicom.svg" download>SVGを保存</a></section>
      <section><img src="gameboy.svg" alt="GameBoy Style" width="192" height="192" /><h2>④ GameBoy Style</h2><p>このギャラリー・特設ページ</p><a href="gameboy.svg" download>SVGを保存</a></section>
      <section><img src="heatmap.svg" alt="Heatmap Pixel" width="192" height="192" /><h2>⑤ Heatmap Pixel</h2><p>Web画面・Hero</p><a href="heatmap.svg" download>SVGを保存</a></section>
      <section><img src="pixel-3d.svg" alt="Pixel 3D" width="192" height="192" /><h2>⑥ Pixel 3D</h2><p>ホーム画面・ランチャー</p><a href="app-512.png" download>PNGを保存</a></section>
    </div>
    <section class="home"><h2>ホーム画面に追加する</h2><p>Androidはブラウザのメニュー、iPhoneは共有メニューの「ホーム画面に追加」から登録できます。⑥をアイコンに指定しています。表示や追加手順は端末・ブラウザによって異なります。</p><a href="../">Image Studio</a> / <a href="../slides/">Slide Studio</a> / <a href="../tools/">ドット絵・画像一覧</a></section>
    <div class="print-logo"><img src="mono.svg" width="128" height="128" alt="白黒印刷用Ironmateロゴ" /><p>Ironmate — I’m</p></div>
  </main>
</body>
</html>
"""


def public_assets():
    """Explicit publication allowlist; no user scenes, globbing, or local images."""
    from ironlib.studio_bundle import STUDIO_HTML, STUDIO_JS, STYLE_CSS
    names = ('brand/mono.svg', 'brand/dark-green.svg',
             'brand/famicom.svg', 'brand/gameboy.svg', 'brand/pixel-3d.svg',
             'brand/manifest.webmanifest', 'brand/apple-touch-icon.png', 'brand/app-192.png',
             'brand/app-512.png', 'brand/app-maskable-512.png',
             'brand/icon.svg', 'brand/heatmap.svg', 'brand/hero.svg', 'brand/favicon.ico', 'brand/favicon-16.png',
             'brand/favicon-32.png', 'brand/favicon-48.png', 'brand/icon-192.png',
             'brand/example-demo.gif', 'brand/example-stamp-demo.gif')
    assets = {name: (ROOT / 'studio' / name).read_bytes() for name in names}
    assets['index.html'] = STUDIO_HTML.encode('utf-8')
    assets['studio.js'] = STUDIO_JS.encode('utf-8')
    assets['style.css'] = STYLE_CSS.encode('utf-8')
    from scripts.pages_catalog import catalog_script
    assets['tools/catalog.js'] = catalog_script()
    assets['tools/index.html'] = _TOOLS_HTML.encode('utf-8')
    assets['brand/index.html'] = _BRAND_HTML.encode('utf-8')
    page = assets['index.html'].decode('utf-8')
    for name in ('style.css', 'studio.js', 'brand/icon.svg', 'brand/heatmap.svg', 'brand/favicon.ico',
                 'brand/manifest.webmanifest', 'brand/apple-touch-icon.png',
                 'brand/example-demo.gif', 'brand/example-stamp-demo.gif'):
        page = page.replace('"' + name + '"', '"../' + name + '"')
    page = page.replace('href="tools/"', 'href="../tools/"')
    page = page.replace('<a href="slides/">スライド・PPTX作成 ↗</a>', '<a href="../">Image Studio ↗</a>')
    page = page.replace('<body class="ui-elements" data-ui-theme="green" data-page="studio">', '<body class="ui-elements" data-ui-theme="green" data-page="studio slides" data-mode="slides">').replace('画像にする。', 'スライドにする。')
    page = page.replace('IMAGE STUDIO / 01', 'SLIDE STUDIO / 03').replace('Ironmate — Image Studio', 'Ironmate — Slide Studio')
    page = page.replace('</header>', '</header>' + _SLIDES_PANEL_HTML)
    assets['slides/index.html'] = page.encode('utf-8')
    return assets


def build_site(directory):
    """Publish the allowlisted browser assets and generated procedural presets."""
    directory = Path(directory)
    payloads = public_assets()
    if directory.is_symlink() or (directory.exists() and (not directory.is_dir() or any(directory.iterdir()))):
        raise FileExistsError('site output must be a new or empty directory')
    directory.mkdir(parents=True, exist_ok=True)
    from ironlib.grid_output import write_output
    for name, payload in payloads.items():
        (directory / name).parent.mkdir(parents=True, exist_ok=True)
        write_output(str(directory / name), payload)
    write_output(str(directory / '.nojekyll'), b'')
    return directory


def _node_scene(scene, mode='svg', scale=1):
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required for scene SVG rendering; it is not auto-installed')
    run = subprocess.run([node, str(ROOT / 'studio' / 'render.cjs')],
                         input=json.dumps({'scene': scene, 'mode': mode, 'scale': scale}, allow_nan=False),
                         text=True, capture_output=True, timeout=30)
    if run.returncode:
        raise ValueError(run.stderr.strip() or 'scene rendering failed')
    return run.stdout


def _processed_scene(scene):
    scene = json.loads(_node_scene(scene, 'validate'))
    for layer in scene['layers']:
        if layer['kind'] != 'image' or (layer['cell'] == 1 and layer['levels'] == 256):
            continue
        # Use original pixel dimensions; don't auto-infer a dot-art cell scale.
        from photo_grid import decode_png
        from ironlib.grid_output import to_png
        width, height, rows = decode_png(base64.b64decode(layer['src'].split(',', 1)[1], validate=True), max_pixels=4194304)
        palette, indexes, pixels = [], {}, []
        for row in rows:
            line = []
            for x in range(width):
                color = '#' + bytes(row[x*4:x*4+4]).hex().upper()
                if color not in indexes:
                    indexes[color] = len(palette)
                    palette.append(color)
                line.append(indexes[color])
            pixels.append(line)
        art = {'schema': 'ironmate-pixel-grid/1', 'width': width, 'height': height, 'colors': palette, 'pixels': pixels}
        data = to_png(mosaic(art, layer['cell'], layer['levels']))
        layer['src'] = 'data:image/png;base64,' + base64.b64encode(data).decode()
    return scene


def _find_chrome(chrome=None):
    candidates = [chrome or os.environ.get('CHROME'), 'google-chrome', 'chromium', 'chromium-browser', 'chrome',
                  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for key in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if os.environ.get(key):
            candidates.append(str(Path(os.environ[key]) / 'Google/Chrome/Application/chrome.exe'))
    for candidate in filter(None, candidates):
        executable = shutil.which(candidate)
        if executable:
            return executable
    raise RuntimeError('PNG/Base64 needs local Chrome/Chromium; use --chrome PATH (SVG needs Node.js only)')


def render_scene(scene, format='svg', scale=1, chrome=None, data_uri=False):
    """CPU-only SVG re-render; PNG uses installed headless Chrome, no GPU/AI API.

    The original scene is untouched. SVG remains vector; raster images can only
    interpolate their existing samples. Fonts are supplied by the host system.
    """
    if format not in ('svg', 'png', 'base64'):
        raise ValueError('format must be svg, png or base64')
    processed = _processed_scene(scene)
    svg = _node_scene(processed, scale=scale).encode()
    if format == 'svg':
        return svg
    return _png_output(raster_svg(svg, chrome=chrome), format, data_uri)


def _png_output(png, format='png', data_uri=False):
    if format == 'png':
        return png
    if len(png) > 32*1024*1024:
        raise ValueError('Flutter clipboard PNG must be at most 32MiB; reduce output scale')
    return (('data:image/png;base64,' if data_uri else '') + base64.b64encode(png).decode()).encode()


def raster_svg(svg, *, chrome=None):
    """Rasterize trusted, locally generated SVG using the Studio Chrome backend.

    This is not an arbitrary/untrusted SVG import API. Callers validate their
    source and dimensions; remote HTTP(S) resources are blocked by raster.cjs.
    """
    from xml.etree import ElementTree
    root = ElementTree.fromstring(svg)
    width, height = int(root.attrib['width']), int(root.attrib['height'])
    if not (1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= 16777216):
        raise ValueError('output must be each side <=8192px and <=16MP')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('PNG export requires Node.js 26 or newer')
    with tempfile.TemporaryDirectory(prefix='ironmate-studio-render-') as temp:
        directory = Path(temp)
        html = directory / 'render.html'
        html.write_bytes(b'<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0;overflow:hidden}svg{display:block}</style>' + svg)
        command = [node, str(ROOT / 'studio' / 'raster.cjs'), _find_chrome(chrome),
                   str(html), str(directory / 'profile'), str(width), str(height)]
        run = subprocess.run(command, capture_output=True, timeout=40)
        if run.returncode:
            raise RuntimeError('Chrome PNG render failed: ' + run.stderr.decode(errors='replace')[-1000:])
        png = run.stdout
        if len(png) < 24 or png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (width, height):
            raise RuntimeError('Chrome returned unexpected PNG dimensions')
    if len(png) > 32*1024*1024:
        raise ValueError('PNG must be at most 32MiB; reduce output scale')
    return png



@lru_cache(maxsize=1)
def cached_public_assets():
    return public_assets()


class StudioHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        assets = cached_public_assets()
        route = self.path.split('?', 1)[0]
        filename = {'/': 'index.html', '/tools/': 'tools/index.html', '/slides/': 'slides/index.html', '/brand/': 'brand/index.html'}.get(route, route.lstrip('/'))
        if filename not in assets:
            self.send_error(404)
            return
        mime = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
                '.svg': 'image/svg+xml', '.png': 'image/png', '.gif': 'image/gif', '.ico': 'image/x-icon', '.webmanifest': 'application/manifest+json'}[Path(filename).suffix]
        payload = assets[filename]
        self.send_response(200)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if Path(filename).suffix in ('.html', '.js', '.css', '.svg') else ''))
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; manifest-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--port', type=int, default=8765)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--heatmap', type=Path)
    mode.add_argument('--render', type=Path, help='scene JSON -> SVG/PNG/Base64')
    mode.add_argument('--build-site', type=Path, help='write standalone GitHub Pages assets')
    p.add_argument('--format', choices=('svg', 'png', 'base64'), default='svg')
    p.add_argument('--scale', type=float, default=1)
    p.add_argument('--chrome', help='installed Chrome/Chromium executable')
    p.add_argument('--data-uri', action='store_true', help='prefix Base64 with data:image/png;base64,')
    p.add_argument('-o', '--output', type=Path)
    p.add_argument('--force', action='store_true')
    p.add_argument('--json', action='store_true',
                   help='on a fixable failure, write one JSON object to stderr; success output is unchanged')
    args = p.parse_args(argv)
    try:
        return _run_studio(p, args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        from ironlib.ironmate_cli import emit_error
        return emit_error('image_studio.py', exc, json_mode=args.json)


def _run_studio(p, args):
    if args.build_site:
        print(build_site(args.build_site))
        return 0
    if args.render:
        data = render_scene(json.loads(args.render.read_text(encoding='utf-8')), args.format, args.scale, args.chrome, args.data_uri)
        if args.output:
            from ironlib.grid_output import write_output
            write_output(str(args.output), data, args.force)
        else:
            sys.stdout.buffer.write(data)
        return 0
    if args.heatmap:
        if not args.output:
            p.error('--heatmap needs -o scene.json')
        from ironlib.grid_output import write_output
        write_output(str(args.output), json.dumps(heatmap_scene(json.loads(args.heatmap.read_text(encoding='utf-8'))), ensure_ascii=False, allow_nan=False).encode(), args.force)
        return 0
    if not 0 <= args.port <= 65535:
        p.error('port must be 0..65535')
    with ThreadingHTTPServer(('127.0.0.1', args.port), StudioHandler) as server:
        print(f'Ironmate Studio: http://127.0.0.1:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
