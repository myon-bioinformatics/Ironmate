"""Bundled Studio HTML, CSS, and browser JS (pure stdlib, served in-memory or written at build time)."""

PIXEL_EDITOR_HTML = r"""      <section id="pixels">
        <div class="section-heading">
          <h2>ドット絵</h2>
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
              形・サイズ・加工・配色を選んで生成します。
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
              JSONは色番号を、PNGは色表と寸法を保持します。
            </p>
          </div>
        </div>
      </section>"""

STUDIO_PIXEL_PANEL = r"""        <details id="pixel-editor">
          <summary>▦ ドット絵</summary>
""" + PIXEL_EDITOR_HTML + r"""
          <button id="place-grid">画像にレイヤーとして追加</button>
          <p id="pixel-status" role="status"></p>
        </details>"""

STUDIO_HTML = r"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; manifest-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; font-src 'self'; connect-src 'none'; object-src 'none'; base-uri 'none'"
    />
    <link rel="manifest" href="brand/manifest.webmanifest" />
    <link rel="apple-touch-icon" sizes="180x180" href="brand/apple-touch-icon.png" />
    <meta name="theme-color" content="#003D32" />
    <meta name="apple-mobile-web-app-title" content="Ironmate" />
    <title>Ironmate — Image Studio</title>
    <link rel="icon" href="brand/favicon.ico" sizes="16x16 32x32 48x48" />
    <link rel="icon" type="image/svg+xml" href="brand/icon.svg" sizes="any" />
    <link rel="stylesheet" href="style.css" />
    <script defer src="studio.js"></script>
  </head>
  <body class="ui-elements" data-ui-theme="green" data-page="studio">
    <header id="studio-head">
      <div class="brand"><img src="brand/heatmap.svg" width="48" height="48" alt="I’m — 🔰がアポストロフィのIronmateロゴ" /><div>IRONMATE <span>画像編集</span></div></div>
      <div class="top-actions">
        <details id="studios">
          <summary data-ui-word="工房一覧" title="工房一覧" aria-label="工房一覧">🏭</summary>
          <a href="slides/">スライド・PPTX作成 ↗</a>
          <a href="tools/#composition">🎵 作曲 ↗</a>
          <a href="tools/">画像一覧・素材 ↗</a>
          <a href="https://myon-bioinformatics.github.io/#ironmate">🏠 ポートフォリオ ↗</a>
          <a href="https://github.com/myon-bioinformatics/Ironmate">🐙 GitHub リポジトリ ↗</a>
        </details>
      </div>
    </header>
    <main>
      <aside class="tools">
        <h1>画像を編集</h1>
        <p class="hint">
          ツールを選び、キャンバスを押して配置します。
        </p>
        <!-- 🧰 toolbar: studio_toolbar("image") -->
""" + STUDIO_PIXEL_PANEL + r"""
        <div id="keyboard-input" hidden>
          <button id="keyboard-focus">⌨ ほかの文字を入力</button>
          <p class="hint">Windows は Win + .、Mac は Control + Command + Space。スマホはキーボードの絵文字キーから。顔文字の入力・貼り付けもできます。</p>
        </div>
        <label
          >T 文字列<textarea id="text" rows="2" placeholder="文字列 😊 (・∀・)"></textarea
        ></label>
        <label
          >✦ スタンプ<textarea id="stamp-text" rows="1" placeholder="済 ✨ (｡•̀ᴗ-)✧"></textarea
        ></label>
        <div class="two">
          <label>絵文字<input id="emoji-text" placeholder="😊" /></label
          ><label>顔文字<input id="kaomoji-text" placeholder="(・∀・)" /></label>
        </div>
        <label
          >◷ 時計の時刻<input id="clock-time" type="time" value="10:10"
        /></label>
        <div class="two">
          <label>塗り<input id="fill" type="color" value="#18a7a1" /></label
          ><label>線<input id="stroke" type="color" value="#183c42" /></label>
        </div>
        <label class="check"
          ><input id="outline" type="checkbox" />枠線だけにする</label
        >
        <button id="custom" class="wide">選択したレイヤーをスタンプに</button>
        <p id="stamp-note" class="hint">
          選択したレイヤーを再利用できます。
        </p>
        <div class="section">
          <a href="https://myon-bioinformatics.github.io/tools/heatmap/">ヒートマップを作成（DRAgoWing）</a>
          <p class="hint">作成したシーンJSONは「開く」で読み込めます。</p>
        </div>
      </aside>
      <section class="workspace">
        <div class="canvas-heading">
          <div>
            <h2>キャンバス</h2>
          </div>
          <span id="size-note">1280 × 720</span>
        </div>
        <div
          id="board"
          class="board"
          tabindex="0"
          aria-label="画像編集キャンバス"
        ></div>
        <div class="canvas-footer">
          <span id="status" role="status">準備できました。</span
          ><span>ドラッグで移動 / 右下の点で拡縮</span>
        </div>
        <div class="canvas-settings">
          <button id="blank">＋ 新しいキャンバス</button
          ><label
            >背景<input id="background" type="color" value="#f8f7f2" /></label
          ><label class="check"
            ><input id="transparent" type="checkbox" />透明</label
          ><label
            >幅<input
              id="canvas-width"
              type="number"
              value="1280"
              min="64"
              max="4096" /></label
          ><label
            >高さ<input
              id="canvas-height"
              type="number"
              value="720"
              min="64"
              max="4096" /></label
          ><button id="canvas-size">適用</button>
        </div>
        <div class="note">
          再編集用にはJSONを保存してください。
        </div>
        <details id="workspace-history">
          <summary>作業履歴（最大40状態）</summary>
          <ol id="history-list" aria-label="作業履歴"></ol>
          <button id="trim-history">現在の状態だけ残す</button>
          <p class="hint">履歴を整理すると過去の状態へ戻せなくなります。現在の画像・レイヤーは保持します。</p>
          <p class="hint">履歴JSONは画像データを含む場合があります。共有時は内容を確認してください。</p>
        </details>
      </section>
      <aside class="inspector">
        <p class="eyebrow">レイヤー</p>
        <div id="layers" class="layers"></div>
        <div class="section">
          <h2 id="selection">レイヤーを選択</h2>
          <label
            >✏️ 編集<textarea id="edit-text" rows="2" placeholder="選んだ文字を後から変更"></textarea
          ></label>
          <div class="two">
            <label class="check"><input id="bold" type="checkbox" />太字</label
            ><label class="check"><input id="italic" type="checkbox" />斜体</label
            ><label>塗り<input id="edit-fill" type="color" /></label
            ><label>線<input id="edit-stroke" type="color" /></label
            ><label
              >図形<select id="edit-shape">
                <option value="rect">▭ 四角</option>
                <option value="ellipse">◯ 丸</option>
                <option value="triangle">△ 三角</option>
              </select></label
            ><label>時刻<input id="edit-time" type="time" /></label>
          </div>
          <button id="apply-text" class="wide" data-ui-word="編集を適用" title="編集を適用" aria-label="編集を適用">✏️</button>
          <div class="two">
            <label>X<input id="x" type="number" /></label
            ><label>Y<input id="y" type="number" /></label
            ><label>幅<input id="w" type="number" min="1" /></label
            ><label>高さ<input id="h" type="number" min="1" /></label>
          </div>
          <label
            >角度<input
              id="rotation"
              type="range"
              min="-180"
              max="180"
              value="0" /></label
          ><label
            >不透明度<input
              id="opacity"
              type="range"
              min="0"
              max="1"
              step="0.05"
              value="1" /></label
          ><label
            >文字サイズ<input
              id="font-size"
              type="number"
              min="4"
              max="512"
              value="48" /></label
          ><label
            >文字の配置<select id="font-family">
              <option value="sans">標準</option>
              <option value="mono">等幅（ASCIIアート・顔文字）</option>
            </select></label
          >
          <label class="check"
            ><input
              id="monochrome"
              type="checkbox"
              checked
            />文字・絵文字・画像を単色で描く</label
          >
          <label
            >矢羽根の形<select id="arrow-style">
              <option value="beginner">🔰を黒にする</option>
              <option value="triangle">三角形</option>
            </select></label
          >
          <label
            >矢羽根の位置<select id="arrow-placement">
              <option value="tip">先端</option>
              <option value="middle">中央（PPTXと同じ）</option>
            </select></label
          >
          <label
            >画像の拡大<select id="sampling">
              <option value="pixelated">ドットを保持</option>
              <option value="smooth">なめらかに補間</option>
            </select></label
          >
        </div>
        <div class="section">
          <p class="eyebrow">解像度</p>
          <label
            >モザイクのセル幅 <output id="cell-value">1 px</output
            ><input id="cell" type="range" min="1" max="128" value="1" /></label
          ><label
            >色の段階 <output id="levels-value">256</output
            ><input
              id="levels"
              type="range"
              min="2"
              max="256"
              value="256" /></label
          ><button id="continuous" class="wide">ヒートマップを連続色に</button
          ><label class="check"
            ><input
              id="value-labels"
              type="checkbox"
              checked
            />数値ラベル</label
          >
          <p class="hint">
            セル幅を変えると元画像から再計算します。
          </p>
        </div>
      </aside>
    </main>
    <dialog id="shelf-dialog">
      <h2>クリップボード・シェルフ</h2>
      <p>画像・Base64・テキストを一時保存できます。</p>
      <div class="shelf-actions">
        <button id="shelf-paste-clip" class="primary">クリップボードから追加 ＋</button>
        <button id="shelf-clear">シェルフをクリア</button>
        <a class="button" href="slides/#from-image-studio" target="_blank" rel="opener">編集中の画像をスライド工房へ</a>
      </div>
      <label>Base64 / data URI / テキストを入力して追加
        <textarea id="shelf-input-text" rows="2" placeholder="data:image/png;base64,... または Raw Base64"></textarea>
      </label>
      <button id="shelf-add-text" class="wide">テキストを追加</button>
      <p id="shelf-status" role="status"></p>
      <textarea id="shelf-copy-text" aria-label="手動コピー用テキスト" readonly hidden></textarea>
      <div id="shelf-items-container" class="shelf-list"></div>
      <form method="dialog"><button>閉じる</button></form>
    </dialog>
    <dialog id="base64-dialog">
      <h2>Flutterなどへ画像を渡す</h2>
      <p>PNGの標準Base64です。画像や元のシーンをサーバーへ送信しません。</p>
      <label
        >形式<select id="base64-mode">
          <option value="dataUri">PNG data URI</option>
          <option value="base64">Base64のみ</option>
        </select></label
      ><textarea
        id="base64-text"
        rows="7"
        readonly
        aria-label="Base64画像"
      ></textarea>
      <p id="base64-status" role="status"></p>
      <button id="copy-base64">コピー</button
      ><button id="download-base64">テキスト保存</button>
      <form method="dialog"><button>閉じる</button></form>
    </dialog>
    <dialog id="error">
      <h2>操作を完了できませんでした</h2>
      <p id="error-text"></p>
      <form method="dialog"><button>閉じる</button></form>
    </dialog>
  </body>
