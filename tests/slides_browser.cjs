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
    assert.deepEqual((await page.evaluate(() => IronmateStudio.scene)).layers, []);
    await page.check("#slide-grid-mode");
    for (let i = 1; i < 5; i++) {
      await page.click("#slide-add");
      await page.waitForFunction(n => IronmateSlideEditor.active === n, i);
    }
    assert.equal(await page.locator(".slide-grid > div").count(), 1);
    await page.selectOption("#slide-select", "0");
    await page.waitForFunction(() => IronmateSlideEditor.active === 0);
    assert.equal(await page.locator(".slide-grid > div").count(), 4);
    await page.getByRole("button", {name: "3 枚目を編集"}).click();
    await page.waitForFunction(() => IronmateSlideEditor.active === 2);
    // The tools place everything: 図形(→) is the arrow, T 文字列 a text box (wide enough to keep its words on one line).
    const press = async (fx, fy) => {
      const box = await page.locator("#board svg").boundingBox();
      await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
    };
    const arrow = async () => {
      await page.click('[data-tool="shape"]');
      await page.locator("#candidates button", { hasText: "→" }).click();
      assert.equal(await page.textContent('[data-tool="shape"]'), "図形(→)");
      await press(0.4, 0.7);
      await page.click('[data-tool="select"]');
    };
    const words = async (text, fy) => {
      const before = await page.evaluate(() => IronmateStudio.scene.layers.length);
      await page.click('[data-tool="text"]');
      await page.fill("#text", text);
      await press(0.45, fy);
      await page.waitForFunction((n) => IronmateStudio.scene.layers.length === n + 1, before);
      await page.click('[data-tool="select"]');
      for (const [id, value] of [["w", "1200"], ["font-size", "32"]]) {
        await page.fill("#" + id, value);
        await page.locator("#" + id).blur();
      }
    };
    assert.equal(await page.locator("#slide-template, #slide-arrow, #slide-bold, #slide-title, #slide-body, #font-sample").count(), 0);
    await arrow();
    await page.waitForFunction(() => IronmateStudio.scene.layers.length === 1);
    await page.click("#slide-up");
    await page.waitForFunction(() => IronmateSlideEditor.active === 1);
    await page.click("#slide-duplicate");
    await page.waitForFunction(() => IronmateSlideEditor.active === 2);
    await words("スライドのタイトル", 0.2);
    await words("ここに本文を入力します。", 0.5);
    await page.waitForFunction(() => IronmateStudio.scene.layers.length === 3);
    assert.deepEqual(await page.evaluate(() => IronmateSlideEditor.deck.slides.map(s => s.layers.length)), [0,1,3,0,0,0]);
    for (let count = 5; count >= 1; count--) {
      await page.click("#slide-delete");
      await page.waitForFunction(n => IronmateSlideEditor.deck.slides.length === n, count);
    }
    await page.uncheck("#slide-grid-mode");
    assert.equal(await page.locator(".workspace > #board").count(), 1);
    await words("スライドのタイトル", 0.2);
    await words("ここに本文を入力します。", 0.5);
    await page.waitForFunction(() => IronmateStudio.scene.layers.length === 2);
    assert.equal(await page.inputValue("#text"), "ここに本文を入力します。");
    const [titleId, bodyId] = await page.evaluate(() => IronmateStudio.scene.layers.map(layer => layer.id));
    await page.click(`[data-layer-id="${titleId}"]`);
    assert.equal(await page.inputValue("#edit-text"), "スライドのタイトル");
    await page.fill("#edit-text", "編集したタイトル <>&");
    await page.click("#apply-text");
    assert.equal(await page.inputValue("#text"), "ここに本文を入力します。"); // ✏️ 編集 leaves the tool's own input alone
    assert.equal(await page.locator(`[data-layer-id="${titleId}"]`).textContent(), "文字 / 編集したタイトル <>&");
    await page.fill("#font-size", "64");
    await page.locator("#font-size").blur();
    await page.check("#bold");
    await page.check("#italic");
    await page.fill("#edit-fill", "#123456");
    assert.deepEqual(await page.evaluate(() => { const l = IronmateStudio.scene.layers[0]; return [l.bold, l.italic, l.fill]; }), [true, true, "#123456"]);
    await page.uncheck("#bold");
    let first = await page.evaluate(() => IronmateStudio.scene);
    assert.equal(first.layers[0].text, "編集したタイトル <>&");
    assert.equal(first.layers[0].fontSize, 64);
    assert.equal(first.layers[0].bold, false);
    await arrow();
    await page.waitForFunction(() =>
      IronmateStudio.scene.layers.some((l) => l.kind === "arrow" && l.headStyle === "triangle"),
    );
    await page.click("#slide-duplicate");
    await page.waitForFunction(() => IronmateSlideEditor.active === 1);
    await page.click("#slide-add");
    await page.waitForFunction(() => IronmateSlideEditor.active === 2);
    await words("二枚目のタイトル", 0.2);
    await words("日本語の文章と ABC abc 0123456789", 0.5);
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
    // 🧰 💾 in the chrome: the deck's JSON and the PPTX are rows of the one save
    const download = async (id, name) => {
      const pending = page.waitForEvent("download");
      const row = page.locator(`[data-chrome-action="${{ "deck-save": "deck-json", "deck-pptx": "pptx" }[id]}"]`);
      await row.locator("xpath=ancestor::details[1]/summary").click();
      await row.click();
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
        `from pathlib import Path\nfrom zipfile import ZipFile\nfrom xml.etree import ElementTree as E\nfrom ironlib.pptx_ooxml import require_package,ordered_slide_members\np=Path('build/pages-evidence/slides.pptx')\nassert require_package(p)==2\nns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}\nwith ZipFile(p) as z:\n assert z.testzip() is None\n slides=[E.fromstring(z.read(n)) for n in ordered_slide_members(z)]\n assert slides[0].find('.//a:t',ns).text=='編集したタイトル <>&'\n assert slides[0].find('.//a:rPr',ns).get('i')=='1' and slides[1].find('.//a:rPr',ns).get('i') is None\n assert slides[0].find('.//p:grpSp',ns) is not None\n assert slides[1].find('.//a:t',ns).text=='二枚目のタイトル'\n assert len(slides[1].findall('.//p:pic',ns))==1\n assert [e.text for e in slides[1].findall('.//a:t',ns)][1]=='日本語の文章と ABC abc 0123456789'\n for name in z.namelist():\n  if name.endswith(('.xml','.rels')):E.fromstring(z.read(name))\nprint('Browser PPTX: two ordered slides, editable text, native grouped arrow, per-layer PNG, XML and ZIP CRC verified')`,
      ],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    console.log(result.stdout.trim());

    // Paste long text through the real inspector, then compare the visible
    // SVG line strings with the editable DrawingML exported by this browser.
    await page.setViewportSize({ width: 1600, height: 1100 });
    await page.click(`[data-layer-id="${titleId}"]`);
    const japanese = "日本語の長い文章を貼り付け、ボックスの幅に合わせて折り返します。".repeat(3) + "\n\n明示改行の後です。\n";
    await page.fill("#edit-text", japanese);
    await page.click("#apply-text");
    for (const [id, value] of [["w", "520"], ["h", "60"], ["font-size", "32"], ["rotation", "12"]]) {
      await page.fill("#" + id, value);
      await page.locator("#" + id).blur();
    }
    const titleLines = `#board g[data-layer="${titleId}"] tspan`;
    const lineCount = () => page.locator(titleLines).count();
    const wideCount = await lineCount();
    assert(wideCount > 3);
    await page.fill("#w", "300");
    await page.locator("#w").blur();
    assert((await lineCount()) > wideCount);
    await page.fill("#font-size", "24");
    await page.locator("#font-size").blur();
    const smallCount = await lineCount();
    await page.check("#bold");
    const boldCount = await lineCount();
    assert(boldCount >= smallCount);
    await page.click(`[data-layer-id="${bodyId}"]`);
    const english = "English words should stay together when they fit. ".repeat(5) + "\n\nhttps://example.test/" + "longurl".repeat(14) + " 👨‍👩‍👧‍👦 e\u0301 🇯🇵\n";
    await page.fill("#edit-text", english);
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
    await page.locator(titleLines).first().waitFor();
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
from ironlib.pptx_ooxml import require_package, ordered_slide_members
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
    // 📱 Phone slides: the slide stays pinned on top, emoji controls, 🧭 PySaiyanWeBoo's pager in every shape, text editable later.
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, acceptDownloads: true }),
      mobile = await phone.newPage(),
      shots = [];
    mobile.on("pageerror", (e) => errors.push(e.message));
    mobile.on("request", (r) => requests.push(r.url()));
    const snap = async (name) => {
      const file = path.join(out, `phone-${String(shots.length + 1).padStart(2, "0")}-${name}.png`);
      await mobile.screenshot({ path: file });
      shots.push(file);
    };
    const state = () => mobile.evaluate(() => ({ deck: IronmatePhone.deck, active: IronmatePhone.active, level: IronmatePhone.level, selected: IronmatePhone.selected }));
    const act = (name) => mobile.tap(`[data-act="${name}"]`);
    const pageNo = () => mobile.textContent("#phone-pager output"); // 🧭 PySaiyanWeBoo's pager: n/N in every shape
    const stageAt = async (fx, fy) => {
      const box = await mobile.locator("#phone-stage").boundingBox();
      return { x: box.x + box.width * fx, y: box.y + box.height * fy };
    };
    await mobile.goto(url + "phone/");
    await mobile.waitForFunction(() => !!window.IronmatePhone);
    const stageBox = await mobile.locator("#phone-stage").boundingBox();
    assert.equal(Math.round(stageBox.y), 0); // 📌 pinned at the top, full width, 16:9
    assert.equal(Math.round(stageBox.width), 390);
    assert.ok(Math.abs(stageBox.height - (390 * 9) / 16) < 2);
    assert.deepEqual((await state()).deck.slides[0].layers, []); // ⬜ starts blank
    for (const label of await mobile.$$eval("[data-act]", (nodes) => nodes.map((n) => n.textContent.trim())))
      assert.ok(!/[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}A-Za-z]/u.test(label), label); // emoji only on the face
    await snap("blank");
    await act("text");
    assert.ok(await mobile.locator("#phone-edit").isVisible());
    assert.equal(await mobile.evaluate(() => document.activeElement.id), "phone-edit"); // ⌨️ ready to type
    await mobile.keyboard.type("こんにちは Ironmate");
    await snap("typing");
    let p = await stageAt(0.5, 0.9);
    await mobile.touchscreen.tap(p.x, p.y); // tap outside → the box is kept
    let s = await state();
    assert.equal(s.deck.slides[0].layers.length, 1);
    assert.equal(s.deck.slides[0].layers[0].text, "こんにちは Ironmate");
    assert.equal(s.deck.slides[0].layers[0].fontSize, 32);
    // ✏️ later: tap to select, tap again to edit the same box
    const layer = s.deck.slides[0].layers[0];
    p = await stageAt((layer.x + 40) / 1280, (layer.y + layer.h / 2) / 720);
    await mobile.touchscreen.tap(p.x, p.y);
    assert.equal((await state()).selected, layer.id);
    await mobile.touchscreen.tap(p.x, p.y);
    assert.ok(await mobile.locator("#phone-edit").isVisible());
    assert.equal(await mobile.inputValue("#phone-edit"), "こんにちは Ironmate");
    await mobile.fill("#phone-edit", "あとから編集した文字\n2 行目");
    await snap("edit-later");
    p = await stageAt(0.5, 0.9);
    await mobile.touchscreen.tap(p.x, p.y);
    s = await state();
    assert.equal(s.deck.slides[0].layers[0].text, "あとから編集した文字\n2 行目");
    assert.ok(s.deck.slides[0].layers[0].h >= 2 * 32 * 1.3 - 1); // 📏 grows with its lines
    // 👆 drag moves the box
    const before = s.deck.slides[0].layers[0];
    const from = await stageAt((before.x + 40) / 1280, (before.y + 20) / 720),
      to = await stageAt((before.x + 40) / 1280, (before.y + 20 + 160) / 720);
    await mobile.mouse.move(from.x, from.y);
    await mobile.mouse.down();
    await mobile.mouse.move(to.x, to.y, { steps: 8 });
    await mobile.mouse.up();
    s = await state();
    assert.ok(Math.abs(s.deck.slides[0].layers[0].y - (before.y + 160)) < 8, JSON.stringify(s.deck.slides[0].layers[0]));
    // 🔼 🔄 🔽 every text box together
    await act("bigger");
    await act("bigger");
    assert.equal((await state()).deck.slides[0].layers[0].fontSize, 48);
    await snap("bigger");
    await act("reset");
    assert.equal((await state()).deck.slides[0].layers[0].fontSize, 32);
    await act("smaller");
    assert.equal((await state()).deck.slides[0].layers[0].fontSize, 24);
    await act("reset");
    // ➕📄 pages and ⬅️ ➡️
    await act("slide-add");
    assert.equal(await pageNo(), "2/2");
    await act("rect");
    await act("arrow");
    await act("text");
    await mobile.keyboard.type("2 ページ目");
    await mobile.tap('[data-ui-pager-go="prev"]');
    assert.equal(await pageNo(), "1/2");
    await mobile.tap('[data-ui-pager-go="next"]');
    assert.equal(await pageNo(), "2/2");
    s = await state();
    assert.deepEqual(s.deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow", "text"]);
    await snap("page-2");
    await mobile.tap('[data-ui-pager-go="prev"]');
    assert.equal(await pageNo(), "1/2");
    await snap("page-back");
    assert.ok(await mobile.locator('[data-ui-pager-go="prev"]').isDisabled());
    await mobile.tap('[data-ui-pager-go="next"]');
    // 🧭 one tap per shape, no reload: each fits the phone with nothing overlapping, and each turns the page its own way
    const shapes = [];
    const there = async (shape, tap) => {
      await tap();
      assert.equal(await pageNo(), "1/2", shape);
      assert.equal((await state()).active, 0, shape);
    };
    for (let i = 0; i < 6; i++) {
      await act("pager");
      const shape = await mobile.evaluate(() => IronmatePhone.pager),
        parts = await mobile.$$eval("#phone-pager > *", (cs) =>
          cs.filter((c) => c.checkVisibility()).map((c) => [c.dataset.uiPagerPart, ...Object.values(c.getBoundingClientRect().toJSON()).slice(0, 4)]));
      shapes.push(shape);
      for (const [name, x, , w] of parts) assert.ok(x >= 0 && x + w <= 390, `${shape}: ${name} leaves the screen`);
      for (let a = 0; a < parts.length; a++)
        for (let b = 0; b < a; b++) {
          const [n1, x1, y1, w1, h1] = parts[a], [n2, x2, y2, w2, h2] = parts[b];
          assert.ok(!(x1 < x2 + w2 && x2 < x1 + w1 && y1 < y2 + h2 && y2 < y1 + h1), `${shape}: ${n1} overlaps ${n2}`);
        }
      if (shape === "dots") {
        await there(shape, () => mobile.tap('[data-ui-pager-to="0"]'));
        await mobile.tap('[data-ui-pager-to="1"]');
      } else if (shape === "slider") {
        await there(shape, () => mobile.fill('#phone-pager input[data-ui-pager-part="slider"]', "1"));
        await mobile.fill('#phone-pager input[data-ui-pager-part="slider"]', "2");
      } else if (shape === "dial") {
        await mobile.focus("#phone-pager .ui-dial input");
        await there(shape, () => mobile.keyboard.press("ArrowLeft"));
        await mobile.keyboard.press("ArrowRight");
        await mobile.evaluate(() => document.activeElement.blur());
      } else if (shape === "dpad" || shape === "ends") {
        await there(shape, () => mobile.tap(`[data-ui-pager-part="${shape === "dpad" ? "up" : "first"}"]`));
        await mobile.tap(`[data-ui-pager-part="${shape === "dpad" ? "down" : "last"}"]`);
      }
      assert.equal(await pageNo(), "2/2", shape);
      assert.equal((await state()).active, 1, shape);
      await snap(`pager-${shape}`);
    }
    assert.deepEqual(shapes, ["dots", "slider", "dial", "dpad", "ends", "arrows"]); // 🧭 comes back to ⬅️ 1/N ➡️
    await act("pager"); // ● dots, kept across the reload below
    // ↩️ undo the last box, ↪️ redo it
    await act("undo");
    assert.deepEqual((await state()).deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow"]);
    await act("redo");
    assert.deepEqual((await state()).deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow", "text"]);
    // 🖼️ a 6MP photo is not refused: StudioCore.picture shrinks it to 1920 on the long side, then ↩️ takes it back
    const photo = await mobile.evaluate(() => {
      const c = Object.assign(document.createElement("canvas"), { width: 3000, height: 2000 });
      c.getContext("2d").fillRect(0, 0, 8, 8);
      return c.toDataURL("image/png").split(",")[1];
    });
    await mobile.setInputFiles('[data-file="image"]', { name: "photo.png", mimeType: "image/png", buffer: Buffer.from(photo, "base64") });
    await mobile.waitForFunction(() => IronmatePhone.deck.slides[1].layers.length === 4);
    assert.deepEqual(await mobile.evaluate(async () => {
      const img = new Image();
      img.src = IronmatePhone.deck.slides[1].layers[3].src;
      await img.decode();
      return [img.naturalWidth, img.naturalHeight];
    }), [1920, 1280]);
    await act("undo");
    assert.deepEqual((await state()).deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow", "text"]);
    // 💾 autosave survives a reload
    await mobile.reload();
    await mobile.waitForFunction(() => !!window.IronmatePhone);
    s = await state();
    assert.equal(s.deck.slides.length, 2);
    assert.equal(s.deck.slides[0].layers[0].text, "あとから編集した文字\n2 行目");
    assert.equal(await mobile.evaluate(() => IronmatePhone.pager), "dots"); // 🧭 the shape survives the reload too
    // 📤 PPTX and 💾 JSON (the same all-slide JSON Slide Studio opens)
    const [pptx] = await Promise.all([mobile.waitForEvent("download"), act("pptx")]);
    await pptx.saveAs(path.join(out, "phone.pptx"));
    const [json] = await Promise.all([mobile.waitForEvent("download"), act("save")]);
    await json.saveAs(path.join(out, "phone.json"));
    await snap("saved");
    const phoneCheck = spawnSync(process.env.PYTHON || "python", ["-S", "-c", `
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
from ironlib.pptx_ooxml import require_package, ordered_slide_members
p=Path('build/pages-evidence/phone.pptx')
assert require_package(p)==2
ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
with ZipFile(p) as z:
    texts=[[t.text for t in E.fromstring(z.read(m)).findall('.//a:t',ns)] for m in ordered_slide_members(z)]
assert texts==[['あとから編集した文字','2 行目'],['2 ページ目']], texts
print('📱 phone: 2 slides, native text kept')
`], { encoding: "utf8" });
    assert.equal(phoneCheck.status, 0, phoneCheck.stderr);
    console.log(phoneCheck.stdout.trim());
    await page.setInputFiles("#deck-open", path.join(out, "phone.json"));
    await page.waitForFunction(() => IronmateSlideEditor.deck.slides.length === 2);
    assert.equal((await page.evaluate(() => IronmateSlideEditor.deck)).slides[0].layers[0].text, "あとから編集した文字\n2 行目");
    fs.writeFileSync(path.join(out, "phone-frames.json"), JSON.stringify(shots.map((f) => path.basename(f)), null, 2));
    // The same multiplier is bounded by the largest font, then reversed across a reload.
    const openPhone = async (deck) => {
      await mobile.setInputFiles('input[data-file="open"]', {
        name: "test.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(deck)),
      });
      await mobile.waitForFunction((title) => IronmatePhone.deck.title === title, deck.title);
    };
    const scaleDeck = s.deck;
    scaleDeck.title = "font bounds";
    scaleDeck.slides[0].layers[0].fontSize = 320;
    scaleDeck.slides[1].layers.find((l) => l.kind === "text").fontSize = 160;
    await openPhone(scaleDeck);
    const fonts = async () => (await state()).deck.slides.flatMap((slide) =>
      slide.layers.filter((l) => l.kind === "text").map((l) => l.fontSize));
    for (let i = 0; i < 4; i++) await act("bigger");
    assert.deepEqual(await fonts(), [512, 256]);
    await mobile.reload();
    await mobile.waitForFunction(() => !!window.IronmatePhone);
    await act("reset");
    assert.deepEqual(await fonts(), [320, 160]);

    // A storage failure must remain visible after the action and clear on the next successful write.
    const storageKey = "ironmate-phone-deck";
    const stored = await mobile.evaluate((key) => localStorage.getItem(key), storageKey);
    await mobile.evaluate(() => {
      window.restoreStorage = Storage.prototype.setItem;
      Storage.prototype.setItem = () => { throw new DOMException("full", "QuotaExceededError"); };
    });
    await act("rect");
    await mobile.waitForFunction(() => document.querySelector("#phone-status").textContent.includes("⚠️ 💾"));
    assert.equal(await mobile.evaluate((key) => localStorage.getItem(key), storageKey), stored);
    await mobile.evaluate(() => { Storage.prototype.setItem = window.restoreStorage; });
    await act("undo");
    await mobile.waitForFunction(() => !document.querySelector("#phone-status").textContent.includes("⚠️ 💾"));

    // A rejected duplicate must not alter the active page or create a history entry.
    // This synthetic payload exercises the 32MiB deck validator, not image decoding.
    const image = { id: "big", kind: "image", x: 0, y: 0, w: 128, h: 128, rotation: 0, opacity: 1,
      src: "data:image/png;base64," + "A".repeat(9_000_000), cell: 1, levels: 256 };
    const largeDeck = { ...scaleDeck, title: "deck bounds",
      slides: [{ ...scaleDeck.slides[0], layers: [image, { ...image, id: "big2" }] }] };
    await openPhone(largeDeck);
    await act("slide-copy");
    await mobile.waitForFunction(() => document.querySelector("#phone-status").textContent.includes("32MiB"));
    assert.equal(await pageNo(), "1/1");
    assert.equal(await mobile.evaluate(() => IronmatePhone.active), 0);
    assert.ok(await mobile.locator('[data-act="redo"]').isDisabled());
    const [stillExportable] = await Promise.all([mobile.waitForEvent("download"), act("save")]);
    assert.equal(await stillExportable.failure(), null);
    await act("undo");
    await mobile.waitForFunction(() => IronmatePhone.deck.title === "font bounds");
    await phone.close();
    assert(requests.every((r) => r.startsWith(new URL(url).origin + "/") || /^(blob|data):/.test(r)));
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
