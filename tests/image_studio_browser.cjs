/* Real browser evidence. Run with Node + test-only Playwright and a local Chrome. */
"use strict";
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { chromium } = require(
  process.env.IRONMATE_PLAYWRIGHT_MODULE || "playwright",
);
const root = path.resolve(__dirname, ".."),
  out = path.resolve(
    process.env.IRONMATE_STUDIO_EVIDENCE ||
      path.join(root, "build/image-studio"),
  );
const staticMode = process.env.IRONMATE_STUDIO_STATIC === "1";
const staticRoot = staticMode
  ? fs.mkdtempSync(path.join(require("node:os").tmpdir(), "ironmate-site-"))
  : null;
const staticCode = `from image_studio import build_site
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
root=Path(__import__('sys').argv[1])
build_site(root/'Ironmate')
s=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(root)))
print(f'Ironmate Studio: http://127.0.0.1:{s.server_port}',flush=True)
s.serve_forever()`;
const server = spawn(
  process.env.PYTHON || "python",
  staticMode
    ? ["-u", "-c", staticCode, staticRoot]
    : ["-S", "image_studio.py", "--port", "0"],
  { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
);
let browser;
let acceptHistoryTrim = true;
const failures = [],
  requests = [];
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const url = await new Promise((resolve, reject) => {
    let data = "";
    server.stdout.on("data", (chunk) => {
      data += chunk;
      const m = data.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (m) resolve(m[0] + (staticMode ? "/Ironmate/" : ""));
    });
    server.on("error", reject);
    server.on("exit", (code) =>
      reject(new Error("studio server exited " + code)),
    );
    setTimeout(
      () => reject(new Error("server startup timed out")),
      10000,
    ).unref();
  });
  browser = await chromium.launch({
    headless: true,
    executablePath: process.env.IRONMATE_CHROME || undefined,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1100 },
    acceptDownloads: true,
  });
  // 🧰 PySaiyanWeBoo's toolbar: act(name) is a control; as(tool, face) opens 📥 / 📤 (or 🔷 😊 (^^)) unless its row is already open and
  // gives the candidate. 📥 どの形式から？ 📤 どの形式に？ hide after a pick, so each use opens them again.
  const act = (name) => `#studio-toolbar [data-act="${name}"]`;
  const chooser = (name) => `#studio-toolbar [data-ui-file="${name}"]`; // 📥 the toolbar's own file chooser for a format
  const as = async (tool, face) => {
    if (!(await page.evaluate((t) => { const r = document.getElementById("studio-candidates"); return !r.hidden && r.dataset.tool === t; }, tool)))
      await page.click(act(tool));
    return `#studio-candidates button:text-is("${face}")`;
  };
  const download = async (format, name) => {
    const wait = page.waitForEvent("download");
    await page.click(await as("export", format));
    await (await wait).saveAs(path.join(out, name));
  };
  page.on("pageerror", (e) => failures.push(e.message));
  page.on("request", (r) => requests.push(r.url()));
  page.on("dialog", (dialog) =>
    dialog.type() === "confirm" && !acceptHistoryTrim ? dialog.dismiss() : dialog.accept());
  await page.goto(url);
  assert.equal(await page.locator("#studio-candidates").isHidden(), true);                   // no candidates until a tool asks
  for (const id of ["studio-toolbar", "export-scale", "trim-history"])
    assert.equal(await page.locator(`#${id}`).count(), 1, `required Studio control: ${id}`);
  for (const name of ["image", "camera", "open-json", "open-workspace"])                       // 📥 the toolbar's own choosers
    assert.equal(await page.locator(chooser(name)).count(), 1, `required Studio chooser: ${name}`);
  await page.waitForFunction(() => !!window.IronmateStudio, null, {timeout:10000});
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.screenshot({
    path: path.join(out, "desktop.png"),
    fullPage: true,
  });
  // 💻 To textual ⇄ 📱 To iconic: emoji faces by default, short words on the same page with no reload, remembered
  const face = (sel, pseudo) => page.evaluate(([q, p]) => { const st = getComputedStyle(document.querySelector(q), p);
    return { content: st.content, size: st.fontSize }; }, [sel, pseudo]);
  assert.equal(await page.evaluate(() => document.body.dataset.uiLabels), "emoji");
  assert.deepEqual([await page.textContent(act("undo")), (await face(act("undo"), null)).size], ["↩️", "24px"]);   // the toolbar's face, as on the slide editor
  await page.click("#labels-switch");
  assert.equal(await page.evaluate(() => document.body.dataset.uiLabels), "words");
  assert.deepEqual([(await face(act("undo"), "::after")).content, (await face(act("undo"), null)).size], ['"戻す"', "0px"]);
  assert.equal((await face(act("text"), "::after")).content, '"文字"');                 // the same word as the slide editor's
  await page.screenshot({ path: path.join(out, "desktop-words.png"), fullPage: true });
  await page.reload();
  await page.waitForFunction(() => !!window.IronmateStudio, null, {timeout:10000});
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(await page.evaluate(() => document.body.dataset.uiLabels), "words");
  await page.click("#labels-switch");
  assert.equal(await page.evaluate(() => document.body.dataset.uiLabels), "emoji");
  const initial = await page.evaluate(() => window.IronmateStudio.scene);
  assert.deepEqual(initial.layers, []);
  assert.equal(await page.locator("#demo, #stamp-demo, #example-view").count(), 0);
  await page.click(act("text"));
  for (const value of ["背面", "前面", "中央"]) {
    await page.fill("#text", value);
    await page.locator("#board svg").click({position: {x: 50, y: 40}});
  }
  await page.click(act("backward"));                                       // ⬇️ one step back
  const texts = () => page.evaluate(() => IronmateStudio.scene.layers.map(layer => layer.text));
  assert.deepEqual(await texts(), ["背面", "中央", "前面"]);
  assert.equal(await page.inputValue("#edit-text"), "中央"); // ✏️ 編集 shows the selected layer's words
  await page.fill("#edit-text", "中央を編集");
  await page.click("#apply-text");
  assert.equal(await page.inputValue("#text"), "中央"); // the tool's own input keeps what it had
  assert.deepEqual(await texts(), ["背面", "中央を編集", "前面"]);
  await page.click(act("forward"));                                      // ⬆️ one step forward
  assert.deepEqual(await texts(), ["背面", "前面", "中央を編集"]);
  // Older saved scenes remain editable on the empty canvas.
  await page.setInputFiles(chooser("open-json"), path.join(root, "docs/evidence/image-studio/demo-scene.json"));
  const legacyText = page.locator("#layers button").filter({hasText: /^タイトル$/});
  await legacyText.click();
  assert.equal(await page.isChecked("#monochrome"), false);
  await page.click("#blank");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    0,
  );
  // 🧰 IronmateStudio.act opens a File / Blob the way 📥's chooser does (a host or Node needs no file input); loading is undoable
  const demo = fs.readFileSync(path.join(root, "docs/evidence/image-studio/demo-scene.json"), "utf8");
  await page.evaluate((text) => IronmateStudio.act("open-json", new Blob([text], { type: "application/json" })), demo);
  assert.ok((await page.evaluate(() => IronmateStudio.scene.layers.length)) > 0);
  await page.evaluate(() => IronmateStudio.act("undo"));
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.length), 0);
  await page.click(act("shape")); // 図形(▭ ◯ △ →): one tool, the shape is a candidate
  assert.deepEqual(await page.locator("#studio-candidates button").allTextContents(), ["▭", "◯", "△", "→"]);
  await page.locator("#studio-candidates button", {hasText: "△"}).click();
  assert.equal(await page.textContent(act("shape")), "△");                          // 📱 the face is the sign
  assert.equal(await page.getAttribute(act("shape"), "data-ui-word"), "図形(△)");   // 💻 the word names it
  let box = await page.locator("#board").boundingBox();
  await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.2);
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.click(act("select"));
  let model = await page.evaluate(() => window.IronmateStudio.scene);
  const first = model.layers[0];
  // Move using an interior point of the actual triangle, not its transparent corner.
  const sx = box.x + ((first.x + first.w / 2) / model.width) * box.width,
    sy = box.y + ((first.y + first.h * 0.7) / model.height) * box.height;
  await page.mouse.move(sx, sy);
  await page.mouse.down();
  await page.mouse.move(sx + 45, sy + 20, { steps: 5 });
  await page.mouse.up();
  await page.evaluate(() => window.IronmateStudio.ready);
  const moved = await page.evaluate(
    () => window.IronmateStudio.scene.layers[0],
  );
  assert(moved.x > first.x + 10);
  assert(moved.y > first.y);
  const handle = await page.locator("[data-handle]").boundingBox();
  await page.mouse.move(
    handle.x + handle.width / 2,
    handle.y + handle.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    handle.x + handle.width / 2 + 25,
    handle.y + handle.height / 2 + 20,
    { steps: 4 },
  );
  await page.mouse.up();
  await page.evaluate(() => window.IronmateStudio.ready);
  assert(
    (await page.evaluate(() => window.IronmateStudio.scene.layers[0])).w >
      moved.w,
  );
  await page.click("#custom");
  // Explicitly choose stamp mode: editor state must not depend on previous tool.
  await page.click(act("stamp"));
  await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.25);
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    2,
  );
  await page.click(act("undo"));
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    1,
  );
  await page.click(act("redo"));
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    2,
  );
  await page.click(act("emoji")); // 絵文字 has its own input; ✦ スタンプ keeps its own
  await page.click("#studio-candidates button:nth-child(3)");
  assert.deepEqual([await page.inputValue("#emoji-text"), await page.inputValue("#stamp-text"), await page.inputValue("#text")], ["🌱", "", "中央"]);
  await page.mouse.click(box.x + box.width * 0.8, box.y + box.height * 0.65);
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.at(-1).text),
    "🌱",
  );
  const heatScene = await page.evaluate(() => window.IronmateStudio.scene);
  const heatPalette = ["#112233", "#778899"];
  heatScene.layers.push({id:"heat", kind:"heatmap", name:"Heatmap", x:80, y:90, w:500, h:300,
    rotation:0, opacity:1, z:[[-1.123456789,null],[4,9]], xlabels:[2025,2026], ylabels:["A","B"],
    low:-1.123456789, high:9, levels:0, labels:true, palette:heatPalette});
  await page.setInputFiles(chooser("open-json"), {name:"heatmap.json", mimeType:"application/json", buffer:Buffer.from(JSON.stringify(heatScene))});
  await page.waitForFunction(() => window.IronmateStudio.scene.layers.at(-1)?.id === "heat");
  await page.click('[data-layer-id="heat"]');
  const exact = await page.evaluate(
    () => window.IronmateStudio.scene.layers.at(-1).z,
  );
  await page.locator("#levels").fill("4");
  await page.locator("#levels").dispatchEvent("change");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.deepEqual(
    await page.evaluate(() => {
      const { z, levels, palette } = window.IronmateStudio.scene.layers.at(-1);
      return { z, levels, palette };
    }),
    { z: exact, levels: 4, palette: heatPalette },
  );
  await download("PNG", "heatmap-palette.png");
  const pngColor = await page.evaluate(async (bytes) => {
    const bitmap = await createImageBitmap(new Blob([new Uint8Array(bytes)], { type: "image/png" }));
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(bitmap, 180, 128, 1, 1, 0, 0, 1, 1);
    return [...ctx.getImageData(0, 0, 1, 1).data];
  }, [...fs.readFileSync(path.join(out, "heatmap-palette.png"))]);
  assert.deepEqual(pngColor, [17, 34, 51, 255]);
  // Generate an original RGBA fixture in-browser, including transparency and an uneven edge.
  const fixture = await page.evaluate(() => {
    const c = document.createElement("canvas");
    c.width = 19;
    c.height = 13;
    const t = c.getContext("2d");
    t.fillStyle = "#ff0000";
    t.fillRect(0, 0, 9, 13);
    t.fillStyle = "#0000ff";
    t.fillRect(9, 0, 10, 13);
    t.clearRect(18, 12, 1, 1);
    return c.toDataURL("image/png");
  });
  const fixturePath = path.join(out, "fixture.png");
  fs.writeFileSync(fixturePath, Buffer.from(fixture.split(",")[1], "base64"));
  const [picker] = await Promise.all([page.waitForEvent("filechooser"), page.click(await as("import", "画像"))]); // 📥 どの形式から？ 画像
  assert.equal(await picker.element().getAttribute("accept"), "image/png,image/jpeg,image/webp");
  assert.equal(await page.locator("#studio-candidates").isHidden(), true);                     // the row hides; the chooser is open
  await picker.setFiles(fixturePath);
  await page.waitForFunction(
    () => window.IronmateStudio.scene.layers.at(-1)?.kind === "image",
  );
  await page.evaluate(() => window.IronmateStudio.ready);
  const original = await page.evaluate(
    () => window.IronmateStudio.scene.layers.at(-1).src,
  );
  await page.locator("#cell").fill("7");
  await page.locator("#cell").dispatchEvent("change");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.at(-1).src),
    original,
  );
  await page.locator("#cell").fill("1");
  await page.locator("#cell").dispatchEvent("change");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.locator("[data-layer] image").getAttribute("href"),
    original,
  );
  await download("JSON", "scene.json");
  assert.equal(await page.locator("#studio-candidates").isHidden(), true);                     // 📤 選んだら候補は隠れる
  await download("SVG", "composition.svg");
  await download("PNG", "composition.png");
  const saved = JSON.parse(
    fs.readFileSync(path.join(out, "scene.json"), "utf8"),
  );
  assert.deepEqual(saved.layers.find(({ id }) => id === "heat").palette, heatPalette);
  const exportedSvg = fs.readFileSync(path.join(out, "composition.svg"), "utf8");
  assert(!exportedSvg.includes('class="selection"'));
  assert(exportedSvg.includes('fill="#556677"><title>B / 2025: 4</title>'));
  assert(exportedSvg.includes('fill="none"><title>A / 2026: 欠測</title>'));
  const png1 = await page.evaluate(async () =>
    Array.from(
      new Uint8Array(
        await (await window.IronmateStudio.pngBlob()).arrayBuffer(),
      ),
    ),
  );
  await page.click("#blank");
  await page.setInputFiles(chooser("open-json"), path.join(out, "scene.json"));
  await page.waitForFunction(
    (n) => window.IronmateStudio.scene.layers.length === n,
    saved.layers.length,
  );
  await page.evaluate(() => window.IronmateStudio.ready);
  const png2 = await page.evaluate(async () =>
    Array.from(
      new Uint8Array(
        await (await window.IronmateStudio.pngBlob()).arrayBuffer(),
      ),
    ),
  );
  assert.deepEqual(png1, png2, "reload preserves exact browser PNG bytes");
  assert.deepEqual(
    await page.evaluate(() => window.IronmateStudio.scene),
    saved,
  );
  // Editing and exports continue after network is disabled.
  await page.click(await as("export", "Base64"));
  await page.waitForFunction(() =>
    document
      .getElementById("base64-text")
      .value.startsWith("data:image/png;base64,"),
  );
  const dataUri = await page.locator("#base64-text").inputValue();
  assert.deepEqual(
    Buffer.from(dataUri.split(",")[1], "base64"),
    fs.readFileSync(path.join(out, "composition.png")),
  );
  await page.selectOption("#base64-mode", "base64");
  const raw = await page.locator("#base64-text").inputValue();
  assert.equal(raw, dataUri.split(",")[1]);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.click("#copy-base64");
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), raw);
  await page.evaluate(() => {
    window.savedClipboardWrite = navigator.clipboard.writeText;
    navigator.clipboard.writeText = async () => {
      throw new DOMException("denied", "NotAllowedError");
    };
  });
  await page.click("#copy-base64");
  assert(
    (await page.locator("#base64-status").textContent()).includes(
      "自動コピーが使えません",
    ),
  );
  await page.evaluate(() => {
    navigator.clipboard.writeText = window.savedClipboardWrite;
    delete window.savedClipboardWrite;
  });

  await page
    .locator("#base64-dialog button")
    .filter({ hasText: "閉じる" })
    .click();
  await page.selectOption("#export-scale", "2");
  await download("PNG", "composition-2x.png");
  // 🧰 IronmateStudio.act runs what the toolbar runs, by its act's name (a host or Node needs no button)
  const viaAct = page.waitForEvent("download");
  await page.evaluate(() => IronmateStudio.act("png"));
  assert.match((await viaAct).suggestedFilename(), /\.png$/);
  assert.equal(await page.inputValue("#export-scale"), "2");
  // 📋 a row of a host's header (studio_rows) sends the key of an act: the shelf, as from the toolbar
  await page.evaluate(() => document.dispatchEvent(new CustomEvent("ui-chrome-action", { detail: { key: "shelf" } })));
  assert.equal(await page.evaluate(() => document.getElementById("shelf-dialog").open), true);
  await page.evaluate(() => document.getElementById("shelf-dialog").close());
  const enlarged = fs.readFileSync(path.join(out, "composition-2x.png"));
  assert.equal(enlarged.readUInt32BE(16), saved.width * 2);
  assert.equal(enlarged.readUInt32BE(20), saved.height * 2);
  await page.selectOption("#export-scale", "1");
  await page.context().setOffline(true);
  await download("PNG", "offline.png");
  assert.deepEqual(
    fs.readFileSync(path.join(out, "offline.png")),
    fs.readFileSync(path.join(out, "composition.png")),
  );
  // More images than the preview cache capacity must all keep their processing.
  const cacheDoc = {
    ...saved,
    layers: Array.from({ length: 20 }, (_, i) => ({
      ...saved.layers.at(-1),
      id: "cache-" + i,
      cell: 2 + i,
      x: i * 10,
      y: i * 10,
    })),
  };
  const cachePath = path.join(out, "cache-scene.json");
  fs.writeFileSync(cachePath, JSON.stringify(cacheDoc));
  await page.setInputFiles(chooser("open-json"), cachePath);
  await page.waitForFunction(
    () => window.IronmateStudio.scene.layers.length === 20,
  );
  await page.evaluate(() => window.IronmateStudio.ready);
  assert(
    await page.evaluate(async () => {
      const img = new Image();
      img.src = window.IronmateStudio.scene.layers[0].src;
      await img.decode();
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth;
      cv.height = img.naturalHeight;
      const ctx = cv.getContext("2d");
      ctx.drawImage(img, 0, 0);
      const raw = ctx.getImageData(0, 0, cv.width, cv.height).data;
      const nodes = [...document.querySelectorAll("[data-layer] image")];
      for (let i = 0; i < nodes.length; i++) {
        const output = new Image();
        output.src = nodes[i].getAttribute("href");
        await output.decode();
        ctx.clearRect(0, 0, cv.width, cv.height);
        ctx.drawImage(output, 0, 0);
        const actual = ctx.getImageData(0, 0, cv.width, cv.height).data,
          expected = StudioCore.mosaicRGBA(
            raw,
            cv.width,
            cv.height,
            2 + i,
            256,
          );
        // Canvas normalizes hidden RGB on fully transparent pixels.
        for (let p = 0; p < actual.length; p++)
          if (
            (p % 4 === 3 || expected[p - (p % 4) + 3]) &&
            Math.abs(actual[p] - expected[p]) > 1
          )
            return false;
      }
      return true;
    }),
    "all 20 image previews use their processed pixels, including evicted cache entries",
  );
  // Restore connectivity after the preceding offline-export regression.
  await page.context().setOffline(false);
  // Workspace history roundtrip: retain undo/redo states and selected index.
  const workspaceDownload = page.waitForEvent("download");
  await page.click(await as("export", "作業履歴"));
  const workspace = await workspaceDownload;
  const workspacePath = path.join(out, "workspace-history.json");
  await workspace.saveAs(workspacePath);
  const historyData = JSON.parse(fs.readFileSync(workspacePath, "utf8"));
  assert.equal(historyData.schema, "ironmate-studio-workspace/1");
  assert(historyData.items.length >= 1 && historyData.items.length <= 40);
  const historyCurrent = historyData.items[historyData.index];
  await page.click("#blank");
  await page.setInputFiles(chooser("open-workspace"), workspacePath);
  await page.waitForFunction(() => document.querySelector("#status").textContent === "作業履歴を復元しました");
  assert.deepEqual(await page.evaluate(() => IronmateStudio.scene), historyCurrent);
  assert.equal(await page.locator("#history-list li").count(), historyData.items.length);
  const restoredDownload = page.waitForEvent("download");
  await page.click(await as("export", "作業履歴"));
  const restoredPath = path.join(out, "workspace-restored.json");
  await (await restoredDownload).saveAs(restoredPath);
  assert.deepEqual(JSON.parse(fs.readFileSync(restoredPath, "utf8")), historyData);
  await page.locator("#workspace-history summary").click();
  acceptHistoryTrim = false;
  await page.click("#trim-history");
  assert.equal(await page.locator("#history-list li").count(), historyData.items.length);
  acceptHistoryTrim = true;
  await page.click("#trim-history");
  await page.waitForFunction(() => document.querySelectorAll("#history-list li").length === 1);
  assert.deepEqual(await page.evaluate(() => IronmateStudio.scene), historyCurrent);
  assert(await page.locator(act("undo")).isDisabled());
  assert(await page.locator(act("redo")).isDisabled());
  // Invalid embedded PNG must leave the complete current workspace intact.
  const brokenWorkspace = structuredClone(historyData);
  const brokenImage = brokenWorkspace.items.flatMap(s => s.layers).find(l => l.kind === "image");
  assert(brokenImage, "workspace fixture includes an embedded image");
  brokenImage.src = "data:image/png;base64,AAAA";
  await page.setInputFiles(chooser("open-workspace"), {name:"broken.json",mimeType:"application/json",
    buffer:Buffer.from(JSON.stringify(brokenWorkspace))});
  await page.locator("#error").waitFor({state:"visible"});
  assert.deepEqual(await page.evaluate(() => IronmateStudio.scene), historyCurrent);
  assert.equal(await page.locator("#history-list li").count(), 1);
  await page.locator("#error button").click();
  // Isolate the new ingress smoke from legacy editor tool/selection state.
  await page.goto(url);
  await page.locator("#pixel-editor summary").click();
  await page.waitForFunction(() => !!window.IronmateWorkbench?.grid);
  await page.locator("#grid").click();
  await page.locator("#place-grid").click();
  await page.waitForFunction(() => IronmateStudio.scene.layers.some(layer => layer.name === "ドット絵.png"));
  for (const tool of ["emoji", "kaomoji"]) {
    await page.locator(act(tool)).click();
    await page.locator("#keyboard-focus").click();
    assert.equal(await page.evaluate(() => document.activeElement.id), tool + "-text");
  }
  await page.evaluate(() => window.IronmateStudio.ready);
  // Same real browser: feed exported PNG back via Base64 and clipboard.
  const pngIn = await page.evaluate(async () => Array.from(
    new Uint8Array(await (await IronmateStudio.pngBlob()).arrayBuffer())));
  const inputText = "data:image/png;base64," + Buffer.from(pngIn).toString("base64");
  await page.click("#blank");
  // 🗂️ image text typed by hand goes through シェルフ: its text box, then 取り込み (📥 → シェルフ)
  const throughShelf = async (text) => {
    await page.click(await as("import", "シェルフ"));
    const cards = page.locator("#shelf-items-container .shelf-card"), before = await cards.count();
    await page.fill("#shelf-input-text", text);
    await page.click("#shelf-add-text");
    if ((await cards.count()) > before) await cards.last().locator("button", { hasText: "取り込み" }).click();
  };
  await throughShelf(inputText);
  await page.waitForFunction(() => IronmateStudio.scene.layers.some(l => l.kind === "image"));
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.at(-1).kind), "image");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.evaluate(text => navigator.clipboard.writeText(text), inputText);
  await page.click(await as("import", "クリップボード"));                                 // 📥 どの形式から？ → クリップボード
  await page.waitForFunction(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length === 2 || document.querySelector("#error")?.open);
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length), 2);
  await throughShelf(inputText.replace("image/png", "image/jpeg"));                          // the type and the bytes disagree
  await assert.doesNotReject(() => page.locator("#error").waitFor({state: "visible", timeout: 3000}));
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length), 2);
  await page.locator("#error button").click();
  await page.click("#shelf-clear");                                                           // the shelf suite starts from an empty shelf
  await page.evaluate(() => document.getElementById("shelf-dialog").close());
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.locator("#demo, #stamp-demo, #example-view").count(), 0);
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.screenshot({ path: path.join(out, "mobile.png"), fullPage: true });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    "no horizontal page overflow on mobile",
  );
  await require("./studio_shelf_browser.cjs")({ page, out });
  await require("./studio_scale_browser.cjs")({ page, out, root, download, act });
  await require("./studio_tradeoff_browser.cjs")({ page, out, root });
  assert.equal(failures.length, 0, failures.join("\n"));
  assert(
    requests.every(
      (url) =>
        url.startsWith("http://127.0.0.1:") ||
        url.startsWith("blob:") ||
        url.startsWith("data:"),
    ),
    "no external requests",
  );
  // Existing pinned PptxGenJS embeds the exported image without changing its bytes.
  const PptxGenJS = require("pptxgenjs"),
    pptx = new PptxGenJS();
  pptx.layout = "LAYOUT_WIDE";
  pptx.addSlide().addImage({
    data:
      "image/png;base64," +
      fs.readFileSync(path.join(out, "composition.png")).toString("base64"),
    x: 0,
    y: 0,
    w: 13.333333,
    h: 7.5,
  });
  await pptx.writeFile({ fileName: path.join(out, "composition.pptx") });
  const zip = await require("jszip").loadAsync(
    fs.readFileSync(path.join(out, "composition.pptx")),
  );
  const media = Object.keys(zip.files).filter(
    (n) => n.startsWith("ppt/media/") && n.endsWith(".png"),
  );
  assert.equal(media.length, 1);
  assert.deepEqual(
    await zip.file(media[0]).async("nodebuffer"),
    fs.readFileSync(path.join(out, "composition.png")),
  );
  fs.writeFileSync(
    path.join(out, "browser-result.json"),
    JSON.stringify(
      {
        browser: browser.version(),
        hosting: staticMode ? "static under /Ironmate/" : "loopback",
        checks: [
          "place",
          "move",
          "resize",
          "custom-stamp",
          "emoji",
          "undo-redo",
          "exact-matrix",
          "heatmap-palette-SVG-PNG-JSON",
          "mosaic-original-retained",
          "20-image-cache",
          "JSON-PNG-roundtrip",
          "offline-export",
          "mobile-no-overflow",
          "PPTX-image",
          staticMode ? "static-subpath" : "loopback",
          "Base64-Flutter-PNG",
          "clipboard-copy",
          "clipboard-denied-fallback",
          "vector-export-2x",
          "clock-arrow-monochrome",
          "CPU-CLI-PNG-Base64",
          "scale-controls",
        ],
        pageErrors: failures,
        remoteRequests: requests.filter(
          (u) =>
            !u.startsWith(url) &&
            !u.startsWith("blob:") &&
            !u.startsWith("data:"),
        ),
      },
      null,
      2,
    ),
  );
  console.log("Image Studio browser checks passed; evidence: " + out);
})()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    if (browser) await browser.close();
    server.kill();
    if (staticRoot) fs.rmSync(staticRoot, { recursive: true, force: true });
  });
