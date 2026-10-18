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
  page.on("pageerror", (e) => failures.push(e.message));
  page.on("request", (r) => requests.push(r.url()));
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto(url);
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.screenshot({
    path: path.join(out, "desktop.png"),
    fullPage: true,
  });
  const initial = await page.evaluate(() => window.IronmateStudio.scene);
  assert.equal(initial.layers.length, 8);
  const legacyText = initial.layers.find((l) => l.kind === "text");
  await page.click(`[data-layer-id="${legacyText.id}"]`);
  assert.equal(await page.isChecked("#monochrome"), false);
  fs.writeFileSync(
    path.join(out, "demo-scene.json"),
    JSON.stringify(initial, null, 2),
  );
  fs.writeFileSync(
    path.join(out, "demo.svg"),
    await page.evaluate(() => StudioCore.svg(IronmateStudio.scene)),
  );
  fs.writeFileSync(
    path.join(out, "demo.png"),
    Buffer.from(
      await page.evaluate(async () =>
        Array.from(
          new Uint8Array(await (await IronmateStudio.pngBlob()).arrayBuffer()),
        ),
      ),
    ),
  );

  await page.click("#blank");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    0,
  );
  await page.click('[data-tool="triangle"]');
  let box = await page.locator("#board").boundingBox();
  await page.mouse.click(box.x + box.width * 0.25, box.y + box.height * 0.2);
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.click('[data-tool="select"]');
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
  await page.click('[data-tool="stamp"]');
  await page.mouse.click(box.x + box.width * 0.7, box.y + box.height * 0.25);
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    2,
  );
  await page.click("#undo");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    1,
  );
  await page.click("#redo");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.length),
    2,
  );
  await page.click("#emojis button:nth-child(3)");
  await page.mouse.click(box.x + box.width * 0.8, box.y + box.height * 0.65);
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.equal(
    await page.evaluate(() => window.IronmateStudio.scene.layers.at(-1).text),
    "🌱",
  );
  await page.fill(
    "#matrix",
    '{"data":[{"type":"heatmap","z":[[-1.123456789,null],[4,9]],"x":[2025,2026],"y":["A","B"]}]}',
  );
  await page.click("#heatmap");
  await page.evaluate(() => window.IronmateStudio.ready);
  const exact = await page.evaluate(
    () => window.IronmateStudio.scene.layers.at(-1).z,
  );
  await page.locator("#levels").fill("4");
  await page.locator("#levels").dispatchEvent("change");
  await page.evaluate(() => window.IronmateStudio.ready);
  assert.deepEqual(
    await page.evaluate(() => window.IronmateStudio.scene.layers.at(-1).z),
    exact,
  );
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
  await page.setInputFiles("#image", fixturePath);
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
  const download = async (id, name) => {
    const wait = page.waitForEvent("download");
    await page.click(id);
    await (await wait).saveAs(path.join(out, name));
  };
  await download("#save", "scene.json");
  await download("#svg", "composition.svg");
  await download("#png", "composition.png");
  const saved = JSON.parse(
    fs.readFileSync(path.join(out, "scene.json"), "utf8"),
  );
  assert(
    !fs
      .readFileSync(path.join(out, "composition.svg"), "utf8")
      .includes('class="selection"'),
  );
  const png1 = await page.evaluate(async () =>
    Array.from(
      new Uint8Array(
        await (await window.IronmateStudio.pngBlob()).arrayBuffer(),
      ),
    ),
  );
  await page.click("#blank");
  await page.setInputFiles("#open", path.join(out, "scene.json"));
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
  await page.click("#base64");
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
  await download("#png", "composition-2x.png");
  const enlarged = fs.readFileSync(path.join(out, "composition-2x.png"));
  assert.equal(enlarged.readUInt32BE(16), saved.width * 2);
  assert.equal(enlarged.readUInt32BE(20), saved.height * 2);
  await page.selectOption("#export-scale", "1");
  await page.context().setOffline(true);
  await download("#png", "offline.png");
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
  await page.setInputFiles("#open", cachePath);
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
  // Isolate the new ingress smoke from legacy editor tool/selection state.
  await page.goto(url);
  await page.evaluate(() => window.IronmateStudio.ready);
  // Same real browser: feed exported PNG back via Base64 and clipboard.
  const pngIn = await page.evaluate(async () => Array.from(
    new Uint8Array(await (await IronmateStudio.pngBlob()).arrayBuffer())));
  const inputText = "data:image/png;base64," + Buffer.from(pngIn).toString("base64");
  await page.click("#blank");
  await page.fill("#import-base64", inputText);
  await page.click("#import-base64-button");
  await page.waitForFunction(() => IronmateStudio.scene.layers.some(l => l.kind === "image"));
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.at(-1).kind), "image");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.evaluate(text => navigator.clipboard.writeText(text), inputText);
  await page.click("#paste-image");
  await page.waitForFunction(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length === 2 || document.querySelector("#error")?.open);
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length), 2);
  await page.fill("#import-base64", inputText.replace("image/png", "image/jpeg"));
  await page.click("#import-base64-button");
  await assert.doesNotReject(() => page.locator("#error").waitFor({state: "visible", timeout: 3000}));
  assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.filter(l => l.kind === "image").length), 2);
  await page.locator("#error button").click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.click("#demo");
  await page.evaluate(() => window.IronmateStudio.ready);
  await page.screenshot({ path: path.join(out, "mobile.png"), fullPage: true });
  assert(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    "no horizontal page overflow on mobile",
  );
  await require("./studio_scale_browser.cjs")({ page, out, root, download });
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
