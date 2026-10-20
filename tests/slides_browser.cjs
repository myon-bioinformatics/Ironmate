"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path"),
  { spawnSync } = require("node:child_process");
const { chromium } = require(
  process.env.IRONMATE_PLAYWRIGHT_MODULE || "playwright",
);
const url =
    (process.env.IRONMATE_PAGES_URL || "http://127.0.0.1:8080/Ironmate/") +
    "slides/",
  out = path.resolve("build/pages-evidence");
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
        viewport: { width: 1600, height: 1100 },
        acceptDownloads: true,
      }),
      errors = [],
      requests = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) => requests.push(r.url()));
    page.on("dialog", (d) => d.accept());
    await page.goto(url);
    await page.waitForFunction(() => !!window.IronmateSlideEditor);
    assert.equal(
      (await page.evaluate(() => IronmateSlideEditor.deck)).slides.length,
      1,
    );
    await page.click('[data-layer-id="title"]');
    await page.fill("#text", "編集したタイトル <>&");
    await page.click("#apply-text");
    await page.fill("#font-size", "64");
    await page.locator("#font-size").blur();
    await page.click("#slide-bold");
    let first = await page.evaluate(() => IronmateStudio.scene);
    assert.equal(first.layers[0].text, "編集したタイトル <>&");
    assert.equal(first.layers[0].fontSize, 64);
    assert.equal(first.layers[0].bold, false);
    await page.click("#slide-arrow");
    await page.waitForFunction(() =>
      IronmateStudio.scene.layers.some((l) => l.kind === "arrow"),
    );
    await page.click("#slide-duplicate");
    await page.waitForFunction(() => IronmateSlideEditor.active === 1);
    await page.click("#slide-add");
    await page.waitForFunction(() => IronmateSlideEditor.active === 2);
    await page.fill("#slide-title", "二枚目のタイトル");
    await page.selectOption(
      "#font-sample",
      "日本語の文章と ABC abc 0123456789",
    );
    await page.click("#slide-template");
    await page.waitForFunction(() => IronmateStudio.scene.layers.length === 2);
    await page.click('[data-tool="clock"]');
    await page.locator("#board").click({ position: { x: 250, y: 300 } });
    await page.waitForFunction(() =>
      IronmateStudio.scene.layers.some((l) => l.kind === "clock"),
    );
    await page.click("#slide-up");
    await page.waitForFunction(() => IronmateSlideEditor.active === 1);
    await page.selectOption("#slide-select", "2");
    await page.waitForFunction(() => IronmateSlideEditor.active === 2);
    await page.click("#slide-delete");
    await page.waitForFunction(
      () => IronmateSlideEditor.deck.slides.length === 2,
    );
    await page.selectOption("#slide-select", "0");
    await page.waitForFunction(() => IronmateSlideEditor.active === 0);
    const restored = await page.evaluate(() => IronmateStudio.scene);
    assert.equal(restored.layers[0].text, "編集したタイトル <>&");
    assert.equal(restored.layers[0].fontSize, 64);
    const download = async (id, name) => {
      const pending = page.waitForEvent("download");
      await page.click("#" + id);
      await (await pending).saveAs(path.join(out, name));
    };
    await download("deck-save", "slides.json");
    const saved = await page.evaluate(() => IronmateSlideEditor.deck);
    await page.setInputFiles("#deck-open", {
      name: "invalid.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"schema":"wrong"}'),
    });
    await page.waitForFunction(
      () => document.getElementById("deck-status").dataset.error === "true",
    );
    assert.deepEqual(
      await page.evaluate(() => IronmateSlideEditor.deck),
      saved,
    );
    await page.click("#slide-add");
    await page.waitForFunction(
      () => IronmateSlideEditor.deck.slides.length === 3,
    );
    await page.setInputFiles("#deck-open", path.join(out, "slides.json"));
    await page.waitForFunction(
      () =>
        IronmateSlideEditor.deck.slides.length === 2 &&
        IronmateSlideEditor.active === 0,
    );
    assert.deepEqual(
      await page.evaluate(() => IronmateSlideEditor.deck),
      saved,
    );
    await download("deck-pptx", "slides.pptx");
    await page.waitForFunction(() =>
      document.getElementById("deck-status").textContent.includes("2枚のPPTX"),
    );
    await page.screenshot({
      path: path.join(out, "slides-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(out, "slides-mobile.png"),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert(
      requests.every(
        (r) =>
          r.startsWith(new URL(url).origin + "/") || /^(blob|data):/.test(r),
      ),
    );
    const result = spawnSync(
      process.env.PYTHON || "python",
      [
        "-S",
        "-c",
        `from pathlib import Path\nfrom zipfile import ZipFile\nfrom xml.etree import ElementTree as E\nfrom pptx_ooxml import require_package,ordered_slide_members\np=Path('build/pages-evidence/slides.pptx')\nassert require_package(p)==2\nns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}\nwith ZipFile(p) as z:\n assert z.testzip() is None\n slides=[E.fromstring(z.read(n)) for n in ordered_slide_members(z)]\n assert slides[0].find('.//a:t',ns).text=='編集したタイトル <>&'\n assert slides[0].find('.//p:grpSp',ns) is not None\n assert slides[1].find('.//a:t',ns).text=='二枚目のタイトル'\n assert len(slides[1].findall('.//p:pic',ns))==1\n assert [e.text for e in slides[1].findall('.//a:t',ns)][1]=='日本語の文章と ABC abc 0123456789'\n for name in z.namelist():\n  if name.endswith(('.xml','.rels')):E.fromstring(z.read(name))\nprint('Browser PPTX: two ordered slides, editable text, native grouped arrow, per-layer PNG, XML and ZIP CRC verified')`,
      ],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    console.log(result.stdout.trim());

    // Paste long text through the real inspector, then compare the visible
    // SVG line strings with the editable DrawingML exported by this browser.
    await page.setViewportSize({ width: 1600, height: 1100 });
    await page.click('[data-layer-id="title"]');
    const japanese = "日本語の長い文章を貼り付け、ボックスの幅に合わせて折り返します。".repeat(3) + "\n\n明示改行の後です。\n";
    await page.fill("#text", japanese);
    await page.click("#apply-text");
    for (const [id, value] of [["w", "520"], ["h", "60"], ["font-size", "32"], ["rotation", "12"]]) {
      await page.fill("#" + id, value);
      await page.locator("#" + id).blur();
    }
    const lineCount = () => page.locator('#board g[data-layer="title"] tspan').count();
    const wideCount = await lineCount();
    assert(wideCount > 3);
    await page.fill("#w", "300");
    await page.locator("#w").blur();
    assert((await lineCount()) > wideCount);
    await page.fill("#font-size", "24");
    await page.locator("#font-size").blur();
    const smallCount = await lineCount();
    await page.click("#slide-bold");
    const boldCount = await lineCount();
    assert(boldCount >= smallCount);
    await page.click('[data-layer-id="body"]');
    const english = "English words should stay together when they fit. ".repeat(5) + "\n\nhttps://example.test/" + "longurl".repeat(14) + " 👨‍👩‍👧‍👦 e\u0301 🇯🇵\n";
    await page.fill("#text", english);
    await page.click("#apply-text");
    await page.selectOption("#font-family", "mono");
    for (const [id, value] of [["w", "600"], ["font-size", "24"]]) {
      await page.fill("#" + id, value);
      await page.locator("#" + id).blur();
    }
    const longDeck = await page.evaluate(() => IronmateSlideEditor.deck);
    assert.equal(longDeck.slides[0].layers[0].text, japanese);
    assert.equal(longDeck.slides[0].layers[1].text, english);
    await download("deck-save", "slides-wrapped.json");
    // Old deck JSON and the existing single-scene/workspace import routes
    // must all receive the same wrap default without rewriting source text.
    const legacy = JSON.parse(JSON.stringify(longDeck));
    for (const scene of legacy.slides) for (const l of scene.layers) delete l.wrap;
    await page.setInputFiles("#deck-open", { name: "legacy.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(legacy)) });
    await page.waitForFunction(() => IronmateSlideEditor.ready);
    assert.deepEqual(await page.evaluate(() => IronmateSlideEditor.deck), longDeck);
    await page.setInputFiles("#open", { name: "legacy-scene.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(legacy.slides[0])) });
    await page.waitForFunction(() => document.querySelector('#board g[data-layer="title"] tspan')?.textContent !== undefined);
    assert.equal(await page.evaluate(() => IronmateStudio.scene.layers[0].wrap), true);
    const workspace = await page.evaluate((scene) => StudioCore.workspaceText(new StudioCore.History(scene)), legacy.slides[0]);
    await page.setInputFiles("#open-workspace", { name: "legacy-workspace.json", mimeType: "application/json", buffer: Buffer.from(workspace) });
    await page.waitForFunction(() => document.getElementById("status").textContent.includes("作業履歴を復元"));
    const manifest = await page.evaluate(() => IronmateStudio.scene.layers.filter(l => l.kind === "text" && !l.mono).map(l => {
      const spans = [...document.querySelectorAll(`#board g[data-layer="${l.id}"] tspan`)];
      const layout = StudioCore.textLayout(l);
      return { id: l.id, layer: l, layout, visible: spans.map(s => s.textContent), widths: spans.map(s => s.getComputedTextLength()) };
    }));
    for (const item of manifest) {
      assert.deepEqual(item.visible, item.layout.flat());
      assert(item.widths.every(w => w <= item.layer.w + 1), JSON.stringify(item));
    }
    fs.writeFileSync(path.join(out, "slides-wrapped-layout.json"), JSON.stringify(manifest, null, 2));
    await download("deck-pptx", "slides-wrapped.pptx");
    await page.screenshot({ path: path.join(out, "slides-wrapped-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(out, "slides-wrapped-mobile.png"), fullPage: true });
    const wrapped = spawnSync(process.env.PYTHON || "python", ["-S", "-c", `
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
from pptx_ooxml import require_package, ordered_slide_members
p=Path('build/pages-evidence/slides-wrapped.pptx')
assert require_package(p)==2
ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with ZipFile(p) as z:
 assert z.testzip() is None
 root=E.fromstring(z.read(ordered_slide_members(z)[0]))
 for item in json.loads(Path('build/pages-evidence/slides-wrapped-layout.json').read_text()):
  shape=next(s for s in root.findall('.//p:sp',ns) if s.find('p:nvSpPr/p:cNvPr',ns).get('name')==item['layer'].get('name',item['id']))
  layout=[[t.text or '' for t in para.findall('a:r/a:t',ns)] for para in shape.findall('p:txBody/a:p',ns)]
  assert layout==item['layout'], (item['id'],layout,item['layout'])
  assert shape.find('p:txBody/a:bodyPr',ns).get('wrap')=='square'
  assert shape.find('p:txBody/a:bodyPr/a:noAutofit',ns) is not None
  assert shape.find('p:spPr/a:xfrm',ns).get('rot')==str(round(item['layer']['rotation']*60000))
print('Long Japanese/English: visible SVG lines match native PPTX, explicit paragraphs, blank lines and rotation')
`], { encoding: "utf8" });
    assert.equal(wrapped.status, 0, wrapped.stderr);
    console.log(wrapped.stdout.trim());
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
