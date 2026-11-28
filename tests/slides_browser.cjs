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
    const errors = [],
      requests = [];
    // The shelf hands the canvas to the normal slide image importer and leaves the source open.
    const source = await browser.newPage();
    await source.goto(new URL("../", url).href);
    await source.locator('#studio-toolbar [data-act="import"]').click();                       // 📥 どの形式から？ → シェルフ
    await source.locator('#studio-candidates button:text-is("シェルフ")').click();
    const popup = source.waitForEvent("popup");
    await source.getByRole("link", {name: "編集中の画像をスライド工房へ"}).click();
    const destination = await popup;
    await destination.locator('[data-act="undo"]:enabled').waitFor();
    assert.equal(await destination.evaluate(() => IronmateSlideStudio.deck.slides[0].layers[0].kind), "image");
    await destination.locator('[data-act="undo"]').click();
    await destination.reload();
    assert.equal(await destination.evaluate(() => IronmateSlideStudio.deck.slides[0].layers.length), 0);
    await destination.close();
    await source.close();
    // 📽️ The one slide editor (slides/, phone-first): the slide stays pinned on top, emoji controls, 🧭 PySaiyanWeBoo's pager in every shape, text editable later.
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, acceptDownloads: true,
      permissions: ["clipboard-read", "clipboard-write"] }),
      mobile = await phone.newPage(),
      shots = [];
    mobile.on("pageerror", (e) => errors.push(e.message));
    mobile.on("request", (r) => requests.push(r.url()));
    const snap = async (name) => {
      const file = path.join(out, `phone-${String(shots.length + 1).padStart(2, "0")}-${name}.png`);
      await mobile.screenshot({ path: file });
      shots.push(file);
    };
    const state = () => mobile.evaluate(() => ({ deck: IronmateSlideStudio.deck, active: IronmateSlideStudio.active, level: IronmateSlideStudio.level, selected: IronmateSlideStudio.selected }));
    const act = (name) => mobile.tap(`[data-act="${name}"]`);
    // 🔷 😊 (^^): open the tool's candidates (once) and tap one; it is placed at once
    const pick = async (tool, value) => {
      if ((await mobile.getAttribute("#slides-candidates", "data-tool")) !== tool) await act(tool);
      await mobile.locator("#slides-candidates button", { hasText: value }).tap();
    };
    const pageNo = () => mobile.textContent("#slides-pager output"); // 🧭 PySaiyanWeBoo's pager: n/N in every shape
    const stageAt = async (fx, fy) => {
      const box = await mobile.locator("#slides-stage").boundingBox();
      return { x: box.x + box.width * fx, y: box.y + box.height * fy };
    };
    await mobile.goto(url);
    await mobile.waitForFunction(() => !!window.IronmateSlideStudio);
    const stageBox = await mobile.locator("#slides-stage").boundingBox();
    assert.equal(Math.round(stageBox.y), 0); // 📌 pinned at the top, full width, 16:9
    assert.equal(Math.round(stageBox.width), 390);
    assert.ok(Math.abs(stageBox.height - (390 * 9) / 16) < 2);
    assert.deepEqual((await state()).deck.slides[0].layers, []); // ⬜ starts blank
    for (const label of await mobile.$$eval("[data-act]", (nodes) => nodes.map((n) => n.textContent.trim())))
      assert.ok(!/[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}A-Za-z]/u.test(label), label); // emoji only on the face
    await snap("blank");
    await act("text");
    assert.ok(await mobile.locator("#slides-edit").isVisible());
    assert.equal(await mobile.evaluate(() => document.activeElement.id), "slides-edit"); // ⌨️ ready to type
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
    assert.ok(await mobile.locator("#slides-edit").isVisible());
    assert.equal(await mobile.inputValue("#slides-edit"), "こんにちは Ironmate");
    await mobile.fill("#slides-edit", "あとから編集した文字\n2 行目");
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
    // A second finger on the empty stage must not take over an in-flight drag.
    const touch = await mobile.context().newCDPSession(mobile);
    const empty = await stageAt(0.95, 0.9);
    const first = { ...to, id: 1 }, second = { ...empty, id: 2 };
    const sendTouch = (type, touchPoints) => touch.send("Input.dispatchTouchEvent", { type, touchPoints });
    await sendTouch("touchStart", [first]);
    await sendTouch("touchStart", [first, second]);
    await sendTouch("touchMove", [{ ...first, y: first.y + 20 }, second]);
    await sendTouch("touchEnd", []);
    await touch.detach();
    assert.ok((await state()).deck.slides[0].layers[0].y > s.deck.slides[0].layers[0].y + 20);
    await act("undo");
    assert.deepEqual((await state()).deck, s.deck);
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
    assert.equal(await mobile.locator("#slides-candidates").isHidden(), true); // no candidates, and no gap, until a tool asks
    assert.equal(await mobile.locator("#slides-layers").isHidden(), true);     // 📚 nor a layer row for a blank page
    await pick("shape", "▭");
    assert.deepEqual(await mobile.locator("#slides-candidates button").allTextContents(), ["▭", "◯", "△", "→"]);
    await pick("shape", "→");
    // 😊 (^^) 🕒 🅱️ 🎨 ⏫ on a page of their own, so the pages the rest of this test counts stay as they were
    await act("slide-add");
    await pick("emoji", "🌱");
    await pick("kaomoji", "(・∀・)");
    await act("clock");
    await pick("shape", "△");
    let extra = (await state()).deck.slides[2].layers;
    assert.deepEqual(extra.map((l) => [l.kind, l.text ?? ""]), [["text", "🌱"], ["text", "(・∀・)"], ["clock", ""], ["triangle", ""]]);
    assert.ok(extra[2].hour >= 0 && extra[2].hour < 24 && extra[2].w === extra[2].h);
    assert.ok(extra[0].w <= 1280 * 0.9 && extra[0].x > 0 && extra[1].wrap === true);          // a stamp is a text box that fits its words
    assert.equal(await mobile.isDisabled('[data-act="edit"]'), true);                          // the triangle is selected
    await pick("look", "🎨");
    assert.equal((await state()).deck.slides[2].layers[3].fill, "#D7263D");                    // 🎨 teal → the next colour
    // 🎨 🖌 🌗 and ↻ ↺ ⏹ on the triangle, then ↩️ back to just the 🎨 step
    const triangle = () => mobile.evaluate(() => IronmateSlideStudio.deck.slides[2].layers[3]);
    assert.deepEqual(await mobile.locator("#slides-candidates button").allTextContents(), ["🎨", "🖌", "🌗", "🅱️", "🔠"]);
    await pick("look", "🖌");
    await pick("look", "🌗");
    await pick("look", "🅱️");                                                                    // not a text: nothing happens
    let t = await triangle();
    assert.ok(t.stroke === "#000000" && t.opacity === 0.75 && !("bold" in t), JSON.stringify(t));
    await pick("turn", "↻");
    await pick("turn", "↻");
    await pick("turn", "↺");
    assert.equal((await triangle()).rotation, 15);
    assert.match(await mobile.evaluate(() => document.querySelector("#slides-pick").style.transform), /rotate\(15deg\)/); // the frame turns too
    await pick("turn", "⏹");
    assert.equal((await triangle()).rotation, 0);
    for (let i = 0; i < 6; i++) await act("undo");
    t = await triangle();
    assert.ok(t.fill === "#D7263D" && t.stroke === "#183C42" && t.opacity === 1 && t.rotation === 0, JSON.stringify(t));
    assert.equal((await state()).selected, null);                                              // ↩️ leaves nothing selected
    await mobile.locator("#slides-layers button").nth(3).tap();                                 // 📚 pick the triangle again
    // 📚 the page's layers, back to front: the kaomoji is under the clock and the triangle, and is picked from the row
    const layerFaces = () => mobile.locator("#slides-layers button").allTextContents();
    assert.deepEqual(await layerFaces(), ["🌱", "(・∀", "🕒", "△"]);
    assert.equal(await mobile.getAttribute('#slides-layers [aria-current="step"]', "aria-label"), "4 △");
    assert.equal(await mobile.isDisabled('[data-act="front"]'), true);                         // already the front one
    const kao = extra[1];
    await mobile.locator("#slides-layers button").nth(1).tap();
    assert.equal((await state()).selected, kao.id);
    await pick("look", "🅱️");
    await act("front");
    extra = (await state()).deck.slides[2].layers;
    assert.deepEqual(extra.map((l) => l.kind), ["text", "clock", "triangle", "text"]);
    assert.ok(extra[3].id === kao.id && extra[3].bold === true);
    await snap("candidates");
    const rows = await mobile.$$eval(".ui-toolbar-row:not([hidden])", (nodes) => nodes.map((n) => new Set([...n.children].map((c) => c.offsetTop)).size));
    assert.ok(rows.every((n) => n === 1), JSON.stringify(rows));                                // 📱 390 px: no row wraps
    await act("back");
    assert.deepEqual(await layerFaces(), ["(・∀", "🌱", "🕒", "△"]);
    assert.equal(await mobile.isDisabled('[data-act="back"]'), true);
    assert.equal(await mobile.isDisabled('[data-act="backward"]'), true);
    // ⬆️ ⬇️ one step, ⧉ a copy in front (shifted 32 on 1280), ⏪ ⏩ two steps at once
    await act("forward");
    assert.deepEqual(await layerFaces(), ["🌱", "(・∀", "🕒", "△"]);
    await act("backward");
    await act("duplicate");
    extra = (await state()).deck.slides[2].layers;
    assert.deepEqual(await layerFaces(), ["(・∀", "🌱", "🕒", "△", "(・∀"]);
    assert.ok(extra[4].id !== kao.id && extra[4].x === extra[0].x + 32 && extra[4].y === extra[0].y + 32 && extra[4].bold === true
      && (await state()).selected === extra[4].id, JSON.stringify(extra));
    await act("undo-2");                                                                        // ⧉ and ⬇️
    assert.deepEqual(await layerFaces(), ["🌱", "(・∀", "🕒", "△"]);
    await act("redo-2");
    assert.equal((await state()).deck.slides[2].layers.length, 5);
    await act("undo-2");
    for (let i = 0; i < 5; i++) await act("undo");                                             // ⬆️ ⏬ ⏫ 🅱️ 🎨
    extra = (await state()).deck.slides[2].layers;
    assert.ok(extra[1].id === kao.id && extra[1].bold === false && extra[3].fill === "#18A7A1", JSON.stringify(extra));
    // ✏️ a clock's time is edited like words: 14:30, and what is not a time leaves it as it was
    await mobile.locator("#slides-layers button").nth(2).tap();
    await act("edit");
    assert.match(await mobile.inputValue("#slides-edit"), /^\d\d:\d\d$/);
    await mobile.fill("#slides-edit", "14:30");
    await mobile.evaluate(() => document.activeElement.blur());
    let clock = (await state()).deck.slides[2].layers[2];
    assert.deepEqual([clock.kind, clock.hour, clock.minute], ["clock", 14, 30]);
    await act("edit");
    await mobile.fill("#slides-edit", "25:00");
    await mobile.evaluate(() => document.activeElement.blur());
    clock = (await state()).deck.slides[2].layers[2];
    assert.deepEqual([clock.hour, clock.minute], [14, 30]);
    // 🗂️ every page as a picture; a tap goes there, and it is a view (not in ↩️)
    assert.equal(await mobile.locator("#slides-pages").isHidden(), true);
    await act("pages");
    assert.equal(await mobile.locator("#slides-pages button").count(), 3);
    assert.equal(await mobile.getAttribute('#slides-pages [aria-current="step"]', "aria-label"), "3/3");
    assert.equal(await mobile.locator("#slides-pages button svg").first().getAttribute("width"), "80");
    assert.deepEqual(await mobile.$$eval("#slides-pages button", (b) => b.map((x) => x.lastChild.textContent)), ["1", "2", "3"]); // under the picture
    await snap("pages");
    await mobile.locator("#slides-pages button").first().tap();
    assert.equal(await pageNo(), "1/3");
    await mobile.locator("#slides-pages button").nth(2).tap();
    assert.equal(await pageNo(), "3/3");
    await act("pages");
    assert.equal(await mobile.locator("#slides-pages").isHidden(), true);
    await act("slide-delete");
    assert.equal(await pageNo(), "2/2");
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
    // ⬅️ ➡️ the one shape of the pager (🧭 is gone: 🗂️ shows every page); ← → keys too
    assert.equal(await mobile.getAttribute("#slides-pager", "data-ui-pager"), "arrows");
    assert.equal(await mobile.locator('[data-act="pager"]').count(), 0);
    await mobile.tap('[data-ui-pager-part="prev"]');
    assert.equal(await pageNo(), "1/2");
    await mobile.tap('[data-ui-pager-part="next"]');
    assert.equal(await pageNo(), "2/2");
    await snap("pager");
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
    const [chooser] = await Promise.all([mobile.waitForEvent("filechooser"), pick("import", "画像")]); // 📥 どの形式から？ 画像
    assert.equal(await chooser.element().getAttribute("accept"), "image/png,image/jpeg,image/webp");
    await chooser.setFiles({ name: "photo.png", mimeType: "image/png", buffer: Buffer.from(photo, "base64") });
    await mobile.waitForFunction(() => IronmateSlideStudio.deck.slides[1].layers.length === 4);
    assert.deepEqual(await mobile.evaluate(async () => {
      const img = new Image();
      img.src = IronmateSlideStudio.deck.slides[1].layers[3].src;
      await img.decode();
      return [img.naturalWidth, img.naturalHeight];
    }), [1920, 1280]);
    await act("undo");
    assert.deepEqual((await state()).deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow", "text"]);
    // 🧰 IronmateSlideStudio.act runs what the toolbar runs, awaitable (a host or Node needs no file input): a Blob is 📥's 画像 / カメラ
    assert.deepEqual(await mobile.evaluate(async (b64) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const image = new Blob([bytes], { type: "image/png" });
      const first = IronmateSlideStudio.act("camera", image);
      const busy = await IronmateSlideStudio.act("image", image);
      const imported = await first;
      const before = IronmateSlideStudio.deck;
      const invalid = await IronmateSlideStudio.act("image", new Blob(["invalid"], { type: "image/png" }));
      const unchanged = JSON.stringify(IronmateSlideStudio.deck) === JSON.stringify(before);
      await IronmateSlideStudio.act("undo");
      return { imported, busy, invalid, unchanged };
    }, photo), { imported: true, busy: false, invalid: false, unchanged: true });
    assert.deepEqual((await state()).deck.slides[1].layers.map((l) => l.kind), ["rect", "arrow", "text"]);
    const beforePageTurn = await state();
    const importedAfterPageTurn = await mobile.evaluate((b64) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const pending = IronmateSlideStudio.act("image", new Blob([bytes], { type: "image/png" }));
      document.querySelector('[data-ui-pager-go="prev"]').click();
      return pending;
    }, photo);
    assert.equal(importedAfterPageTurn, false);
    assert.equal((await state()).active, 0);
    assert.deepEqual((await state()).deck, beforePageTurn.deck);
    await mobile.tap('[data-ui-pager-go="next"]');
    assert.equal(await mobile.evaluate(() => IronmateSlideStudio.act("redo").then(() => IronmateSlideStudio.deck.slides[1].layers.at(-1).kind)), "image");
    await mobile.evaluate(() => IronmateSlideStudio.act("undo"));
    // Undo an imported document at the page the user was viewing when it replaced the deck.
    const beforeOpen = await state();
    assert.equal(beforeOpen.active, 1);
    const openedTitle = await mobile.evaluate(async () => {
      const next = { ...IronmateSlideStudio.deck, title: "Import while turning pages" };
      const pending = IronmateSlideStudio.act("open", new Blob([JSON.stringify(next)], { type: "application/json" }));
      document.querySelector('[data-ui-pager-go="prev"]').click();
      await pending;
      return IronmateSlideStudio.deck.title;
    });
    assert.equal(openedTitle, "Import while turning pages");
    await act("undo");
    assert.deepEqual((await state()).deck, beforeOpen.deck);
    assert.equal((await state()).active, 0);
    await mobile.tap('[data-ui-pager-go="next"]');
    // 💾 autosave survives a reload
    await mobile.reload();
    await mobile.waitForFunction(() => !!window.IronmateSlideStudio);
    s = await state();
    assert.equal(s.deck.slides.length, 2);
    assert.equal(s.deck.slides[0].layers[0].text, "あとから編集した文字\n2 行目");
    // 📤 どの形式に？ the candidates, in words like 図形・顔文字's: PPTX, JSON (the same all-slide JSON the PC studio opens), PNG,
    // SVG; a pick does it and the row hides again.
    const saveAs = (format) => pick("export", format);
    await act("export");
    assert.deepEqual(await mobile.locator("#slides-candidates button").allTextContents(), ["PPTX", "JSON", "PNG", "SVG", "Base64"]);
    assert.equal(await mobile.getAttribute('#slides-candidates button >> nth=2', "title"), "PNG（このページ）");
    const [pptx] = await Promise.all([mobile.waitForEvent("download"), mobile.locator("#slides-candidates button", { hasText: "PPTX" }).tap()]);
    assert.equal(await mobile.locator("#slides-candidates").isHidden(), true);                       // 選んだら候補は隠れる
    await pptx.saveAs(path.join(out, "phone.pptx"));
    const [json] = await Promise.all([mobile.waitForEvent("download"), saveAs("JSON")]);
    await json.saveAs(path.join(out, "phone.json"));
    const [png] = await Promise.all([mobile.waitForEvent("download"), saveAs("PNG")]);
    assert.equal(png.suggestedFilename(), `ironmate-slide-${(await state()).active + 1}.png`);
    const pngBytes = fs.readFileSync(await png.path());
    assert.deepEqual([...pngBytes.subarray(0, 8)], [137, 80, 78, 71, 13, 10, 26, 10]);
    assert.deepEqual([pngBytes.readUInt32BE(16), pngBytes.readUInt32BE(20)], [1280, 720]);  // the slide's own size
    const [svg] = await Promise.all([mobile.waitForEvent("download"), saveAs("SVG")]);
    assert.match(fs.readFileSync(await svg.path(), "utf8"), /^<svg [^>]*width="1280" height="720"/);
    // 📤 Base64: this page's PNG as a data URI on the clipboard; 📥 クリップボード puts it back on the page as a picture (then ↩️)
    await saveAs("Base64");
    await mobile.waitForFunction(() => document.querySelector("#slides-status").textContent === "📤 ✅ 📋");
    assert.match(await mobile.evaluate(() => navigator.clipboard.readText()), /^data:image\/png;base64,iVBORw0KGgo/);
    const onPage = async () => { const t = await state(); return t.deck.slides[t.active].layers; };
    const held = (await onPage()).length;
    await pick("import", "クリップボード");
    await mobile.waitForFunction((n) => IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.length === n + 1, held);
    assert.equal((await onPage()).at(-1).kind, "image");
    await act("undo");
    assert.equal((await onPage()).length, held);
    // 🎛️ with nothing selected it is the page's: 幅・高さ for every page (the stage takes the shape), 透明 for this one
    await act("inspect");
    assert.deepEqual(await Promise.all(["width", "height", "transparent", "x"].map((k) => mobile.locator(`[data-property="${k}"]`).isVisible())),
      [true, true, true, false]);
    const field = async (key, value) => { const el = mobile.locator(`[data-property="${key}"]`); await el.fill(String(value)); await el.press("Tab"); };
    await field("width", 720);
    await field("height", 1280);
    assert.ok((await state()).deck.slides.every((x) => x.width === 720 && x.height === 1280));
    const tall = await mobile.locator("#slides-stage").boundingBox();
    assert.ok(Math.abs(tall.width / tall.height - 720 / 1280) < 0.02, JSON.stringify(tall));
    await mobile.locator('[data-property="transparent"]').check();
    assert.equal((await state()).deck.slides[(await state()).active].background, "none");
    await snap("page-tall-clear");
    const [clear] = await Promise.all([mobile.waitForEvent("download"), saveAs("PNG")]);
    const clearBytes = fs.readFileSync(await clear.path());
    assert.deepEqual([clearBytes.readUInt32BE(16), clearBytes.readUInt32BE(20), clearBytes[25]], [720, 1280, 6]);   // RGBA
    await field("width", 4096);                                                                  // 4096 × 1280 is over 4 MP
    assert.equal(await mobile.getAttribute("#slides-status", "data-error"), "true");
    assert.equal((await state()).deck.slides[0].width, 720);
    assert.equal(await mobile.inputValue('[data-property="width"]'), "720");
    for (let i = 0; i < 3; i++) await act("undo");
    assert.ok((await state()).deck.slides.every((x) => x.width === 1280 && x.height === 720 && x.background === "#FFFFFF"));
    await act("inspect");
    // ▦ the dot-art editor under the tools: ➕ puts the art on this page, crisp (pixelated), and folds the editor away; then ↩️
    await mobile.locator("#pixel-editor summary").tap();
    await mobile.waitForFunction(() => !!window.IronmateWorkbench?.grid);
    await mobile.locator("#generate").tap();
    const beforeArt = (await onPage()).length;
    await mobile.locator("#place-grid").tap();
    await mobile.waitForFunction((n) => IronmateSlideStudio.deck.slides[IronmateSlideStudio.active].layers.length === n + 1, beforeArt);
    const art = (await onPage()).at(-1);
    assert.ok(art.kind === "image" && art.sampling === "pixelated" && art.name === "image", JSON.stringify({ ...art, src: art.src.slice(0, 32) }));
    assert.equal(await mobile.locator("#pixel-editor").getAttribute("open"), null);
    await snap("pixel-art");
    await act("undo");
    assert.equal((await onPage()).length, beforeArt);
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
    const roundTrip = JSON.parse(fs.readFileSync(path.join(out, "phone.json"), "utf8"));                // 📦 opens again (openPhone below)
    assert.equal(roundTrip.schema, "ironmate-slide-deck/1");
    assert.equal(roundTrip.slides[0].layers[0].text, "あとから編集した文字\n2 行目");
    fs.writeFileSync(path.join(out, "phone-frames.json"), JSON.stringify(shots.map((f) => path.basename(f)), null, 2));
    // The same multiplier is bounded by the largest font, then reversed across a reload.
    const openPhone = async (deck) => {
      await mobile.setInputFiles('#slides-toolbar [data-ui-file="open"]', {
        name: "test.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(deck)),
      });
      await mobile.waitForFunction((title) => IronmateSlideStudio.deck.title === title, deck.title);
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
    await mobile.waitForFunction(() => !!window.IronmateSlideStudio);
    await act("reset");
    assert.deepEqual(await fonts(), [320, 160]);

    // A storage failure must remain visible after the action and clear on the next successful write.
    const storageKey = "ironmate-slides-deck";
    const stored = await mobile.evaluate((key) => localStorage.getItem(key), storageKey);
    await mobile.evaluate(() => {
      window.restoreStorage = Storage.prototype.setItem;
      Storage.prototype.setItem = () => { throw new DOMException("full", "QuotaExceededError"); };
    });
    await pick("shape", "▭");
    await mobile.waitForFunction(() => document.querySelector("#slides-status").textContent.includes("⚠️ 💾"));
    assert.equal(await mobile.evaluate((key) => localStorage.getItem(key), storageKey), stored);
    await mobile.evaluate(() => { Storage.prototype.setItem = window.restoreStorage; });
    await act("undo");
    await mobile.waitForFunction(() => !document.querySelector("#slides-status").textContent.includes("⚠️ 💾"));

    // A rejected duplicate must not alter the active page or create a history entry.
    // This synthetic payload exercises the 32MiB deck validator, not image decoding.
    const image = { id: "big", kind: "image", x: 0, y: 0, w: 128, h: 128, rotation: 0, opacity: 1,
      src: "data:image/png;base64," + "A".repeat(9_000_000), cell: 1, levels: 256 };
    const largeDeck = { ...scaleDeck, title: "deck bounds",
      slides: [{ ...scaleDeck.slides[0], layers: [image, { ...image, id: "big2" }] }] };
    await openPhone(largeDeck);
    await act("slide-copy");
    await mobile.waitForFunction(() => document.querySelector("#slides-status").textContent.includes("32MiB"));
    assert.equal(await pageNo(), "1/1");
    assert.equal(await mobile.evaluate(() => IronmateSlideStudio.active), 0);
    assert.ok(await mobile.locator('[data-act="redo"]').isDisabled());
    const [stillExportable] = await Promise.all([mobile.waitForEvent("download"), pick("export", "JSON")]);
    assert.equal(await stillExportable.failure(), null);
    await act("undo");
    await mobile.waitForFunction(() => IronmateSlideStudio.deck.title === "font bounds");
    await phone.close();
    // 🖥️ The same page in a PC window: the controls sit beside the slide, every row on one line, nothing to scroll.
    const wide = await browser.newPage({ viewport: { width: 1280, height: 800 }, acceptDownloads: true });
    wide.on("pageerror", (e) => errors.push(e.message));
    wide.on("request", (r) => requests.push(r.url()));
    await wide.goto(url);
    await wide.waitForFunction(() => !!window.IronmateSlideStudio);
    await wide.click('[data-act="shape"]');
    await wide.click("#slides-candidates button >> nth=2");
    await wide.click('[data-act="emoji"]');
    await wide.click("#slides-candidates button >> nth=1");
    const stage = await wide.locator("#slides-stage").boundingBox(),
      tools = await wide.locator(".slides-tools").boundingBox();
    assert.ok(tools.x >= stage.x + stage.width && stage.width >= 896, JSON.stringify({ stage, tools }));
    assert.ok(tools.y + tools.height <= 800 && (await wide.evaluate(() => document.documentElement.scrollHeight)) === 800);
    const wideRows = await wide.$$eval(".ui-toolbar-row:not([hidden])", (nodes) => nodes.filter((n) => n.id !== "slides-candidates")
      .map((n) => new Set([...n.children].map((c) => c.offsetTop)).size));
    assert.ok(wideRows.every((n) => n === 1), JSON.stringify(wideRows));
    await wide.screenshot({ path: path.join(out, "slides-wide.png") });
    // 💻 To textual ⇄ 📱 To iconic: the same page shows emoji faces (the default) or short words, as on a PC, with no reload; the choice is remembered.
    // Rows are CRUD-like groups with a light dashed line between them.
    const look = (sel, pseudo) => wide.evaluate(([q, p]) => { const st = getComputedStyle(document.querySelector(q), p);
      return { content: st.content, size: st.fontSize, line: st.borderTopStyle }; }, [sel, pseudo]);
    assert.equal(await wide.evaluate(() => document.body.dataset.uiLabels), "emoji");
    assert.equal((await look('[data-ui-group="create"]', null)).line, "none");
    for (const g of ["adjust", "update", "order", "pages", "file", "detail"]) assert.equal((await look(`[data-ui-group="${g}"]`, null)).line, "dashed", g);
    assert.equal((await look('[data-act="export"]', "::after")).content, "none");
    await wide.click("[data-ui-labels-switch]");
    assert.equal(await wide.evaluate(() => document.body.dataset.uiLabels), "words");
    assert.equal(await wide.getAttribute("[data-ui-labels-switch]", "aria-pressed"), "true");
    const exportWord = await look('[data-act="export"]', "::after");
    assert.ok(exportWord.content === '"エクスポート"' && (await look('[data-act="export"]', null)).size === "0px", JSON.stringify(exportWord));
    assert.equal((await look("[data-ui-labels-switch]", "::after")).content, '"📱 To iconic"');   // the way back
    assert.equal((await look('[data-act="image-studio"]', null)).size, "0px");                          // a link button too: only its word
    await wide.click('[data-act="export"]');
    assert.equal((await look('#slides-candidates button[title^="PPTX"]', "::after")).content, '"PPTX"'); // the format's own word
    await wide.click('[data-act="export"]');                                                        // a second press hides them
    await wide.screenshot({ path: path.join(out, "slides-words.png") });
    await wide.reload();
    await wide.waitForFunction(() => !!window.IronmateSlideStudio);
    assert.equal(await wide.evaluate(() => document.body.dataset.uiLabels), "words");             // remembered
    await wide.click("[data-ui-labels-switch]");
    await wide.reload();
    await wide.waitForFunction(() => !!window.IronmateSlideStudio);
    assert.equal(await wide.evaluate(() => document.body.dataset.uiLabels), "emoji");
    // 📏 Long Japanese / English: the visible SVG lines are the editable DrawingML lines of the PPTX, and an old deck without
    // "wrap" opens wrapping, its words untouched (explicit paragraphs, blank lines, grapheme clusters, a long URL, rotation).
    const japanese = "日本語の長い文章を貼り付け、ボックスの幅に合わせて折り返します。".repeat(3) + "\n\n明示改行の後です。\n",
      english = "English words should stay together when they fit. ".repeat(5) + "\n\nhttps://example.test/" + "longurl".repeat(14) + " 👨‍👩‍👧‍👦 e\u0301 🇯🇵\n",
      words = (id, text, more) => ({ id, kind: "text", name: id, x: 40, y: 40, w: 300, h: 60, rotation: 0, opacity: 1, text, fill: "#000000",
        fontSize: 24, font: "sans", mono: false, bold: false, ...more }),
      legacy = { schema: "ironmate-slide-deck/1", title: "long", slides: [{ schema: "ironmate-image-studio/1", width: 1280, height: 720,
        background: "#FFFFFF", layers: [words("title", japanese, { bold: true, rotation: 12 }), words("body", english, { x: 400, w: 600, font: "mono" })] }] };
    await wide.setInputFiles('#slides-toolbar [data-ui-file="open"]', { name: "legacy.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(legacy)) });
    await wide.waitForFunction(() => IronmateSlideStudio.deck.title === "long");
    assert.deepEqual((await wide.evaluate(() => IronmateSlideStudio.deck.slides[0].layers)).map((l) => [l.text, l.wrap]), [[japanese, true], [english, true]]);
    const manifest = await wide.evaluate(() => IronmateSlideStudio.deck.slides[0].layers.map((l) => {
      const spans = [...document.querySelectorAll(`#slides-svg g[data-layer="${l.id}"] tspan`)];
      return { id: l.id, layer: l, layout: StudioCore.textLayout(l), visible: spans.map((t) => t.textContent), widths: spans.map((t) => t.getComputedTextLength()) };
    }));
    for (const item of manifest) {
      assert.ok(item.visible.length > 3, JSON.stringify(item.visible));
      assert.deepEqual(item.visible, item.layout.flat());
      assert.ok(item.widths.every((w) => w <= item.layer.w + 1), JSON.stringify(item));
    }
    fs.writeFileSync(path.join(out, "slides-wrapped-layout.json"), JSON.stringify(manifest, null, 2));
    const exportAs = async (format) => {
      await wide.click('[data-act="export"]');
      return wide.locator("#slides-candidates button", { hasText: format }).click();
    };
    const [wrappedPptx] = await Promise.all([wide.waitForEvent("download"), exportAs("PPTX")]);
    await wrappedPptx.saveAs(path.join(out, "slides-wrapped.pptx"));
    await wide.screenshot({ path: path.join(out, "slides-wrapped-desktop.png") });
    // Legacy PC controls: use the same editor and prove the exact state and the rendered/exported result.
    const parity = await wide.evaluate(() => {
      const canvas = Object.assign(document.createElement("canvas"), { width: 2, height: 2 });
      const c = canvas.getContext("2d");
      c.fillStyle = "#F00"; c.fillRect(0, 0, 1, 2);
      c.fillStyle = "#00F"; c.fillRect(1, 0, 1, 2);
      return canvas.toDataURL();
    });
    const geometry = { x: 10, y: 10, w: 140, h: 70, rotation: 0, opacity: 1 };
    const scene = (layers) => ({ ...legacy.slides[0], layers });
    const deck = { ...legacy, title: "PC controls", slides: [
      scene([words("italic", "Edit me", {})]),
      scene([{ ...geometry, id: "arrow", kind: "arrow", stroke: "#000000", fill: "#000000", strokeWidth: 4,
        headSize: 28, headPlacement: "tip" }]),
      scene([{ ...geometry, id: "photo", kind: "image", src: parity, cell: 1, levels: 256 }]),
      scene([]),
    ] };
    await wide.setInputFiles('#slides-toolbar [data-ui-file="open"]', { name: "parity.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(deck)) });
    await wide.waitForFunction(() => IronmateSlideStudio.deck.title === "PC controls");
    await wide.click('[data-act="grid"]');
    assert.equal(await wide.locator("#slides-grid > div").count(), 4);
    assert.equal(await wide.locator("#slides-grid #slides-stage").count(), 1);
    const selectLayer = async (id) => {
      await wide.locator(`#slides-svg [data-layer="${id}"]`).click();
      await wide.waitForFunction(() => Boolean(IronmateSlideStudio.selected));
      if (!(await wide.locator("#slides-inspector").isVisible())) await wide.click('[data-act="inspect"]');
    };
    const number = async (key, value) => {
      const el = wide.locator(`[data-property="${key}"]`);
      await el.fill(String(value)); await el.press("Tab");
    };
    await selectLayer("italic");
    await wide.locator('[data-property="italic"]').check();
    await number("x", 55);
    await number("w", 420);
    assert.equal(await wide.locator('#slides-svg text[font-style="italic"]').count(), 1);
    assert.equal(await wide.evaluate(() => IronmateSlideStudio.deck.slides[0].layers[0].w), 420);
    assert.equal(await wide.evaluate(() => IronmateSlideStudio.deck.slides[0].layers[0].x), 55);
    await wide.getByRole("button", {name: "2 枚目を編集"}).click();
    assert.equal(await wide.locator("#slides-grid > div").nth(1).locator("#slides-stage").count(), 1);
    await selectLayer("arrow");
    await number("strokeWidth", 12);
    await wide.locator('[data-property="headPlacement"]').selectOption("middle");
    assert.equal(await wide.evaluate(() => IronmateSlideStudio.deck.slides[1].layers[0].headPlacement), "middle");
    assert.equal(await wide.locator('#slides-svg line').getAttribute("stroke-width"), "12");
    await wide.getByRole("button", {name: "3 枚目を編集"}).click();
    await selectLayer("photo");
    await number("cell", 2);
    await wide.waitForFunction((src) => {
      const image = document.querySelector("#slides-svg image");
      return image && image.getAttribute("href") !== src;
    }, parity);
    const mosaic = await wide.locator("#slides-svg image").getAttribute("href");
    assert.ok(mosaic?.startsWith("data:image/png;base64,") && mosaic !== parity);
    assert.equal(await wide.evaluate(() => IronmateSlideStudio.deck.slides[2].layers[0].src), parity);
    const [mosaicSvg] = await Promise.all([wide.waitForEvent("download"), exportAs("SVG")]);
    assert.ok(fs.readFileSync(await mosaicSvg.path(), "utf8").includes(mosaic));
    const [mosaicPptx] = await Promise.all([wide.waitForEvent("download"), exportAs("PPTX")]);
    await mosaicPptx.saveAs(path.join(out, "slides-parity.pptx"));
    fs.writeFileSync(path.join(out, "slides-parity-mosaic.png"), Buffer.from(mosaic.split(",")[1], "base64"));
    const packageCheck = spawnSync(process.env.PYTHON || "python", ["-S", "-c", `
from pathlib import Path
from zipfile import ZipFile
with ZipFile('build/pages-evidence/slides-parity.pptx') as z:
 assert len([n for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml')]) == 4
 assert any(z.read(n) == Path('build/pages-evidence/slides-parity-mosaic.png').read_bytes()
            for n in z.namelist() if n.startswith('ppt/media/'))
`], { encoding: "utf8" });
    assert.equal(packageCheck.status, 0, packageCheck.stderr);
    await wide.screenshot({ path: path.join(out, "slides-four-up.png") });
    await wide.click('[data-act="grid"]');
    assert.ok(await wide.locator("#slides-grid").isHidden());
    assert.equal(await wide.locator(".slides > #slides-stage").count(), 1);
    await wide.close();
    const wrapped = spawnSync(process.env.PYTHON || "python", ["-S", "-c", `
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as E
from ironlib.pptx_ooxml import require_package, ordered_slide_members
p=Path('build/pages-evidence/slides-wrapped.pptx')
assert require_package(p)==1
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
    assert(requests.every((r) => r.startsWith(new URL(url).origin + "/") || /^(blob|data):/.test(r)));
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