</html>
"""

STYLE_CSS = r"""/* web-ui-bundle/1 commit=ed32bdf8174591fa7c79c5d76acb5fd1e4369743 sha256=1050864a3a1a27473139fe3db824ea5917975b3f4c803c5383fafb276aeea663 scripts/build_studio_css.py*/
@layer base,components,theme;
/* css/tokens.css */
:root{--ui-bg:#0d1117;--ui-panel:#101820;--ui-fg:#d1f7c4;--ui-muted:#8b949e;--ui-border:#58a6ff;--ui-accent:#7ee787;--ui-danger:#cf222e;--ui-radius:0;--ui-text:16px;--ui-space:1rem;--ui-max:960px;--ui-font:Meiryo,メイリオ,sans-serif;--ui-font-mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}
/* auto: dark (the :root palette) unless the browser prefers light, then the github-like palette. */
body[data-ui-theme="auto"]{color-scheme:dark light}@media(prefers-color-scheme:light){body[data-ui-theme="auto"]{--ui-bg:#ffffff;--ui-panel:#f6f8fa;--ui-fg:#1f2328;--ui-muted:#59636e;--ui-border:#d0d7de;--ui-accent:#0969da}}
/* Candidate themes, token-only: palettes, no theme files (see theme_palettes()). */
body[data-ui-theme="green"]{--ui-bg:#edf0ec;--ui-panel:#ffffff;--ui-fg:#163b3b;--ui-muted:#546a61;--ui-border:#ccdcd4;--ui-accent:#126d66;--ui-danger:#a73528;--ui-radius:.5rem;color-scheme:light}
body[data-ui-theme="red"]{--ui-bg:#f6eeee;--ui-panel:#fdfcfc;--ui-fg:#6c4141;--ui-muted:#7e6363;--ui-border:#d4bfbf;--ui-accent:#c43131;--ui-danger:#d02525;--ui-radius:.5rem;color-scheme:light}
body[data-ui-theme="blue"]{--ui-bg:#eef1f6;--ui-panel:#fcfcfd;--ui-fg:#41526c;--ui-muted:#636e7e;--ui-border:#bfc7d4;--ui-accent:#316cc4;--ui-danger:#d02525;--ui-radius:.5rem;color-scheme:light}
body[data-ui-theme="purple"]{--ui-bg:#fffbfe;--ui-panel:#f7f2fa;--ui-fg:#1c1b1f;--ui-muted:#49454f;--ui-border:#cac4d0;--ui-accent:#6750a4;--ui-danger:#b3261e;--ui-radius:.5rem;color-scheme:light}
body[data-ui-theme="terminal"]{--ui-bg:#0a0e10;--ui-panel:#11171a;--ui-fg:#d5dee0;--ui-muted:#7c8a8d;--ui-border:#2b3436;--ui-accent:#5fd7a7;--ui-danger:#ff8080;--ui-radius:0;--ui-font:var(--ui-font-mono);color-scheme:dark}
/* css/base.css */
@layer base{*{box-sizing:border-box}body{margin:0;background:var(--ui-bg);color:var(--ui-fg);font:var(--ui-text)/1.6 var(--ui-font)}pre,code,kbd,samp{font-family:var(--ui-font-mono)!important}.ui-page{max-width:var(--ui-max);margin:auto;padding:var(--ui-space)}.ui-title{overflow-wrap:anywhere}a{color:inherit}.ui-print-only{display:none}@media print{body{background:#fff;color:#000}.ui-page{max-width:none;padding:0}.ui-no-print{display:none}.ui-print-only{display:block}a{text-decoration:none}}@media(prefers-reduced-motion:reduce){*,::before,::after{animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}}
/* css/components.css */
@layer components{.ui-panel,.ui-card{background:var(--ui-panel);border:1px solid var(--ui-border);padding:var(--ui-space);margin:var(--ui-space) 0;border-radius:var(--ui-radius)}.ui-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.75rem}.ui-tag{display:inline-block;border:1px solid var(--ui-border);padding:.1rem .4rem}.ui-button,.ui-input,.ui-elements button,.ui-elements select,.ui-elements textarea,.ui-elements input:not([type=checkbox],[type=radio],[type=range],[type=color],[type=file]){font:inherit;background:var(--ui-panel);color:var(--ui-fg);border:1px solid var(--ui-border);padding:.6rem;border-radius:var(--ui-radius)}.ui-button,.ui-elements button{cursor:pointer}.ui-button:hover,.ui-elements button:hover{border-color:var(--ui-accent)}.ui-button:disabled,.ui-elements button:disabled{opacity:.4;cursor:default}.ui-elements input[type=range],.ui-elements input[type=checkbox],.ui-elements input[type=radio]{accent-color:var(--ui-accent)}.ui-elements label{color:var(--ui-muted)}.ui-muted{color:var(--ui-muted)}.ui-back{margin:0 0 8px;font-size:.875rem}.ui-back .ui-links{margin:0}.ui-back a{color:var(--ui-muted);text-decoration:none}.ui-back a:hover,.ui-back a:focus-visible{color:var(--ui-accent);text-decoration:underline}.ui-output{font:inherit;white-space:pre-wrap;overflow:auto;background:#d8dee4;color:#161b22;border:1px solid #8c959f;border-radius:4px;padding:.75rem}pre code,.ui-output code{font-family:inherit;color:inherit}pre.ui-output code{background:transparent}@media(max-width:480px){.ui-page{padding:.75rem}.ui-grid{grid-template-columns:1fr}.ui-card,.ui-panel{margin:.75rem 0;padding:.75rem}}.ui-lightbox{border:1px solid var(--ui-border);background:var(--ui-panel);color:var(--ui-fg);padding:1rem;max-width:min(96vw,960px);max-height:96vh;border-radius:var(--ui-radius)}.ui-lightbox::backdrop{background:rgba(0,0,0,.72)}.ui-lightbox img{display:block;max-width:100%;max-height:calc(96vh - 8rem);margin:auto}.ui-lightbox-bar{display:flex;gap:.5rem;justify-content:space-between;margin-top:.75rem}body:has(.ui-lightbox[open]){overflow:hidden}.ui-table,.ui-elements table{border-collapse:collapse;width:100%}.ui-table th,.ui-table td,.ui-elements th,.ui-elements td{border-bottom:1px solid var(--ui-border);padding:.25rem .5rem;text-align:left;vertical-align:top;overflow-wrap:anywhere}.ui-table th,.ui-elements th{color:var(--ui-muted);font-weight:500}.ui-table caption,.ui-elements caption{text-align:left;color:var(--ui-muted);padding:.25rem 0}.ui-pass{color:var(--ui-accent)}.ui-fail{color:var(--ui-danger)}.ui-changed{background:color-mix(in srgb,var(--ui-accent) 18%,transparent)}.ui-tag.ui-pass{border-color:var(--ui-accent)}.ui-tag.ui-fail{border-color:var(--ui-danger)}}
body[data-ui-labels=words] [data-ui-word]{font-size:0}[data-ui-labels=words] [data-ui-word]::after{content:attr(data-ui-word);font-size:14px}[data-ui-group]~[data-ui-group]{border-top:1px dashed var(--ui-border);padding-top:8px}
@layer components{.ui-stage{--ui-stage-w:16;--ui-stage-h:9;--ui-stage-room:64dvh;position:relative;flex:none;align-self:center;box-sizing:border-box;margin:0 auto;width:min(100%,calc(var(--ui-stage-room) * var(--ui-stage-w) / var(--ui-stage-h)));aspect-ratio:var(--ui-stage-w)/var(--ui-stage-h);overflow:hidden;background:var(--ui-panel);border:1px solid var(--ui-border)}.ui-stage[data-ui-stage=pinned]{position:sticky;top:0;z-index:1}.ui-stage>:is(svg,img,canvas,video,[data-ui-fill]){position:absolute;inset:0;width:100%;height:100%;display:block;object-fit:contain}@media(orientation:landscape) and (max-height:560px){.ui-stage{--ui-stage-room:100dvh}}}
@layer components{.ui-pager{display:inline-flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:8px;max-width:100%}.ui-pager button{box-sizing:border-box;min-width:48px;min-height:48px;padding:0 8px;font-size:24px;line-height:1;color:var(--ui-fg);background:var(--ui-panel);border:1px solid var(--ui-border);border-radius:var(--ui-radius);cursor:pointer;touch-action:manipulation}.ui-pager button:disabled{opacity:.32;cursor:default}.ui-pager button:focus-visible{outline:2px solid var(--ui-accent);outline-offset:2px}.ui-pager output{min-width:48px;text-align:center;font-weight:700;font-variant-numeric:tabular-nums}.ui-pager>[data-ui-pager-part=dots]{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;max-width:100%}.ui-pager>[data-ui-pager-part=dots] button{min-width:32px;min-height:32px;padding:0;font-size:16px;color:var(--ui-accent)}.ui-pager>input[type=range]{width:160px;max-width:100%;min-height:48px;margin:0;accent-color:var(--ui-accent)}.ui-pager[data-ui-pager=dpad]{display:inline-grid;grid-template-columns:repeat(3,48px);grid-template-rows:repeat(3,48px)}[data-ui-pager=dpad]>[data-ui-pager-part=up]{grid-area:1/2}[data-ui-pager=dpad]>[data-ui-pager-part=prev]{grid-area:2/1}[data-ui-pager=dpad]>[data-ui-pager-part=page]{grid-area:2/2;place-self:center}[data-ui-pager=dpad]>[data-ui-pager-part=next]{grid-area:2/3}[data-ui-pager=dpad]>[data-ui-pager-part=down]{grid-area:3/2}.ui-pager[data-ui-pager=dpad]>:not([data-ui-pager-in~=dpad]),.ui-pager[data-ui-pager=ends]>:not([data-ui-pager-in~=ends]),.ui-pager[data-ui-pager=arrows]>:not([data-ui-pager-in~=arrows]),.ui-pager[data-ui-pager=dots]>:not([data-ui-pager-in~=dots]),.ui-pager[data-ui-pager=slider]>:not([data-ui-pager-in~=slider]),.ui-pager[data-ui-pager=dial]>:not([data-ui-pager-in~=dial]){display:none}}
@layer components{.ui-dial{position:relative;display:inline-block;width:48px;height:48px;border-radius:50%;border:2px solid var(--ui-border);background:var(--ui-panel);box-sizing:border-box;touch-action:none;cursor:grab;vertical-align:middle}.ui-dial[data-ui-dial-drag]{cursor:grabbing}.ui-dial::after{content:"";position:absolute;left:50%;top:4px;width:4px;height:16px;border-radius:2px;background:var(--ui-accent);transform-origin:50% 18px;transform:translateX(-50%) rotate(var(--ui-dial-angle,-135deg))}.ui-dial>input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;pointer-events:none}.ui-dial:focus-within{outline:2px solid var(--ui-accent);outline-offset:2px}}
@layer components{.ui-toolbar{display:flex;flex-direction:column;gap:8px}.ui-toolbar-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}.ui-toolbar-row[hidden]{display:none}.ui-toolbar-row>button,.ui-toolbar-row>a{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;min-width:48px;min-height:48px;padding:0 8px;font-size:24px;line-height:1;text-decoration:none;touch-action:manipulation}.ui-toolbar-row>button:disabled{opacity:.32}}

@layer components{.ui-current-items > [aria-current=step]{font-weight:700;text-decoration:underline;text-decoration-color:var(--ui-accent);text-decoration-thickness:.16em;text-underline-offset:.18em}}

/* studio layout */
body:where([data-page~="studio"]){font-size:13px;line-height:1.5;margin:0}
:where([data-page~="studio"]) header{min-height:76px;background:var(--ui-panel);color:var(--ui-fg);box-shadow:inset 0 -1px var(--ui-border);padding:18px 26px;display:flex;align-items:center;justify-content:space-between;gap:20px}
:where([data-page~="studio"]) .brand{display:flex;align-items:center;gap:12px;font-weight:800;letter-spacing:2px;font-size:19px;white-space:nowrap}
:where([data-page~="studio"]) .brand span{font-weight:400;font-size:10px;display:block;letter-spacing:3px;margin:5px 0 0;color:var(--ui-muted)}
:where([data-page~="studio"]) .brand img{flex:none;image-rendering:pixelated}
:where([data-page~="studio"]) .top-actions{display:flex;flex-wrap:wrap;gap:7px}
:where([data-page~="studio"]) .top-actions summary{cursor:pointer;padding:7px}
:where([data-page~="studio"]) .top-actions details a{color:var(--ui-accent);align-self:center;padding:7px 3px;text-underline-offset:3px}
:where([data-page~="studio"]) button:where(:not(.ui-toolbar-row>*)),:where([data-page~="studio"]) .button{display:inline-flex;align-items:center;justify-content:center;gap:5px;text-decoration:none;min-height:38px;padding:10px 12px}
:where([data-page~="studio"]) .button{font:inherit;cursor:pointer;background:var(--ui-panel);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}
:where([data-page~="studio"]) button:hover,:where([data-page~="studio"]) .button:hover{border-color:var(--ui-accent);background:color-mix(in srgb,var(--ui-accent) 12%,var(--ui-panel))}
:where([data-page~="studio"]) .primary{background:var(--ui-accent);border-color:var(--ui-accent);color:var(--ui-bg);font-weight:700}
:where([data-page~="studio"]) header button,:where([data-page~="studio"]) header .button,:where([data-page~="studio"]) header select{border-color:var(--ui-border);background:var(--ui-bg);color:var(--ui-fg)}
:where([data-page~="studio"]) header .primary{background:var(--ui-accent);color:var(--ui-bg);border-color:var(--ui-accent)}
:where([data-page~="studio"]) input[type=file]{display:none}
:where([data-page~="studio"]) main{display:grid;grid-template-columns:250px minmax(0,1fr) 238px;min-height:calc(100vh - 76px)}
:where([data-page~="studio"]) aside{padding:24px 20px;background:var(--ui-panel)}
:where([data-page~="studio"]) aside.tools{border-right:1px solid var(--ui-border)}
:where([data-page~="studio"]) aside.inspector{border-left:1px solid var(--ui-border)}
:where([data-page~="studio"]) h1{font-size:25px;line-height:1.55;letter-spacing:-1px;margin:12px 0}
:where([data-page~="studio"]) h2{font-size:15px;line-height:1.6;margin:8px 0}
:where([data-page~="studio"]) .eyebrow{font-size:10px;letter-spacing:2px;font-weight:800;color:var(--ui-muted);margin:0 0 12px}
:where([data-page~="studio"]) .hint,:where([data-page~="studio"]) .note{font-size:11px;color:var(--ui-muted);line-height:1.85}
:where([data-page~="studio"]) .note{margin-top:18px}
:where([data-page~="studio"]) .two{display:grid;grid-template-columns:1fr 1fr;gap:7px}
:where([data-page~="studio"]) .tools>.ui-toolbar{margin:24px 0 16px}
:where([data-page~="studio"]) .active{background:color-mix(in srgb,var(--ui-accent) 22%,var(--ui-panel))!important;border-color:var(--ui-accent)!important;color:var(--ui-fg)!important;font-weight:700}
:where([data-page~="studio"]) label{display:block;font-size:11px;margin:12px 0 7px}
:where([data-page~="studio"]) input,:where([data-page~="studio"]) textarea,:where([data-page~="studio"]) select{display:block;width:100%;font-size:13px;padding:9px;margin-top:5px}
:where([data-page~="studio"]) select{width:auto;max-width:100%;padding:8px}
:where([data-page~="studio"]) input[type=color]{height:35px;padding:3px}
:where([data-page~="studio"]) input[type=range]{padding:0}
:where([data-page~="studio"]) input[type=checkbox]{display:inline;width:auto;margin:0 7px 0 0}
:where([data-page~="studio"]) .check{display:flex;align-items:center}
:where([data-page~="studio"]) .wide{width:100%;margin:6px 0}
:where([data-page~="studio"]) .section{border-top:1px solid var(--ui-border);padding-top:20px;margin-top:22px}
:where([data-page~="studio"]) .workspace{padding:30px;min-width:0}
:where([data-page~="studio"]) .canvas-heading{display:flex;justify-content:space-between;align-items:end;gap:12px;margin:5px 0 24px}
:where([data-page~="studio"]) .canvas-heading h2{font-size:22px;font-weight:500;letter-spacing:-.5px}
:where([data-page~="studio"]) .canvas-heading span{font-size:11px;white-space:nowrap;color:var(--ui-muted)}
:where([data-page~="studio"]) .board{position:relative;aspect-ratio:16/9;background:repeating-conic-gradient(#e4e9e2 0 25%,#f7f9f4 0 50%) 0/20px 20px;box-shadow:0 12px 45px color-mix(in srgb,var(--ui-fg) 8%,transparent);outline:none;touch-action:none}
:where([data-page~="studio"]) .board svg{width:100%;height:100%;display:block;user-select:none}
:where([data-page~="studio"]) .board g[data-layer]{cursor:move}
:where([data-page~="studio"]) .board .selection{pointer-events:none}
:where([data-page~="studio"]) .board .handle{pointer-events:all;cursor:nwse-resize}
:where([data-page~="studio"]) .canvas-footer{display:flex;justify-content:space-between;gap:10px;font-size:10px;line-height:1.5;color:var(--ui-muted);margin:16px 0}
:where([data-page~="studio"]) .canvas-settings{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-top:1px solid var(--ui-border);padding-top:24px;margin-top:30px}
:where([data-page~="studio"]) .canvas-settings label{margin:0;max-width:76px}
:where([data-page~="studio"]) .canvas-settings input[type=color]{width:45px}
:where([data-page~="studio"]) .canvas-settings input[type=number]{width:68px}
:where([data-page~="studio"]) .canvas-settings .check{max-width:none}
:where([data-page~="studio"]) .layers{max-height:240px;overflow:auto;margin-bottom:12px}
:where([data-page~="studio"]) .layers button{width:100%;justify-content:space-between;margin-bottom:5px;text-align:left}
:where([data-page~="studio"]) .layers small{color:var(--ui-muted);font-size:9px}
:where([data-page~="studio"]) output{float:right;color:var(--ui-accent)}
:where([data-page~="studio"]) .inspector h2{font-size:14px;margin-bottom:20px}
:where([data-page~="studio"]) dialog{border:1px solid var(--ui-border);border-radius:14px;max-width:480px;padding:30px;color:var(--ui-fg)}
:where([data-page~="studio"]) dialog::backdrop{background:color-mix(in srgb,var(--ui-bg) 60%,transparent)}
:where([data-page~="studio"]) dialog textarea{max-width:100%;word-break:break-all}
:where([data-page~="studio"]) #error-text{white-space:pre-wrap;line-height:1.8}
:where([data-page~="studio"]) #shelf-dialog,:where([data-page~="studio"]) #base64-dialog{width:min(600px,92vw);max-width:600px}
:where([data-page~="studio"]) .shelf-actions{display:flex;gap:10px;margin:12px 0}
:where([data-page~="studio"]) .shelf-list{max-height:320px;overflow-y:auto;margin:15px 0;display:flex;flex-direction:column;gap:10px}
:where([data-page~="studio"]) .shelf-card{display:flex;align-items:center;justify-content:space-between;background:var(--ui-panel);border:1px solid var(--ui-border);border-radius:8px;padding:10px 14px;gap:12px}
:where([data-page~="studio"]) .shelf-card-info{display:flex;align-items:center;gap:12px;overflow:hidden}
:where([data-page~="studio"]) .shelf-thumb{width:48px;height:48px;object-fit:contain;background:repeating-conic-gradient(#e4e9e2 0 25%,#f7f9f4 0 50%) 0/10px 10px;border:1px solid var(--ui-border);border-radius:4px;flex-shrink:0}
:where([data-page~="studio"]) .shelf-details{font-size:11px;overflow:hidden}
:where([data-page~="studio"]) .shelf-details strong{display:block;font-size:12px;color:var(--ui-fg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
:where([data-page~="studio"]) .shelf-details span{color:var(--ui-muted)}
:where([data-page~="studio"]) .shelf-card-actions{display:flex;gap:6px;flex-shrink:0}
:where([data-page~="studio"]) #base64-text{font:11px var(--ui-font-mono);resize:vertical}
:where([data-page~="studio"]) #base64-dialog form{display:inline}
:where([data-page~="studio"]) #base64-dialog p{font-size:12px;line-height:1.8}
@media(min-width:1600px){:where([data-page~="studio"]) .workspace{padding:44px}}
@media(max-width:1150px){:where([data-page~="studio"]) main{grid-template-columns:210px minmax(0,1fr)}:where([data-page~="studio"]) .inspector{grid-column:1/-1;display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px}:where([data-page~="studio"]) .inspector>.eyebrow{display:none}:where([data-page~="studio"]) .inspector>.section{margin:0;border:0;padding:0}:where([data-page~="studio"]) .workspace{padding:22px}}
@media(max-width:680px){:where([data-page~="studio"]) header{padding:14px;display:block}:where([data-page~="studio"]) .top-actions{margin-top:15px}:where([data-page~="studio"]) .top-actions button,:where([data-page~="studio"]) .top-actions .button{padding:7px;font-size:11px}:where([data-page~="studio"]) main{display:flex;flex-direction:column}:where([data-page~="studio"]) .workspace{order:-1;padding:18px}:where([data-page~="studio"]) .canvas-heading h2{font-size:17px}:where([data-page~="studio"]) .canvas-heading{margin-bottom:16px}:where([data-page~="studio"]) .canvas-footer{display:block}:where([data-page~="studio"]) .canvas-footer span{display:block;margin:5px 0}:where([data-page~="studio"]) .tools{display:block}:where([data-page~="studio"]) .tools h1,:where([data-page~="studio"]) .tools>.hint{display:none}:where([data-page~="studio"]) .tools>.ui-toolbar{margin:8px 0}:where([data-page~="studio"]) .inspector{display:block}:where([data-page~="studio"]) .inspector>.section{margin-top:20px}:where([data-page~="studio"]) .canvas-settings{margin-top:20px;padding-top:15px}:where([data-page~="studio"]) .board{width:100%}:where([data-page~="studio"]) aside{padding:18px}:where([data-page~="studio"]) .tools>.section{margin-top:15px}}

/* tools page layout */
body:where([data-page~="tools"]){font-size:15px;line-height:1.65;margin:0}
:where([data-page~="tools"]) a{color:var(--ui-accent);text-underline-offset:4px}
:where([data-page~="tools"]) header{padding:24px 4vw;border-bottom:1px solid var(--ui-border);display:flex;justify-content:space-between;gap:24px;align-items:center;flex-wrap:wrap}
:where([data-page~="tools"]) .brand{display:flex;align-items:center;gap:12px;font-weight:900;letter-spacing:.1em;text-decoration:none;color:inherit}
:where([data-page~="tools"]) .brand img{flex:none;image-rendering:pixelated}
:where([data-page~="tools"]) .brand-hero{display:block;max-width:100%;height:auto;image-rendering:pixelated}
:where([data-page~="tools"]) nav,:where([data-page~="tools"]) .jump,:where([data-page~="tools"]) .exports,:where([data-page~="tools"]) .digest-options{display:flex;flex-wrap:wrap;gap:16px;align-items:center}
:where([data-page~="tools"]) nav{font-size:13px}
:where([data-page~="tools"]) main{max-width:1240px;margin:auto;padding:48px 28px}
:where([data-page~="tools"]) .eyebrow,:where([data-page~="tools"]) .section-heading span{font-size:12px;letter-spacing:.15em;font-weight:800;color:var(--ui-muted)}
:where([data-page~="tools"]) h1{font-size:clamp(38px,7vw,76px);letter-spacing:-.04em;line-height:1.12;margin:20px 0 28px}
:where([data-page~="tools"]) h2{font-size:30px;letter-spacing:-.03em;margin:10px 0 25px}
:where([data-page~="tools"]) .lead{font-size:18px;color:var(--ui-muted)}
:where([data-page~="tools"]) .jump{margin:30px 0}
:where([data-page~="tools"]) .jump a{background:var(--ui-panel);border:1px solid var(--ui-border);padding:10px 16px;border-radius:30px;text-decoration:none}
:where([data-page~="tools"]) section{scroll-margin-top:20px;border-top:1px solid var(--ui-border);margin-top:52px;padding-top:28px}
:where([data-page~="tools"]) .workspace{display:grid;grid-template-columns:310px minmax(0,1fr);gap:28px}
:where([data-page~="tools"]) .controls,:where([data-page~="tools"]) .preview{background:var(--ui-panel);padding:24px;border:1px solid var(--ui-border);border-radius:18px}
:where([data-page~="tools"]) .controls{display:flex;flex-direction:column;gap:14px}
:where([data-page~="tools"]) label{display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:650}
:where([data-page~="tools"]) .pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}
:where([data-page~="tools"]) button,:where([data-page~="tools"]) select,:where([data-page~="tools"]) input,:where([data-page~="tools"]) textarea{max-width:100%;min-width:0}
:where([data-page~="tools"]) button,:where([data-page~="tools"]) select,:where([data-page~="tools"]) input[type=number],:where([data-page~="tools"]) textarea{padding:10px 12px}
:where([data-page~="tools"]) button{font-weight:650}
:where([data-page~="tools"]) button:hover{background:color-mix(in srgb,var(--ui-accent) 12%,var(--ui-panel))}
:where([data-page~="tools"]) .primary{background:var(--ui-accent);border-color:var(--ui-accent);color:var(--ui-bg)}
:where([data-page~="tools"]) .primary:hover{background:color-mix(in srgb,var(--ui-accent) 80%,var(--ui-fg))}
:where([data-page~="tools"]) .hint{color:var(--ui-muted);font-size:12px;font-weight:400;margin:0}
:where([data-page~="tools"]) .preview{display:flex;flex-direction:column;gap:16px;justify-content:center;align-items:stretch}
:where([data-page~="tools"]) .preview canvas{display:block;width:min(100%,480px);height:auto;image-rendering:pixelated;margin:auto;border:1px solid var(--ui-border);background:repeating-conic-gradient(#e1e8e3 0% 25%,#fff 0% 50%) 0 0/20px 20px;cursor:crosshair;touch-action:manipulation}
:where([data-page~="tools"]) textarea{width:100%;font-size:11px;overflow-wrap:anywhere}
:where([data-page~="studio"]) #pixel-editor .workspace{display:block;padding:0}
:where([data-page~="studio"]) #pixel-editor #grid{width:min(100%,320px);height:auto;image-rendering:pixelated;cursor:crosshair}
:where([data-page~="tools"]) #grid-info{font-size:13px;color:var(--ui-muted)}
:where([data-page~="tools"]) #message{border-left:3px solid var(--ui-accent);padding:8px 16px;min-height:42px;background:color-mix(in srgb,var(--ui-accent) 12%,var(--ui-panel))}
:where([data-page~="tools"]) #message[data-error=true]{border-color:var(--ui-danger);color:var(--ui-danger)}
:where([data-page~="tools"]) .image-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-top:24px}
:where([data-page~="tools"]) .image-list figure{margin:0;padding:14px;background:var(--ui-panel);border:1px solid var(--ui-border);border-radius:10px;overflow:hidden}
:where([data-page~="tools"]) .image-list img{width:100%;height:160px;object-fit:contain}
:where([data-page~="tools"]) .image-list figcaption{font-size:12px;overflow-wrap:anywhere}
:where([data-page~="tools"]) .digest-options{margin:25px 0}
@media print{body:where([data-page~="tools"]):has(#brand:target) header,body:where([data-page~="tools"]):has(#brand:target) footer,:where([data-page~="tools"]) main:has(#brand:target)>:not(#brand),:where([data-page~="tools"]) #brand:target p,:where([data-page~="tools"]) #brand:target h2,:where([data-page~="tools"]) #brand:target a:not(:first-child){display:none}}
:where([data-page~="tools"]) .table-wrap{overflow-x:auto}
:where([data-page~="tools"]) table{background:var(--ui-panel);font-size:13px}
:where([data-page~="tools"]) th,:where([data-page~="tools"]) td{padding:16px;min-width:180px}
:where([data-page~="tools"]) th{background:color-mix(in srgb,var(--ui-accent) 10%,var(--ui-panel))}
:where([data-page~="tools"]) footer{padding:30px;text-align:center;color:var(--ui-muted);font-size:12px;border-top:1px solid var(--ui-border)}
@media(max-width:760px){:where([data-page~="tools"]) main{padding:30px 16px}:where([data-page~="tools"]) .workspace{grid-template-columns:1fr}:where([data-page~="tools"]) .controls,:where([data-page~="tools"]) .preview{padding:18px}:where([data-page~="tools"]) header{padding:18px}:where([data-page~="tools"]) h2{font-size:25px}:where([data-page~="tools"]) .exports{gap:8px}}

/* 💻 ⇄ 📱 an emoji face (a control with data-ui-word) is read at 20 px, not at the studio's small text size; a toolbar's are its own (toolbar.css) */
:where([data-page~="studio"]) button[data-ui-word]:where(:not(.ui-toolbar-row>*)),:where([data-page~="studio"]) summary[data-ui-word],:where([data-page~="studio"]) label[data-ui-word]{font-size:20px;line-height:1}

/* 📱 phone slides: the slide is pinned on top (PySaiyanWeBoo's .ui-stage) and the emoji controls scroll under it (landscape: beside it) */
body:where([data-page~="phone"]){margin:0;background:var(--ui-bg)}
:where([data-page~="phone"]) input[type=file]{display:none}
:where([data-page~="phone"]) .button{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;cursor:pointer;text-decoration:none;background:var(--ui-panel);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}
:where([data-page~="phone"]) .phone{display:flex;flex-direction:column;height:100dvh;max-width:960px;margin:0 auto}
:where([data-page~="phone"]) .ui-stage{background:#fff;border:0;box-shadow:0 8px 24px rgba(0,0,0,.16);touch-action:none;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
:where([data-page~="phone"]) .phone-svg svg{position:absolute;inset:0;width:100%;height:100%;display:block}
:where([data-page~="phone"]) .phone-pick{position:absolute;box-sizing:border-box;border:2px dashed var(--ui-accent);pointer-events:none}
:where([data-page~="phone"]) .phone-pick[hidden],:where([data-page~="phone"]) .phone-edit[hidden]{display:none}
:where([data-page~="phone"]) .phone-grip{position:absolute;right:-16px;bottom:-16px;width:32px;height:32px;display:grid;place-items:center;border-radius:50%;background:var(--ui-accent);color:var(--ui-bg);font-size:16px;pointer-events:auto;touch-action:none}
:where([data-page~="phone"]) .phone-edit{flex:1 1 100%;box-sizing:border-box;margin:0;min-height:88px;padding:8px;font-size:16px;line-height:1.5;border:2px solid var(--ui-accent);resize:vertical}
:where([data-page~="phone"]) .phone-deck{flex:1;min-height:0;overflow:auto;display:flex;flex-wrap:wrap;align-items:flex-start;align-content:flex-start;gap:16px;padding:16px}
:where([data-page~="phone"]) .phone-tools{flex:1 1 328px;min-width:0}
:where([data-page~="phone"]) .phone-status{flex:1 1 128px;margin:0;align-self:center;min-height:24px;font-size:16px;overflow-wrap:anywhere}
:where([data-page~="phone"]) .phone-status[data-error=true]{color:var(--ui-danger)}
@media(orientation:landscape) and (max-height:560px),(min-width:960px){:where([data-page~="phone"]) .phone{flex-direction:row;max-width:none}:where([data-page~="phone"]) .ui-stage{max-width:72vw;--ui-stage-room:100dvh}:where([data-page~="phone"]) .phone-deck{flex-direction:column;flex-wrap:nowrap}:where([data-page~="phone"]) .phone-tools,:where([data-page~="phone"]) .phone-status{flex:none}}
@media(min-width:960px){:where([data-page~="phone"]) .ui-stage{max-width:calc(100vw - 376px)}}

#phone-inspector:not([hidden]){display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;min-width:0}
#phone-inspector label:not([hidden]){display:flex;align-items:center;gap:6px}
#phone-inspector input:not([type=checkbox]),#phone-inspector select{min-width:0;width:100%;font-size:16px}
#phone-grid:not([hidden]){display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:6px;flex:0 0 auto;width:100%}
#phone-grid>div{min-width:0}
#phone-grid .ui-stage,#phone-grid button{width:100%;max-width:100%;margin:0;position:relative;top:auto}
#phone-grid .ui-stage{outline:2px solid var(--ui-accent)}
#phone-grid button{padding:0;display:block}
@media(min-width:960px){#phone-grid:not([hidden]){width:calc(100vw - 376px);max-height:100dvh;overflow:auto}}"""

STUDIO_JS = r"""/* Ironmate studio: the one browser script for every page (studio, tools, slides; brand needs none).
   Models first (composition, pixel-grid tools, slide shell, Open XML writer), then each page's UI. */
/* Composition model. Optional browser canvas metrics; no network/framework dependency. */
const StudioCore = (function (root) {
  "use strict";
  const SCHEMA = "ironmate-image-studio/1";
  const WORKSPACE_SCHEMA = "ironmate-studio-workspace/1";
  const WORKSPACE_MAX_BYTES = 32 * 1024 * 1024;
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const escape = (x) =>
    String(x).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&apos;",
        })[c],
    );
  const num = (v, lo, hi) =>
    typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
  const color = (c) =>
    typeof c === "string" && /^(#[0-9a-f]{6}|none)$/i.test(c);
  const fail = (message) => {
    throw new Error(message);
  };
  /* PSWB heatmap-color.js @ ed32bdf8174591fa7c79c5d76acb5fd1e4369743. Generated by scripts/build_studio_css.py. */
  const heatmapDefaultPalette=["#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725"];
  function heatmapColor(v,lo,hi,levels=0,palette=heatmapDefaultPalette){
   if(!Array.isArray(palette)||palette.length<2||palette.length>256||
      [...palette].some(stop=>typeof stop!=="string"||stop.length!==7||!/^#[0-9a-f]{6}$/i.test(stop)))throw new TypeError("配色には2〜256個の #RRGGBB が必要です");
   if(v===null)return"none";
   if(![v,lo,hi].every(Number.isFinite)||lo>hi||!Number.isInteger(levels)||(levels!==0&&(levels<2||levels>256)))throw new TypeError("色の範囲または段階数が不正です");
   let t=hi===lo?0.5:Math.max(0,Math.min(1,(v-lo)/(hi-lo)));if(levels)t=Math.round(t*(levels-1))/(levels-1);
   const p=t*(palette.length-1),i=Math.min(palette.length-2,Math.floor(p)),a=palette[i].match(/\w\w/g).map(x=>parseInt(x,16)),b=palette[i+1].match(/\w\w/g).map(x=>parseInt(x,16));
   return"#"+a.map((x,j)=>Math.round(x+(b[j]-x)*(p-i)).toString(16).padStart(2,"0")).join("").toUpperCase()}
  /* End PSWB heatmap-color.js */
  function matrix(source) {
    let t;
    if (Array.isArray(source)) t = { z: source };
    else if (Array.isArray(source?.data)) {
      const traces = source.data.filter((t) => t?.type === "heatmap");
      if (traces.length !== 1) fail("heatmapトレースは1つにしてください");
      t = traces[0];
    } else t = source;
    const z = t?.z,
      cols = z?.[0]?.length;
    if (
      !Array.isArray(z) ||
      !cols ||
      z.length * cols > 4096 ||
      z.some((r) => !Array.isArray(r) || r.length !== cols)
    )
      fail("1〜4096セルの長方形の数値行列が必要です");
    const values = z.flat().filter((v) => v !== null);
    if (
      values.some(
        (v) =>
          !Number.isFinite(v) ||
          (Number.isInteger(v) && !Number.isSafeInteger(v)),
      )
    )
      fail("有限の数値またはnullを指定してください（巨大な整数は非対応）");
    const low = t.zmin ?? (values.length ? Math.min(...values) : 0),
      high = t.zmax ?? (values.length ? Math.max(...values) : 1);
    if (
      [low, high].some(
        (v) =>
          !Number.isFinite(v) ||
          (Number.isInteger(v) && !Number.isSafeInteger(v)),
      )
    )
      fail("色の範囲には有限の安全な数値を指定してください");
    heatmapColor(low, low, high);
    const xlabels = t.x ?? Array.from({ length: cols }, (_, i) => i),
      ylabels = t.y ?? Array.from({ length: z.length }, (_, i) => i);
    if (
      !Array.isArray(xlabels) ||
      !Array.isArray(ylabels) ||
      xlabels.length !== cols ||
      ylabels.length !== z.length
    )
      fail("軸ラベルの数が一致しません");
    return {
      z: clone(z),
      xlabels: clone(xlabels),
      ylabels: clone(ylabels),
      low,
      high,
      levels: 0,
      labels: true,
    };
  }
  function validate(scene) {
    if (
      scene?.schema !== SCHEMA ||
      !Number.isInteger(scene.width) ||
      !Number.isInteger(scene.height) ||
      !num(scene.width, 64, 4096) ||
      !num(scene.height, 64, 4096) ||
      scene.width * scene.height > 4194304 ||
      !color(scene.background) ||
      !Array.isArray(scene.layers) ||
      scene.layers.length > 100
    )
      fail("シーンの形式・サイズが不正です（最大100レイヤー、4MP）");
    const ids = new Set();
    let imageBytes = 0;
    for (const l of scene.layers) {
      if (
        !l ||
        typeof l.id !== "string" ||
        l.id.length > 100 ||
        ids.has(l.id) ||
        ![
          "rect",
          "ellipse",
          "triangle",
          "text",
          "image",
          "heatmap",
          "arrow",
          "clock",
        ].includes(l.kind)
      )
        fail("レイヤーのIDまたは種類が不正です");
      ids.add(l.id);
      for (const f of ["x", "y"])
        if (!num(l[f], -8192, 8192)) fail("位置が不正です");
      for (const f of ["w", "h"])
        if (!num(l[f], 1, 8192)) fail("サイズが不正です");
      if (!num(l.rotation, -360, 360) || !num(l.opacity, 0, 1))
        fail("角度または不透明度が不正です");
      if (l.mono !== undefined && typeof l.mono !== "boolean")
        fail("単色設定が不正です");
      if (l.mono && !color(l.fill)) fail("単色の色が不正です");
      if (l.kind === "text") {
        if (l.wrap !== undefined && typeof l.wrap !== "boolean") fail("折り返しの指定が不正です");
        if (l.bold !== undefined && typeof l.bold !== "boolean") fail("太字の指定が不正です");
        if (l.italic !== undefined && typeof l.italic !== "boolean") fail("斜体の指定が不正です");
        if (l.font !== undefined && !["sans", "mono"].includes(l.font))
          fail("フォント設定が不正です");
        if (
          typeof l.text !== "string" ||
          l.text.length > 2000 ||
          !num(l.fontSize, 4, 512) ||
          !color(l.fill)
        )
          fail("テキストが不正です");
      } else if (l.kind === "image") {
        if (
          typeof l.src !== "string" ||
          l.src.length > 12000000 ||
          !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(l.src)
        )
          fail("画像は埋め込みPNGが必要です");
        imageBytes += l.src.length;
        if (imageBytes > 20000000)
          fail("シーンの画像合計は20MB以下にしてください");
        if (
          !Number.isInteger(l.cell) ||
          !num(l.cell, 1, 512) ||
          !Number.isInteger(l.levels) ||
          !num(l.levels, 2, 256)
        )
          fail("モザイク設定が不正です");
        if (
          l.sampling !== undefined &&
          !["pixelated", "smooth"].includes(l.sampling)
        )
          fail("補間方式が不正です");
      } else if (l.kind === "heatmap") {
        matrix({
          z: l.z,
          x: l.xlabels,
          y: l.ylabels,
          zmin: l.low,
          zmax: l.high,
        });
        heatmapColor(l.low, l.low, l.high, l.levels, l.palette);
      } else if (
        !color(l.fill) ||
        !color(l.stroke) ||
        !num(l.strokeWidth, 0, 64)
      )
        fail("図形の色または線幅が不正です");
      if (l.kind === "arrow") {
        arrowGeometry(l.w, l.h, l.headSize, l.headPlacement);
        if (
          l.headStyle !== undefined &&
          !["triangle", "beginner"].includes(l.headStyle)
        )
          fail("矢羽根の形が不正です");
      }
      if (
        l.kind === "clock" &&
        (!Number.isInteger(l.hour) ||
          !num(l.hour, 0, 23) ||
          !Number.isInteger(l.minute) ||
          !num(l.minute, 0, 59))
      )
        fail("時計の時刻が不正です");
    }
    return clone(scene);
  }
  function mosaicRGBA(data, width, height, cell, levels = 256) {
    if (
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width < 1 ||
      height < 1 ||
      width * height > 4194304 ||
      data.length !== width * height * 4 ||
      !Number.isInteger(cell) ||
      cell < 1 ||
      cell > 512 ||
      !Number.isInteger(levels) ||
      levels < 2 ||
      levels > 256
    )
      fail("モザイク入力が不正です");
    const out = new Uint8ClampedArray(data.length);
    for (let y = 0; y < height; y += cell)
      for (let x = 0; x < width; x += cell) {
        const endX = Math.min(width, x + cell),
          endY = Math.min(height, y + cell),
          sums = [0, 0, 0];
        let alpha = 0,
          count = 0;
        for (let j = y; j < endY; j++)
          for (let i = x; i < endX; i++) {
            const n = (j * width + i) * 4,
              a = data[n + 3];
            alpha += a;
            count++;
            for (let c = 0; c < 3; c++) sums[c] += data[n + c] * a;
          }
        const rgba = sums.map((s) =>
          Math.round(
            (Math.round(
              ((alpha ? Math.round(s / alpha) : 0) / 255) * (levels - 1),
            ) /
              (levels - 1)) *
              255,
          ),
        );
        rgba.push(Math.round(alpha / count));
        for (let j = y; j < endY; j++)
          for (let i = x; i < endX; i++) out.set(rgba, (j * width + i) * 4);
      }
    return out;
  }
  function arrowGeometry(w, h, head = 28, placement = "tip") {
    if (
      !num(w, 1, 8192) ||
      !num(h, 1, 8192) ||
      !num(head, 1, 512) ||
      !["tip", "middle"].includes(placement)
    )
      fail("矢印の寸法が不正です");
    const size = Math.min(head, w, h),
      cx = placement === "middle" ? w / 2 : w - size / 2;
    return {
      line: [0, h / 2, w, h / 2],
      points: [
        [cx + size / 2, h / 2],
        [cx - size / 2, h / 2 + size / 2],
        [cx - size / 2, h / 2 - size / 2],
      ],
    };
  }
  function outputSize(scene, scale = 1) {
    if (!num(scale, 0.25, 8)) fail("出力倍率は0.25〜8です");
    const width = Math.round(scene.width * scale),
      height = Math.round(scene.height * scale);
    if (width > 8192 || height > 8192 || width * height > 16777216)
      fail("出力は各辺8192px・合計16MP以下にしてください");
    return { width, height };
  }
  function pngPayload(bytes) {
    const a = Uint8Array.from(bytes),
      signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (
      a.length < 8 ||
      a.length > 32 * 1024 * 1024 ||
      signature.some((v, i) => a[i] !== v)
    )
      fail("32MiB以下のPNGが必要です");
    let base64;
    if (typeof Buffer !== "undefined")
      base64 = Buffer.from(a).toString("base64");
    else {
      let binary = "";
      for (let i = 0; i < a.length; i += 8192)
        binary += String.fromCharCode(...a.subarray(i, i + 8192));
      base64 = btoa(binary);
    }
    return {
      base64,
      dataUri: "data:image/png;base64," + base64,
      mimeType: "image/png",
      bytes: a.length,
    };
  }
  function textFont(l) {
    return l.font === "mono"
      ? `${l.wrap ? "'MS Gothic', " : ""}ui-monospace, 'Noto Sans Mono', monospace`
      : "Meiryo, 'Noto Sans', 'Noto Color Emoji', sans-serif";
  }
  let textContext;
  function measureText(text, l) {
    // Node exports use conservative em estimates. Browser SVG and PPTX share
    // the actual installed font's metrics, including bold and kerning.
    if (textContext === undefined) {
      const canvas = root.document?.createElement("canvas");
      textContext = canvas?.getContext("2d") || null;
    }
    if (textContext) {
      textContext.font = `${l.italic ? "italic " : ""}${l.bold ? 700 : 400} ${l.fontSize}px ${textFont(l)}`;
      return textContext.measureText(text).width;
    }
    return Array.from(text).reduce((n, c) => n + (/^[\x20-\x7e]$/.test(c) ? 0.65 : 1), 0) * l.fontSize;
  }
  const words = new Intl.Segmenter("ja", { granularity: "word" }),
    graphemes = new Intl.Segmenter("ja", { granularity: "grapheme" });
  function textLayout(l, measure = (text) => measureText(text, l)) {
    const paragraphs = l.text.replace(/\r\n?/g, "\n").split("\n");
    return paragraphs.map((paragraph) => {
      if (!l.wrap || !paragraph) return [paragraph];
      const lines = [];
      let line = "";
      const flush = () => { lines.push(line.replace(/[ \t]+$/, "")); line = ""; };
      for (const { segment: token } of words.segment(paragraph)) {
        if (!line && lines.length && /^[ \t]+$/.test(token)) continue;
        if (measure(line + token) <= l.w) { line += token; continue; }
        // Keep ordinary words intact; split a long word/URL at grapheme
        // boundaries. A single glyph wider than the box is never compressed.
        if (line) flush();
        if (lines.length && /^[ \t]+$/.test(token)) continue;
        if (measure(token) <= l.w) { line = token; continue; }
        for (const { segment: glyph } of graphemes.segment(token)) {
          if (line && measure(line + glyph) > l.w) flush();
          line += glyph;
        }
      }
      if (line || !lines.length) lines.push(line);
      return lines;
    });
  }
  function layerSVG(l, imageSource = (x) => x.src) {
    let body = "";
    if (["rect", "ellipse", "triangle"].includes(l.kind)) {
      const attrs = `fill="${l.fill}" stroke="${l.stroke}" stroke-width="${l.strokeWidth}"`;
      if (l.kind === "rect")
        body = `<rect width="${l.w}" height="${l.h}" ${attrs}/>`;
      if (l.kind === "ellipse")
        body = `<ellipse cx="${l.w / 2}" cy="${l.h / 2}" rx="${l.w / 2}" ry="${l.h / 2}" ${attrs}/>`;
      if (l.kind === "triangle")
        body = `<polygon points="${l.w / 2},0 ${l.w},${l.h} 0,${l.h}" ${attrs}/>`;
    } else if (l.kind === "text") {
      body =
        `<text xml:space="preserve" fill="${l.fill}" font-family="${textFont(l)}" font-size="${l.fontSize}" font-weight="${l.bold ? "700" : "400"}"${l.italic ? ' font-style="italic"' : ""} dominant-baseline="text-before-edge">` +
        textLayout(l).flat()
          .map(
            (line, i) =>
              `<tspan x="0" y="${i * l.fontSize * 1.3}">${escape(line)}</tspan>`,
          )
          .join("") +
        "</text>";
    } else if (l.kind === "image")
      body = `<image href="${escape(imageSource(l))}" width="${l.w}" height="${l.h}" preserveAspectRatio="none" image-rendering="${l.sampling === "smooth" ? "auto" : "pixelated"}"/>`;
    else if (l.kind === "arrow") {
      const g = arrowGeometry(l.w, l.h, l.headSize, l.headPlacement);
      body = `<line x1="${g.line[0]}" y1="${g.line[1]}" x2="${g.line[2]}" y2="${g.line[3]}" stroke="${l.stroke}" stroke-width="${l.strokeWidth}"/>`;
      if (l.headStyle === "beginner") {
        const size = Math.min(l.headSize ?? 28, l.w, l.h),
          x = g.points[0][0] - size,
          y = l.h / 2 - size / 2;
        // The emoji points down; rotate -90 degrees to point along +x.
        // Alpha masking removes the font's embedded yellow/green colors.
        const id =
          "head-" +
          Array.from(l.id)
            .map((c) => c.codePointAt(0).toString(16))
            .join("-");
        body += `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 100 100"><defs><mask id="${id}" mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100"><text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-family="'Noto Color Emoji', 'Segoe UI Emoji', 'Apple Color Emoji', sans-serif" font-size="90" transform="rotate(-90 50 50)">🔰</text></mask></defs><rect width="100" height="100" fill="#000000" mask="url(#${id})"/></svg>`;
      } else
        body += `<polygon points="${g.points.map((p) => p.join(",")).join(" ")}" fill="${l.stroke}"/>`;
    } else if (l.kind === "clock") {
      const cx = l.w / 2,
        cy = l.h / 2,
        r = Math.max(0.1, Math.min(l.w, l.h) / 2 - l.strokeWidth),
        ink = l.stroke;
      const point = (a, k) => [
        cx + Math.sin(a) * r * k,
        cy - Math.cos(a) * r * k,
      ];
      const line = (p, q, width) =>
        `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke="${ink}" stroke-width="${width}"/>`;
      body = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${l.fill}" stroke="${ink}" stroke-width="${l.strokeWidth}"/>`;
      for (let i = 0; i < 12; i++)
        body += line(
          point((i * Math.PI) / 6, 0.85),
          point((i * Math.PI) / 6, 0.96),
          l.strokeWidth,
        );
      body +=
        line(
          [cx, cy],
          point((((l.hour % 12) + l.minute / 60) * Math.PI) / 6, 0.52),
          l.strokeWidth * 1.5,
        ) +
        line([cx, cy], point((l.minute * Math.PI) / 30, 0.76), l.strokeWidth);
    } else if (l.kind === "heatmap") {
      const left = 90,
        top = 28,
        right = 24,
        bottom = 56,
        cw = Math.max(1, l.w - left - right) / l.z[0].length,
        ch = Math.max(1, l.h - top - bottom) / l.z.length;
      for (let y = 0; y < l.z.length; y++) {
        for (let x = 0; x < l.z[y].length; x++) {
          const v = l.z[y][x],
            title = `${l.ylabels[y]} / ${l.xlabels[x]}: ${v === null ? "欠測" : v}`;
          body += `<rect x="${left + x * cw}" y="${top + y * ch}" width="${cw}" height="${ch}" fill="${heatmapColor(v, l.low, l.high, l.levels, l.palette)}"><title>${escape(title)}</title></rect>`;
          if (l.labels && cw >= 35 && ch >= 24 && v !== null)
            body += `<text x="${left + (x + 0.5) * cw}" y="${top + (y + 0.5) * ch}" text-anchor="middle" dominant-baseline="central" font-family="Meiryo,sans-serif" font-size="12" fill="#111827" stroke="#FFFFFF" stroke-width="2" paint-order="stroke">${escape(v)}</text>`;
        }
        body += `<text x="${left - 10}" y="${top + (y + 0.5) * ch}" text-anchor="end" dominant-baseline="central" font-family="Meiryo,sans-serif" font-size="12">${escape(l.ylabels[y])}</text>`;
      }
      for (let x = 0; x < l.z[0].length; x++)
        body += `<text x="${left + (x + 0.5) * cw}" y="${l.h - bottom + 20}" text-anchor="middle" font-family="Meiryo,sans-serif" font-size="12">${escape(l.xlabels[x])}</text>`;
      body += `<text x="${left}" y="${l.h - 5}" font-family="Meiryo,sans-serif" font-size="12">${escape(l.low)} → ${escape(l.high)} ・ ${l.levels ? l.levels + "段階" : "連続色"} ・ 欠測は透明</text>`;
    }
    if (l.mono && ["text", "image"].includes(l.kind)) {
      const id =
        "ink-" +
        Array.from(l.id)
          .map((c) => c.codePointAt(0).toString(16))
          .join("-");
      body = `<defs><mask id="${id}" mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="${l.w}" height="${l.h}">${body}</mask></defs><rect width="${l.w}" height="${l.h}" fill="${l.fill}" mask="url(#${id})"/>`;
    }
    return `<g data-layer="${escape(l.id)}" transform="translate(${l.x} ${l.y}) rotate(${l.rotation} ${l.w / 2} ${l.h / 2})" opacity="${l.opacity}">${body}</g>`;
  }
  function svg(scene, imageSource, scale = 1) {
    validate(scene);
    const size = outputSize(scene, scale);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size.width}" height="${size.height}" viewBox="0 0 ${scene.width} ${scene.height}"><rect width="${scene.width}" height="${scene.height}" fill="${scene.background}"/>${scene.layers.map((l) => layerSVG(l, imageSource)).join("")}</svg>`;
  }
  class History {
    constructor(scene) {
      this.items = [validate(scene)];
      this.index = 0;
    }
    get current() {
      return clone(this.items[this.index]);
    }
    commit(scene) {
      const next = validate(scene);
      if (JSON.stringify(next) === JSON.stringify(this.items[this.index]))
        return;
      this.items = this.items.slice(0, this.index + 1);
      this.items.push(next);
      if (this.items.length > 40) this.items.shift();
      this.index = this.items.length - 1;
    }
    undo(steps = 1) {
      this.index = Math.max(0, this.index - steps);
      return this.current;
    }
    redo(steps = 1) {
      this.index = Math.min(this.items.length - 1, this.index + steps);
      return this.current;
    }
  }
  function workspaceShape(record) {
    if (record?.schema !== WORKSPACE_SCHEMA ||
        !Array.isArray(record.items) || record.items.length < 1 || record.items.length > 40 ||
        !Number.isInteger(record.index) || record.index < 0 || record.index >= record.items.length)
      fail("作業履歴の形式が不正です");
  }
  function workspaceSize(text) {
    const bytes = new TextEncoder().encode(text).length;
    if (bytes > WORKSPACE_MAX_BYTES) fail("作業履歴は32MiB以下にしてください。履歴を整理して再保存できます");
    return bytes;
  }
  function workspaceText(history) {
    const record = { schema: WORKSPACE_SCHEMA, items: history.items, index: history.index };
    workspaceShape(record);
    const parts = ['{"schema":' + JSON.stringify(WORKSPACE_SCHEMA) + ',"items":['];
    const tail = '],"index":' + record.index + '}';
    let bytes = workspaceSize(parts[0]) + workspaceSize(tail);
    // Validate/serialize one state at a time and stop before assembling an oversize record.
    for (let i = 0; i < record.items.length; i++) {
      const part = (i ? ',' : '') + JSON.stringify(validate(record.items[i]));
      bytes += workspaceSize(part);
      if (bytes > WORKSPACE_MAX_BYTES) fail("作業履歴は32MiB以下にしてください。履歴を整理して再保存できます");
      parts.push(part);
    }
    parts.push(tail);
    return parts.join('');
  }
  function workspaceHistory(text) {
    if (typeof text !== "string") fail("作業履歴の形式が不正です");
    workspaceSize(text);
    const record = JSON.parse(text);
    workspaceShape(record);
    const states = record.items.map(validate);
    const next = new History(states[0]);
    next.items = states;
    next.index = record.index;
    return next;
  }
  // 💾 ブラウザでファイルを保存（Blob・文字列・バイト列）。どのページもこの 1 つを使う
  function save(name, data, type) {
    const url = URL.createObjectURL(data instanceof Blob ? data : new Blob([data], { type })),
      a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  // 🖼️ PNG / JPEG / WebP by their first bytes (what a file says it is does not decide)
  function imageType(bytes) {
    if ([137, 80, 78, 71, 13, 10, 26, 10].every((v, i) => bytes[i] === v)) return "image/png";
    if (bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255) return "image/jpeg";
    if (bytes.length >= 12 && [82, 73, 70, 70].every((v, i) => bytes[i] === v) && [87, 69, 66, 80].every((v, i) => bytes[i + 8] === v))
      return "image/webp";
    return null;
  }
  // 🖼️ The one way an image comes in, on every studio page (📥 画像 カメラ クリップボード, a drop, the shelf, the Tools page): a
  // PNG / JPEG / WebP of at most 32 MiB whose bytes match its declared type, as a PNG shrunk to 4 MP and to `longest` px on its long
  // side (a phone's photo fits; nothing is refused for its size in pixels).
  async function picture(file, longest = Infinity, signal) {
    signal?.throwIfAborted();
    if (!file.size || file.size > 33554432) fail("画像は32MiB以下にしてください");
    const type = imageType(new Uint8Array(await file.slice(0, 12).arrayBuffer()));
    if (!type || (file.type && file.type.toLowerCase() !== type)) fail("画像形式またはMIME宣言が実データと一致しません");
    const url = URL.createObjectURL(file),
      img = new Image();
    const abort = () => {
      img.removeAttribute("src");
      URL.revokeObjectURL(url);
    };
    try {
      signal?.addEventListener("abort", abort, {once: true});
      img.src = url;
      await img.decode();
      signal?.throwIfAborted();
    } finally {
      signal?.removeEventListener("abort", abort);
      if (!signal?.aborted) URL.revokeObjectURL(url);
    }
    const w = img.naturalWidth,
      h = img.naturalHeight;
    const k = Math.min(1, longest / Math.max(w, h), Math.sqrt(4194304 / (w * h))),
      canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.floor(w * k)); // floor: rounding never takes it past 4 MP
    canvas.height = Math.max(1, Math.floor(h * k));
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return { canvas, type, src: canvas.toDataURL("image/png"), w: canvas.width, h: canvas.height };
  }
  function mosaicSource(img, cell, levels) {
    const canvas = Object.assign(document.createElement("canvas"), { width: img.naturalWidth, height: img.naturalHeight });
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    data.data.set(mosaicRGBA(data.data, canvas.width, canvas.height, cell, levels));
    ctx.putImageData(data, 0, 0);
    return canvas.toDataURL("image/png");
  }
  async function scenePng(doc, imageSource, scale = 1) {
    const size = outputSize(doc, scale);
    const source = svg(doc, imageSource, scale),
      url = URL.createObjectURL(new Blob([source], { type: "image/svg+xml" }));
    try {
      const img = new Image();
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = () => reject(new Error("SVGの画像化に失敗しました"));
        img.src = url;
      });
      const canvas = document.createElement("canvas");
      canvas.width = size.width;
      canvas.height = size.height;
      canvas.getContext("2d").drawImage(img, 0, 0);
      return await new Promise((resolve, reject) =>
        canvas.toBlob(
          (b) => (b ? resolve(b) : reject(new Error("PNG出力に失敗しました"))),
          "image/png",
        ),
      );
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  const api = {
    scenePng,
    mosaicSource,
    SCHEMA,
    WORKSPACE_MAX_BYTES,
    clone,
    escape,
    heatmapColor,
    matrix, // 🌡️ the heatmap parity test (Python ⇄ JS) reads it
    validate,
    mosaicRGBA,
    arrowGeometry,
    pngPayload,
    textLayout,
    layerSVG,
    svg,
    History,
    workspaceText,
    workspaceHistory,
    save,
    picture,
    imageType,
  };
  return api;
})(typeof globalThis !== "undefined" ? globalThis : this);

/* Browser/Node shared operations. Pixel coordinates follow grid_tools.py. */
const IronmateTools = (function (root) {
  "use strict";
  /* PSWB pixel-grid.js @ ed32bdf8174591fa7c79c5d76acb5fd1e4369743. Generated by scripts/build_studio_css.py. */
  /* web-ui pixel-grid: a dot-art grid checked, resized, drawn as SVG and described for a PNG; Base64 length; PNG chunks. pysaiyanweboo.py (pixel_grid_*, base64_length) is the reference; this must agree. */
  const PIXEL_GRID_SCHEMA="ironmate-pixel-grid/1";
  function pixelGridValidate(value){
   const g=JSON.parse(JSON.stringify(value));
   if(!g||typeof g!=="object"||Array.isArray(g)||g.schema!==PIXEL_GRID_SCHEMA||![g.width,g.height].every(n=>Number.isInteger(n)&&n>=1&&n<=256))throw new Error("グリッドは1〜256セル／辺です。");
   if(!Array.isArray(g.colors)||!g.colors.length||g.colors.length>65536||g.colors.some(c=>typeof c!=="string"||!/^#[0-9a-f]{8}$/i.test(c)))throw new Error("色表は#RRGGBBAAで指定してください。");
   if(!Array.isArray(g.pixels)||g.pixels.length!==g.height||g.pixels.some(r=>!Array.isArray(r)||r.length!==g.width||r.some(i=>!Number.isInteger(i)||i<0||i>=g.colors.length)))throw new Error("色番号または行列の寸法が不正です。");
   return g}
  function pixelGridResize(value,width,height){
   const g=pixelGridValidate(value);
   if(![width,height].every(n=>Number.isInteger(n)&&n>=1&&n<=256))throw new Error("幅・高さは1〜256の整数です。");
   const pixels=Array.from({length:height},(_,y)=>Array.from({length:width},(_,x)=>g.pixels[Math.min(g.height-1,Math.floor(((y+0.5)*g.height)/height))][Math.min(g.width-1,Math.floor(((x+0.5)*g.width)/width))]));
   return{...g,width,height,pixels,resampling:"nearest"}}
  function pixelGridSvg(value,scale=1){
   const g=pixelGridValidate(value);
   if(!Number.isInteger(scale)||scale<1||scale>16)throw new Error("倍率は1〜16です。");
   const cells=[];
   g.pixels.forEach((row,y)=>row.forEach((i,x)=>{const c=g.colors[i],a=parseInt(c.slice(7),16)/255;if(a)cells.push(`<rect x="${x}" y="${y}" width="1" height="1" fill="${c.slice(0,7)}" fill-opacity="${a}"/>`)}));
   return`<svg xmlns="http://www.w3.org/2000/svg" width="${g.width*scale}" height="${g.height*scale}" viewBox="0 0 ${g.width} ${g.height}" shape-rendering="crispEdges">${cells.join("")}</svg>`}
  function pixelGridHeader(value){
   const g=pixelGridValidate(value),always=["schema","width","height","colors"];
   return Object.fromEntries([...always,"mask","palette","effect","resampling"].filter(k=>Object.hasOwn(g,k)&&(always.includes(k)||g[k]===null||(typeof g[k]==="string"&&/^[A-Za-z0-9_./-]{1,64}$/.test(g[k])))).map(k=>[k,g[k]]))}
  function base64Length(bytes,dataUri=false){
   if(!Number.isSafeInteger(bytes)||bytes<0||bytes>Number.MAX_SAFE_INTEGER/2)throw new Error("ファイルサイズが大きすぎます。");
   return 4*Math.ceil(bytes/3)+(dataUri?22:0)}
  function crc32(bytes){let c=0xffffffff;for(const b of bytes){c^=b;for(let k=0;k<8;k++)c=(c>>>1)^(c&1?0xedb88320:0)}return(c^0xffffffff)>>>0}
  function pngChunk(type,body){
   const out=new Uint8Array(body.length+12),view=new DataView(out.buffer);
   view.setUint32(0,body.length);out.set(new TextEncoder().encode(type),4);out.set(body,8);view.setUint32(out.length-4,crc32(out.subarray(4,out.length-4)));
   return out}
  /* End PSWB pixel-grid.js */
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const api = {
    canonical: pixelGridValidate,
    resize: pixelGridResize,
    svg: pixelGridSvg,
    esc,
    base64Length,
    pngHeader: pixelGridHeader,
    pngChunk,
  };
  return api;
})(typeof globalThis === "object" ? globalThis : this);

/* <slide-shell> Generated by scripts/build_slide_shell.py using locked PptxGenJS 4.0.1. Do not edit by hand. */
const IronmateSlideShell = {"[Content_Types].xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"xml\" ContentType=\"application/xml\"/><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"jpeg\" ContentType=\"image/jpeg\"/><Default Extension=\"jpg\" ContentType=\"image/jpg\"/><Default Extension=\"svg\" ContentType=\"image/svg+xml\"/><Default Extension=\"png\" ContentType=\"image/png\"/><Default Extension=\"gif\" ContentType=\"image/gif\"/><Default Extension=\"m4v\" ContentType=\"video/mp4\"/><Default Extension=\"mp4\" ContentType=\"video/mp4\"/><Default Extension=\"vml\" ContentType=\"application/vnd.openxmlformats-officedocument.vmlDrawing\"/><Default Extension=\"xlsx\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\"/><Override PartName=\"/ppt/presentation.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml\"/><Override PartName=\"/ppt/notesMasters/notesMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml\"/><Override PartName=\"/ppt/slideMasters/slideMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml\"/><Override PartName=\"/ppt/slides/slide1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/><Override PartName=\"/ppt/presProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presProps+xml\"/><Override PartName=\"/ppt/viewProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml\"/><Override PartName=\"/ppt/theme/theme1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.theme+xml\"/><Override PartName=\"/ppt/tableStyles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml\"/><Override PartName=\"/ppt/slideLayouts/slideLayout1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml\"/><Override PartName=\"/ppt/notesSlides/notesSlide1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml\"/> <Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/> <Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/></Types>","_rels/.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>\n\t\t<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>\n\t\t<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"ppt/presentation.xml\"/>\n\t\t</Relationships>","docProps/app.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">\n\t<TotalTime>0</TotalTime>\n\t<Words>0</Words>\n\t<Application>Microsoft Office PowerPoint</Application>\n\t<PresentationFormat>On-screen Show (16:9)</PresentationFormat>\n\t<Paragraphs>0</Paragraphs>\n\t<Slides>1</Slides>\n\t<Notes>1</Notes>\n\t<HiddenSlides>0</HiddenSlides>\n\t<MMClips>0</MMClips>\n\t<ScaleCrop>false</ScaleCrop>\n\t<HeadingPairs>\n\t\t<vt:vector size=\"6\" baseType=\"variant\">\n\t\t\t<vt:variant><vt:lpstr>Fonts Used</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>2</vt:i4></vt:variant>\n\t\t\t<vt:variant><vt:lpstr>Theme</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>1</vt:i4></vt:variant>\n\t\t\t<vt:variant><vt:lpstr>Slide Titles</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>1</vt:i4></vt:variant>\n\t\t</vt:vector>\n\t</HeadingPairs>\n\t<TitlesOfParts>\n\t\t<vt:vector size=\"4\" baseType=\"lpstr\">\n\t\t\t<vt:lpstr>Arial</vt:lpstr>\n\t\t\t<vt:lpstr>Calibri</vt:lpstr>\n\t\t\t<vt:lpstr>Office Theme</vt:lpstr>\n\t\t\t<vt:lpstr>Slide 1</vt:lpstr>\n\t\t</vt:vector>\n\t</TitlesOfParts>\n\t<Company>PptxGenJS</Company>\n\t<LinksUpToDate>false</LinksUpToDate>\n\t<SharedDoc>false</SharedDoc>\n\t<HyperlinksChanged>false</HyperlinksChanged>\n\t<AppVersion>16.0000</AppVersion>\n\t</Properties>","docProps/core.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">\n\t\t<dc:title>PptxGenJS Presentation</dc:title>\n\t\t<dc:subject>PptxGenJS Presentation</dc:subject>\n\t\t<dc:creator>PptxGenJS</dc:creator>\n\t\t<cp:lastModifiedBy>PptxGenJS</cp:lastModifiedBy>\n\t\t<cp:revision>1</cp:revision>\n\t\t<dcterms:created xsi:type=\"dcterms:W3CDTF\">2000-01-01T00:00:00Z</dcterms:created>\n\t\t<dcterms:modified xsi:type=\"dcterms:W3CDTF\">2000-01-01T00:00:00Z</dcterms:modified>\n\t</cp:coreProperties>","ppt/_rels/presentation.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"slideMasters/slideMaster1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" Target=\"slides/slide1.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster\" Target=\"notesMasters/notesMaster1.xml\"/><Relationship Id=\"rId4\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps\" Target=\"presProps.xml\"/><Relationship Id=\"rId5\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps\" Target=\"viewProps.xml\"/><Relationship Id=\"rId6\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"theme/theme1.xml\"/><Relationship Id=\"rId7\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles\" Target=\"tableStyles.xml\"/></Relationships>","ppt/notesMasters/_rels/notesMaster1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"../theme/theme1.xml\"/>\n\t\t</Relationships>","ppt/notesMasters/notesMaster1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:notesMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Header Placeholder 1\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"hdr\" sz=\"quarter\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"2971800\" cy=\"458788\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle><a:lvl1pPr algn=\"l\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Date Placeholder 2\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"dt\" idx=\"1\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"3884613\" y=\"0\"/><a:ext cx=\"2971800\" cy=\"458788\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle><a:lvl1pPr algn=\"r\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:fld id=\"{5282F153-3F37-0F45-9E97-73ACFA13230C}\" type=\"datetimeFigureOut\"><a:rPr lang=\"en-US\"/><a:t>7/23/19</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"4\" name=\"Slide Image Placeholder 3\"/><p:cNvSpPr><a:spLocks noGrp=\"1\" noRot=\"1\" noChangeAspect=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldImg\" idx=\"2\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"685800\" y=\"1143000\"/><a:ext cx=\"5486400\" cy=\"3086100\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:noFill/><a:ln w=\"12700\"><a:solidFill><a:prstClr val=\"black\"/></a:solidFill></a:ln></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"ctr\"/><a:lstStyle/><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"5\" name=\"Notes Placeholder 4\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"body\" sz=\"quarter\" idx=\"3\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"685800\" y=\"4400550\"/><a:ext cx=\"5486400\" cy=\"3600450\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle/><a:p><a:pPr lvl=\"0\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Click to edit Master text styles</a:t></a:r></a:p><a:p><a:pPr lvl=\"1\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Second level</a:t></a:r></a:p><a:p><a:pPr lvl=\"2\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Third level</a:t></a:r></a:p><a:p><a:pPr lvl=\"3\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Fourth level</a:t></a:r></a:p><a:p><a:pPr lvl=\"4\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Fifth level</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"6\" name=\"Footer Placeholder 5\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"ftr\" sz=\"quarter\" idx=\"4\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"8685213\"/><a:ext cx=\"2971800\" cy=\"458787\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"b\"/><a:lstStyle><a:lvl1pPr algn=\"l\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"7\" name=\"Slide Number Placeholder 6\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldNum\" sz=\"quarter\" idx=\"5\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"3884613\" y=\"8685213\"/><a:ext cx=\"2971800\" cy=\"458787\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"b\"/><a:lstStyle><a:lvl1pPr algn=\"r\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:fld id=\"{CE5E9CC1-C706-0F49-92D6-E571CC5EEA8F}\" type=\"slidenum\"><a:rPr lang=\"en-US\"/><a:t>\u2039#\u203a</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp></p:spTree><p:extLst><p:ext uri=\"{BB962C8B-B14F-4D97-AF65-F5344CB8AC3E}\"><p14:creationId xmlns:p14=\"http://schemas.microsoft.com/office/powerpoint/2010/main\" val=\"1024086991\"/></p:ext></p:extLst></p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/><p:notesStyle><a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr><a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr><a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr><a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr><a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr><a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr><a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr><a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr><a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr></p:notesStyle></p:notesMaster>","ppt/notesSlides/_rels/notesSlide1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t\t<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster\" Target=\"../notesMasters/notesMaster1.xml\"/>\n\t\t\t<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" Target=\"../slides/slide1.xml\"/>\n\t\t</Relationships>","ppt/notesSlides/notesSlide1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:notes xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Slide Image Placeholder 1\"/><p:cNvSpPr><a:spLocks noGrp=\"1\" noRot=\"1\" noChangeAspect=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldImg\"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Notes Placeholder 2\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"body\" idx=\"1\"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang=\"en-US\" dirty=\"0\"/><a:t></a:t></a:r><a:endParaRPr lang=\"en-US\" dirty=\"0\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"4\" name=\"Slide Number Placeholder 3\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldNum\" sz=\"quarter\" idx=\"10\"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:fld id=\"{F7021451-1387-4CA6-816F-3879F97B5CBC}\" type=\"slidenum\"><a:rPr lang=\"en-US\"/><a:t>1</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp></p:spTree><p:extLst><p:ext uri=\"{BB962C8B-B14F-4D97-AF65-F5344CB8AC3E}\"><p14:creationId xmlns:p14=\"http://schemas.microsoft.com/office/powerpoint/2010/main\" val=\"1024086991\"/></p:ext></p:extLst></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>","ppt/presProps.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:presentationPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"/>","ppt/presentation.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:presentation xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"  saveSubsetFonts=\"1\" autoCompressPictures=\"0\"><p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id=\"256\" r:id=\"rId2\"/></p:sldIdLst><p:notesMasterIdLst><p:notesMasterId r:id=\"rId3\"/></p:notesMasterIdLst><p:sldSz cx=\"9144000\" cy=\"5143500\"/><p:notesSz cx=\"5143500\" cy=\"9144000\"/><p:defaultTextStyle><a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr><a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr><a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr><a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr><a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr><a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr><a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr><a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr><a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr></p:defaultTextStyle></p:presentation>","ppt/slideLayouts/_rels/slideLayout1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"../slideMasters/slideMaster1.xml\"/></Relationships>","ppt/slideLayouts/slideLayout1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t\t<p:sldLayout xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" preserve=\"1\">\n\t\t<p:cSld name=\"DEFAULT\"><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>\n\t\t<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>","ppt/slideMasters/_rels/slideMaster1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"../theme/theme1.xml\"/></Relationships>","ppt/slideMasters/slideMaster1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:sldMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/><p:sldLayoutIdLst><p:sldLayoutId id=\"2147483649\" r:id=\"rId1\"/></p:sldLayoutIdLst><p:hf sldNum=\"0\" hdr=\"0\" ftr=\"0\" dt=\"0\"/><p:txStyles> <p:titleStyle>  <a:lvl1pPr algn=\"ctr\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"0\"/></a:spcBef><a:buNone/><a:defRPr sz=\"4400\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mj-lt\"/><a:ea typeface=\"+mj-ea\"/><a:cs typeface=\"+mj-cs\"/></a:defRPr></a:lvl1pPr> </p:titleStyle> <p:bodyStyle>  <a:lvl1pPr marL=\"342900\" indent=\"-342900\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"3200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr>  <a:lvl2pPr marL=\"742950\" indent=\"-285750\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2013\"/><a:defRPr sz=\"2800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr>  <a:lvl3pPr marL=\"1143000\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2400\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr>  <a:lvl4pPr marL=\"1600200\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2013\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr>  <a:lvl5pPr marL=\"2057400\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u00bb\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr>  <a:lvl6pPr marL=\"2514600\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr>  <a:lvl7pPr marL=\"2971800\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr>  <a:lvl8pPr marL=\"3429000\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr>  <a:lvl9pPr marL=\"3886200\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr> </p:bodyStyle> <p:otherStyle>  <a:defPPr><a:defRPr lang=\"en-US\"/></a:defPPr>  <a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr>  <a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr>  <a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr>  <a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr>  <a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr>  <a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr>  <a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr>  <a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr>  <a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr> </p:otherStyle></p:txStyles></p:sldMaster>","ppt/tableStyles.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<a:tblStyleLst xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" def=\"{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}\"/>","ppt/theme/theme1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><a:theme xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" name=\"Office Theme\"><a:themeElements><a:clrScheme name=\"Office\"><a:dk1><a:sysClr val=\"windowText\" lastClr=\"000000\"/></a:dk1><a:lt1><a:sysClr val=\"window\" lastClr=\"FFFFFF\"/></a:lt1><a:dk2><a:srgbClr val=\"44546A\"/></a:dk2><a:lt2><a:srgbClr val=\"E7E6E6\"/></a:lt2><a:accent1><a:srgbClr val=\"4472C4\"/></a:accent1><a:accent2><a:srgbClr val=\"ED7D31\"/></a:accent2><a:accent3><a:srgbClr val=\"A5A5A5\"/></a:accent3><a:accent4><a:srgbClr val=\"FFC000\"/></a:accent4><a:accent5><a:srgbClr val=\"5B9BD5\"/></a:accent5><a:accent6><a:srgbClr val=\"70AD47\"/></a:accent6><a:hlink><a:srgbClr val=\"0563C1\"/></a:hlink><a:folHlink><a:srgbClr val=\"954F72\"/></a:folHlink></a:clrScheme><a:fontScheme name=\"Office\"><a:majorFont><a:latin typeface=\"Calibri Light\" panose=\"020F0302020204030204\"/><a:ea typeface=\"\"/><a:cs typeface=\"\"/><a:font script=\"Jpan\" typeface=\"\u6e38\u30b4\u30b7\u30c3\u30af Light\"/><a:font script=\"Hang\" typeface=\"\ub9d1\uc740 \uace0\ub515\"/><a:font script=\"Hans\" typeface=\"\u7b49\u7ebf Light\"/><a:font script=\"Hant\" typeface=\"\u65b0\u7d30\u660e\u9ad4\"/><a:font script=\"Arab\" typeface=\"Times New Roman\"/><a:font script=\"Hebr\" typeface=\"Times New Roman\"/><a:font script=\"Thai\" typeface=\"Angsana New\"/><a:font script=\"Ethi\" typeface=\"Nyala\"/><a:font script=\"Beng\" typeface=\"Vrinda\"/><a:font script=\"Gujr\" typeface=\"Shruti\"/><a:font script=\"Khmr\" typeface=\"MoolBoran\"/><a:font script=\"Knda\" typeface=\"Tunga\"/><a:font script=\"Guru\" typeface=\"Raavi\"/><a:font script=\"Cans\" typeface=\"Euphemia\"/><a:font script=\"Cher\" typeface=\"Plantagenet Cherokee\"/><a:font script=\"Yiii\" typeface=\"Microsoft Yi Baiti\"/><a:font script=\"Tibt\" typeface=\"Microsoft Himalaya\"/><a:font script=\"Thaa\" typeface=\"MV Boli\"/><a:font script=\"Deva\" typeface=\"Mangal\"/><a:font script=\"Telu\" typeface=\"Gautami\"/><a:font script=\"Taml\" typeface=\"Latha\"/><a:font script=\"Syrc\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Orya\" typeface=\"Kalinga\"/><a:font script=\"Mlym\" typeface=\"Kartika\"/><a:font script=\"Laoo\" typeface=\"DokChampa\"/><a:font script=\"Sinh\" typeface=\"Iskoola Pota\"/><a:font script=\"Mong\" typeface=\"Mongolian Baiti\"/><a:font script=\"Viet\" typeface=\"Times New Roman\"/><a:font script=\"Uigh\" typeface=\"Microsoft Uighur\"/><a:font script=\"Geor\" typeface=\"Sylfaen\"/><a:font script=\"Armn\" typeface=\"Arial\"/><a:font script=\"Bugi\" typeface=\"Leelawadee UI\"/><a:font script=\"Bopo\" typeface=\"Microsoft JhengHei\"/><a:font script=\"Java\" typeface=\"Javanese Text\"/><a:font script=\"Lisu\" typeface=\"Segoe UI\"/><a:font script=\"Mymr\" typeface=\"Myanmar Text\"/><a:font script=\"Nkoo\" typeface=\"Ebrima\"/><a:font script=\"Olck\" typeface=\"Nirmala UI\"/><a:font script=\"Osma\" typeface=\"Ebrima\"/><a:font script=\"Phag\" typeface=\"Phagspa\"/><a:font script=\"Syrn\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syrj\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syre\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Sora\" typeface=\"Nirmala UI\"/><a:font script=\"Tale\" typeface=\"Microsoft Tai Le\"/><a:font script=\"Talu\" typeface=\"Microsoft New Tai Lue\"/><a:font script=\"Tfng\" typeface=\"Ebrima\"/></a:majorFont><a:minorFont><a:latin typeface=\"Calibri\" panose=\"020F0502020204030204\"/><a:ea typeface=\"\"/><a:cs typeface=\"\"/><a:font script=\"Jpan\" typeface=\"\u6e38\u30b4\u30b7\u30c3\u30af\"/><a:font script=\"Hang\" typeface=\"\ub9d1\uc740 \uace0\ub515\"/><a:font script=\"Hans\" typeface=\"\u7b49\u7ebf\"/><a:font script=\"Hant\" typeface=\"\u65b0\u7d30\u660e\u9ad4\"/><a:font script=\"Arab\" typeface=\"Arial\"/><a:font script=\"Hebr\" typeface=\"Arial\"/><a:font script=\"Thai\" typeface=\"Cordia New\"/><a:font script=\"Ethi\" typeface=\"Nyala\"/><a:font script=\"Beng\" typeface=\"Vrinda\"/><a:font script=\"Gujr\" typeface=\"Shruti\"/><a:font script=\"Khmr\" typeface=\"DaunPenh\"/><a:font script=\"Knda\" typeface=\"Tunga\"/><a:font script=\"Guru\" typeface=\"Raavi\"/><a:font script=\"Cans\" typeface=\"Euphemia\"/><a:font script=\"Cher\" typeface=\"Plantagenet Cherokee\"/><a:font script=\"Yiii\" typeface=\"Microsoft Yi Baiti\"/><a:font script=\"Tibt\" typeface=\"Microsoft Himalaya\"/><a:font script=\"Thaa\" typeface=\"MV Boli\"/><a:font script=\"Deva\" typeface=\"Mangal\"/><a:font script=\"Telu\" typeface=\"Gautami\"/><a:font script=\"Taml\" typeface=\"Latha\"/><a:font script=\"Syrc\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Orya\" typeface=\"Kalinga\"/><a:font script=\"Mlym\" typeface=\"Kartika\"/><a:font script=\"Laoo\" typeface=\"DokChampa\"/><a:font script=\"Sinh\" typeface=\"Iskoola Pota\"/><a:font script=\"Mong\" typeface=\"Mongolian Baiti\"/><a:font script=\"Viet\" typeface=\"Arial\"/><a:font script=\"Uigh\" typeface=\"Microsoft Uighur\"/><a:font script=\"Geor\" typeface=\"Sylfaen\"/><a:font script=\"Armn\" typeface=\"Arial\"/><a:font script=\"Bugi\" typeface=\"Leelawadee UI\"/><a:font script=\"Bopo\" typeface=\"Microsoft JhengHei\"/><a:font script=\"Java\" typeface=\"Javanese Text\"/><a:font script=\"Lisu\" typeface=\"Segoe UI\"/><a:font script=\"Mymr\" typeface=\"Myanmar Text\"/><a:font script=\"Nkoo\" typeface=\"Ebrima\"/><a:font script=\"Olck\" typeface=\"Nirmala UI\"/><a:font script=\"Osma\" typeface=\"Ebrima\"/><a:font script=\"Phag\" typeface=\"Phagspa\"/><a:font script=\"Syrn\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syrj\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syre\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Sora\" typeface=\"Nirmala UI\"/><a:font script=\"Tale\" typeface=\"Microsoft Tai Le\"/><a:font script=\"Talu\" typeface=\"Microsoft New Tai Lue\"/><a:font script=\"Tfng\" typeface=\"Ebrima\"/></a:minorFont></a:fontScheme><a:fmtScheme name=\"Office\"><a:fillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"110000\"/><a:satMod val=\"105000\"/><a:tint val=\"67000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"105000\"/><a:satMod val=\"103000\"/><a:tint val=\"73000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"105000\"/><a:satMod val=\"109000\"/><a:tint val=\"81000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:satMod val=\"103000\"/><a:lumMod val=\"102000\"/><a:tint val=\"94000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:satMod val=\"110000\"/><a:lumMod val=\"100000\"/><a:shade val=\"100000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"99000\"/><a:satMod val=\"120000\"/><a:shade val=\"78000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill></a:fillStyleLst><a:lnStyleLst><a:ln w=\"6350\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln><a:ln w=\"12700\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln><a:ln w=\"19050\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst><a:outerShdw blurRad=\"57150\" dist=\"19050\" dir=\"5400000\" algn=\"ctr\" rotWithShape=\"0\"><a:srgbClr val=\"000000\"><a:alpha val=\"63000\"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"><a:tint val=\"95000\"/><a:satMod val=\"170000\"/></a:schemeClr></a:solidFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:tint val=\"93000\"/><a:satMod val=\"150000\"/><a:shade val=\"98000\"/><a:lumMod val=\"102000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:tint val=\"98000\"/><a:satMod val=\"130000\"/><a:shade val=\"90000\"/><a:lumMod val=\"103000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:shade val=\"63000\"/><a:satMod val=\"120000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/><a:extLst><a:ext uri=\"{05A4C25C-085E-4340-85A3-A5531E510DB2}\"><thm15:themeFamily xmlns:thm15=\"http://schemas.microsoft.com/office/thememl/2012/main\" name=\"Office Theme\" id=\"{62F939B6-93AF-4DB8-9C6B-D6C7DFDC589F}\" vid=\"{4A3C46E8-61CC-4603-A589-7422A47A8E4A}\"/></a:ext></a:extLst></a:theme>","ppt/viewProps.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:viewPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:normalViewPr horzBarState=\"maximized\"><p:restoredLeft sz=\"15611\"/><p:restoredTop sz=\"94610\"/></p:normalViewPr><p:slideViewPr><p:cSldViewPr snapToGrid=\"0\" snapToObjects=\"1\"><p:cViewPr varScale=\"1\"><p:scale><a:sx n=\"136\" d=\"100\"/><a:sy n=\"136\" d=\"100\"/></p:scale><p:origin x=\"216\" y=\"312\"/></p:cViewPr><p:guideLst/></p:cSldViewPr></p:slideViewPr><p:notesTextViewPr><p:cViewPr><p:scale><a:sx n=\"1\" d=\"1\"/><a:sy n=\"1\" d=\"1\"/></p:scale><p:origin x=\"0\" y=\"0\"/></p:cViewPr></p:notesTextViewPr><p:gridSpacing cx=\"76200\" cy=\"76200\"/></p:viewPr>"};
/* </slide-shell> */

/* The deck (check, JSON, template, page operations) and its native Open XML writer are PySaiyanWeBoo's slide-deck.js;
   Ironmate supplies the PptxGenJS-generated package shell. */
const IronmateSlides = (function (root) {
  "use strict";
  const C = StudioCore;
  const shell = IronmateSlideShell;
  /* PSWB slide-deck.js @ ed32bdf8174591fa7c79c5d76acb5fd1e4369743. Generated by scripts/build_studio_css.py. */
  /* web-ui slide-deck: several scenes of the image studio as one deck (checked, kept as JSON, pages added, copied, deleted and moved) and written as a PPTX in the page: text, rectangles, ellipses, triangles and arrows stay editable, anything else is a picture. slideDeck(core, shell): core is js/imagestudio.js (or the same functions), shell the empty package the slides go into (part name to text). pysaiyanweboo.py (slide_deck_*) is the reference; this must agree. */
  function slideDeck(C, shell) {
    const SCHEMA = "ironmate-slide-deck/1",
      LIMIT = 32 * 1024 * 1024;
    const encoder = new TextEncoder(),
      clone = C.clone;
    function validate(deck) {
      if (
        !deck ||
        deck.schema !== SCHEMA ||
        !Array.isArray(deck.slides) ||
        deck.slides.length < 1 ||
        deck.slides.length > 20
      )
        throw Error("スライドは1〜20枚です。");
      let bytes = 0;
      const slides = deck.slides.map((scene) => {
        bytes += encoder.encode(JSON.stringify(scene)).length;
        if (bytes > LIMIT) throw Error("全スライドは32MiB以下にしてください。");
        const checked = C.validate(scene);
        for (const layer of checked.layers)
          if (layer.kind === "text" && !layer.mono && layer.wrap === undefined)
            layer.wrap = true;
        return checked;
      });
      if (
        slides.some(
          (s) => s.width !== slides[0].width || s.height !== slides[0].height,
        )
      )
        throw Error("全スライドを同じ幅・高さにしてください。");
      const title = typeof deck.title === "string" ? deck.title : "Ironmate";
      if (title.length > 200) throw Error("資料名は200文字以下です。");
      return { schema: SCHEMA, title, slides };
    }
    function deckText(deck) {
      const text = JSON.stringify(validate(deck));
      if (encoder.encode(text).length > LIMIT)
        throw Error("全スライドは32MiB以下にしてください。");
      return text;
    }
    function parse(text) {
      if (typeof text !== "string" || encoder.encode(text).length > LIMIT)
        throw Error("全スライドJSONは32MiB以下です。");
      return validate(JSON.parse(text));
    }
    function edit(input, action, active = 0) {
      // One page operation on a deck: "add" (a blank page after this one), "duplicate", "delete", "up", "down".
      // Returns the checked deck and the page to show next; the last page is never deleted and the ends do not wrap.
      const deck = validate(input),
        slides = deck.slides;
      if (!Number.isInteger(active) || active < 0 || active >= slides.length)
        throw Error("スライドの位置が不正です。");
      if (action === "add" || action === "duplicate") {
        if (slides.length >= 20) throw Error("スライドは最大20枚です。");
        slides.splice(
          active + 1,
          0,
          action === "add"
            ? { schema: C.SCHEMA, width: slides[0].width, height: slides[0].height, background: "#FFFFFF", layers: [] }
            : clone(slides[active]),
        );
        return { deck, active: active + 1 };
      }
      if (action === "delete") {
        if (slides.length > 1) slides.splice(active, 1);
        return { deck, active: Math.min(active, slides.length - 1) };
      }
      if (action !== "up" && action !== "down") throw Error("スライドの操作が不正です。");
      const index = active + (action === "up" ? -1 : 1);
      if (index < 0 || index >= slides.length) return { deck, active };
      [slides[active], slides[index]] = [slides[index], slides[active]];
      return { deck, active: index };
    }
    function template(
      width = 1280,
      height = 720,
      title = "スライドのタイトル",
      body = "ここに本文を入力します。",
    ) {
      const text = (id, value, x, y, w, h, size, bold) => ({
        id,
        kind: "text",
        name: id,
        x,
        y,
        w,
        h,
        rotation: 0,
        opacity: 1,
        text: value,
        fill: "#000000",
        fontSize: Math.max(4, size),
        font: "sans",
        mono: false,
        bold,
        wrap: true,
      });
      return C.validate({
        schema: C.SCHEMA,
        width,
        height,
        background: "#FFFFFF",
        layers: [
          text(
            "title",
            title,
            width * 0.075,
            height * 0.08,
            width * 0.85,
            height * 0.16,
            width * 0.045,
            true,
          ),
          text(
            "body",
            body,
            width * 0.075,
            height * 0.3,
            width * 0.85,
            height * 0.55,
            width * 0.027,
            false,
          ),
        ],
      });
    }
    function xml(value) {
      for (const c of String(value)) {
        const n = c.codePointAt(0);
        if (
          (n < 32 && ![9, 10, 13].includes(n)) ||
          (n >= 0xd800 && n <= 0xdfff) ||
          n === 0xfffe ||
          n === 0xffff
        )
          throw Error("PPTXに保存できない制御文字が含まれています。");
      }
      return C.escape(value);
    }
    const A = "http://schemas.openxmlformats.org/drawingml/2006/main",
      P = "http://schemas.openxmlformats.org/presentationml/2006/main",
      R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      REL = "http://schemas.openxmlformats.org/package/2006/relationships";
    const declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
    function crc(bytes) {
      let c = 0xffffffff;
      for (const b of bytes) {
        c ^= b;
        for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
      }
      return (c ^ 0xffffffff) >>> 0;
    }
    function zip(files, mediaChecksums) {
      const entries = Object.entries(files).map(([name, data]) => ({
        name: encoder.encode(name),
        data: typeof data === "string" ? encoder.encode(data) : data,
      }));
      let size = 22;
      for (const e of entries) {
        if (!(e.data instanceof Uint8Array)) throw Error("ZIPデータが不正です。");
        size += 76 + 2 * e.name.length + e.data.length;
      }
      if (size > LIMIT) throw Error("PPTXは32MiB以下にしてください。");
      const out = new Uint8Array(size),
        v = new DataView(out.buffer);
      let offset = 0;
      const central = [];
      const word = (p, n) => v.setUint16(p, n, true),
        dword = (p, n) => v.setUint32(p, n, true),
        date = (20 << 9) | (1 << 5) | 1;
      for (const e of entries) {
        const start = offset,
          sum = mediaChecksums?.get(e.data) ?? crc(e.data);
        dword(offset, 0x04034b50);
        word(offset + 4, 20);
        word(offset + 6, 0x800);
        word(offset + 8, 0);
        word(offset + 12, date);
        dword(offset + 14, sum);
        dword(offset + 18, e.data.length);
        dword(offset + 22, e.data.length);
        word(offset + 26, e.name.length);
        out.set(e.name, offset + 30);
        out.set(e.data, offset + 30 + e.name.length);
        offset += 30 + e.name.length + e.data.length;
        central.push({ ...e, start, sum });
      }
      const cd = offset;
      for (const e of central) {
        dword(offset, 0x02014b50);
        word(offset + 4, 20);
        word(offset + 6, 20);
        word(offset + 8, 0x800);
        word(offset + 10, 0);
        word(offset + 14, date);
        dword(offset + 16, e.sum);
        dword(offset + 20, e.data.length);
        dword(offset + 24, e.data.length);
        word(offset + 28, e.name.length);
        dword(offset + 42, e.start);
        out.set(e.name, offset + 46);
        offset += 46 + e.name.length;
      }
      dword(offset, 0x06054b50);
      word(offset + 8, entries.length);
      word(offset + 10, entries.length);
      dword(offset + 12, offset - cd);
      dword(offset + 16, cd);
      return out;
    }
    function isNative(layer) {
      return (
        ["rect", "ellipse", "triangle"].includes(layer.kind) ||
        (layer.kind === "text" && !layer.mono) ||
        (layer.kind === "arrow" && layer.headStyle !== "beginner")
      );
    }
    async function exportPptx(input, imageForLayer) {
      const deck = validate(input),
        files = { ...shell };
      for (const part of ["[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels", "docProps/core.xml"])
        if (typeof files[part] !== "string") throw Error("PPTXの空パッケージが不正です。");
      const mediaByChecksum = new Map();
      const mediaChecksums = new Map();
      let imageNumber = 0,
        totalNative = 0,
        totalImages = 0;
      const unit =
          9144000 / Math.max(deck.slides[0].width, deck.slides[0].height),
        emu = (n) => Math.round(n * unit);
      const slideIds = [],
        presRels = [];
      for (let number = 1; number <= deck.slides.length; number++) {
        const scene = deck.slides[number - 1],
          parts = [],
          rels = [
            `<Relationship Id="rIdLayout" Type="${R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>`,
          ];
        let nextId = 2;
        const nv = (id, name, tx = false) =>
          `<p:nvSpPr><p:cNvPr id="${id}" name="${xml(name)}"/><p:cNvSpPr${tx ? ' txBox="1"' : ""}/><p:nvPr/></p:nvSpPr>`;
        const transform = (l) =>
          `<a:xfrm rot="${Math.round(l.rotation * 60000)}"><a:off x="${emu(l.x)}" y="${emu(l.y)}"/><a:ext cx="${emu(l.w)}" cy="${emu(l.h)}"/></a:xfrm>`;
        const fill = (color, opacity) =>
          color === "none"
            ? "<a:noFill/>"
            : `<a:solidFill><a:srgbClr val="${color.slice(1).toUpperCase()}"><a:alpha val="${Math.round(opacity * 100000)}"/></a:srgbClr></a:solidFill>`;
        const line = (l) =>
          `<a:ln w="${emu(l.strokeWidth)}">${l.strokeWidth ? fill(l.stroke, l.opacity) : "<a:noFill/>"}<a:prstDash val="solid"/></a:ln>`;
        for (const layer of scene.layers) {
          const l = clone(layer),
            name = l.name || l.id;
          if (l.kind === "text" && !l.mono) {
            const size = Math.round((l.fontSize * unit) / 127),
              font = l.font === "mono" ? "MS Gothic" : "Meiryo";
            if (size < 100 || size > 400000)
              throw Error(
                "PPTXの文字サイズが1〜4000ptの範囲を超えています。キャンバスまたは文字サイズを調整してください。",
              );
            const properties = `<a:rPr lang="ja-JP" sz="${size}" b="${l.bold ? 1 : 0}"${l.italic ? ' i="1"' : ""}>${fill(l.fill, l.opacity)}<a:latin typeface="${font}"/><a:ea typeface="${font}"/></a:rPr>`;
            // Explicit input newlines remain paragraphs; measured soft wraps are
            // editable line breaks. Preserve the source text only in deck JSON.
            const paragraphs = C.textLayout(l)
              .map(
                (lines) =>
                  `<a:p><a:pPr><a:lnSpc><a:spcPts val="${Math.round(size * 1.3)}"/></a:lnSpc><a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft></a:pPr>${lines.map(t => `<a:r>${properties}<a:t xml:space="preserve">${xml(t)}</a:t></a:r>`).join(`<a:br>${properties}</a:br>`)}<a:endParaRPr lang="ja-JP" sz="${size}"/></a:p>`,
              )
              .join("");
            parts.push(
              `<p:sp>${nv(nextId++, name, true)}<p:spPr>${transform(l)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="${l.wrap ? "square" : "none"}" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" vertOverflow="overflow"><a:noAutofit/></a:bodyPr><a:lstStyle/>${paragraphs}</p:txBody></p:sp>`,
            );
            totalNative++;
          } else if (["rect", "ellipse", "triangle"].includes(l.kind)) {
            const kind = {
              rect: "rect",
              ellipse: "ellipse",
              triangle: "triangle",
            }[l.kind];
            parts.push(
              `<p:sp>${nv(nextId++, name)}<p:spPr>${transform(l)}<a:prstGeom prst="${kind}"><a:avLst/></a:prstGeom>${fill(l.fill, l.opacity)}${line(l)}</p:spPr></p:sp>`,
            );
            totalNative++;
          } else if (l.kind === "arrow" && l.headStyle !== "beginner") {
            const geometry = C.arrowGeometry(
                l.w,
                l.h,
                l.headSize,
                l.headPlacement,
              ),
              groupId = nextId++,
              shaftId = nextId++,
              headId = nextId++,
              points = geometry.points;
            const gTransform = `<a:xfrm rot="${Math.round(l.rotation * 60000)}"><a:off x="${emu(l.x)}" y="${emu(l.y)}"/><a:ext cx="${emu(l.w)}" cy="${emu(l.h)}"/><a:chOff x="0" y="0"/><a:chExt cx="${emu(l.w)}" cy="${emu(l.h)}"/></a:xfrm>`;
            const local = { ...l, x: 0, y: 0, rotation: 0 },
              shaft = { ...local, y: l.h / 2, h: 0 };
            const custom = `<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/><a:pathLst><a:path w="${emu(l.w)}" h="${emu(l.h)}"><a:moveTo><a:pt x="${emu(points[0][0])}" y="${emu(points[0][1])}"/></a:moveTo>${points
              .slice(1)
              .map(
                (p) =>
                  `<a:lnTo><a:pt x="${emu(p[0])}" y="${emu(p[1])}"/></a:lnTo>`,
              )
              .join("")}<a:close/></a:path></a:pathLst></a:custGeom>`;
            parts.push(
              `<p:grpSp><p:nvGrpSpPr><p:cNvPr id="${groupId}" name="${xml(name)}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>${gTransform}</p:grpSpPr><p:sp>${nv(shaftId, "Arrow shaft")}<p:spPr>${transform(shaft)}<a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>${line(l)}</p:spPr></p:sp><p:sp>${nv(headId, "Arrow head")}<p:spPr>${transform(local)}${custom}${fill(l.fill, l.opacity)}<a:ln><a:noFill/></a:ln></p:spPr></p:sp></p:grpSp>`,
            );
            totalNative += 2;
          } else {
            if (typeof imageForLayer !== "function")
              throw Error(
                "画像化が必要なレイヤーがあります。ブラウザから書き出してください。",
              );
            const bytes = await imageForLayer(l, scene);
            if (
              !(bytes instanceof Uint8Array) ||
              bytes.length < 8 ||
              ![137, 80, 78, 71, 13, 10, 26, 10].every((b, i) => bytes[i] === b)
            )
              throw Error("埋め込み画像はPNGが必要です。");
            const checksum = crc(bytes);
            const candidates = mediaByChecksum.get(checksum) || [];
            let media = candidates.find((name) => {
              const saved = files["ppt/media/" + name];
              return saved.length === bytes.length && saved.every((value, i) => value === bytes[i]);
            });
            if (!media) {
              media = `image${++imageNumber}.png`;
              const saved = new Uint8Array(bytes);
              files["ppt/media/" + media] = saved;
              mediaChecksums.set(saved, checksum);
              candidates.push(media);
              mediaByChecksum.set(checksum, candidates);
            }
            const rid = `rIdImage${totalImages + 1}`;
            rels.push(
              `<Relationship Id="${rid}" Type="${R}/image" Target="../media/${media}"/>`,
            );
            parts.push(
              `<p:pic><p:nvPicPr><p:cNvPr id="${nextId++}" name="${xml(name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="${rid}"><a:alphaModFix amt="${Math.round(l.opacity * 100000)}"/></a:blip><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>${transform(l)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>`,
            );
            totalImages++;
          }
        }
        files[`ppt/slides/slide${number}.xml`] =
          declaration +
          `<p:sld xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}"><p:cSld name="Slide ${number}"><p:bg><p:bgPr>${scene.background === "none" ? "<a:noFill/>" : `<a:solidFill><a:srgbClr val="${scene.background.slice(1)}"/></a:solidFill>`}<a:effectLst/></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>${parts.join("")}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`;
        files[`ppt/slides/_rels/slide${number}.xml.rels`] =
          declaration +
          `<Relationships xmlns="${REL}">${rels.join("")}</Relationships>`;
        slideIds.push(
          `<p:sldId id="${255 + number}" r:id="rIdBrowserSlide${number}"/>`,
        );
        presRels.push(
          `<Relationship Id="rIdBrowserSlide${number}" Type="${R}/slide" Target="slides/slide${number}.xml"/>`,
        );
      }
      files["ppt/presentation.xml"] = files["ppt/presentation.xml"]
        .replace(
          /<p:sldIdLst>[\s\S]*?<\/p:sldIdLst>/,
          `<p:sldIdLst>${slideIds.join("")}</p:sldIdLst>`,
        )
        .replace(
          /<p:sldSz[^>]*\/>/,
          `<p:sldSz cx="${emu(deck.slides[0].width)}" cy="${emu(deck.slides[0].height)}"/>`,
        );
      files["ppt/_rels/presentation.xml.rels"] = files[
        "ppt/_rels/presentation.xml.rels"
      ]
        .replace(/<Relationship\b[^>]*Type="[^"]*\/slide"[^>]*\/>/g, "")
        .replace("</Relationships>", presRels.join("") + "</Relationships>");
      files["[Content_Types].xml"] = files["[Content_Types].xml"]
        .replace(/<Override\b[^>]*PartName="\/ppt\/slides\/[^"]*"[^>]*\/>/g, "")
        .replace(
          "</Types>",
          deck.slides
            .map(
              (_, i) =>
                `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`,
            )
            .join("") + "</Types>",
        );
      const title = xml(deck.title); // text, not a replacement pattern: "$&" stays as written
      files["docProps/core.xml"] = files["docProps/core.xml"].replace(
        /<dc:title>[\s\S]*?<\/dc:title>/,
        () => `<dc:title>${title}</dc:title>`,
      );
      files["docProps/app.xml"] =
        declaration +
        `<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Ironmate</Application><Slides>${deck.slides.length}</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides></Properties>`;
      return {
        data: zip(files, mediaChecksums),
        native: totalNative,
        images: totalImages,
        slides: deck.slides.length,
      };
    }
    const bytesFromData = (uri) =>
      Uint8Array.from(atob(uri.split(",")[1]), (c) => c.charCodeAt(0));
    async function layerPng(layer, imageSource = (x) => x.src) {
      // Browser only: PNG bytes for a layer PPTX keeps as a picture (images, clocks, heatmaps, 🔰 arrows).
      if (layer.kind === "image" && !layer.mono)
        return bytesFromData(imageSource(layer));
      const l = { ...layer, x: 0, y: 0, rotation: 0, opacity: 1 },
        scale = Math.min(2, Math.sqrt(4194304 / (l.w * l.h))),
        canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(l.w * scale));
      canvas.height = Math.max(1, Math.round(l.h * scale));
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}" viewBox="0 0 ${l.w} ${l.h}">${C.layerSVG(l, imageSource)}</svg>`;
      const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" })),
        image = new Image();
      try {
        image.src = url;
        await image.decode();
        canvas.getContext("2d").drawImage(image, 0, 0);
        const blob = await new Promise((resolve) =>
          canvas.toBlob(resolve, "image/png"),
        );
        if (!blob) throw Error("画像レイヤーを出力できませんでした。");
        return new Uint8Array(await blob.arrayBuffer());
      } finally {
        URL.revokeObjectURL(url);
      }
    }
    return { SCHEMA, LIMIT, validate, deckText, parse, template, edit, zip, isNative, exportPptx, layerPng };
  }
  /* End PSWB slide-deck.js */
  const api = slideDeck(C, shell); // 📽️ the writer too: the same bytes this file used to write itself
  return api;
})(globalThis);

const IronmateComposition = (() => {
  function arrangeSong(partsText, orderText) {
    const parts = new Map();
    for (const line of partsText.split("\n").filter(line => line.trim())) {
      const match = /^\s*([^\s=]+)\s*=\s*([^=]+)$/.exec(line);
      if (!match || !match[2].trim()) throw Error("パート名 = コード進行 の形で入力してください。");
      if (parts.has(match[1])) throw Error("同じパート名があります: " + match[1]);
      parts.set(match[1], match[2].trim().split(/\s+/));
    }
    const arrangement = [];
    let chordCount = 0;
    for (const name of orderText.trim().split(/\s+/)) {
      if (!parts.has(name)) throw Error("曲順のパートを確認してください: " + name);
      const chords = parts.get(name);
      chordCount += chords.length;
      if (chordCount > 32) throw Error("曲全体を32コード以内にしてください。");
      arrangement.push({name, chords});
    }
    return arrangement;
  }
  function planSong(parts, key, bpm) {
    const tonic = {C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11}[key];
    if (!Number.isInteger(tonic) || !Number.isInteger(bpm) || bpm < 30 || bpm > 300)
      throw Error("キーまたはBPMを確認してください。");
    const scale = [0, 2, 4, 5, 7, 9, 11];
    const degrees = ["I", "II", "III", "IV", "V", "VI", "VII"];
    const intervalSeconds = 30 / bpm;
    const notes = [];
    const starts = [];
    for (const {chords} of parts) {
      starts.push(notes.length * intervalSeconds);
      for (const chord of chords) {
        const match = /^([IViv]+)(dim|°)?(7)?$/.exec(chord);
        const roman = match?.[1];
        const degree = degrees.indexOf(roman?.toUpperCase());
        if (degree < 0 || (roman !== roman.toUpperCase() && roman !== roman.toLowerCase()))
          throw Error("未対応のコード: " + chord);
        const diminished = Boolean(match[2]);
        const intervals = [0, diminished || roman === roman.toLowerCase() ? 3 : 4, diminished ? 6 : 7];
        if (match[3]) intervals.push(diminished ? 9 : 10);
        for (const semitones of intervals) {
          const midi = 60 + tonic + scale[degree] + semitones;
          const hz = 440 * 2 ** ((midi - 69) / 12);
          notes.push({hz, start: notes.length * intervalSeconds, duration: intervalSeconds * 0.85});
        }
      }
    }
    return {notes, starts};
  }
  return {arrangeSong, planSong};
})();

/* Node: require("./studio/studio.js") is the composition model, with .tools, .slides and .slideShell beside it.
   Browser: the same objects as globals, then each page's UI below runs only on the page that names it in data-page. */
if (typeof module === "object" && module.exports)
  module.exports = Object.assign({}, StudioCore, {tools: IronmateTools, slides: IronmateSlides, slideShell: IronmateSlideShell, composition: IronmateComposition});
else Object.assign(globalThis, {StudioCore, IronmateTools, IronmateSlides, IronmateSlideShell});

/* Image Studio UI (data-page~="studio"): browser only. */
if (typeof document !== "undefined" && document.body && (document.body.dataset.page || "").split(" ").includes("studio")) (function () {
/* Local-only UI; all output passes through the same SVG composition function. */
"use strict";
const C = window.StudioCore,
  $ = (id) => document.getElementById(id),
  control = (act) => document.querySelector(`#studio-toolbar [data-act="${act}"]`),
  // 🧰 what each toolbar act and each key of a host's header (image_studio.host_rows) does: the same function either way
  STUDIO_ACTS = {},
  copy = (value) => C.clone(value);
let serial = 0,
  toolbar = null, // PySaiyanWeBoo's bindToolbar on #studio-toolbar: { offer, close }
  tool = "select",
  shape = "rect", // 図形(▭ ◯ △ →): the candidate the 図形 tool places
  edited = { id: null, text: "" }, // what ✏️ 編集 last showed, so a repaint never undoes typing
  selected = null,
  template = null,
  dirty = false,
  drag = null,
  paintSerial = 0;
const blank = () => ({
  schema: C.SCHEMA,
  width: 1280,
  height: 720,
  background: "#F8F7F2",
  layers: [],
});
let scene = blank(),
  history = new C.History(scene);
const images = new Map(),
  processed = new Map();
const uid = () => `layer-${Date.now()}-${++serial}`;
const selectedLayer = () => scene.layers.find((l) => l.id === selected);
const message = (text) => {
  $("status").textContent = text;
};
function error(e) {
  $("error-text").textContent = e.message || String(e);
  $("error").dataset.code = e.code || "";
  $("error").showModal();
}
function guarded(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      error(e);
    }
  };
}
function base(kind, x = 80, y = 80, w = 180, h = 120) {
  return { id: uid(), kind, name: kind, x, y, w, h, rotation: 0, opacity: 1 };
}
async function decoded(src) {
  if (!images.has(src))
    images.set(
      src,
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          if (img.naturalWidth * img.naturalHeight > 4194304) {
            reject(new Error("画像は4MP以下にしてください"));
            return;
          }
          resolve(img);
        };
        img.onerror = () => reject(new Error("画像を読み込めません"));
        img.src = src;
      }),
    );
  return images.get(src);
}
async function prepare(doc) {
  const sources = new Map();
  for (const l of doc.layers.filter((l) => l.kind === "image")) {
    const key = l.src + ":" + l.cell + ":" + l.levels;
    if (processed.has(key)) {
      sources.set(key, processed.get(key));
      continue;
    }
    const img = await decoded(l.src);
    if (l.cell === 1 && l.levels === 256) {
      processed.set(key, l.src);
      sources.set(key, l.src);
      continue;
    }
    processed.set(key, C.mosaicSource(img, l.cell, l.levels));
    sources.set(key, processed.get(key));
    // Processed previews are disposable; the immutable source always remains in JSON.
    if (processed.size > 16) processed.delete(processed.keys().next().value);
  }
  return (l) => sources.get(l.src + ":" + l.cell + ":" + l.levels) || l.src;
}
function selectionSVG(l) {
  return `<g class="selection" transform="translate(${l.x} ${l.y}) rotate(${l.rotation} ${l.w / 2} ${l.h / 2})"><rect width="${l.w}" height="${l.h}" fill="none" stroke="#126fef" stroke-width="2" stroke-dasharray="8 5"/><rect class="handle" data-handle="resize" x="${l.w - 9}" y="${l.h - 9}" width="18" height="18" rx="3" fill="#126fef" stroke="white" stroke-width="2"/></g>`;
}
function updateHistoryTimeline() {
  const list = $("history-list");
  list.replaceChildren();
  history.items.forEach((state, index) => {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = (index === history.index ? "● " : "○ ") +
      "状態 " + (index + 1) + " / " + state.layers.length + "レイヤー";
    button.setAttribute("aria-current", index === history.index ? "step" : "false");
    button.onclick = () => {
      history.index = index;
      scene = history.current;
      selected = null;
      dirty = true;
      render().catch(error);
    };
    row.append(button);
    list.append(row);
  });
}
// ✏️ 編集: the control, the layers it changes, and the change (each applies as soon as it is set)
const SHAPE_NAMES = { rect: "四角", ellipse: "丸", triangle: "三角" },
  clockText = (l) => String(l.hour).padStart(2, "0") + ":" + String(l.minute).padStart(2, "0"),
  EDITS = [
    ["bold", ["text"], (l, input) => { l.bold = input.checked; }],
    ["italic", ["text"], (l, input) => { l.italic = input.checked; }],
    ["edit-fill", ["text", "image", "rect", "ellipse", "triangle", "arrow", "clock"], (l, input) => { l.fill = input.value; }],
    ["edit-stroke", ["rect", "ellipse", "triangle", "arrow", "clock"], (l, input) => { l.stroke = input.value; }],
    ["edit-shape", ["rect", "ellipse", "triangle"], (l, input) => {
      if (l.name === SHAPE_NAMES[l.kind]) l.name = SHAPE_NAMES[input.value];
      l.kind = input.value;
    }],
    ["edit-time", ["clock"], (l, input) => {
      const [hour, minute] = input.value.split(":").map(Number);
      if (l.name === "時計 " + clockText(l)) l.name = "時計 " + input.value;
      l.hour = hour;
      l.minute = minute;
    }],
  ];
function updateInspector() {
  const l = selectedLayer();
  $("selection").textContent = l ? `${l.name || l.kind}` : "レイヤーを選択";
  for (const f of ["x", "y", "w", "h", "rotation", "opacity"]) {
    $(f).disabled = !l;
    $(f).value = l?.[f] ?? "";
  }
  $("monochrome").disabled = !["text", "image"].includes(l?.kind);
  $("monochrome").checked = l?.mono ?? false;
  $("sampling").disabled = l?.kind !== "image";
  $("sampling").value = l?.sampling ?? "pixelated";
  $("arrow-placement").disabled = l?.kind !== "arrow";
  $("arrow-placement").value = l?.headPlacement ?? "tip";
  $("arrow-style").disabled = l?.kind !== "arrow";
  $("arrow-style").value =
    l?.kind === "arrow" ? (l.headStyle ?? "triangle") : "beginner";
  const text = l?.kind === "text" ? l.text : "";
  if (edited.id !== (l?.id ?? null) || edited.text !== text) {
    $("edit-text").value = text;
    edited = { id: l?.id ?? null, text };
  }
  $("edit-text").disabled = l?.kind !== "text";
  for (const [id, kinds] of EDITS) $(id).disabled = !kinds.includes(l?.kind);
  $("bold").checked = !!l?.bold;
  $("italic").checked = !!l?.italic;
  if (/^#[0-9a-f]{6}$/i.test(l?.fill ?? "")) $("edit-fill").value = l.fill.toLowerCase();
  if (/^#[0-9a-f]{6}$/i.test(l?.stroke ?? "")) $("edit-stroke").value = l.stroke.toLowerCase();
  if (!$("edit-shape").disabled) $("edit-shape").value = l.kind;
  $("edit-time").value = l?.kind === "clock" ? clockText(l) : "";
  $("font-family").disabled = l?.kind !== "text";
  $("font-family").value = l?.font ?? "sans";
  $("font-size").disabled = l?.kind !== "text";
  $("font-size").value = l?.fontSize ?? 48;
  $("cell").disabled = l?.kind !== "image";
  $("cell").value = l?.cell ?? 1;
  $("cell-value").textContent = `${l?.cell ?? 1} px`;
  $("levels").disabled = !["image", "heatmap"].includes(l?.kind);
  $("levels").value = l?.levels || 256;
  $("levels-value").textContent =
    l?.kind === "heatmap" && !l.levels ? "連続" : (l?.levels ?? 256);
  $("value-labels").disabled = l?.kind !== "heatmap";
  $("value-labels").checked = l?.labels ?? true;
  $("continuous").disabled = l?.kind !== "heatmap";
  for (const name of ["delete", "duplicate", "forward", "backward"]) control(name).disabled = !l;
  $("custom").disabled = !l;
  for (const name of ["undo", "undo-2"]) control(name).disabled = history.index === 0;
  for (const name of ["redo", "redo-2"]) control(name).disabled = history.index === history.items.length - 1;
  $("size-note").textContent = `${scene.width} × ${scene.height}`;
  $("canvas-width").value = scene.width;
  $("canvas-height").value = scene.height;
  $("transparent").checked = scene.background === "none";
  if (scene.background !== "none") $("background").value = scene.background;
  updateHistoryTimeline();
  $("layers").replaceChildren();
  for (const layer of [...scene.layers].reverse()) {
    const button = document.createElement("button");
    button.textContent = layer.name || layer.kind;
    button.dataset.layerId = layer.id;
    if (layer.id === selected) button.classList.add("active");
    button.onclick = () => {
      selected = layer.id;
      render();
    };
    $("layers").append(button);
  }
}
async function render() {
  const n = ++paintSerial;
  const doc = copy(scene);
  const imageSource = await prepare(doc);
  if (n !== paintSerial) return;
  let svg = C.svg(doc, imageSource);
  const l = doc.layers.find((l) => l.id === selected);
  if (l) svg = svg.replace("</svg>", selectionSVG(l) + "</svg>");
  $("board").innerHTML = svg;
  $("board").style.aspectRatio = `${doc.width} / ${doc.height}`;
  updateInspector();
}
function change(fn) {
  const next = copy(scene);
  fn(next);
  C.validate(next);
  history.commit(next);
  scene = next;
  dirty = true;
  if (!selectedLayer()) selected = null;
  render().catch(error);
}
function add(layer) {
  if (scene.layers.length >= 100) throw new Error("レイヤーは100件までです");
  selected = layer.id;
  change((doc) => doc.layers.push(layer));
  message(`${layer.name || layer.kind}を追加しました`);
}
const SHAPES = { rect: "▭", ellipse: "◯", triangle: "△", arrow: "→" }; // 🔷 a kind and the face it shows
function setTool(value, opened = false) {
  // 🧰 a mode of the toolbar's make row; 🔷 😊 (^^) show their candidates (PySaiyanWeBoo's bindToolbar opened them already when pressed)
  tool = value;
  for (const b of document.querySelectorAll('#studio-toolbar [data-ui-group="create"] [data-act]')) {
    b.classList.toggle("active", b.dataset.act === value);
    b.setAttribute("aria-pressed", b.dataset.act === value);
  }
  $("keyboard-input").hidden = !["emoji", "kaomoji"].includes(tool);
  const button = control(value), row = $("studio-candidates");
  if (!button?.dataset.candidates) toolbar?.close();
  else if (!opened && (row.hidden || row.dataset.tool !== value)) toolbar?.offer(button);
}
function pick(value, face) {
  // A candidate: 図形 sets the shape the next press places (face is its kind: rect …), 絵文字・顔文字 the text.
  setTool(value, true);
  if (value === "shape") {
    const button = control("shape");
    shape = face;
    face = SHAPES[shape];
    button.textContent = face; // 💻 の表示では「図形(◯)」（data-ui-word）
    button.dataset.uiWord = button.title = `図形(${face})`;
    button.setAttribute("aria-label", button.title);
  } else {
    $(value + "-text").value = face;
    if (face === "🔰") $("fill").value = "#000000";
  }
  $("stamp-note").textContent = `${face}をキャンバスに押せます`;
}
function toolText() {
  // 文字列・スタンプ・絵文字・顔文字 each keep an input of their own; an empty one places its example.
  const input = $(tool === "text" ? "text" : tool + "-text");
  return input.value || input.placeholder;
}
function textLayer(text, x, y) {
  const size = 48,
    lines = text.split("\n");
  return {
    ...base(
      "text",
      x,
      y,
      Math.min(
        700,
        Math.max(
          120,
          Math.max(...lines.map((s) => Array.from(s).length)) * size,
        ),
      ),
      Math.max(70, lines.length * size * 1.3),
    ),
    name: "文字 / " + text.slice(0, 12),
    text,
    fill: $("fill").value,
    fontSize: size,
    font: $("font-family").value,
    mono: true,
    wrap: false,
  };
}
function place(x, y) {
  const kind = tool === "shape" ? shape : tool;
  if (kind === "stamp" && template) {
    const l = copy(template);
    l.id = uid();
    l.x = x - l.w / 2;
    l.y = y - l.h / 2;
    add(l);
  } else if (["text", "stamp", "emoji", "kaomoji"].includes(kind))
    add(textLayer(toolText(), x, y));
  else if (kind === "arrow")
    add({
      ...base("arrow", x, y, 200, 80),
      name: "直線＋矢羽根",
      fill: $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 4,
      headSize: 28,
      headPlacement: $("arrow-placement").value,
      headStyle: $("arrow-style").value,
    });
  else if (kind === "clock") {
    const [hour, minute] = $("clock-time").value.split(":").map(Number);
    add({
      ...base("clock", x, y, 160, 160),
      name: "時計 " + $("clock-time").value,
      hour,
      minute,
      fill: $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 3,
    });
  } else
    add({
      ...base(kind, x, y),
      name: { rect: "四角", ellipse: "丸", triangle: "三角" }[kind],
      fill: $("outline").checked ? "none" : $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 3,
    });
}
function point(e) {
  const svg = $("board").querySelector("svg");
  return new DOMPoint(e.clientX, e.clientY).matrixTransform(
    svg.getScreenCTM().inverse(),
  );
}
$("board").addEventListener(
  "pointerdown",
  guarded(async (e) => {
    if (e.button !== 0) return;
    const p = point(e),
      handle = e.target.closest("[data-handle]"),
      node = e.target.closest("[data-layer]");
    if (tool !== "select") {
      place(p.x, p.y);
      return;
    }
    if (!handle) selected = node?.dataset.layer ?? null;
    const l = selectedLayer();
    if (l) {
      drag = { point: p, layer: copy(l), resize: !!handle, changed: false };
      $("board").setPointerCapture(e.pointerId);
    }
    await render();
  }),
);
$("board").addEventListener("pointermove", (e) => {
  if (!drag) return;
  const p = point(e),
    dx = p.x - drag.point.x,
    dy = p.y - drag.point.y,
    l = selectedLayer();
  if (!l) return;
  const old = drag.layer;
  if (drag.resize) {
    const a = (old.rotation * Math.PI) / 180,
      c = Math.cos(a),
      s = Math.sin(a);
    l.w = Math.max(8, Math.min(8192, old.w + c * dx + s * dy));
    l.h = Math.max(8, Math.min(8192, old.h - s * dx + c * dy));
    const dw = l.w - old.w,
      dh = l.h - old.h;
    l.x = old.x + ((c - 1) * dw) / 2 - (s * dh) / 2;
    l.y = old.y + (s * dw) / 2 + ((c - 1) * dh) / 2;
    if (l.kind === "text")
      l.fontSize = Math.max(
        4,
        Math.min(512, old.fontSize * Math.min(l.w / old.w, l.h / old.h)),
      );
  } else {
    l.x = Math.max(-8192, Math.min(8192, old.x + dx));
    l.y = Math.max(-8192, Math.min(8192, old.y + dy));
  }
  drag.changed = drag.changed || Math.abs(dx) + Math.abs(dy) > 1;
  render().catch(error);
});
function finishDrag() {
  if (drag?.changed) {
    history.commit(scene);
    dirty = true;
    message("位置・サイズを変更しました");
  }
  drag = null;
  updateInspector();
}
$("board").addEventListener("pointerup", finishDrag);
$("board").addEventListener("pointercancel", () => {
  if (drag) {
    Object.assign(selectedLayer(), drag.layer);
    drag = null;
    render().catch(error);
  }
});
$("keyboard-focus").onclick = () => $(tool + "-text").focus();
const MODES = ["select", "text", "shape", "stamp", "emoji", "kaomoji", "clock"];
queueMicrotask(() => {
  // PySaiyanWeBoo's script comes later in studio.js: 💻 To textual ⇄ 📱 To iconic（ページ内と ⋯ の行）and the toolbar
  globalThis.PySaiyanWeBoo.bindLabels();
  toolbar = globalThis.PySaiyanWeBoo.bindToolbar($("studio-toolbar"), (name, face) => {
    if (SHAPES[name]) return pick("shape", name); // 🔷 ▭ ◯ △ → run their kind
    if (MODES.includes(name)) return face === undefined ? setTool(name, true) : pick(name, face);
    STUDIO_ACTS[name]?.(face); // 📥 📤 the format picked (their rows hide after it; 📥's chosen File comes as face), ↩️ ↪️, ⧉ 🗑️ ⬆️ ⬇️
  });
  setTool(tool);
});
for (const [id, name] of [["text", "text"], ["stamp-text", "stamp"], ["emoji-text", "emoji"], ["kaomoji-text", "kaomoji"]])
  $(id).onfocus = () => setTool(name); // typing into an input means its tool
$("stamp-text").oninput = () => {
  template = null;
};
$("clock-time").value = new Date().toTimeString().slice(0, 5); // ◷ starts at the time now
$("custom").onclick = () => {
  const l = selectedLayer();
  if (l) {
    template = copy(l);
    setTool("stamp");
    $("stamp-note").textContent = `「${l.name || l.kind}」を繰り返し押せます`;
  }
};
// ↶ ↷ move one state, ⏪ ⏩ two (data-steps); History clamps at both ends.
for (const [act, move, steps] of [["undo", "undo", 1], ["undo-2", "undo", 2], ["redo", "redo", 1], ["redo-2", "redo", 2]])
  STUDIO_ACTS[act] = () => {
    scene = history[move](steps);
    dirty = true;
    selected = null;
    render().catch(error);
  };
STUDIO_ACTS.duplicate = guarded(() => {
  const l = copy(selectedLayer());
  l.id = uid();
  l.x += 24;
  l.y += 24;
  add(l);
});
STUDIO_ACTS.delete = () => {
  if (selected)
    change((doc) => {
      doc.layers = doc.layers.filter((l) => l.id !== selected);
    });
};
for (const [act, delta] of [
  ["forward", 1],
  ["backward", -1],
])
  STUDIO_ACTS[act] = () =>
    change((doc) => {
      const i = doc.layers.findIndex((l) => l.id === selected),
        j = Math.max(0, Math.min(doc.layers.length - 1, i + delta));
      if (i >= 0)
        [doc.layers[i], doc.layers[j]] = [doc.layers[j], doc.layers[i]];
    });
for (const f of ["x", "y", "w", "h", "rotation", "opacity"])
  $(f).onchange = guarded(() => {
    if (selectedLayer())
      change((doc) => {
        doc.layers.find((l) => l.id === selected)[f] = Number($(f).value);
      });
  });
$("font-size").onchange = guarded(() => {
  if (selectedLayer()?.kind === "text")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).fontSize = Number(
        $("font-size").value,
      );
    });
});
$("apply-text").onclick = guarded(() => {
  if (!selectedLayer()) return;
  change((doc) => {
    const l = doc.layers.find((l) => l.id === selected);
    if (l.kind === "text") {
      if (l.name === "文字 / " + l.text.slice(0, 12))
        l.name = "文字 / " + $("edit-text").value.slice(0, 12); // the layer list follows the new words
      l.text = $("edit-text").value;
      l.font = $("font-family").value;
    }
    if (["text", "image"].includes(l.kind)) l.mono = $("monochrome").checked;
    for (const [id, kinds] of EDITS.filter(([id]) => id === "edit-fill" || id === "edit-stroke"))
      if (kinds.includes(l.kind)) l[id.slice(5)] = $(id).value;
    if (l.kind in SHAPE_NAMES && $("outline").checked) l.fill = "none"; // 枠線だけにする still empties a placed shape
  });
});
for (const [id, kinds, set] of EDITS)
  $(id).onchange = guarded(() => {
    if (kinds.includes(selectedLayer()?.kind))
      change((doc) => set(doc.layers.find((l) => l.id === selected), $(id)));
  });
$("font-family").onchange = () => {
  if (selectedLayer()?.kind === "text")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).font = $("font-family").value;
    });
};
$("monochrome").onchange = () => {
  if (["text", "image"].includes(selectedLayer()?.kind))
    change((doc) => {
      const l = doc.layers.find((l) => l.id === selected);
      l.mono = $("monochrome").checked;
      l.fill = $("fill").value;
    });
};
$("sampling").onchange = () => {
  if (selectedLayer()?.kind === "image")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).sampling = $("sampling").value;
    });
};
$("arrow-style").onchange = () => {
  if (selectedLayer()?.kind === "arrow")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).headStyle =
        $("arrow-style").value;
    });
};
$("arrow-placement").onchange = () => {
  if (selectedLayer()?.kind === "arrow")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).headPlacement =
        $("arrow-placement").value;
    });
};
for (const [id, field] of [
  ["cell", "cell"],
  ["levels", "levels"],
])
  $(id).onchange = guarded(() => {
    if (selectedLayer())
      change((doc) => {
        doc.layers.find((l) => l.id === selected)[field] = Number($(id).value);
      });
  });
$("value-labels").onchange = () => {
  if (selectedLayer()?.kind === "heatmap")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).labels =
        $("value-labels").checked;
    });
};
$("continuous").onclick = () => {
  if (selectedLayer()?.kind === "heatmap")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).levels = 0;
    });
};
$("background").onchange = () =>
  change((doc) => {
    doc.background = $("background").value;
  });
$("transparent").onchange = () =>
  change((doc) => {
    doc.background = $("transparent").checked ? "none" : $("background").value;
  });
$("canvas-size").onclick = guarded(() =>
  change((doc) => {
    doc.width = Number($("canvas-width").value);
    doc.height = Number($("canvas-height").value);
  }),
);
function download(name, data, type) {
  C.save(name, data, type);
  message(`${name}を書き出しました`);
}
STUDIO_ACTS.workspace = guarded(async () => {
  const serialized = C.workspaceText(history);
  download("ironmate-workspace.json", serialized, "application/json");
  message("作業履歴を保存しました");
});
async function openWorkspace(file) {
  if (file.size > C.WORKSPACE_MAX_BYTES) throw new Error("作業履歴は32MiB以下にしてください");
  const next = C.workspaceHistory(await file.text());
  // Decode every state's images before replacing the editable workspace.
  const sources = new Set(next.items.flatMap(state => state.layers
    .filter(layer => layer.kind === "image").map(layer => layer.src)));
  for (const src of sources) await decoded(src);
  history = next;
  scene = next.current;
  selected = null;
  dirty = true;
  await render();
  message("作業履歴を復元しました");
}
$("trim-history").onclick = guarded(async () => {
  if (!window.confirm("現在の状態だけ残して、過去の作業履歴を削除しますか？")) return;
  history = new C.History(scene);
  dirty = true;
  await render();
  message("現在の画像・レイヤーを残して履歴を整理しました");
});
STUDIO_ACTS.json = () => {
  download(
    "ironmate-scene.json",
    JSON.stringify(C.validate(scene), null, 2),
    "application/json",
  );
  dirty = false;
};
STUDIO_ACTS.svg = guarded(async () => {
  const doc = copy(scene),
    imageSource = await prepare(doc);
  download(
    "ironmate-image.svg",
    C.svg(doc, imageSource, Number($("export-scale").value)),
    "image/svg+xml",
  );
});
async function pngBlob(scale = Number($("export-scale").value)) {
  const doc = copy(scene),
    imageSource = await prepare(doc);
  return C.scenePng(doc, imageSource, scale);
}
STUDIO_ACTS.png = guarded(async () =>
  download("ironmate-image.png", await pngBlob(), "image/png"),
);
let clipboardPayload = null;
function showBase64() {
  if (clipboardPayload)
    $("base64-text").value = clipboardPayload[$("base64-mode").value];
}
STUDIO_ACTS.base64 = guarded(async () => {
  clipboardPayload = C.pngPayload(
    new Uint8Array(await (await pngBlob()).arrayBuffer()),
  );
  showBase64();
  $("base64-status").textContent =
    `PNG ${clipboardPayload.bytes.toLocaleString()} bytes ・ 32MiB以下`;
  $("base64-dialog").showModal();
});
$("base64-mode").onchange = showBase64;
async function copyDialogText(text, field, status, success, failure) {
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = success;
  } catch {
    field.value = text;
    field.hidden = false;
    field.focus();
    field.select();
    status.textContent = failure;
  }
}
$("copy-base64").onclick = () => copyDialogText(
  $("base64-text").value, $("base64-text"), $("base64-status"),
  "コピーしました。Flutterのクリップボード欄へ貼り付けられます。",
  "自動コピーが使えません。選択した文字をコピーするか、テキスト保存を使ってください。",
);
$("download-base64").onclick = () =>
  download("ironmate-image.base64.txt", $("base64-text").value, "text/plain");
async function openScene(file) {
  if (file.size > 20000000) throw new Error("JSONは20MB以下にしてください");
  const next = C.validate(JSON.parse(await file.text()));
  await prepare(next);
  // Loading is an undoable edit; an existing composition is never silently lost.
  history.commit(next);
  scene = next;
  selected = null;
  dirty = false;
  await render();
  message("JSONを読み込みました（戻すで前の編集へ戻れます）");
}
// Keep acquisition (picker, camera capture, clipboard) separate from normalization.
async function importImageBytes(bytes, declaredMime, name = "取り込み画像") {
  // 🖼️ StudioCore's picture(): the same checks and the same 4 MP fit as the slide editor's 📥 画像
  const p = await C.picture(new Blob([bytes], { type: declaredMime || "" }));
  const w = Math.min(700, scene.width * 0.65);
  add({
    ...base("image", 80, 90, w, (w * p.h) / p.w),
    name, src: p.src,
    cell: 1, levels: 256, sampling: "pixelated", mono: false,
  });
  setTool("select");
  message(p.type + "を取り込みました");
}
function imageBase64(text, maxBytes = 32 * 1024 * 1024) {
  let value = text.replace(/^\uFEFF/, "").trim();
  const header = /^data:([a-z0-9.+-]+\/[a-z0-9.+-]+)?(?:;[a-z0-9.+-]+=[a-z0-9.+-]+)*;base64,/i.exec(value);
  let mime = null;
  if (header) {
    mime = header[1]?.toLowerCase() || null;
    if (mime === "image/jpg") mime = "image/jpeg";
    value = value.slice(header[0].length);
  } else if (/^data:/i.test(value)) throw new Error("data URIが不正です");
  if (mime && !["image/png", "image/jpeg", "image/webp"].includes(mime))
    throw new Error("対応していない画像MIMEです");
  const compact = value.replace(/\s+/g, "");
  if (!compact || compact.length > 4 * Math.ceil(maxBytes / 3)
      || compact.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(compact))
    throw new Error("Base64形式または容量が不正です");
  const size = compact.length / 4 * 3 - (compact.endsWith("==") ? 2 : compact.endsWith("=") ? 1 : 0);
  if (size > maxBytes) throw new Error("画像は残り容量以下にしてください");
  const binary = atob(compact);
  const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
  if (btoa(binary) !== compact)
    throw new Error("Base64のパディングまたは容量が不正です");
  const actual = C.imageType(bytes);
  if (!actual || (mime && mime !== actual))
    throw new Error("画像形式またはMIME宣言が実データと一致しません");
  return { bytes, mime: actual };
}
async function importImageFile(file) {
  await importImageBytes(new Uint8Array(await file.arrayBuffer()), file.type || null, file.name || "取り込み画像");
}
{
  const board = $("board");
  board.addEventListener("dragover", event => {
    if (event.dataTransfer?.types.includes("Files")) event.preventDefault();
  });
  board.addEventListener("drop", guarded(async event => {
    if (!event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
    const files = event.dataTransfer.files;
    if (files.length !== 1) throw new Error("画像ファイルを1枚ずつドロップしてください");
    await importImageFile(files[0]);
  }));
}
// 📥 画像 カメラ JSON 作業履歴: PySaiyanWeBoo's toolbar holds the choosers and runs the act with the chosen File; a File / Blob
// given to IronmateStudio.act is opened the same way, and the act alone opens the chooser.
for (const [act, open] of [["image", importImageFile], ["camera", importImageFile], ["open-json", openScene], ["open-workspace", openWorkspace]])
  STUDIO_ACTS[act] = guarded(async (file) => (file instanceof Blob ? open(file) : toolbar.choose(act)));
function clipboardError(code, message, cause) {
  return Object.assign(new Error(message), { code, cause });
}
function clipboardImageText(text) {
  const value = text.replace(/^\uFEFF/, "").trim();
  const explicit = /^data:image(?:\/|[;,]|$)/i.test(value);
  // Once text has an image signature, a malformed decode must not fall back
  // to a different binary clipboard image.
  const rawImage = hasRawImageSignature(value);
  try {
    const payload = imageBase64(value);
    if (C.imageType(payload.bytes)) return payload;
    if (explicit) throw new Error("PNG・JPEG・WebP画像ではありません");
  } catch (e) {
    if (explicit || rawImage)
      throw clipboardError("clipboard-invalid-image", "クリップボードの画像テキストが不正です: " + e.message, e);
  }
  return null; // Ordinary text, even if it happens to be valid Base64.
}
STUDIO_ACTS.clipboard = guarded(async () => {
  // 📥 クリップボード: an image, or image text (Base64 / data URI), from the clipboard
  const clipboard = navigator.clipboard;
  if (!clipboard || (typeof clipboard.readText !== "function" && typeof clipboard.read !== "function"))
    throw clipboardError("clipboard-unsupported", "このブラウザにはクリップボード読取APIがありません。ファイル選択またはBase64入力を利用してください");
  const failures = [];
  if (typeof clipboard.readText === "function") {
    let text = "";
    try { text = await clipboard.readText(); }
    catch (e) { failures.push(e); }
    const payload = clipboardImageText(text);
    if (payload) {
      // Explicit/recognized image text wins over a possibly stale binary image.
      // Validation/decode failures must not silently import different content.
      try { return await importImageBytes(payload.bytes, payload.mime, "クリップボードBase64"); }
      catch (e) { throw clipboardError("clipboard-invalid-image", e.message, e); }
    }
  }
  if (typeof clipboard.read === "function") {
    let items = [];
    try { items = await clipboard.read(); }
    catch (e) { failures.push(e); }
    for (const item of items) {
      for (const type of item.types.filter(t => ["image/png", "image/jpeg", "image/webp"].includes(t))) {
        try {
          const blob = await item.getType(type);
          if (blob.size > 32 * 1024 * 1024) throw new Error("画像は32MiB以下にしてください");
          return await importImageBytes(new Uint8Array(await blob.arrayBuffer()), type, "クリップボード画像");
        } catch (e) {
          // Other representations/items may still contain a usable image.
          failures.push(e.name === "NotAllowedError" || e.name === "SecurityError" || e.name === "NotSupportedError"
            ? e : clipboardError("clipboard-invalid-image", e.message, e));
        }
      }
    }
  }
  const denied = failures.find(e => ["NotAllowedError", "SecurityError"].includes(e.name));
  if (denied)
    throw clipboardError("clipboard-denied", "クリップボードの読み取りが許可されていません。権限を確認するか、ファイル選択またはBase64入力を利用してください", denied);
  const invalid = failures.find(e => e.code === "clipboard-invalid-image");
  if (invalid) throw invalid;
  if (failures.length) {
    const unsupported = failures.every(e => e.name === "NotSupportedError");
    throw clipboardError(unsupported ? "clipboard-unsupported" : "clipboard-read-failed",
      unsupported ? "このブラウザではクリップボードの読み取りに対応していません" : "クリップボードの取得に失敗しました。再試行するかファイル選択を利用してください", failures[0]);
  }
  throw clipboardError("clipboard-no-image", "クリップボードにPNG・JPEG・WebP画像または画像Base64テキストがありません");
});
$("blank").onclick = () => {
  change((doc) => {
    doc.layers = [];
  });
  selected = null;
  message("新しいキャンバス（戻すで復帰できます）");
};
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
// --- Clipboard Shelf ---
const shelfItems = [];
const SHELF_MAX_BYTES = 32 * 1024 * 1024;
let shelfReservedBytes = 0, shelfReservedCount = 0, shelfGeneration = 0;
function shelfRemaining() {
  return SHELF_MAX_BYTES - shelfReservedBytes - shelfItems.reduce((sum, item) => sum + item.size, 0);
}
function checkShelfCapacity(size) {
  if (shelfItems.length + shelfReservedCount >= 20)
    throw new Error("シェルフの項目は最大20件までです");
  if (size > shelfRemaining()) throw new Error("シェルフ全体は32MiB以下にしてください");
}
function shelfTextSize(text) {
  const remaining = shelfRemaining();
  if (text.length > remaining) throw new Error("シェルフ全体は32MiB以下にしてください");
  let size = 0;
  for (const char of text) {
    const code = char.codePointAt(0);
    size += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    if (size > remaining) throw new Error("シェルフ全体は32MiB以下にしてください");
  }
  return size;
}
function hasRawImageSignature(text) {
  // Bound the amount decoded regardless of the original clipboard size.
  let prefix = "";
  for (const char of text) {
    if (!/\s/.test(char)) prefix += char;
    if (prefix.length === 16) break;
  }
  if (prefix.startsWith("iVBORw0KGg") || prefix.startsWith("/9j/")) return true;
  try { return !!C.imageType(Uint8Array.from(atob(prefix), c => c.charCodeAt(0))); }
  catch { return false; }
}
function isImageText(text) {
  return /^data:/i.test(text) || hasRawImageSignature(text);
}
function addShelfText(text, label) {
  const value = text.replace(/^\uFEFF/, "").trim();
  if (!value) throw new Error("テキストを入力してください");
  checkShelfCapacity(0);
  if (isImageText(value)) {
    const { bytes, mime } = imageBase64(value, shelfRemaining());
    addShelfItem(bytes, mime, null, label);
  } else addShelfItem(null, null, text, label);
}
function checkShelfGeneration(generation) {
  if (generation !== shelfGeneration) throw new Error("シェルフはクリアされました");
}
async function addShelfBlob(blob, mime, generation) {
  checkShelfGeneration(generation);
  if (blob.type && blob.type.toLowerCase() !== mime)
    throw new Error("画像MIMEが一致しません");
  if (!blob.size) throw new Error("画像が空です");
  checkShelfCapacity(blob.size); // Must precede arrayBuffer(), including in-flight additions.
  shelfReservedBytes += blob.size;
  shelfReservedCount++;
  let bytes;
  try { bytes = new Uint8Array(await blob.arrayBuffer()); }
  finally { shelfReservedBytes -= blob.size; shelfReservedCount--; }
  checkShelfGeneration(generation);
  addShelfItem(bytes, mime, null, "クリップボード画像");
}
async function shelfCopyText(item) {
  if (!item.bytes) return item.rawText;
  // FileReader produces a portable data URI, never the preview's transient blob URL.
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(new Blob([item.bytes], { type: item.mime }));
  });
}
function releaseShelfItem(item) {
  if (item.dataUrl) URL.revokeObjectURL(item.dataUrl);
}
function renderShelf() {
  $("shelf-copy-text").hidden = true;
  $("shelf-copy-text").value = "";
  const container = $("shelf-items-container");
  container.replaceChildren();
  if (!shelfItems.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "シェルフは空です。「クリップボードから追加」またはテキスト入力からデータを追加できます。";
    container.append(empty);
    return;
  }
  shelfItems.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "shelf-card";

    const info = document.createElement("div");
    info.className = "shelf-card-info";

    if (item.dataUrl) {
      const img = document.createElement("img");
      img.className = "shelf-thumb";
      img.src = item.dataUrl;
      img.alt = item.label;
      info.append(img);
    }

    const details = document.createElement("div");
    details.className = "shelf-details";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${item.label}`;
    const sub = document.createElement("span");
    sub.textContent = `${item.mime || "text"} ・ ${item.sizeText}`;
    details.append(title, sub);
    info.append(details);

    const actions = document.createElement("div");
    actions.className = "shelf-card-actions";

    if (item.bytes) {
      const btnImport = document.createElement("button");
      btnImport.textContent = "取り込み";
      btnImport.onclick = guarded(async () => {
        await importImageBytes(item.bytes, item.mime, item.label);
        $("shelf-dialog").close();
      });
      actions.append(btnImport);
    }

    const btnCopy = document.createElement("button");
    btnCopy.textContent = item.bytes ? "データURLをコピー" : "コピー";
    btnCopy.onclick = guarded(async () => {
      const field = $("shelf-copy-text");
      field.hidden = true;
      field.value = "";
      await copyDialogText(await shelfCopyText(item), field, $("shelf-status"),
        `「${item.label}」をクリップボードにコピーしました`,
        "自動コピーが使えません。選択した文字をコピーしてください。");
    });
    actions.append(btnCopy);

    const btnDel = document.createElement("button");
    btnDel.textContent = "削除";
    btnDel.onclick = () => {
      const current = shelfItems.indexOf(item);
      if (current !== -1) releaseShelfItem(shelfItems.splice(current, 1)[0]);
      renderShelf();
    };
    actions.append(btnDel);

    card.append(info, actions);
    container.append(card);
  });
}
function addShelfItem(bytes, mime, rawText, label = "シェルフ項目") {
  // This is also the final gate for binary callers and rechecks after async reads.
  const size = bytes ? bytes.length : shelfTextSize(rawText || "");
  checkShelfCapacity(size);
  if (bytes) {
    const actual = bytes instanceof Uint8Array && C.imageType(bytes);
    if (!actual || (mime && mime.toLowerCase() !== actual))
      throw new Error("画像形式またはMIME宣言が実データと一致しません");
    mime = actual;
    rawText = null; // Avoid retaining another full Base64 copy of an image.
  } else if (mime || isImageText((rawText || "").trim())) {
    throw new Error("画像入力には検証済みデータが必要です");
  }
  let dataUrl = null;
  if (bytes && mime) {
    const blob = new Blob([bytes], { type: mime });
    dataUrl = URL.createObjectURL(blob);
  }
  const sizeText = bytes ? `${bytes.length.toLocaleString()} bytes` : `${(rawText || "").length} chars`;
  shelfItems.unshift({
    id: uid(),
    bytes,
    mime,
    rawText,
    dataUrl,
    label,
    sizeText,
    size,
  });
  renderShelf();
}
STUDIO_ACTS.shelf = () => {
  renderShelf();
  $("shelf-dialog").showModal();
};
$("shelf-clear").onclick = () => {
  shelfGeneration++;
  shelfItems.forEach(releaseShelfItem);
  shelfItems.length = 0;
  renderShelf();
  $("shelf-status").textContent = "シェルフをクリアしました";
};
$("shelf-paste-clip").onclick = guarded(async () => {
  if (!navigator.clipboard) throw new Error("Clipboard APIが使用できません");
  const generation = shelfGeneration;
  checkShelfCapacity(0);
  let text = "";
  if (navigator.clipboard.readText) {
    // A denied text permission may still allow a binary clipboard image.
    try { text = await navigator.clipboard.readText(); } catch { /* try binary API */ }
    checkShelfGeneration(generation);
    if (text.trim() && isImageText(text.trim())) {
      addShelfText(text, "クリップボードBase64");
      $("shelf-status").textContent = "クリップボードのBase64画像を追加しました";
      return;
    }
  }
  if (navigator.clipboard.read) {
    let items = [];
    try { items = await navigator.clipboard.read(); }
    catch (e) { if (!text.trim()) throw e; }
    checkShelfGeneration(generation);
    for (const item of items) {
      const type = item.types.find(t => ["image/png", "image/jpeg", "image/webp"].includes(t));
      if (type) {
        const blob = await item.getType(type);
        await addShelfBlob(blob, type, generation);
        $("shelf-status").textContent = "クリップボードの画像を追加しました";
        return;
      }
      if (item.types.some(t => t.startsWith("image/")))
        throw new Error("対応していない画像MIMEです");
    }
  }
  if (text.trim()) {
    addShelfText(text, "クリップボードテキスト");
    $("shelf-status").textContent = "テキスト項目を追加しました";
  } else {
    throw new Error("クリップボードに画像またはテキストがありません");
  }
});

$("shelf-add-text").onclick = guarded(async () => {
  const val = $("shelf-input-text").value;
  addShelfText(val, "入力項目");
  $("shelf-status").textContent = "項目を追加しました";
  $("shelf-input-text").value = "";
});

// Read-only snapshots and export entry point also make browser regression tests observable.
window.IronmateStudio = {
  get scene() {
    return copy(scene);
  },
  get ready() {
    return render();
  },
  pngBlob,
  importImageFile,
  // 🧰 what a toolbar press runs, awaitable from Node or a host: act("clipboard"), act("png"), act("image", file) (a File or Blob)
  act: (name, value) => STUDIO_ACTS[name]?.(value),
  get selectedId() { return selected; },
  async replaceScene(value) {
    const next = C.validate(value);
    await prepare(next);
    scene = next; history = new C.History(next); selected = null; dirty = true;
    await render();
  },
  async imageSource(value) { return prepare(C.validate(value)); },
  patchSelected(properties) {
    if (!selectedLayer()) throw new Error("先にレイヤーを選択してください");
    change(doc => Object.assign(doc.layers.find(l => l.id === selected), properties));
  },
  get shelfItems() { return shelfItems.map(item => ({ ...item })); },
  addShelfItem,
};
render().catch(error);
})();

/* PSWB pixel-editor.js */
function bindPixelEditor({ root, catalog, gridTools: C, save, pngPayload, status }) {
  const $ = id => root.querySelector("#" + id);
  let grid, previous = null;
  const action = (id, fn) => $(id).addEventListener("click", () =>
    Promise.resolve().then(fn).catch(error => status(error.message, true))
  );
  const choose = (id, items) => {
    $(id).replaceChildren(
      ...items.map(([value, text]) => new Option(text, value)),
    );
  };
  choose(
    "mask",
    catalog.masks.map((x) => [
      x,
      {
        triangle: "三角",
        diamond: "ひし形",
        cloud: "雲",
        circle: "丸",
        rock: "岩",
      }[x],
    ]),
  );
  $("mask").value = "cloud";
  choose(
    "size",
    catalog.sizes.map((x) => [x, `${x} × ${x}`]),
  );
  $("size").value = 32;
  choose(
    "effect",
    catalog.effects.map((x) => [
      x,
      {
        normal: "通常",
        shadow: "影",
        highlight: "ハイライト",
        outline: "輪郭",
      }[x],
    ]),
  );
  choose(
    "palette",
    Object.keys(catalog.palettes).map((x) => [
      x,
      `${x} / ${catalog.labels[x]}`,
    ]),
  );
  function draw() {
    const canvas = $("grid");
    canvas.width = grid.width;
    canvas.height = grid.height;
    const ctx = canvas.getContext("2d"),
      data = ctx.createImageData(grid.width, grid.height);
    grid.pixels.forEach((row, y) =>
      row.forEach((i, x) => {
        const color = grid.colors[i];
        for (let k = 0; k < 4; k++)
          data.data[(y * grid.width + x) * 4 + k] = parseInt(
            color.slice(1 + k * 2, 3 + k * 2),
            16,
          );
      }),
    );
    ctx.putImageData(data, 0, 0);
    // CSS scales the canvas; the backing pixels remain the original grid.
    $("width").value = grid.width;
    $("height").value = grid.height;
    $("grid-info").textContent =
      `${grid.width} × ${grid.height} cells · ${grid.colors.length} colors`;
    choose(
      "ink",
      grid.colors.map((c, i) => [i, `${i} / ${c}`]),
    );
    $("ink").value = Math.min(1, grid.colors.length - 1);
    $("base64-output").value = "";
  }
  function update(value) {
    const next = C.canonical(value);
    previous = grid;
    grid = next;
    draw();
  }
  function generate() {
    const mask = $("mask").value,
      effect = $("effect").value,
      size = Number($("size").value),
      palette = $("palette").value;
    const rows = catalog.grids[`${mask}/${effect}/${size}`];
    update({
      schema: "ironmate-pixel-grid/1",
      mask,
      effect,
      palette,
      width: size,
      height: size,
      colors: catalog.palettes[palette],
      pixels: rows.map((r) => Array.from(r, Number)),
      resampling: "procedural_mask",
    });
    status(
      "Python版のプリセットから生成しました。クリックで色番号を編集できます。",
    );
  }
  async function png() {
    const scale = Number($("scale").value),
      g = C.canonical(grid),
      width = g.width * scale,
      height = g.height * scale;
    // Direct RGBA encoding preserves hidden RGB in transparent cells, unlike Canvas exports.
    if (!globalThis.CompressionStream)
      throw Error(
        "PNG出力にはCompressionStream対応ブラウザが必要です。JSON / SVG保存を利用できます。",
      );
    const bytes = new Uint8Array(height * (1 + 4 * width));
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) {
        const color =
          g.colors[g.pixels[Math.floor(y / scale)][Math.floor(x / scale)]];
        for (let k = 0; k < 4; k++)
          bytes[y * (width * 4 + 1) + 1 + x * 4 + k] = parseInt(
            color.slice(1 + 2 * k, 3 + 2 * k),
            16,
          );
      }
    const compressed = await new Response(
      new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate")),
    ).arrayBuffer();
    const ihdr = new Uint8Array(13),
      view = new DataView(ihdr.buffer);
    view.setUint32(0, width);
    view.setUint32(4, height);
    ihdr[8] = 8;
    ihdr[9] = 6;
    const metadata =
      "ironmate\0" +
      JSON.stringify(C.pngHeader(g)).replace(
        /[\u007f-\uffff]/g,
        (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
      );
    return new Blob(
      [
        new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]),
        C.pngChunk("IHDR", ihdr),
        C.pngChunk("tEXt", new TextEncoder().encode(metadata)),
        C.pngChunk("IDAT", new Uint8Array(compressed)),
        C.pngChunk("IEND", new Uint8Array()),
      ],
      { type: "image/png" },
    );
  }
  action("generate", generate);
  action("resize", () => {
    update(C.resize(grid, Number($("width").value), Number($("height").value)));
    status("最近傍でサイズ変更しました。縮小は不可逆です。");
  });
  action("recolor", () => {
    if (grid.colors.length > 5)
      throw Error("配色IDの置換は5役割までのグリッドに対応します。");
    update({
      ...grid,
      palette: $("palette").value,
      colors: catalog.palettes[$("palette").value],
    });
    status("色番号を保持して配色を変更しました。");
  });
  action("undo-grid", () => {
    if (previous) {
      [grid, previous] = [previous, grid];
      draw();
      status("ひとつ前の状態に戻しました。");
    }
  });
  action("grid-json", () =>
    save("ironmate-grid.json", JSON.stringify(grid, null, 2), "application/json"),
  );
  action("grid-svg", () =>
    save("ironmate-grid.svg", C.svg(grid, Number($("scale").value)), "image/svg+xml"),
  );
  action("grid-png", async () =>
    save("ironmate-grid.png", await png(), "image/png"),
  );
  action("grid-base64", async () => {
    const blob = await png(),
      bytes = new Uint8Array(await blob.arrayBuffer());
    $("base64-output").value = pngPayload(bytes).dataUri;
    status(
      `PNG ${blob.size.toLocaleString()} bytes / data URI ${C.base64Length(blob.size, true).toLocaleString()}文字。選択してコピーできます。`,
    );
  });
  $("grid").addEventListener("click", (e) => {
    const bounds = e.currentTarget.getBoundingClientRect(),
      x = Math.min(
        grid.width - 1,
        Math.floor(((e.clientX - bounds.left) * grid.width) / bounds.width),
      ),
      y = Math.min(
        grid.height - 1,
        Math.floor(((e.clientY - bounds.top) * grid.height) / bounds.height),
      ),
      ink = $("ink").value;
    const next = C.canonical(grid);
    next.pixels[y][x] = Number(ink);
    next.resampling = "edited";
    update(next);
    $("ink").value = ink;
    status("セルを編集しました。");
  });
  $("grid-file").addEventListener("change", async (e) => {
    try {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 4 * 1024 * 1024) throw Error("JSONは4MiB以下です。");
      update(JSON.parse(await file.text()));
      status("グリッドJSONを読み込みました。");
    } catch (err) {
      status(err.message, true);
    } finally {
      e.target.value = "";
    }
  });
  generate();
  return { get grid() { return C.canonical(grid); }, png };
}
/* End PSWB pixel-editor.js */

/* PSWB current-item.js */
function setCurrentItem(list, index) {
  const next = Number.isInteger(index) ? list.children[index] : undefined;
  for (const item of list.children) {
    if (item === next) {
      if (item.getAttribute("aria-current") !== "step") item.setAttribute("aria-current", "step");
    } else if (item.hasAttribute("aria-current")) {
      item.removeAttribute("aria-current");
    }
  }
}
/* End PSWB current-item.js */

/* Tools page UI (data-page~="tools"): browser only. */
if (typeof document !== "undefined" && (document.getElementById("pixel-editor") || document.getElementById("digest"))) (function () {
"use strict";
  const $ = (id) => document.getElementById(id);
  const C = IronmateTools;
  const status = (text, error = false) => {
    const output = $("pixel-status") || $("message");
    output.textContent = text;
    output.dataset.error = error;
  };
  const action = (id, fn) =>
    $(id).addEventListener("click", () =>
      Promise.resolve()
        .then(fn)
        .catch((e) => status(e.message, true)),
    );
  const { save, picture } = StudioCore;
  const editor = $("pixel-editor");
  if (editor) {
    editor.addEventListener("toggle", function start() {
      if (!editor.open) return;
      editor.removeEventListener("toggle", start);
      const workbench = bindPixelEditor({
        root: $("pixels"), catalog: buildIronmateCatalog(), gridTools: C, save,
        pngPayload: StudioCore.pngPayload, status,
      });
      window.IronmateWorkbench = workbench;
      action("place-grid", async () => {
        await window.IronmateStudio.importImageFile(new File([await workbench.png()], "ドット絵.png", { type: "image/png" }));
        editor.open = false;
      });
    });
    return;
  }
  const songSections = $("song-sections");
  function updateArrangement() {
    setCurrentItem(songSections, null);
    try {
      const parts = IronmateComposition.arrangeSong($("song-parts").value, $("song-order").value);
      songSections.replaceChildren(...parts.map(({name}) => {
        const item = document.createElement("li");
        item.textContent = name;
        return item;
      }));
      $("song-progression").value = parts.flatMap(part => part.chords).join(" ");
      $("song-status").textContent = "曲順に展開しました。";
      return parts;
    } catch (err) {
      songSections.replaceChildren();
      $("song-progression").value = "";
      $("song-status").textContent = err.message;
      return null;
    }
  }
  $("song-arrange").onclick = () => {
    $("song-stop").click();
    updateArrangement();
  };
  $("song-stop").onclick = () => {
    document.dispatchEvent(new Event("studio-audio-stop"));
    setCurrentItem(songSections, null);
    $("song-status").textContent = "停止しました。";
  };
  $("song-play").onclick = () => {
    $("song-stop").click();
    const parts = updateArrangement();
    if (!parts || !$("song-bpm").reportValidity()) return;
    try {
      const key = $("song-key").value;
      const bpm = Number($("song-bpm").value);
      const {notes, starts} = IronmateComposition.planSong(parts, key, bpm);
      document.dispatchEvent(new CustomEvent("studio-audio-play", { detail: {
        notes,
        report: text => { $("song-status").textContent = text; },
        position: elapsed => setCurrentItem(songSections, elapsed === null ? null : starts.findLastIndex(start => start <= elapsed)),
      } }));
    } catch (err) { $("song-status").textContent = err.message; }
  };
  let images = [];
  let imageGeneration = 0;
  let imageLoad;
  $("images-cancel").onclick = () => imageLoad?.cancel();
  window.addEventListener("pagehide", () => imageLoad?.cancel());
  $("images").addEventListener("change", async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    e.target.value = "";
    const generation = ++imageGeneration;
    imageLoad?.cancel();
    $("images-cancel").hidden = true;
    $("digest-png").disabled = true;
    $("digest-html").disabled = true;
    try {
      if (
        files.length > 20 ||
        files.some((f) => f.size > 8 * 1024 * 1024) ||
        files.reduce((s, f) => s + f.size, 0) > 32 * 1024 * 1024
      )
        throw Error("画像は20枚、1枚8MiB、合計32MiB以下です。");
      const {startTask} = await import(new URL("./async-task.js", document.baseURI));
      if (generation !== imageGeneration) return;
      imageLoad = startTask(async signal => {
        const thumbnails = [];
        for (const file of files) {
          signal.throwIfAborted();
          const {src, canvas} = await picture(file, 512, signal); // checks the type from the bytes
          thumbnails.push({name: file.name, src, canvas});
        }
        return thumbnails;
      }, {timeoutMs: 30000});
      $("images-cancel").hidden = false;
      const next = await imageLoad.promise;
      if (generation !== imageGeneration) return;
      images = next;
      $("image-list").replaceChildren(
        ...images.map((item) => {
          const figure = document.createElement("figure"),
            image = new Image(),
            caption = document.createElement("figcaption");
          image.src = item.src;
          image.alt = item.name;
          caption.textContent = item.name;
          figure.append(image, caption);
          return figure;
        }),
      );
      status(
        `${images.length}枚を読み込みました。表示用サムネイルに縮小しています。`,
      );
    } catch (err) {
      if (generation === imageGeneration) {
        if (err.name === "AbortError") status("画像の読み込みを中止しました。");
        else if (err.name === "TimeoutError") status("画像の読み込みがタイムアウトしました。", true);
        else status(err.message, true);
      }
    } finally {
      if (generation === imageGeneration) {
        imageLoad = undefined;
        $("images-cancel").hidden = true;
        $("digest-png").disabled = !images.length;
        $("digest-html").disabled = !images.length;
      }
    }
  });
  action("digest-png", async () => {
    const columns = Number($("columns").value),
      canvas = document.createElement("canvas");
    canvas.width = columns * 288;
    canvas.height = Math.ceil(images.length / columns) * 260;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#f2f6f3";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "14px sans-serif";
    images.forEach((item, i) => {
      const x = (i % columns) * 288,
        y = Math.floor(i / columns) * 260,
        ratio = Math.min(256 / item.canvas.width, 210 / item.canvas.height);
      ctx.drawImage(
        item.canvas,
        x + 16 + (256 - item.canvas.width * ratio) / 2,
        y + 12 + (210 - item.canvas.height * ratio) / 2,
        item.canvas.width * ratio,
        item.canvas.height * ratio,
      );
      ctx.fillStyle = "#183d42";
      ctx.fillText(item.name, x + 16, y + 244, 256);
    });
    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/png"),
    );
    if (!blob) throw Error("一覧PNGを生成できませんでした。");
    save("ironmate-digest.png", blob, "image/png");
  });
  action("digest-html", () => {
    const columns = Number($("columns").value),
      html = `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'"><title>Ironmate Image Digest</title><style>body{font:14px system-ui;background:#f2f6f3;color:#183d42;margin:24px}.grid{display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:16px}figure{margin:0;padding:16px;background:white;overflow-wrap:anywhere}img{width:100%;height:210px;object-fit:contain}@media(max-width:600px){.grid{grid-template-columns:1fr}}</style><h1>Ironmate Image Digest</h1><div class="grid">${images.map((i) => `<figure><img src="${i.src}" alt="${C.esc(i.name)}"><figcaption>${C.esc(i.name)}</figcaption></figure>`).join("")}</div></html>`;
    save("ironmate-digest.html", html, "text/html");
  });
})();

/* ⬇️ pysaiyanweboo ed32bdf8 (stage, pager, labels-switch, toolbar): written by scripts/build_studio_css.py from the pinned commit; --check fails when it drifts */
(() => {
/* A rotary dial over a range input (dial_html): drag around its centre, turn the wheel, or use the range's own keys. Value and events stay the input's. */
function dialAngle(value,min,max){const span=max-min;const t=span>0?(Number(value)-min)/span:0;return -135+270*Math.min(1,Math.max(0,t))}
function dialValue(angle,min,max,step){const t=(Math.min(135,Math.max(-135,angle))+135)/270,raw=min+t*(max-min),s=step>0?step:1;
 const v=min+Math.round((raw-min)/s)*s;return Math.min(max,Math.max(min,Number(v.toFixed(6))))}
function bindDial(root=document){
 for(const dial of root.querySelectorAll("[data-ui-dial]")){const input=dial.querySelector('input[type="range"]');if(!input||dial.dataset.uiDialBound)continue;dial.dataset.uiDialBound="";
  const num=k=>Number(input[k])||0,paint=()=>dial.style.setProperty("--ui-dial-angle",dialAngle(input.value,num("min"),num("max"))+"deg");
  const turn=(x,y)=>{const r=dial.getBoundingClientRect(),a=Math.atan2(x-(r.left+r.width/2),(r.top+r.height/2)-y)*180/Math.PI;
   const v=dialValue(a,num("min"),num("max"),Number(input.step)||0);if(String(v)===input.value)return;input.value=v;input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))};
  dial.addEventListener("pointerdown",e=>{if(e.button)return;e.preventDefault();dial.setPointerCapture(e.pointerId);dial.dataset.uiDialDrag="";input.focus({preventScroll:true});turn(e.clientX,e.clientY)});
  dial.addEventListener("pointermove",e=>{if("uiDialDrag"in dial.dataset)turn(e.clientX,e.clientY)});
  for(const t of["pointerup","pointercancel","lostpointercapture"])dial.addEventListener(t,()=>{delete dial.dataset.uiDialDrag});
  dial.addEventListener("wheel",e=>{e.preventDefault();e.deltaY<0?input.stepUp():input.stepDown();input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}))},{passive:false});
  input.addEventListener("input",paint);paint()}}
if(typeof document!=="undefined")bindDial();
/* 🧭 Page controls (pager_html): every variant is in the markup and the stylesheet shows one, so data-ui-pager switches it with no reload.
 pagerIndex takes pager_index's steps; a change sends ui-pager {index, count}; pagerSet(el, index, count) follows a change the page made itself. */
function pagerIndex(index,count,action,wrap=false){const last=Math.max(0,count-1);
 if(typeof action==="number")return Math.min(last,Math.max(0,Math.trunc(action)));
 if(action==="first"||action==="last")return action==="first"?0:last;
 if(action!=="prev"&&action!=="next")throw Error("unknown pager action: "+action);
 const target=index+(action==="next"?1:-1);return wrap&&count>0?((target%count)+count)%count:Math.min(last,Math.max(0,target))}
function pagerSet(el,index=Number(el.dataset.uiPagerIndex)||0,count=Number(el.dataset.uiPagerCount)||1){
 count=Math.max(1,Math.trunc(count));index=pagerIndex(0,count,index);const wrap="uiPagerWrap"in el.dataset;el.dataset.uiPagerIndex=index;el.dataset.uiPagerCount=count;
 for(const b of el.querySelectorAll("[data-ui-pager-go]"))b.disabled=pagerIndex(index,count,b.dataset.uiPagerGo,wrap)===index;
 for(const o of el.querySelectorAll('output[data-ui-pager-part="page"]'))o.textContent=`${index+1}/${count}`;
 for(const dots of el.querySelectorAll('[data-ui-pager-part="dots"]')){const word=dots.dataset.uiPagerWord||"Page";
  while(dots.children.length<count)dots.append(Object.assign(document.createElement("button"),{type:"button"}));
  while(dots.children.length>count)dots.lastElementChild.remove();
  [...dots.children].forEach((d,i)=>{d.dataset.uiPagerTo=i;d.textContent=i===index?"●":"○";d.title=`${word} ${i+1}`;d.setAttribute("aria-label",d.title);
   i===index?d.setAttribute("aria-current","page"):d.removeAttribute("aria-current")})}
 for(const r of el.querySelectorAll('input[type="range"]')){r.max=Math.max(2,count);r.disabled=count<2;
  if(r.value!==String(index+1)){r.value=index+1;r.dispatchEvent(new Event("input"))}}}
function bindPager(root=document){
 for(const el of root.querySelectorAll("[data-ui-pager]")){if("uiPagerBound"in el.dataset)continue;el.dataset.uiPagerBound="";
  const go=action=>{const index=Number(el.dataset.uiPagerIndex)||0,count=Number(el.dataset.uiPagerCount)||1,next=pagerIndex(index,count,action,"uiPagerWrap"in el.dataset);
   pagerSet(el,next,count);if(next!==index)el.dispatchEvent(new CustomEvent("ui-pager",{bubbles:true,detail:{index:next,count}}))};
  el.addEventListener("pointerdown",e=>{if(e.target.closest("button"))e.preventDefault()});
  el.addEventListener("click",e=>{const b=e.target.closest("[data-ui-pager-go],[data-ui-pager-to]");if(b&&!b.disabled)go(b.dataset.uiPagerGo??Number(b.dataset.uiPagerTo))});
  el.addEventListener("input",e=>{if(e.target.type==="range")go(Number(e.target.value)-1)});
  if("uiPagerKeys"in el.dataset)document.addEventListener("keydown",e=>{const action={ArrowLeft:"prev",ArrowRight:"next",Home:"first",End:"last"}[e.key];
   if(!action||e.defaultPrevented||e.altKey||e.ctrlKey||e.metaKey||!el.isConnected||e.target.closest?.("input,textarea,select,[contenteditable]"))return;e.preventDefault();go(action)});
  pagerSet(el)}}
if(typeof document!=="undefined")bindPager();
/** Set text-only content. User-controlled values are never interpreted as HTML. */
function setText(target,value){const node=typeof target==="string"?document.querySelector(target):target;if(node)node.textContent=String(value)}
/** Serialize a value for human-readable text output. */
function prettyJson(value){return JSON.stringify(value,null,2)}
/** Copy a value as text; falls back to a hidden textarea where the async clipboard is missing (plain http, old WebViews). */
async function copyText(value){const text=String(value);try{await navigator.clipboard.writeText(text)}catch(error){const box=document.createElement("textarea");box.value=text;box.setAttribute("readonly","");box.style.cssText="position:fixed;opacity:0";try{document.body.append(box);box.select();if(typeof document.execCommand!=="function"||!document.execCommand("copy"))throw error}finally{box.remove()}}}
/** [data-ui-copy] copies the <pre> of its .ui-code box with copyText; the button shows data-ui-copied (or data-ui-copy-failed) for a moment. Returns the buttons. */
function bindCopy(root=document){const buttons=[...root.querySelectorAll("[data-ui-copy]")];for(const button of buttons){const box=button.closest(".ui-code"),pre=box&&box.querySelector("pre");if(!pre)continue;const label=button.textContent;button.addEventListener("click",async()=>{let ok=true;try{await copyText(pre.textContent)}catch{ok=false}button.textContent=(ok?button.dataset.uiCopied:button.dataset.uiCopyFailed)||label;setTimeout(()=>{button.textContent=label},1600)})}return buttons}
/** Buttons with data-ui-toggle flip aria-pressed on click (memory only: nothing is saved); data-label-on / data-label-off, when present, rename the button. */
function bindToggles(root=document){return[...root.querySelectorAll("[data-ui-toggle]")].map(b=>{const sync=()=>{const label=b.getAttribute("aria-pressed")==="true"?b.dataset.labelOn:b.dataset.labelOff;if(label){b.setAttribute("aria-label",label);b.title=label}};b.addEventListener("click",()=>{b.setAttribute("aria-pressed",String(b.getAttribute("aria-pressed")!=="true"));sync()});sync();return b})}
/** Switch data-ui-theme on <body> with no reload: controls are <select data-ui-theme-switch> or radios named ui-theme. The choice is remembered (localStorage, best effort) and marked on <body> as data-ui-theme-chosen. An empty-valued option means "the page's own theme" (data-ui-theme-page, by default the theme at bind time; see pageTheme): choosing it forgets the choice. Returns the theme in effect. */
function bindTheme(root=document,{key="web-ui-theme"}={}){const body=document.body,controls=[...root.querySelectorAll("[data-ui-theme-switch],input[name=ui-theme]")];const known=name=>controls.some(c=>c.tagName==="SELECT"?[...c.options].some(o=>o.value===name):c.value===name);if(body.dataset.uiThemePage===undefined)body.dataset.uiThemePage=body.dataset.uiTheme||"";const sync=()=>{const chosen=body.dataset.uiThemeChosen;for(const c of controls){if(c.tagName==="SELECT")c.value=chosen===undefined&&[...c.options].some(o=>o.value==="")?"":body.dataset.uiTheme;else c.checked=c.value===body.dataset.uiTheme}};const choose=name=>{if(name){body.dataset.uiThemeChosen=name;body.dataset.uiTheme=name}else{delete body.dataset.uiThemeChosen;body.dataset.uiTheme=body.dataset.uiThemePage}};let saved=null;try{saved=localStorage.getItem(key)}catch{}if(saved&&known(saved))choose(saved);sync();for(const c of controls)c.addEventListener("change",()=>{if(!known(c.value))return;choose(c.value);sync();try{if(c.value)localStorage.setItem(key,c.value);else localStorage.removeItem(key)}catch{}});return body.dataset.uiTheme}
/** Switch data-ui-labels on <body> with no reload: "emoji" (the default: icon faces) or "words" (as on a PC: every [data-ui-word] shows its short word instead of its face; CSS in components.css). Buttons with data-ui-labels-switch flip it (aria-pressed is true while words show), and so does a header row whose key is "labels" (the ui-chrome-action event). A flip is remembered (localStorage, best effort). Returns the labels in effect. */
function bindLabels(root=document,{key="web-ui-labels"}={}){const body=document.body,buttons=[...root.querySelectorAll("[data-ui-labels-switch]")];const show=v=>{body.dataset.uiLabels=v==="words"?"words":"emoji";for(const b of buttons)b.setAttribute("aria-pressed",String(body.dataset.uiLabels==="words"));return body.dataset.uiLabels};let saved=null;try{saved=localStorage.getItem(key)}catch{}show(saved||body.dataset.uiLabels);const flip=()=>{const v=show(body.dataset.uiLabels==="words"?"emoji":"words");try{localStorage.setItem(key,v)}catch{}};for(const b of buttons)b.addEventListener("click",flip);document.addEventListener("ui-chrome-action",e=>{if(e.detail&&e.detail.key==="labels")flip()});return body.dataset.uiLabels}
/** A toolbar from toolbar_html(): a click on a [data-act] control calls run(act), a button with candidates too (a mode such as 🔷 on a canvas becomes the tool as its row opens; a page with nothing to do for it ignores the name). A button with data-candidates opens its candidates in the toolbar's one candidate row ([data-ui-candidates]), right under its own row; pressing it again closes them. A candidate calls run(its data-acts entry) or, when it names no action, run(the button's act, the candidate's face), and data-close hides the row after the pick. Each candidate's words (data-words, "|"-separated) are its title, aria-label and, up to "（", its data-ui-word. Pressing a control keeps the focus where it was, so a text being typed stays open. A candidate whose act has a chooser ([data-ui-file], from a candidate with accept) opens it instead, and the chosen File runs run(act, file). Returns {offer(button), close(), choose(act)}: choose opens an act's chooser from the page (a host's key). */
function bindToolbar(root,run){const row=root.querySelector("[data-ui-candidates]"),files={};for(const f of root.querySelectorAll("[data-ui-file]")){files[f.dataset.uiFile]=f;f.addEventListener("change",()=>{const x=f.files&&f.files[0];f.value="";if(x)run(f.dataset.uiFile,x)})}const close=()=>{if(!row)return;row.hidden=true;row.dataset.tool="";row.replaceChildren()};const offer=b=>{if(!row)return;if(row.dataset.tool===b.dataset.act&&!row.hidden)return close();const faces=b.dataset.candidates.split(" "),acts=(b.dataset.acts||"").split(" "),words=(b.dataset.words||"").split("|");row.dataset.tool=b.dataset.act;b.closest(".ui-toolbar-row").after(row);row.hidden=false;row.replaceChildren(...faces.map((face,i)=>{const c=document.createElement("button");c.type="button";c.textContent=face;const said=words[i]||face;c.title=said;c.setAttribute("aria-label",said);if(words[i])c.dataset.uiWord=said.split("（")[0];c.addEventListener("click",()=>{if(files[acts[i]])files[acts[i]].click();else if(acts[i])run(acts[i]);else run(b.dataset.act,face);if("close"in b.dataset)close()});return c}))};root.addEventListener("pointerdown",e=>{if(e.target.closest("button,a"))e.preventDefault()});root.addEventListener("click",e=>{const b=e.target.closest("[data-act]");if(!b||!root.contains(b)||b.disabled)return;if(b.dataset.candidates)offer(b);run(b.dataset.act)});return{offer,close,choose:a=>files[a]&&files[a].click()}}
/** Tell bindTheme which theme is the page's own (a page whose own look changes, such as display modes): it shows unless the visitor chose one. Returns the theme in effect. */
function pageTheme(name){const body=document.body;body.dataset.uiThemePage=name;if(body.dataset.uiThemeChosen===undefined)body.dataset.uiTheme=name;return body.dataset.uiTheme}
/** Mark on-screen elements with data-lit (IntersectionObserver); CSS decides what lit looks like. Without IntersectionObserver every element counts as lit. Returns a stop function. */
function observeLit(targets,{threshold=0.4,root=null}={}){const nodes=typeof targets==="string"?[...document.querySelectorAll(targets)]:[...targets];if(typeof IntersectionObserver==="undefined"){for(const n of nodes)n.dataset.lit="";return()=>{}}const io=new IntersectionObserver(entries=>{for(const e of entries){if(e.isIntersecting)e.target.dataset.lit="";else delete e.target.dataset.lit}},{threshold,root});for(const n of nodes)io.observe(n);return()=>io.disconnect()}
/** Click-to-enlarge for <a href="full.png"><img alt="..."></a> items inside [data-ui-lightbox]: one <dialog>; Esc, the backdrop and the close button shut it, arrows, buttons and a 48px swipe step through. Returns {open, close, dialog}, or null without items or <dialog>. */
function bindLightbox(root=document){const items=[...root.querySelectorAll("[data-ui-lightbox] a[href]")];if(!items.length||typeof HTMLDialogElement==="undefined")return null;const dialog=document.createElement("dialog");dialog.className="ui-lightbox";dialog.setAttribute("aria-label","Image viewer");dialog.innerHTML='<img alt=""><p class="ui-muted"></p><div class="ui-lightbox-bar"><button class="ui-button" type="button" data-step="-1" aria-label="Previous">\u2190</button><button class="ui-button" type="button" data-step="1" aria-label="Next">\u2192</button><button class="ui-button" type="button" data-step="0" aria-label="Close">\u00d7</button></div>';const img=dialog.querySelector("img"),note=dialog.querySelector("p");let at=0,x=null;const show=i=>{at=(i+items.length)%items.length;const a=items[at],t=a.querySelector("img");img.src=a.href;img.alt=note.textContent=t?t.alt:""};const open=i=>{show(i);if(!dialog.open)dialog.showModal()};items.forEach((a,i)=>a.addEventListener("click",e=>{e.preventDefault();open(i)}));dialog.addEventListener("click",e=>{const b=e.target.closest("[data-step]");if(b){const s=Number(b.dataset.step);if(s)show(at+s);else dialog.close()}else if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()}});dialog.addEventListener("keydown",e=>{if(e.key==="ArrowLeft")show(at-1);if(e.key==="ArrowRight")show(at+1)});dialog.addEventListener("pointerdown",e=>{x=e.clientX});dialog.addEventListener("pointerup",e=>{if(x!==null&&Math.abs(e.clientX-x)>=48)show(at+(e.clientX<x?1:-1));x=null});document.body.append(dialog);return{open,close:()=>dialog.close(),dialog}}
globalThis.PySaiyanWeBoo = { pagerSet, pagerIndex, bindLabels, bindToolbar };
})();
/* ⬆️ pysaiyanweboo */
/* Phone slides UI (data-page~="phone"): browser only. The slide stays pinned on top (PySaiyanWeBoo's 🖼️ stage), every control is
   an emoji (its words are in aria-label/title), PySaiyanWeBoo's pager (⬅️ 1/N ➡️) turns pages, and the deck is the same
   JSON / PPTX as Slide Studio. */
if (typeof document !== "undefined" && document.body && (document.body.dataset.page || "").split(" ").includes("phone")) (function () {
"use strict";
const C = window.StudioCore,
  D = window.IronmateSlides,
  $ = (id) => document.getElementById(id),
  stage = $("phone-stage"),
  edit = $("phone-edit"),
  pages = $("phone-pager"), // PySaiyanWeBoo's pager, as ⬅️ 1/N ➡️ (🗂️ shows every page)
  STORE = "ironmate-phone-deck",
  textSize = Number(document.body.dataset.textSize),
  scales = document.body.dataset.textScale.split(" ").map(Number),
  plain = scales.indexOf(1);
const blank = (w = 1280, h = 720) => ({ schema: C.SCHEMA, width: w, height: h, background: "#FFFFFF", layers: [] });
let deck = { schema: D.SCHEMA, title: "Ironmate", slides: [blank()] },
  active = 0,
  level = plain,
  textFactor = 1,
  selected = null,
  editing = null,
  editBefore = null,
  drag = null,
  frame = 0,
  serial = 0,
  past = [],
  future = [];
const slide = () => deck.slides[active],
  picked = () => slide().layers.find((l) => l.id === selected),
  uid = (kind) => `${kind}-${Date.now().toString(36)}-${++serial}`,
  pct = (v, of) => `${(v / of) * 100}%`,
  state = () => JSON.stringify({ deck, active, level, textFactor });
let status = "", statusError = false, saveFailed = false;
function note(text = status, error = statusError) {
  status = text;
  statusError = error;
  const s = $("phone-status");
  s.textContent = [text, saveFailed && "⚠️ 💾"].filter(Boolean).join(" ");
  s.dataset.error = error || saveFailed;
}
function restore(text) {
  const saved = JSON.parse(text);
  deck = D.validate(saved.deck);
  active = Math.min(Math.max(0, saved.active | 0), deck.slides.length - 1);
  level = scales[saved.level] ? saved.level : plain;
  textFactor = Number.isFinite(saved.textFactor) && saved.textFactor >= Math.min(...scales)
    && saved.textFactor <= Math.max(...scales) ? saved.textFactor : scales[level];
}
function keep() {
  try {
    localStorage.setItem(STORE, state());
    saveFailed = false;
  } catch {
    saveFailed = true; // 端末の自動保存がいっぱい（画像が大きいとき）。📤 で JSON に保存できる
  }
  saves += 1;
  note();
}
function record(before) {
  if (before === state()) return;
  past.push(before);
  if (past.length > 64) past.shift();
  future = [];
  keep();
}
function validatedEdit(fn) {
  const before = state(), previousSelection = selected;
  try {
    fn();
    D.validate(deck);
  } catch (e) {
    restore(before);
    selected = previousSelection;
    throw e;
  }
  return before;
}
function change(fn) {
  record(validatedEdit(fn));
  render();
}
function fit(l, least = 0) {
  // 📏 文字は箱の幅で折り返し、高さは行数に合わせて伸ばす（書き出しと同じ 1.3 行送り）
  if (l.kind === "text") l.h = Math.max(least, Math.ceil(C.textLayout(l).flat().length * l.fontSize * 1.3));
}
const mosaics = new Map(),
  mosaicKey = (l) => l.src + ":" + l.cell + ":" + l.levels,
  needsMosaic = (l) => l.kind === "image" && (l.cell !== 1 || l.levels !== 256);
function mosaic(l) {
  const key = mosaicKey(l);
  if (mosaics.has(key)) return mosaics.get(key);
  const img = new Image(), { cell, levels } = l;
  img.src = l.src;
  const entry = { src: l.src };
  entry.ready = img.decode().then(() => { entry.src = C.mosaicSource(img, cell, levels); });
  mosaics.set(key, entry);
  if (mosaics.size > 16) mosaics.delete(mosaics.keys().next().value);
  return entry;
}
function slideImages(s) {
  const entries = new Map();
  for (const l of s.layers) if (needsMosaic(l)) {
    const key = mosaicKey(l);
    if (!entries.has(key)) entries.set(key, mosaic(l));
  }
  return { source: (l) => needsMosaic(l) ? entries.get(mosaicKey(l)).src : l.src, pending: [...entries.values()] };
}
async function slideSource(s) {
  const { source, pending } = slideImages(s);
  await Promise.all(pending.map((e) => e.ready));
  return source;
}
const paintVersions = new WeakMap();
function paint(node, s, format = () => {}) {
  const token = {};
  paintVersions.set(node, token);
  const draw = (source) => {
    if (paintVersions.get(node) !== token) return;
    node.innerHTML = C.svg(s, source);
    format(node.firstElementChild);
  };
  const { source, pending } = slideImages(s);
  draw(source);
  if (pending.length) Promise.all(pending.map((e) => e.ready)).then(() => draw(source)).catch((e) => {
    if (paintVersions.get(node) === token && (node.isConnected || node.host?.isConnected)) note(e.message, true);
  });
}
function render() {
  const s = slide();
  paint($("phone-svg"), s); // 👀 打っている文字もそのままスライドに出る
  renderGrid();
  renderInspector();
  PySaiyanWeBoo.pagerSet(pages, active, deck.slides.length);
  const box = $("phone-pick"),
    l = picked();
  box.hidden = !l;
  if (l)
    Object.assign(box.style, { left: pct(l.x, s.width), top: pct(l.y, s.height), width: pct(l.w, s.width), height: pct(l.h, s.height),
      transform: `rotate(${l.rotation}deg)` });
  layerList(s);
  pageList();
  const off = { edit: !["text", "clock"].includes(l?.kind), look: !l, turn: !l, inspect: !l,
    front: !l || s.layers.at(-1) === l, back: !l || s.layers[0] === l,
    delete: !l, undo: !past.length, redo: !future.length,
    "slide-delete": deck.slides.length < 2, smaller: level === 0, bigger: level === scales.length - 1, reset: level === plain };
  for (const [act, disabled] of Object.entries(off)) document.querySelector(`[data-act="${act}"]`).disabled = disabled;
}
let pagesOpen = false,
  saves = 0; // 🗂️ 一覧の絵は保存のたびに描き直す（ドラッグ中は描かない）
function pageList() {
  const row = $("phone-pages"),
    key = pagesOpen && `${saves} ${active} ${deck.slides.length}`;
  if (row.dataset.key === String(key)) return;
  row.dataset.key = key;
  row.hidden = !pagesOpen;
  row.replaceChildren(...(pagesOpen ? deck.slides : []).map((s, i) => {
    const b = document.createElement("button");
    b.type = "button";
    const label = document.createElement("span");
    paint(label, s, (picture) => {
      picture.setAttribute("width", 80);
      picture.setAttribute("height", Math.round((80 * s.height) / s.width));
      picture.setAttribute("aria-hidden", "true");
    });
    b.append(label);
    b.append(String(i + 1)); // 番号に今のページの下線が付く
    b.setAttribute("aria-label", `${i + 1}/${deck.slides.length}`);
    if (i === active) b.setAttribute("aria-current", "step");
    b.addEventListener("pointerdown", (e) => e.preventDefault());
    b.addEventListener("click", () => {
      finishEdit();
      active = i;
      selected = null;
      keep();
      render();
    });
    return b;
  }));
}
let gridOpen = false, inspectorOpen = false;
const grid = $("phone-grid"), inspector = $("phone-inspector");
stage.tabIndex = -1;
function renderGrid() {
  const first = active - active % 4, key = gridOpen ? `${saves} ${active} ${deck.slides.length}` : "";
  if (grid.dataset.key === key) return;
  grid.dataset.key = key;
  grid.hidden = !gridOpen;
  document.querySelector('[data-act="grid"]').setAttribute("aria-pressed", String(gridOpen));
  if (!gridOpen) {
    grid.before(stage);
    grid.replaceChildren();
    return;
  }
  const slots = deck.slides.slice(first, first + 4).map((s, i) => {
    const index = first + i, slot = document.createElement("div");
    if (index === active) return slot;
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", `${index + 1} 枚目を編集`);
    const drawing = document.createElement("span").attachShadow({mode: "open"});
    paint(drawing, s, (svg) => {
      svg.setAttribute("width", "100%");
      svg.removeAttribute("height");
      svg.setAttribute("aria-hidden", "true");
    });
    button.append(drawing.host);
    button.addEventListener("click", () => {
      finishEdit();
      active = index;
      selected = null;
      keep();
      render();
      stage.focus({ preventScroll: true });
    });
    slot.append(button);
    return slot;
  });
  const editorSlot = slots[active - first];
  // During a save keep the focused stage in place, including an open text editor.
  if (stage.parentElement?.parentElement === grid && grid.children[active - first] === stage.parentElement) {
    slots[active - first] = stage.parentElement;
    for (const [i, slot] of slots.entries()) if (i !== active - first) {
      if (grid.children[i]) grid.children[i].replaceWith(slot);
      else grid.append(slot);
    }
    while (grid.children.length > slots.length) grid.lastElementChild.remove();
  } else {
    editorSlot.append(stage);
    grid.replaceChildren(...slots);
  }
}
function renderInspector() {
  const l = picked();
  inspector.hidden = !inspectorOpen || !l;
  document.querySelector('[data-act="inspect"]').setAttribute("aria-expanded", String(!inspector.hidden));
  for (const input of inspector.querySelectorAll("[data-property]")) {
    const key = input.dataset.property;
    input.closest("label").hidden = !l || (input.dataset.kinds && !input.dataset.kinds.split(" ").includes(l.kind));
    if (!l || input.closest("label").hidden || document.activeElement === input) continue;
    if (input.type === "checkbox") input.checked = Boolean(l[key]);
    else input.value = l[key] ?? (key === "headPlacement" ? "tip" : "");
  }
}
inspector.addEventListener("change", (e) => {
  const input = e.target, key = input.dataset.property, l = picked();
  if (!key || !l || (input.dataset.kinds && !input.dataset.kinds.split(" ").includes(l.kind))) return;
  if (input.type === "number" && (!input.value || !input.checkValidity())) {
    input.value = l[key];
    return;
  }
  run(() => change(() => {
    l[key] = input.type === "number" ? input.valueAsNumber : input.type === "checkbox" ? input.checked : input.value;
    if (l.kind === "text" && (key === "italic" || key === "w")) fit(l);
  }));
});
function layerList(s) {
  // 📚 奥 → 手前。2 つ以上あるときだけ出し、重なって触れないものもここから選べる（文字は先頭 3 字、ほかは形の記号）
  const row = $("phone-layers"),
    faces = s.layers.map((l) => (l.kind === "text" && [...new Intl.Segmenter().segment(l.text.trim())].slice(0, 3).map((g) => g.segment).join(""))
      || { text: "🔤", rect: "▭", ellipse: "◯", triangle: "△", arrow: "→", clock: "🕒", image: "🖼️" }[l.kind] || "▫️"),
    key = JSON.stringify([faces, s.layers.map((l) => l.id), selected]);
  if (row.dataset.key === key) return;
  row.dataset.key = key;
  row.hidden = s.layers.length < 2;
  row.replaceChildren(...(row.hidden ? [] : s.layers).map((l, i) => {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = faces[i];
    b.setAttribute("aria-label", `${i + 1} ${faces[i]}`);
    if (l.id === selected) b.setAttribute("aria-current", "step");
    b.addEventListener("pointerdown", (e) => e.preventDefault());
    b.addEventListener("click", () => {
      finishEdit();
      selected = l.id;
      render();
    });
    return b;
  }));
}
function later() {
  if (!frame) frame = requestAnimationFrame(() => ((frame = 0), render()));
}
const clockText = (l) => `${String(l.hour).padStart(2, "0")}:${String(l.minute).padStart(2, "0")}`;
function clockSet(l, text) {
  // 🕒 14:30 / 9:05（時 0–23、分 0–59）。読めないうちは前の時刻のまま
  const m = /^\s*(\d{1,2})\s*[:：]\s*(\d{2})\s*$/.exec(text);
  if (m && +m[1] < 24 && +m[2] < 60) [l.hour, l.minute] = [+m[1], +m[2]];
}
function startEdit(before = state()) {
  const l = picked();
  if (!l || !["text", "clock"].includes(l.kind)) return;
  editing = l.id;
  editBefore = before;
  edit.value = l.kind === "clock" ? clockText(l) : l.text;
  edit.hidden = false; // ⌨️ 固定したスライドのすぐ下で打つ（16 px なのでスマホが拡大しない）
  edit.dataset.least = l.h;
  render();
  edit.focus();
}
function finishEdit() {
  if (!editing) return;
  const s = slide(),
    l = s.layers.find((x) => x.id === editing);
  editing = null;
  edit.hidden = true;
  if (l?.kind === "clock") clockSet(l, edit.value);
  else if (l) {
    l.text = edit.value.slice(0, 2000);
    if (l.text.trim()) fit(l, Number(edit.dataset.least));
    else {
      s.layers = s.layers.filter((x) => x !== l); // 空のまま閉じた箱は残さない
      selected = null;
    }
  }
  record(editBefore);
  render();
}
edit.addEventListener("input", () => {
  const l = slide().layers.find((x) => x.id === editing);
  if (!l) return;
  if (l.kind === "clock") clockSet(l, edit.value);
  else {
    l.text = edit.value.slice(0, 2000);
    fit(l, Number(edit.dataset.least));
  }
  later();
});
edit.addEventListener("blur", finishEdit);
new ResizeObserver(() => stage.style.setProperty("--k", stage.clientWidth / slide().width)).observe(stage);

/* 👆 選ぶ・動かす・↘ で大きさ。選んだ文字をもう一度タップすると編集（後からいつでも直せる） */
function point(e) {
  const r = stage.getBoundingClientRect(),
    s = slide();
  return { x: ((e.clientX - r.left) / r.width) * s.width, y: ((e.clientY - r.top) / r.height) * s.height };
}
function hit(p) {
  const layers = slide().layers;
  for (let i = layers.length - 1; i >= 0; i--) {
    const l = layers[i];
    if (p.x >= l.x && p.x <= l.x + l.w && p.y >= l.y && p.y <= l.y + l.h) return l;
  }
  return null;
}
stage.addEventListener("pointerdown", (e) => {
  if (drag || !e.isPrimary || e.button !== 0 || e.target === edit) return;
  const p = point(e),
    grip = !!e.target.closest("[data-grip]"),
    l = grip ? picked() : hit(p),
    before = state(),
    again = !!l && l.id === selected;
  finishEdit();
  selected = l ? l.id : null;
  if (l) {
    drag = { pointerId: e.pointerId, id: l.id, grip, again, before, start: p, x: l.x, y: l.y, w: l.w, h: l.h, moved: false };
    stage.setPointerCapture(e.pointerId);
    e.preventDefault();
  }
  render();
});
stage.addEventListener("pointermove", (e) => {
  if (drag?.pointerId !== e.pointerId) return;
  const l = picked();
  if (l?.id !== drag.id) return;
  const p = point(e),
    dx = p.x - drag.start.x,
    dy = p.y - drag.start.y;
  if (!drag.moved && Math.hypot(dx, dy) < slide().width / 160) return; // 指のぶれ（1280 なら 8）は動かさない
  drag.moved = true;
  if (drag.grip) {
    l.w = Math.max(16, drag.w + dx);
    l.h = Math.max(16, drag.h + dy);
    fit(l, l.h);
  } else {
    l.x = drag.x + dx;
    l.y = drag.y + dy;
  }
  later();
});
stage.addEventListener("pointerup", (e) => {
  if (drag?.pointerId !== e.pointerId) return;
  const d = drag;
  drag = null;
  if (d.moved) record(d.before);
  else if (d.again && ["text", "clock"].includes(picked()?.kind)) startEdit();
  render();
});
stage.addEventListener("pointercancel", (e) => {
  if (drag?.pointerId !== e.pointerId) return;
  if (drag.moved) record(drag.before);
  drag = null;
});

/* ➕ 置くもの（白紙に足すだけ。図形・矢印・画像は Slide Studio と同じ形） */
function place(make) {
  return validatedEdit(() => {
    const s = slide();
    if (s.layers.length >= 100) throw Error("⚠️ 100");
    const l = make(s);
    s.layers.push(l);
    selected = l.id;
  });
}
function shape(kind) {
  return (s) => ({ id: uid(kind), kind, name: kind, x: s.width * 0.375, y: s.height * 0.375, w: s.width * 0.25, h: s.height * 0.25,
    rotation: 0, opacity: 1, fill: "#18A7A1", stroke: "#183C42", strokeWidth: 4 });
}
  /* 🔷 😊 (^^) 候補から置く（Image Studio と同じ候補）。🕒 はいまの時刻。選んだものは 🅱️ 太字・🎨 色・⏫ 手前へ */
function stamp(text) {
  const size = textSize * textFactor * 2;
  return place((s) => {
    const l = { id: uid("text"), kind: "text", name: "text", x: 0, y: 0, w: Math.min(s.width * 0.9, ([...text].length + 1) * size),
      h: Math.ceil(size * 1.3), rotation: 0, opacity: 1, text, fill: "#000000", fontSize: size, font: "sans", mono: false, bold: false,
      wrap: true };
    fit(l);
    l.x = (s.width - l.w) / 2;
    l.y = (s.height - l.h) / 2;
    return l;
  });
}
const COLORS = ["#000000", "#18A7A1", "#D7263D", "#1B6EF3", "#F5B700", "#FFFFFF"], // 🎨 🖌 黒・青緑・赤・青・黄・白
  nextColor = (c) => COLORS[(COLORS.indexOf(String(c).toUpperCase()) + 1) % COLORS.length];
function restyle(fn) {
  const l = picked();
  if (l) change(() => fn(l));
}
function scaleText(next) {
  // 🔽 🔄 🔼 すべてのページの文字を同じ倍率で（タイトルと本文の比は保つ）
  if (!scales[next] || next === level) return;
  change(() => {
    const layers = deck.slides.flatMap((s) => s.layers.filter((l) => l.kind === "text"));
    // Restrict the shared multiplier, not individual sizes, so reset can reverse it.
    let r = scales[next] / textFactor;
    for (const l of layers)
      r = r > 1 ? Math.min(r, 512 / l.fontSize) : Math.max(r, 4 / l.fontSize);
    for (const l of layers) {
      l.fontSize = Math.min(512, Math.max(4, l.fontSize * r)); // absorb float error at the bounds
      fit(l);
    }
    textFactor = Math.min(Math.max(...scales), Math.max(Math.min(...scales), textFactor * r));
    level = next;
  });
}
pages.addEventListener("ui-pager", (e) => {
  finishEdit();
  active = e.detail.index;
  selected = null;
  keep();
  render();
});
const acts = {
  text() {
    const size = textSize * textFactor,
      before = place((s) => ({ id: uid("text"), kind: "text", name: "text", x: s.width * 0.1,
        y: Math.min(s.height - size * 1.3, s.height * 0.08 + s.layers.filter((l) => l.kind === "text").length * size * 2),
        w: s.width * 0.8, h: Math.ceil(size * 1.3), rotation: 0, opacity: 1, text: "", fill: "#000000",
        fontSize: size, font: "sans", mono: false, bold: false, wrap: true }));
    startEdit(before); // ⌨️ そのまま打てる
  },
  rect: () => record(place(shape("rect"))),
  ellipse: () => record(place(shape("ellipse"))),
  triangle: () => record(place(shape("triangle"))),
  arrow: () => record(place((s) => ({ id: uid("arrow"), kind: "arrow", name: "arrow", x: s.width * 0.25, y: s.height * 0.45,
    w: s.width * 0.5, h: s.height * 0.1, rotation: 0, opacity: 1, fill: "#000000", stroke: "#000000", strokeWidth: 4,
    headSize: 28, headPlacement: "tip", headStyle: "triangle" }))),
  clock() {
    const now = new Date();
    record(place((s) => ({ id: uid("clock"), kind: "clock", name: "clock", x: s.width * 0.5 - s.height * 0.15, y: s.height * 0.35,
      w: s.height * 0.3, h: s.height * 0.3, rotation: 0, opacity: 1, hour: now.getHours(), minute: now.getMinutes(),
      fill: "#FFFFFF", stroke: "#183C42", strokeWidth: 4 })));
  },
  edit: () => startEdit(),
  fill: () => restyle((l) => {
    l.fill = nextColor(l.fill);
    if (l.kind === "arrow") l.stroke = l.fill;
  }),
  stroke: () => restyle((l) => {
    if (!("stroke" in l)) return;
    l.stroke = nextColor(l.stroke);
    if (l.kind === "arrow") l.fill = l.stroke;
  }),
  fade: () => restyle((l) => {
    const steps = [1, 0.75, 0.5, 0.25];
    l.opacity = steps[(steps.indexOf(steps.reduce((a, b) => (Math.abs(b - l.opacity) < Math.abs(a - l.opacity) ? b : a))) + 1) % steps.length];
  }),
  bold: () => restyle((l) => l.kind === "text" && ((l.bold = !l.bold), fit(l))),
  font: () => restyle((l) => l.kind === "text" && ((l.font = l.font === "mono" ? "sans" : "mono"), fit(l))),
  cw: () => restyle((l) => (l.rotation = (l.rotation + 15) % 360)),
  ccw: () => restyle((l) => (l.rotation = (l.rotation - 15) % 360)),
  upright: () => restyle((l) => (l.rotation = 0)),
  inspect() { inspectorOpen = !inspectorOpen; },
  grid() { gridOpen = !gridOpen; },
  pages() {
    pagesOpen = !pagesOpen; // 🗂️ 見るためのもの: ↩️ にも資料にも入らない
  },
  front: () => change(() => {
    const s = slide(),
      l = picked();
    s.layers = [...s.layers.filter((x) => x !== l), l];
  }),
  back: () => change(() => {
    const s = slide(),
      l = picked();
    s.layers = [l, ...s.layers.filter((x) => x !== l)];
  }),
  delete: () => change(() => {
    slide().layers = slide().layers.filter((l) => l.id !== selected);
    selected = null;
  }),
  undo() {
    if (!past.length) return;
    future.push(state());
    restore(past.pop());
    selected = null;
    keep();
  },
  redo() {
    if (!future.length) return;
    past.push(state());
    restore(future.pop());
    selected = null;
    keep();
  },
  smaller: () => scaleText(level - 1),
  reset: () => scaleText(plain),
  bigger: () => scaleText(level + 1),
  "slide-add": () => change(() => {
    if (deck.slides.length >= 20) throw Error("⚠️ 20");
    deck.slides.splice(active + 1, 0, blank(slide().width, slide().height));
    active += 1;
    selected = null;
  }),
  "slide-copy": () => change(() => {
    if (deck.slides.length >= 20) throw Error("⚠️ 20");
    deck.slides.splice(active + 1, 0, C.clone(slide()));
    active += 1;
  }),
  "slide-delete": () => change(() => {
    if (deck.slides.length < 2) return;
    deck.slides.splice(active, 1);
    active = Math.min(active, deck.slides.length - 1);
    selected = null;
  }),
  new: () => change(() => {
    deck = { schema: D.SCHEMA, title: "Ironmate", slides: [blank()] };
    active = 0;
    level = plain;
    textFactor = 1;
    selected = null;
  }),
  open: () => toolbar.choose("open"), // 📥 a host or IronmatePhone.act without a file: the toolbar's chooser
  image: () => toolbar.choose("image"),
  camera: () => toolbar.choose("camera"),
  json: () => C.save("ironmate-slides.json", D.deckText(deck), "application/json"),
  async svg() {
    const s = slide();
    C.save(`ironmate-slide-${active + 1}.svg`, C.svg(s, await slideSource(s)), "image/svg+xml");
  },
  async png() {
    const s = slide();
    const blob = await C.scenePng(s, await slideSource(s));
    C.save(`ironmate-slide-${active + 1}.png`, blob, "image/png");
  },
  async pptx() {
    note("📤 …");
    const sources = new Map();
    for (const s of deck.slides) {
      const source = await slideSource(s);
      for (const l of s.layers) if (needsMosaic(l)) sources.set(mosaicKey(l), source(l));
    }
    const result = await D.exportPptx(deck, (l) => D.layerPng(l, (x) => (needsMosaic(x) ? sources.get(mosaicKey(x)) : x.src)));
    C.save("ironmate-slides.pptx", result.data, "application/vnd.openxmlformats-officedocument.presentationml.presentation");
    note(`📤 ✅ ${result.slides}📄`);
  },
};
const files = {
  async image(file, destination = slide()) {
    const p = await C.picture(file, 1920); // 🖼️ 写真は 4MP・長辺 1920 まで縮めて PNG に（画像工房と同じ取り込み）
    if (slide() !== destination) throw Error("スライドが切り替わりました。追加したいページで画像を選び直してください。");
    const before = place((s) => {
      const k = Math.min((s.width * 0.6) / p.w, (s.height * 0.6) / p.h);
      return { id: uid("image"), kind: "image", name: "image", x: (s.width - p.w * k) / 2, y: (s.height - p.h * k) / 2,
        w: p.w * k, h: p.h * k, rotation: 0, opacity: 1, src: p.src, cell: 1, levels: 256, sampling: "smooth" };
    });
    record(before);
  },
  async open(file) {
    const next = D.parse(await file.text()); // Slide Studio の「全スライドJSON」もそのまま開ける
    const before = state();
    deck = next;
    active = 0;
    level = plain;
    textFactor = 1;
    selected = null;
    record(before);
  },
};
let busy = false;
async function run(fn) {
  if (busy) return false;
  busy = true;
  try {
    await fn();
    if (!/^📤/.test(status)) note("");
    return true;
  } catch (e) {
    note(e.message, true);
    return false;
  } finally {
    busy = false;
    render();
  }
}
function press(name, value) {
  // 🧰 the one way in: a toolbar press (PySaiyanWeBoo's bindToolbar; 🔷 🎨 ↻ 📥 📤 open their candidates themselves), a picked
  // 😊 (^^) (its face), a file 📥's chooser (the toolbar's) chose (its File: 画像 カメラ JSON) and IronmatePhone.act — the same act
  if (name !== "edit") finishEdit();
  if (value instanceof Blob) return run(() => files[name === "camera" ? "image" : name](value)); // 📷 a photo is an image
  if (value !== undefined) return run(() => record(stamp(value)));
  if (acts[name]) return run(acts[name]);
}
const toolbar = PySaiyanWeBoo.bindToolbar($("phone-toolbar"), press);
document.addEventListener("keydown", (e) => {
  if (editing || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return; // ← → Home End: the pager's own keys
  if ((e.key === "Delete" || e.key === "Backspace") && selected) run(acts.delete);
  else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") run(e.shiftKey ? acts.redo : acts.undo);
});
try {
  const saved = localStorage.getItem(STORE);
  if (saved) restore(saved);
} catch {
  deck = { schema: D.SCHEMA, title: "Ironmate", slides: [blank()] };
}
// The same-origin editor opens this tab from its shelf. Keep the original scene editable.
if (location.hash === "#from-image-studio") {
  const source = window.opener;
  window.opener = null;
  history.replaceState(history.state, "", location.pathname + location.search);
  run(async () => {
    if (!source || source.closed || source.location.origin !== location.origin || !source.IronmateStudio)
      throw Error("画像工房のシェルフから開き直してください。");
    const destination = slide();
    await files.image(await source.IronmateStudio.pngBlob(1), destination);
  });
}
stage.style.setProperty("--k", stage.clientWidth / slide().width);
PySaiyanWeBoo.bindLabels(); // 💻 To textual ⇄ 📱 To iconic: 絵文字（既定）と短い言葉を、同じページで切り替え（覚えておく）
render();
window.IronmatePhone = {
  get deck() {
    return C.clone(deck);
  },
  get active() {
    return active;
  },
  get selected() {
    return selected;
  },
  get level() {
    return level;
  },
  // 🧰 what a toolbar press runs, awaitable from Node or a host: act("undo"), act("emoji", "🌱"), act("image", file) (a File or Blob)
  act: (name, value) => press(name, value),
};
})();
"""


# 🔽 🔄 🔼 multiply every text box by the next / plain / previous step; new boxes are 32 px on the 1280×720 slide.
PHONE_TEXT = {"size": 32, "scale": (0.5, 0.75, 1, 1.25, 1.5, 2, 2.5)}
# 🖼️ the stage and 🧭 the pager (⬅️ 1/N ➡️ by default; ← → Home End too) are PySaiyanWeBoo's, written below from the pinned commit.
# ⬇️ pysaiyanweboo: scripts/build_studio_css.py writes PSWB_PARTS from the pinned commit (--check fails when it drifts)
PSWB_PARTS = {
    "stage": (
        '<div class="ui-stage" role="region" aria-label="スライド" data-ui-stage="pinned" id="phone-stage">{slide}</div>'),
    "pager": (
        '<div class="ui-pager" role="group" aria-label="ページ移動" data-ui-pager="arrows" data-ui-pager-index="0" data-ui-pager-count="1" data-ui-pager-keys id="phone-pager">'
        '<button type="button" data-ui-pager-part="up" data-ui-pager-in="dpad" data-ui-pager-go="first" aria-label="最初のページ" title="最初のページ" disabled>⬆️</button>'
        '<button type="button" data-ui-pager-part="first" data-ui-pager-in="ends" data-ui-pager-go="first" aria-label="最初のページ" title="最初のページ" disabled>⏮️</button>'
        '<button type="button" data-ui-pager-part="prev" data-ui-pager-in="arrows ends dpad" data-ui-pager-go="prev" aria-label="前のページ" title="前のページ" disabled>⬅️</button>'
        '<span data-ui-pager-part="dots" data-ui-pager-in="dots" data-ui-pager-word="ページ">'
        '<button type="button" data-ui-pager-to="0" aria-label="ページ 1" title="ページ 1" aria-current="page">●</button>'
        '</span>'
        '<input type="range" data-ui-pager-part="slider" data-ui-pager-in="slider" min="1" max="2" step="1" value="1" aria-label="ページ" disabled>'
        '<span data-ui-pager-part="dial" data-ui-pager-in="dial">'
        '<span class="ui-dial" data-ui-dial>'
        '<input type="range" name="page" min="1" max="2" step="1" value="1" aria-label="ページ" disabled>'
        '</span>'
        '</span>'
        '<output data-ui-pager-part="page" data-ui-pager-in="arrows ends dpad dots slider dial" aria-live="polite">1/1</output>'
        '<button type="button" data-ui-pager-part="next" data-ui-pager-in="arrows ends dpad" data-ui-pager-go="next" aria-label="次のページ" title="次のページ" disabled>➡️</button>'
        '<button type="button" data-ui-pager-part="last" data-ui-pager-in="ends" data-ui-pager-go="last" aria-label="最後のページ" title="最後のページ" disabled>⏭️</button>'
        '<button type="button" data-ui-pager-part="down" data-ui-pager-in="dpad" data-ui-pager-go="last" aria-label="最後のページ" title="最後のページ" disabled>⬇️</button>'
        '</div>'),
    "slides-toolbar": (
        '<div class="ui-toolbar" id="phone-toolbar" role="toolbar" aria-label="道具">'
        '<div class="ui-toolbar-row" data-ui-group="create">'
        '<button type="button" data-act="text" data-ui-word="文字" aria-label="文字を置く" title="文字を置く">🔤</button>'
        '<button type="button" data-acts="rect ellipse triangle arrow" data-words="四角|丸|三角|矢印" data-candidates="▭ ◯ △ →" data-act="shape" data-ui-word="図形" aria-label="図形（四角・丸・三角・矢印）" title="図形（四角・丸・三角・矢印）">🔷</button>'
        '<button type="button" data-candidates="❤️ 😊 🌱 📊 ✨ 📌 🔰" data-act="emoji" data-ui-word="絵文字" aria-label="絵文字" title="絵文字">😊</button>'
        '<button type="button" data-candidates="(・∀・) (｡•̀ᴗ-)✧ ٩(๑❛ᴗ❛๑)۶" data-act="kaomoji" data-ui-word="顔文字" aria-label="顔文字" title="顔文字">(^^)</button>'
        '<button type="button" data-act="clock" data-ui-word="時計" aria-label="いまの時刻の時計" title="いまの時刻の時計">🕒</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-candidates id="phone-candidates" role="group" aria-label="候補" hidden>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="adjust">'
        '<button type="button" data-act="smaller" data-ui-word="小さく" aria-label="文字をすべて小さく" title="文字をすべて小さく">🔽</button>'
        '<button type="button" data-act="reset" data-ui-word="元の大きさ" aria-label="文字をすべて元の大きさに" title="文字をすべて元の大きさに">🔄</button>'
        '<button type="button" data-act="bigger" data-ui-word="大きく" aria-label="文字をすべて大きく" title="文字をすべて大きく">🔼</button>'
        '<button type="button" data-act="undo" data-ui-word="戻す" aria-label="戻す" title="戻す">↩️</button>'
        '<button type="button" data-act="redo" data-ui-word="やり直す" aria-label="やり直す" title="やり直す">↪️</button>'
        '</div>'
        '<div id="phone-layers" class="ui-toolbar-row ui-current-items" role="group" aria-label="レイヤー（奥から手前）" hidden>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="update">'
        '<button type="button" data-act="edit" data-ui-word="編集" aria-label="選んだ文字・時計を編集（選んだものをもう一度タップしても編集。時計は 14:30 のように）" title="選んだ文字・時計を編集（選んだものをもう一度タップしても編集。時計は 14:30 のように）">✏️</button>'
        '<button type="button" data-acts="fill stroke fade bold font" data-words="塗りを次の色へ|線を次の色へ|不透明度（1 → ¾ → ½ → ¼）|太字|等幅 ⇄ ふつう" data-candidates="🎨 🖌 🌗 🅱️ 🔠" data-act="look" data-ui-word="見た目" aria-label="選んだものの見た目（塗り・線の色・不透明度・太字・等幅）" title="選んだものの見た目（塗り・線の色・不透明度・太字・等幅）">🎨</button>'
        '<button type="button" data-acts="cw ccw upright" data-words="右へ 15°|左へ 15°|まっすぐに戻す" data-candidates="↻ ↺ ⏹" data-act="turn" data-ui-word="回転" aria-label="選んだものを回す" title="選んだものを回す">↻</button>'
        '<button type="button" data-act="front" data-ui-word="手前へ" aria-label="選んだものをいちばん手前へ" title="選んだものをいちばん手前へ">⏫</button>'
        '<button type="button" data-act="back" data-ui-word="奥へ" aria-label="選んだものをいちばん奥へ" title="選んだものをいちばん奥へ">⏬</button>'
        '<button type="button" data-act="delete" data-ui-word="削除" aria-label="選んだものを削除" title="選んだものを削除">🗑️</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="pages">'
        '<button type="button" data-act="slide-add" data-ui-word="ページ追加" aria-label="白紙のページを追加" title="白紙のページを追加">➕📄</button>'
        '<button type="button" data-act="slide-copy" data-ui-word="ページ複製" aria-label="ページを複製" title="ページを複製">📑</button>'
        '<button type="button" data-act="slide-delete" data-ui-word="ページ削除" aria-label="ページを削除" title="ページを削除">✖️📄</button>'
        '<button type="button" data-act="pages" data-ui-word="一覧" aria-label="ページの一覧（タップでそのページへ）" title="ページの一覧（タップでそのページへ）">🗂️</button>'
        '</div>'
        '<div id="phone-pages" class="ui-toolbar-row ui-current-items" role="group" aria-label="ページの一覧" hidden>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="file">'
        '<button type="button" data-act="new" data-ui-word="新規" aria-label="最初から（白紙 1 枚）" title="最初から（白紙 1 枚）">🆕</button>'
        '<button type="button" data-close data-acts="image camera open" data-words="画像（PNG・JPEG・WebP をこのページに）|カメラ（撮った写真をこのページに）|JSON（全スライド）" data-candidates="画像 カメラ JSON" data-act="import" data-ui-word="インポート" aria-label="インポート（どの形式から？ 候補から選ぶ）" title="インポート（どの形式から？ 候補から選ぶ）">📥</button>'
        '<button type="button" data-close data-acts="pptx json png svg" data-words="PPTX（全スライド、PowerPoint で編集できる）|JSON（全スライド、また開ける）|PNG（このページ）|SVG（このページ）" data-candidates="PPTX JSON PNG SVG" data-act="export" data-ui-word="エクスポート" aria-label="エクスポート（どの形式に？ 候補から選ぶ）" title="エクスポート（どの形式に？ 候補から選ぶ）">📤</button>'
        '<a class="ui-button" href="../" data-act="home" data-ui-word="Image Studio" aria-label="Image Studio" title="Image Studio">🏠</a>'
        '<button type="button" class="ui-button" id="labels-switch" data-ui-labels-switch data-ui-word="📱 To iconic" aria-pressed="false" aria-label="💻 To textual ⇄ 📱 To iconic" title="💻 To textual ⇄ 📱 To iconic">💻</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="detail">'
        '<button type="button" data-act="inspect" data-ui-word="詳細" aria-label="選んだものの詳細（位置・大きさ・種類別の設定）" title="選んだものの詳細（位置・大きさ・種類別の設定）">🎛️</button>'
        '<button type="button" data-act="grid" data-ui-word="4枚表示" aria-label="4枚表示（その場で編集）" title="4枚表示（その場で編集）">⊞</button>'
        '</div>'
        '<fieldset id="phone-inspector" hidden>'
        '<legend>詳細設定</legend>'
        '<label>横の位置<input type="number" data-property="x" data-kinds="" min="-8192" max="8192" step="any">'
        '</label>'
        '<label>縦の位置<input type="number" data-property="y" data-kinds="" min="-8192" max="8192" step="any">'
        '</label>'
        '<label>幅<input type="number" data-property="w" data-kinds="" min="1" max="8192" step="any">'
        '</label>'
        '<label>高さ<input type="number" data-property="h" data-kinds="" min="1" max="8192" step="any">'
        '</label>'
        '<label>線幅<input type="number" data-property="strokeWidth" data-kinds="rect ellipse triangle arrow clock" min="0" max="64" step="any">'
        '</label>'
        '<label>モザイクの幅<input type="number" data-property="cell" data-kinds="image" min="1" max="512" step="1">'
        '</label>'
        '<label>色の段階<input type="number" data-property="levels" data-kinds="image" min="2" max="256" step="1">'
        '</label>'
        '<label>'
        '<input type="checkbox" data-property="italic" data-kinds="text">斜体</label>'
        '<label>矢印の先端<select data-property="headPlacement" data-kinds="arrow">'
        '<option value="tip">端</option>'
        '<option value="middle">中央</option>'
        '</select>'
        '</label>'
        '</fieldset>'
        '<input type="file" hidden data-ui-file="image" accept="image/png,image/jpeg,image/webp" aria-label="画像（PNG・JPEG・WebP をこのページに）" />'
        '<input type="file" hidden data-ui-file="camera" accept="image/png,image/jpeg,image/webp" capture="environment" aria-label="カメラ（撮った写真をこのページに）" />'
        '<input type="file" hidden data-ui-file="open" accept=".json,application/json" aria-label="JSON（全スライド）" />'
        '</div>'),
    "image-toolbar": (
        '        <div class="ui-toolbar" id="studio-toolbar" role="toolbar" aria-label="道具">'
        '<div class="ui-toolbar-row" data-ui-group="create">'
        '<button type="button" data-act="select" data-ui-word="選択" aria-label="選んで動かす" title="選んで動かす">👆</button>'
        '<button type="button" data-act="text" data-ui-word="文字" aria-label="文字を置く" title="文字を置く">🔤</button>'
        '<button type="button" data-acts="rect ellipse triangle arrow" data-words="四角|丸|三角|矢印" data-candidates="▭ ◯ △ →" data-act="shape" data-ui-word="図形" aria-label="図形（四角・丸・三角・矢印）" title="図形（四角・丸・三角・矢印）">🔷</button>'
        '<button type="button" data-act="stamp" data-ui-word="スタンプ" aria-label="スタンプを押す" title="スタンプを押す">✦</button>'
        '<button type="button" data-candidates="❤️ 😊 🌱 📊 ✨ 📌 🔰" data-act="emoji" data-ui-word="絵文字" aria-label="絵文字" title="絵文字">😊</button>'
        '<button type="button" data-candidates="(・∀・) (｡•̀ᴗ-)✧ ٩(๑❛ᴗ❛๑)۶" data-act="kaomoji" data-ui-word="顔文字" aria-label="顔文字" title="顔文字">(^^)</button>'
        '<button type="button" data-act="clock" data-ui-word="時計" aria-label="いまの時刻の時計" title="いまの時刻の時計">🕒</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-candidates id="studio-candidates" role="group" aria-label="候補" hidden>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="adjust">'
        '<button type="button" data-act="undo-2" data-ui-word="2つ戻す" aria-label="2つ戻す" title="2つ戻す">⏪</button>'
        '<button type="button" data-act="undo" data-ui-word="戻す" aria-label="戻す" title="戻す">↩️</button>'
        '<button type="button" data-act="redo" data-ui-word="やり直す" aria-label="やり直す" title="やり直す">↪️</button>'
        '<button type="button" data-act="redo-2" data-ui-word="2つやり直す" aria-label="2つやり直す" title="2つやり直す">⏩</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="update">'
        '<button type="button" data-act="duplicate" data-ui-word="複製" aria-label="選んだものを複製" title="選んだものを複製">⧉</button>'
        '<button type="button" data-act="forward" data-ui-word="前へ" aria-label="選んだものをひとつ手前へ" title="選んだものをひとつ手前へ">⬆️</button>'
        '<button type="button" data-act="backward" data-ui-word="後ろへ" aria-label="選んだものをひとつ奥へ" title="選んだものをひとつ奥へ">⬇️</button>'
        '<button type="button" data-act="delete" data-ui-word="削除" aria-label="選んだものを削除" title="選んだものを削除">🗑️</button>'
        '</div>'
        '<div class="ui-toolbar-row" data-ui-group="file">'
        '<button type="button" data-close data-acts="image camera clipboard open-json open-workspace shelf" data-words="画像（PNG・JPEG・WebP をキャンバスに）|カメラ（撮った写真をキャンバスに）|クリップボード（コピーした画像・Base64）|JSON（再編集用のシーン）|作業履歴（最大40状態）|シェルフ（クリップボード・シェルフ）" data-candidates="画像 カメラ クリップボード JSON 作業履歴 シェルフ" data-act="import" data-ui-word="インポート" aria-label="インポート（どの形式から？ 候補から選ぶ）" title="インポート（どの形式から？ 候補から選ぶ）">📥</button>'
        '<button type="button" data-close data-acts="png svg json workspace base64" data-words="PNG（出力倍率で）|SVG（出力倍率で）|JSON（再編集用）|作業履歴（最大40状態）|Base64（Flutter などへ渡す）" data-candidates="PNG SVG JSON 作業履歴 Base64" data-act="export" data-ui-word="エクスポート" aria-label="エクスポート（どの形式に？ 候補から選ぶ）" title="エクスポート（どの形式に？ 候補から選ぶ）">📤</button>'
        '<select id="export-scale" title="出力倍率" aria-label="出力倍率">'
        '<option value="1">1×</option>'
        '<option value="2">2×</option>'
        '<option value="4">4×</option>'
        '<option value="8">8×</option>'
        '</select>'
        '<button type="button" class="ui-button" id="labels-switch" data-ui-labels-switch data-ui-word="📱 To iconic" aria-pressed="false" aria-label="💻 To textual ⇄ 📱 To iconic" title="💻 To textual ⇄ 📱 To iconic">💻</button>'
        '</div>'
        '<input type="file" hidden data-ui-file="image" accept="image/png,image/jpeg,image/webp" aria-label="画像（PNG・JPEG・WebP をキャンバスに）" />'
        '<input type="file" hidden data-ui-file="camera" accept="image/png,image/jpeg,image/webp" capture="environment" aria-label="カメラ（撮った写真をキャンバスに）" />'
        '<input type="file" hidden data-ui-file="open-json" accept=".json" aria-label="JSON（再編集用のシーン）" />'
        '<input type="file" hidden data-ui-file="open-workspace" accept=".json,application/json" aria-label="作業履歴（最大40状態）" />'
        '</div>\n'),
}
# ⬆️ pysaiyanweboo


def studio_toolbar(page: str) -> tuple[list, dict[str, str], dict[str, str]]:
    """🧰 Both studios' toolbars as PySaiyanWeBoo's ``toolbar_html`` data, ``(groups, inside, after)``, from one table: an act has one
    face, one word (💻 To textual) and one tip wherever it is listed, so a face never means two things (⬆️ ⬇️ one step, ⏫ ⏬ all the way;
    ⧉ a copy of the selected, 📑 of the page). ``page`` is "slides" (the one slide editor) or "image" (Image Studio) and picks the rows:
    make / adjust / change (/ pages) / file (/ detail). 🔷 😊 (^^) 🎨 ↻ open candidates under their row; 📥 どの形式から？ 📤 どの形式に？
    name each page's formats in words and hide after a pick (Image Studio's are the keys a host's header sends, ``image_studio.host_rows``).
    A format read from a file (📥 画像 カメラ JSON, and Image Studio's 作業履歴) has ``accept``: the toolbar holds its chooser.
    ``inside`` and ``after`` place each page's own pieces: Image Studio's output scale beside 📤 (💻 ⇄ 📱 ends both pages' file rows,
    scripts/build_studio_css.py adds it); the slide editor's 📚 layers, 🗂️ pages and inspector. scripts/build_studio_css.py writes the markup into PSWB_PARTS ("slides-toolbar",
    "image-toolbar"); --check fails when this table and that markup drift."""
    from html import escape

    # act: (face, word, tip[, candidate faces, their acts, their words "|"]); a candidate without acts passes its face
    tools = {
        "select": ("👆", "選択", "選んで動かす"),
        "text": ("🔤", "文字", "文字を置く"),
        "shape": ("🔷", "図形", "図形（四角・丸・三角・矢印）", "▭ ◯ △ →", "rect ellipse triangle arrow", "四角|丸|三角|矢印"),
        "stamp": ("✦", "スタンプ", "スタンプを押す"),
        "emoji": ("😊", "絵文字", "絵文字", "❤️ 😊 🌱 📊 ✨ 📌 🔰"),
        "kaomoji": ("(^^)", "顔文字", "顔文字", "(・∀・) (｡•̀ᴗ-)✧ ٩(๑❛ᴗ❛๑)۶"),
        "clock": ("🕒", "時計", "いまの時刻の時計"),
        "smaller": ("🔽", "小さく", "文字をすべて小さく"),
        "reset": ("🔄", "元の大きさ", "文字をすべて元の大きさに"),
        "bigger": ("🔼", "大きく", "文字をすべて大きく"),
        "undo-2": ("⏪", "2つ戻す", "2つ戻す"),
        "undo": ("↩️", "戻す", "戻す"),
        "redo": ("↪️", "やり直す", "やり直す"),
        "redo-2": ("⏩", "2つやり直す", "2つやり直す"),
        "edit": ("✏️", "編集", "選んだ文字・時計を編集（選んだものをもう一度タップしても編集。時計は 14:30 のように）"),
        "look": ("🎨", "見た目", "選んだものの見た目（塗り・線の色・不透明度・太字・等幅）", "🎨 🖌 🌗 🅱️ 🔠", "fill stroke fade bold font",
                 "塗りを次の色へ|線を次の色へ|不透明度（1 → ¾ → ½ → ¼）|太字|等幅 ⇄ ふつう"),
        "turn": ("↻", "回転", "選んだものを回す", "↻ ↺ ⏹", "cw ccw upright", "右へ 15°|左へ 15°|まっすぐに戻す"),
        "duplicate": ("⧉", "複製", "選んだものを複製"),
        "forward": ("⬆️", "前へ", "選んだものをひとつ手前へ"),
        "backward": ("⬇️", "後ろへ", "選んだものをひとつ奥へ"),
        "front": ("⏫", "手前へ", "選んだものをいちばん手前へ"),
        "back": ("⏬", "奥へ", "選んだものをいちばん奥へ"),
        "delete": ("🗑️", "削除", "選んだものを削除"),
        "slide-add": ("➕📄", "ページ追加", "白紙のページを追加"),
        "slide-copy": ("📑", "ページ複製", "ページを複製"),
        "slide-delete": ("✖️📄", "ページ削除", "ページを削除"),
        "pages": ("🗂️", "一覧", "ページの一覧（タップでそのページへ）"),
        "new": ("🆕", "新規", "最初から（白紙 1 枚）"),
        "import": ("📥", "インポート", "インポート（どの形式から？ 候補から選ぶ）"),
        "export": ("📤", "エクスポート", "エクスポート（どの形式に？ 候補から選ぶ）"),
        "home": ("🏠", "Image Studio", "Image Studio"),
        "inspect": ("🎛️", "詳細", "選んだものの詳細（位置・大きさ・種類別の設定）"),
        "grid": ("⊞", "4枚表示", "4枚表示（その場で編集）"),
    }
    formats = {  # 📥 📤 the same act, each page's own formats
        "slides": {"import": ("画像 カメラ JSON", "image camera open",
                              "画像（PNG・JPEG・WebP をこのページに）|カメラ（撮った写真をこのページに）|JSON（全スライド）"),
                   "export": ("PPTX JSON PNG SVG", "pptx json png svg",
                              "PPTX（全スライド、PowerPoint で編集できる）|JSON（全スライド、また開ける）|PNG（このページ）|SVG（このページ）")},
        "image": {"import": ("画像 カメラ クリップボード JSON 作業履歴 シェルフ", "image camera clipboard open-json open-workspace shelf",
                             "画像（PNG・JPEG・WebP をキャンバスに）|カメラ（撮った写真をキャンバスに）|クリップボード（コピーした画像・Base64）"
                             "|JSON（再編集用のシーン）|作業履歴（最大40状態）|シェルフ（クリップボード・シェルフ）"),
                  "export": ("PNG SVG JSON 作業履歴 Base64", "png svg json workspace base64",
                             "PNG（出力倍率で）|SVG（出力倍率で）|JSON（再編集用）|作業履歴（最大40状態）|Base64（Flutter などへ渡す）")}}[page]
    # 📥 a format read from a file: the toolbar holds its chooser (PySaiyanWeBoo's accept / capture) on both pages
    picture = {"image": "image/png,image/jpeg,image/webp", "camera": "image/png,image/jpeg,image/webp environment"}
    choosers = {"image": {**picture, "open-json": ".json", "open-workspace": ".json,application/json"},
                "slides": {**picture, "open": ".json,application/json"}}[page]
    rows = {"slides": (("create", "text shape emoji kaomoji clock"), ("adjust", "smaller reset bigger undo redo"),
                       ("update", "edit look turn front back delete"), ("pages", "slide-add slide-copy slide-delete pages"),
                       ("file", "new import export home"), ("detail", "inspect grid")),
            "image": (("create", "select text shape stamp emoji kaomoji clock"), ("adjust", "undo-2 undo redo redo-2"),
                      ("update", "duplicate forward backward delete"), ("file", "import export"))}[page]

    def control(act: str) -> dict:
        face, word, tip, *offered = tools[act]
        faces, acts, said = (*formats.get(act, offered), "", "", "")[:3]
        named, picks = said.split("|") if said else [], acts.split()
        return {"act": act, "face": face, "word": word, "words": tip, **({"href": "../"} if act == "home" else {}),
                "candidates": [{"face": f, **({"act": picks[i]} if picks else {}), **({"words": named[i]} if named else {}),
                                **(dict(zip(("accept", "capture"), choosers[picks[i]].split())) if picks and picks[i] in choosers else {})}
                               for i, f in enumerate(faces.split())], "close": act in formats}

    groups = [(group, [control(act) for act in listed.split()]) for group, listed in rows]
    if page == "image":
        scale = ('<select id="export-scale" title="出力倍率" aria-label="出力倍率">'
                 + "".join(f'<option value="{n}">{n}×</option>' for n in (1, 2, 4, 8)) + '</select>')
        return groups, {"file": scale}, {}
    numbers = (
        ("x", "横の位置", -8192, 8192, "any", ""), ("y", "縦の位置", -8192, 8192, "any", ""),
        ("w", "幅", 1, 8192, "any", ""), ("h", "高さ", 1, 8192, "any", ""),
        ("strokeWidth", "線幅", 0, 64, "any", "rect ellipse triangle arrow clock"),
        ("cell", "モザイクの幅", 1, 512, 1, "image"), ("levels", "色の段階", 2, 256, 1, "image"),
    )
    inspector = ('<fieldset id="phone-inspector" hidden><legend>詳細設定</legend>' + "".join(
        f'<label>{escape(label)}<input type="number" data-property="{key}" data-kinds="{kinds}" min="{lo}" max="{hi}" step="{step}"></label>'
        for key, label, lo, hi, step, kinds in numbers)
        + '<label><input type="checkbox" data-property="italic" data-kinds="text">斜体</label>'
        + '<label>矢印の先端<select data-property="headPlacement" data-kinds="arrow">'
          '<option value="tip">端</option><option value="middle">中央</option></select></label></fieldset>')
    after = {"adjust": '<div id="phone-layers" class="ui-toolbar-row ui-current-items" role="group" aria-label="レイヤー（奥から手前）" hidden></div>',
             "pages": '<div id="phone-pages" class="ui-toolbar-row ui-current-items" role="group" aria-label="ページの一覧" hidden></div>',
             "detail": inspector}
    return groups, {}, after


def _phone_html() -> str:
    slide = ('<div id="phone-svg" class="phone-svg" data-ui-fill></div>'
             '<div id="phone-pick" class="phone-pick" hidden><span class="phone-grip" data-grip aria-hidden="true">↘</span></div>')
    head = STUDIO_HTML[:STUDIO_HTML.index("</head>")]
    for name in ("style.css", "studio.js", "brand/manifest.webmanifest", "brand/apple-touch-icon.png", "brand/favicon.ico",
                 "brand/icon.svg"):
        head = head.replace(f'"{name}"', f'"../{name}"')
    head = head.replace("Ironmate — Image Studio", "Ironmate — Slides")
    scale = " ".join(f"{v:g}" for v in PHONE_TEXT["scale"])
    return (head + "</head>\n"
            f'  <body class="ui-elements" data-ui-theme="green" data-page="phone" data-text-size="{PHONE_TEXT["size"]}" data-text-scale="{scale}">\n'
            '    <main class="phone">\n'
            f'      {PSWB_PARTS["stage"].replace("{slide}", slide)}\n'
            '      <div id="phone-grid" role="group" aria-label="4枚表示" hidden></div>\n'
            '      <div class="phone-deck"><textarea id="phone-edit" class="phone-edit" hidden aria-label="文字" rows="3" spellcheck="false"></textarea>'
            f'{PSWB_PARTS["pager"]}'
            '<p id="phone-status" class="phone-status" role="status"></p>'
            f'<div class="phone-tools">{PSWB_PARTS.get("slides-toolbar", "")}</div></div>\n'
            "    </main>\n  </body>\n</html>\n")


PHONE_HTML = _phone_html()
STUDIO_HTML = STUDIO_HTML.replace('        <!-- 🧰 toolbar: studio_toolbar("image") -->\n', PSWB_PARTS.get("image-toolbar", ""), 1)   # 🧰 Image Studio's tools

BROWSER_TASK_JS = r"""/* PSWB async-task.js */
/**
 * Run a browser task with optional deadline. cancel() rejects the pending result,
 * and the operation can observe the AbortSignal to stop its own work.
 */
export function startTask(run, {timeoutMs} = {}) {
  if (timeoutMs !== undefined && (!Number.isFinite(timeoutMs) || timeoutMs < 0 || timeoutMs > 2147483647))
    throw new RangeError("timeoutMs must be a non-negative timer value");
  const controller = new AbortController();
  const {signal} = controller;
  let timer, onAbort, finished = false;
  const stopped = new Promise((_, reject) => {
    onAbort = () => reject(signal.reason);
    signal.addEventListener("abort", onAbort, {once: true});
  });
  if (timeoutMs !== undefined) {
    timer = setTimeout(() => controller.abort(new DOMException("Task timed out", "TimeoutError")), timeoutMs);
  }
  const work = Promise.resolve().then(() => {
    signal.throwIfAborted();
    return run(signal);
  });
  const promise = Promise.race([stopped, work]).finally(() => {
    finished = true;
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  });
  return {promise, cancel() { if (!finished) controller.abort(); }};
}
/* End PSWB async-task.js */
"""

RECORDS_JS = r"""/* PSWB records.js */
/** Record boards: a text and a status filter over table rows or cards, per-field drafts kept in localStorage (best effort), each step's state on its card, and JSON export/import of those drafts (tied to a source version when the board names one). No fetch; values are text, never HTML. */
const KEY=/^[A-Za-z0-9_.:/#@-]{1,200}$/;
function storage(){try{const s=globalThis.localStorage;s.getItem("");return s}catch{return null}}
function value(field){return field.type==="checkbox"?(field.checked?"1":""):field.value}
function assign(field,text){if(field.type==="checkbox")field.checked=text==="1";else field.value=text;field.dispatchEvent(new Event("input",{bubbles:true}))}
/** The rows of a table's bodies, or the [data-ui-item] elements of a board. */
function items(target){return target.tBodies?[...target.tBodies].flatMap(body=>[...body.rows]):[...target.querySelectorAll("[data-ui-item]")]}
/** Show the items of target (table rows, or its [data-ui-item] elements) whose text contains the query and, when status is given, whose data-status is it; returns the number still shown. */
export function filterItems(target,query="",status=""){const q=String(query||"").trim().toLowerCase();let shown=0;for(const item of items(target)){const hit=(!q||item.textContent.toLowerCase().includes(q))&&(!status||item.dataset.status===status);item.hidden=!hit;if(hit)shown++}return shown}
/** input[data-ui-filter="#target"] (text) and select[data-ui-filter-status="#target"] (status) filter one target together; data-ui-filter-count="#out" receives the shown count. One run function per target. */
export function bindFilter(root=document){const targets=new Map();for(const control of[...root.querySelectorAll("input[data-ui-filter]"),...root.querySelectorAll("select[data-ui-filter-status]")]){const target=root.querySelector(control.dataset.uiFilter||control.dataset.uiFilterStatus);if(!target)continue;const t=targets.get(target)||{text:null,status:null,count:null};targets.set(target,t);if(control.dataset.uiFilterStatus!==undefined)t.status=control;else t.text=control;if(control.dataset.uiFilterCount)t.count=root.querySelector(control.dataset.uiFilterCount)}return[...targets].map(([target,t])=>{const run=()=>{const n=filterItems(target,t.text?t.text.value:"",t.status?t.status.value:"");if(t.count)t.count.textContent=String(n)};if(t.text)t.text.addEventListener("input",run);if(t.status)t.status.addEventListener("change",run);target.addEventListener("ui-status",run);run();return run})}
/** select[data-ui-status] (a step's state) writes its value to the closest [data-ui-item] as data-status and its option's text to that item's [data-ui-status-tag], then tells the filters (event ui-status). */
export function bindStatus(root=document){const fields=[...root.querySelectorAll("select[data-ui-status]")];for(const field of fields){const item=field.closest?field.closest("[data-ui-item]"):null;if(!item)continue;const tag=item.querySelector("[data-ui-status-tag]");const sync=()=>{item.dataset.status=field.value;const option=field.selectedOptions&&field.selectedOptions[0];if(tag)tag.textContent=option?option.textContent:field.value;item.dispatchEvent(new Event("ui-status",{bubbles:true}))};field.addEventListener("input",sync);field.addEventListener("change",sync);sync()}return fields}
/** Fields with data-ui-draft="key" restore from and save to localStorage under scope:key. Returns the bound fields. */
export function bindDrafts(root=document,{scope="web-ui-drafts"}={}){const store=storage();const fields=[...root.querySelectorAll("[data-ui-draft]")].filter(f=>KEY.test(f.dataset.uiDraft));for(const field of fields){const key=scope+":"+field.dataset.uiDraft;const saved=store?store.getItem(key):null;if(saved!==null)assign(field,saved);field.addEventListener("input",()=>{try{if(store)store.setItem(key,value(field))}catch{}})}return fields}
/** Non-empty draft values keyed by their data-ui-draft name. */
export function collectDrafts(root=document){const out={};for(const field of root.querySelectorAll("[data-ui-draft]")){const text=value(field);if(text!=="")out[field.dataset.uiDraft]=text}return out}
/** Apply {key: text} to the matching draft fields; unknown keys are ignored. Returns the number applied. */
export function applyDrafts(root,drafts){let n=0;if(!drafts||typeof drafts!=="object")return 0;for(const field of root.querySelectorAll("[data-ui-draft]")){const text=drafts[field.dataset.uiDraft];if(typeof text==="string"){assign(field,text);n++}}return n}
/** Apply a file's drafts. When the board names its source (data-ui-records-source, a commit) and the file names another, the states (select[data-ui-status]) go back to their first option: records of another version are to be checked again. Returns "loaded", "stale" or "bad". */
export function importDrafts(root,data){if(!data||typeof data!=="object"||Array.isArray(data))return"bad";const drafts=data.drafts&&typeof data.drafts==="object"?data.drafts:data;const board=root.matches&&root.matches("[data-ui-records-source]")?root:root.querySelector("[data-ui-records-source]");const source=board?board.dataset.uiRecordsSource:"";if(!applyDrafts(root,drafts))return"bad";if(!source||data.source===source)return"loaded";for(const field of root.querySelectorAll("select[data-ui-status][data-ui-draft]"))if(field.options&&field.options.length)assign(field,field.options[0].value);return"stale"}
/** [data-ui-export] downloads the drafts as JSON (with the board's source when it names one); input[type=file][data-ui-import] reads such a file back; [data-ui-records-message] says how it went. */
export function bindRecordsIO(root=document,{filename="records.json"}={}){const board=root.matches&&root.matches("[data-ui-records-source]")?root:root.querySelector("[data-ui-records-source]");const source=board?board.dataset.uiRecordsSource:undefined;const say=state=>{for(const out of root.querySelectorAll("[data-ui-records-message]")){const text=out.getAttribute("data-ui-msg-"+state);if(text!==null)out.textContent=text}};for(const button of root.querySelectorAll("[data-ui-export]"))button.addEventListener("click",()=>downloadText(button.dataset.uiExport||filename,JSON.stringify({schema:"web-ui-drafts/1",exported:new Date().toISOString(),...(source?{source}:{}),drafts:collectDrafts(root)},null,2)));for(const input of root.querySelectorAll("input[type=file][data-ui-import]"))input.addEventListener("change",async()=>{const file=input.files&&input.files[0];if(!file)return;let state="bad";try{state=importDrafts(root,JSON.parse(await file.text()))}catch{}say(state);input.value=""})}
/** Save text as a file in the browser (a Blob link, revoked after the click). */
export function downloadText(filename,text,type="application/json"){const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([text],{type}));a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
/** [data-ui-download="name.json"] saves the text of its data-ui-download-source (a <script type="application/json">) as that file. Returns the buttons. */
export function bindDownloads(root=document){const buttons=[...root.querySelectorAll("[data-ui-download]")];for(const button of buttons){const source=root.querySelector(button.dataset.uiDownloadSource||"#none");if(source)button.addEventListener("click",()=>downloadText(button.dataset.uiDownload,source.textContent))}return buttons}
/** select[data-ui-choice="name"] shows the [data-ui-choice-panel="name"] whose data-ui-choice-value is its value and hides the others (without JS every panel shows). With data-ui-draft the choice is kept like any draft. Returns the bound selects. */
export function bindChoice(root=document){const fields=[...root.querySelectorAll("select[data-ui-choice]")];for(const field of fields){const panels=[...root.querySelectorAll("[data-ui-choice-panel]")].filter(p=>p.dataset.uiChoicePanel===field.dataset.uiChoice);const sync=()=>{for(const p of panels)p.hidden=p.dataset.uiChoiceValue!==field.value};field.addEventListener("change",sync);field.addEventListener("input",sync);sync()}return fields}
/* 📦📜 A saved state as text, so a page can go on where it stopped on another device or after its storage is gone (no DOM, no storage: the
   page decides what its state is). saveText / saveState: portable JSON as one base64url line (copy it, keep it in a file) — or, with
   kinds, deflated when that is shorter and written as a spell (a Promise then: browsers deflate asynchronously). spellText / spellBytes:
   bytes as a spell (ふっかつのじゅもん) in lines of 5 7 5, of kinds 64 (hiragana, 6 bits a character: to write down and type back), 128
   (with を ん, katakana and A–Z: 7 bits) or 4096 (with JIS kanji: 12 bits, half the characters of base64 — to paste, not to type). Each
   kind holds the one before. bitsPack / bitsUnpack: whole numbers packed by a layout into a few bytes (JSON is too long to type). Every
   text carries a 16-bit check (CRC-16/CCITT-FALSE; the line and a spell of 64 start with it, a spell of 128 or 4096 ends its bytes with
   it, then a 1): in a spell of 64 or 128, one wrong character or two swapped neighbours never pass; any other change passes once in
   65,536. pysaiyanweboo's save_text, save_state, spell_text, spell_bytes, bits_pack and bits_unpack are their twins and read what these
   write. Numbers must fit in JavaScript’s safe range. */
const KANA="あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわがぎぐげござじずぜぞだぢづでどばびぶべぼをんアイエオクケコサシスソタチツテトナニヌネノハヒフホマミムメユヨラルレロワABCDEFGHIJKLMNOPQRSTUVWXYZ";
let KANJI="";
/** The characters of a spell of kinds 64, 128 or 4096: KANA's first 64 (hiragana), all of it (を ん, the katakana no hiragana looks like, A–Z), or it and the first 3968 JIS X 0208 kanji in their own (EUC-JP) order — in every Japanese font, and no table to carry. */
function spellKinds(kinds){if(kinds===64||kinds===128)return KANA.slice(0,kinds);if(kinds!==4096)throw new Error("kinds is 64, 128 or 4096");
 if(!KANJI){const jis=new TextDecoder("euc-jp",{fatal:true});let found="";for(let row=16;row<85;row++)for(let cell=1;cell<95;cell++)try{found+=jis.decode(Uint8Array.of(160+row,160+cell))}catch{}KANJI=found.slice(0,3968)}return KANA+KANJI}
function crc16(bytes){let c=0xFFFF;for(const b of bytes){c^=b<<8;for(let i=0;i<8;i++)c=(c&0x8000?c<<1^0x1021:c<<1)&0xFFFF}return c}
function checked(bytes){const c=crc16(bytes),out=new Uint8Array(bytes.length+2);out[0]=c>>8;out[1]=c&255;out.set(bytes,2);return out}
function unchecked(raw,wrong){if(raw.length<2||crc16(raw.subarray(2))!==(raw[0]<<8|raw[1]))throw new Error(wrong);return raw.subarray(2)}
function portableNumber(_,value){
 if(typeof value==="number"&&!(value>=-Number.MAX_SAFE_INTEGER&&value<=Number.MAX_SAFE_INTEGER))throw new Error("use text for numbers outside the portable JSON range");
 return value
}
async function through(bytes,stream){return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(stream)).arrayBuffer())}
/** Portable JSON as one base64url line: a 16-bit check, then its compact UTF-8 JSON. With kinds (64, 128 or 4096) a Promise of a spell instead: 0 and the JSON, or 1 and it deflated when that is shorter. */
export function saveText(state,kinds){const bytes=()=>{const json=JSON.stringify(state,portableNumber);if(typeof json!=="string")throw new Error("a save must be a JSON value");return new TextEncoder().encode(json)};
 if(kinds)return (async()=>{const raw=bytes(),small=await through(raw,new CompressionStream("deflate")),body=small.length<raw.length?small:raw,out=new Uint8Array(body.length+1);out[0]=body===small?1:0;out.set(body,1);return spellText(out,kinds)})();
 let text="";for(const b of checked(bytes()))text+=String.fromCharCode(b);return btoa(text).replace(/\+/g,"-").replace(/\//g,"_").replace(/=+$/,"")}
/** The value saveText (or save_text) wrote, with the same kinds (a Promise then); an Error when the text was cut or changed. Spaces and line breaks in it are ignored. */
export function saveState(text,kinds){const wrong="the save text is cut or changed",parse=raw=>JSON.parse(new TextDecoder("utf-8",{fatal:true}).decode(raw),portableNumber);
 if(kinds)return (async()=>{try{const bytes=spellBytes(text,kinds);if(!bytes.length||bytes[0]>1)throw 0;return parse(bytes[0]?await through(bytes.subarray(1),new DecompressionStream("deflate")):bytes.subarray(1))}catch{throw new Error(wrong)}})();
 try{const raw=atob(String(text).replace(/[ \t\r\n]/g,"").replace(/-/g,"+").replace(/_/g,"/"));return parse(unchecked(Uint8Array.from(raw,c=>c.charCodeAt(0)),wrong))}catch{throw new Error(wrong)}}
/** Bytes (a Uint8Array or an array of 0..255) as a spell of kinds 64 (the default), 128 or 4096, in lines of 5 7 5. 12 bytes are 19, 17 or 10 characters. */
export function spellText(data,kinds=64){const chars=spellKinds(kinds),width=Math.log2(kinds),bytes=Uint8Array.from(data),byte=b=>b.toString(2).padStart(8,"0");let bits="";
 if(kinds===64)for(const b of checked(bytes))bits+=byte(b);                                                  // 64: the check, the bytes
 else{for(const b of bytes)bits+=byte(b);bits+=crc16(bytes).toString(2).padStart(16,"0")+"1"}                // 128, 4096: the bytes, the check, a 1 (so their end is known)
 bits+="0".repeat((width-bits.length%width)%width);let text="";for(let i=0;i<bits.length;i+=width)text+=chars[parseInt(bits.slice(i,i+width),2)];const lines=[];
 for(let i=0;i<text.length;i+=17)lines.push([text.slice(i,i+5),text.slice(i+5,i+12),text.slice(i+12,i+17)].filter(Boolean).join(" "));return lines.join("\n")}
/** The bytes spellText (or spell_text) wrote with the same kinds, as a Uint8Array; spaces and line breaks are ignored, and in a spell of 64 katakana reads as hiragana. A spell that is not one throws Error("じゅもんが ちがいます"). */
export function spellBytes(text,kinds=64){const wrong="じゅもんが ちがいます",chars=spellKinds(kinds),width=Math.log2(kinds),at=new Map([...chars].map((c,i)=>[c,i]));let bits="";
 for(let c of String(text)){if(" \t\r\n　".includes(c))continue;if(kinds===64&&c>="ァ"&&c<="ヶ")c=String.fromCharCode(c.charCodeAt(0)-96);if(!at.has(c))throw new Error(wrong);bits+=at.get(c).toString(2).padStart(width,"0")}
 const bytes=n=>Uint8Array.from({length:n},(_,i)=>parseInt(bits.slice(i*8,i*8+8),2));
 if(kinds===64){const n=bits.length>>3;if(!bits.length||bits.length-n*8>=6||bits.slice(n*8).includes("1"))throw new Error(wrong);return unchecked(bytes(n),wrong)}
 const end=bits.lastIndexOf("1");if(end<16||bits.length-end>width||end%8)throw new Error(wrong);
 const raw=bytes(end/8),n=raw.length-2;if(crc16(raw.subarray(0,n))!==(raw[n]<<8|raw[n+1]))throw new Error(wrong);return raw.subarray(0,n)}
function layoutBits(layout){for(const[name,width]of layout)if(typeof name!=="string"||!Number.isInteger(width)||width<1||width>32)throw new Error("a layout is [name, width in bits (1 to 32)] pairs");if(new Set(layout.map(f=>f[0])).size!==layout.length)throw new Error("a layout names each field once");return layout.reduce((sum,f)=>sum+f[1],0)}
/** Whole numbers packed by layout ([["version",4],["level",7],["gold",16]]: name and width in bits, first field first), zero-padded to whole bytes. A missing value is 0. */
export function bitsPack(layout,values={}){const total=layoutBits(layout),names=new Set(layout.map(f=>f[0]));for(const name of Object.keys(values))if(!names.has(name))throw new Error("no field "+name);let bits="";
 for(const[name,width]of layout){const value=Number(values[name]??0);if(!Number.isInteger(value)||value<0||value>=2**width)throw new Error(name+" does not fit "+width+" bits");bits+=value.toString(2).padStart(width,"0")}
 bits+="0".repeat((8-total%8)%8);return Uint8Array.from({length:bits.length/8},(_,i)=>parseInt(bits.slice(i*8,i*8+8),2))}
/** The numbers bitsPack (or bits_pack) packed by the same layout; an Error when the bytes are not that layout's. */
export function bitsUnpack(layout,data){const total=layoutBits(layout),bits=[...Uint8Array.from(data)].map(b=>b.toString(2).padStart(8,"0")).join("");if(bits.length!==Math.ceil(total/8)*8||bits.slice(total).includes("1"))throw new Error("the bytes are not this layout's");
 const out={};let at=0;for(const[name,width]of layout){out[name]=parseInt(bits.slice(at,at+width),2);at+=width}return out}
/** Bind everything inside root; pages mark the board with data-ui-records (or carry a data download) so loading the module is enough. */
export function mount(root=document,options={}){bindDrafts(root,options);bindChoice(root);bindStatus(root);bindFilter(root);bindRecordsIO(root,options);bindDownloads(root);return root}
if(typeof document!=="undefined"&&(document.querySelector("[data-ui-records]")||document.querySelector("[data-ui-download]"))){const start=()=>mount(document);if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start()}
/* End PSWB records.js */
"""

TOOLS_HTML = r"""<!doctype html>
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
    <script defer src="../studio.js"></script>
    <script type="module" src="./records.js"></script>
  </head>
  <body class="ui-elements" data-ui-theme="green" data-page="tools">
    <header>
      <a class="brand" href="../"><img src="../brand/heatmap.svg" width="48" height="48" alt="I’m — 🔰がアポストロフィのIronmateロゴ" /> IRONMATE</a>
      <nav aria-label="サイト">
        <a href="#brand">ロゴ素材</a><a href="../">Image Studio ↗</a
        ><a href="https://myon-bioinformatics.github.io/#ironmate"
          >🏠 ポートフォリオ ↗</a
        ><a href="https://github.com/myon-bioinformatics/Ironmate">🐙 GitHub リポジトリ ↗</a>
      </nav>
    </header>
    <main>
      <h1>画像ツール</h1>
      <p class="lead">
        画像とJSONは端末内で処理します。
      </p>
      <div class="jump">
        <a href="#digest">画像一覧</a
        ><a href="#composition">🎵 作曲</a><a href="#features">CLI対応表</a>
      </div>
      <p id="message" role="status" aria-live="polite"></p>
      <section id="digest">
        <div class="section-heading">
          <h2>画像一覧</h2>
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
          ><button id="images-cancel" type="button" hidden>読み込みを中止</button><button id="digest-png" disabled>一覧PNG</button
          ><button id="digest-html" disabled>一覧HTML</button>
        </div>
        <p class="hint">
          1枚8 MiB・4 MP、合計32 MiBまで。一覧では長辺512 px以下に縮小します。
        </p>
        <div id="image-list" class="image-list"></div>
      </section>
      <section id="composition" data-ui-records>
        <h2>🎵 Composition Studio</h2>

        <label>歌詞<textarea id="song-lyrics" data-ui-draft="ironmate-song-lyrics" rows="4"></textarea></label>
        <label>パート別コード進行（パート名 = ローマ数字）<textarea id="song-parts" data-ui-draft="ironmate-song-parts" rows="3">Aメロ = I V vi IV
サビ = IV V I I</textarea></label>
        <label>曲順（空白区切り）<input id="song-order" data-ui-draft="ironmate-song-order" value="Aメロ サビ サビ"></label>
        <button id="song-arrange">曲順に展開</button>
        <ol class="ui-current-items" id="song-sections" aria-label="曲順"></ol>
        <label>曲全体のコード進行<textarea id="song-progression" rows="2" readonly></textarea></label>
        <fieldset id="song-audio" hidden><legend>曲を試聴</legend>
          <label>キー<select id="song-key" data-ui-draft="ironmate-song-key"><option>C</option><option>D</option><option>E</option><option>F</option><option>G</option><option>A</option><option>B</option></select></label>
          <label>BPM<input type="number" id="song-bpm" data-ui-draft="ironmate-song-bpm" value="120" min="30" max="300" required></label>
          <button id="song-play">▶ 曲順で試聴</button><button id="song-stop">■ 停止</button>
        </fieldset>
        <p id="song-status" role="status"></p>
      </section>
      <details id="features" class="ui-panel">
        <summary>ブラウザとCLIの対応表</summary>
        <div class="table-wrap"><table>
          <thead><tr><th>操作</th><th>ブラウザ</th><th>CLI</th></tr></thead>
          <tbody>
            <tr><td>画像・レイヤー編集</td><td><a href="../">画像編集</a></td><td>image_studio.py / studio_ingress.py</td></tr>
            <tr><td>ドット絵</td><td>Image Studio のグリッド編集</td><td>pixel_grid.py / grid_tools.py</td></tr>
            <tr><td>画像一覧・比較</td><td><a href="#digest">一覧作成</a></td><td>image_digest.py / browser_matrix.py</td></tr>
            <tr><td>Base64容量</td><td><a href="https://myon-bioinformatics.github.io/CaChereCyCle/#capacity">CCCCで計算</a></td><td>ironlib/size_estimate.py</td></tr>
            <tr><td>PPTX</td><td><a href="../slides/">スライド編集</a></td><td>pptx_pipeline.py / pptx_replace.py / ironlib/pptx_preview.py</td></tr>
          </tbody>
        </table></div>
      </details>
      <section id="brand">
        <h2>ロゴ素材</h2>
        <p>選択すると保存します。</p>
        <div class="exports">""" + "\n".join(
            f'<a href="../brand/{asset}" download><img src="../brand/{preview}.svg" width="48" height="48" alt=""> {label}</a>'
            for preview, asset, label in (
                ("mono", "mono.svg", "Pixel Mono"), ("dark-green", "dark-green.svg", "Dark Green"),
                ("famicom", "famicom.svg", "Famicom Retro"), ("gameboy", "gameboy.svg", "GameBoy Style"),
                ("heatmap", "heatmap.svg", "Heatmap Pixel"), ("pixel-3d", "app-512.png", "Pixel 3D (PNG)"),
            )
        ) + r"""</div>
        <p>ホーム画面への追加はAndroidのブラウザメニュー、iPhoneの共有メニューから。</p>
      </section>
    </main>
    <footer>
      IRONMATE /
      ブラウザ内の作業は自動保存されません。持ち出すときはダウンロードしてください。
    </footer>
  </body>
</html>
"""

