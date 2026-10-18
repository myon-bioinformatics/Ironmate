// studio_clipboard.cjs
/* Real static-site UI/codec tests; deterministic Clipboard API boundary doubles.
 * Native Chromium ClipboardItem smoke is separate from the cross-engine matrix.
 * No Android/iOS, OS picker, camera hardware, or native permission evidence.
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { deflateSync } = require("node:zlib");
const pw = require(process.env.IRONMATE_PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "..");
const output = path.resolve(process.env.IRONMATE_CLIPBOARD_EVIDENCE || "build/studio-clipboard");
const engines = (process.env.IRONMATE_BROWSERS || "chromium,firefox,webkit").split(",");
const site = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-clipboard-"));
const server = spawn(process.env.PYTHON || "python", ["-u", "-c", `
from image_studio import build_site
from pathlib import Path
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import sys
root = Path(sys.argv[1])
build_site(root / 'Ironmate')
s = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
print(f'http://127.0.0.1:{s.server_port}/Ironmate/', flush=True)
s.serve_forever()
`, site], { cwd: root, stdio: ["ignore", "pipe", "ignore"] });
// Independent PNG fixture encoder. RGBA includes transparent and half-alpha pixels.
function png(width, height, rgba = [255, 0, 0, 255]) {
  const chunk = (tag, data) => {
    const body = Buffer.concat([Buffer.from(tag), data]);
    let crc = 0xffffffff;
    for (const b of body) {
      crc ^= b;
      for (let n = 0; n < 8; n++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    const result = Buffer.alloc(data.length + 12);
    result.writeUInt32BE(data.length);
    body.copy(result, 4);
    result.writeUInt32BE((crc ^ 0xffffffff) >>> 0, result.length - 4);
    return result;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width); header.writeUInt32BE(height, 4); header[8] = 8; header[9] = 6;
  const row = Buffer.alloc(1 + width * 4);
  for (let i = 0; i < width * 4; i++) row[i + 1] = rgba[i % rgba.length];
  return Buffer.concat([Buffer.from("89504e470d0a1a0a", "hex"), chunk("IHDR", header),
    chunk("IDAT", deflateSync(Buffer.concat(Array(height).fill(row)))), chunk("IEND", Buffer.alloc(0))]);
}
const pixels = [255, 0, 0, 255, 0, 255, 0, 128, 0, 0, 0, 0];
const image = png(3, 1, pixels).toString("base64");
const green = png(1, 1, [0, 255, 0, 255]).toString("base64");
const uri = "data:image/png;base64," + image;
const binary = (base64 = image, type = "image/png") => ({ formats: [{ type, base64 }] });
let browser;
(async () => {
  fs.mkdirSync(output, { recursive: true });
  const url = await new Promise((resolve, reject) => {
    let data = "";
    const timer = setTimeout(() => reject(new Error("static server startup timeout")), 10000);
    server.stdout.on("data", c => {
      data += c;
      const m = data.match(/http:\/\/127\.0\.0\.1:\d+\/Ironmate\//);
      if (m) { clearTimeout(timer); resolve(m[0]); }
    });
    server.on("error", e => { clearTimeout(timer); reject(e); });
    server.on("exit", code => { clearTimeout(timer); reject(new Error("server exited " + code)); });
  });
  for (const engine of engines) {
    assert(["chromium", "firefox", "webkit"].includes(engine), "known browser");
    browser = await pw[engine].launch({
      headless: true,
      ...(engine === "chromium" && process.env.IRONMATE_CHROME
        ? { executablePath: process.env.IRONMATE_CHROME } : {}),
    });
    const page = await browser.newPage();
    page.setDefaultTimeout(10000);
    const errors = [], remote = [], checks = [];
    page.on("pageerror", e => errors.push(e.message));
    page.on("request", r => { if (!/^(http:\/\/127\.0\.0\.1:|blob:|data:)/.test(r.url())) remote.push(r.url()); });
    page.on("dialog", d => d.accept());
    await page.goto(url);
    await page.evaluate(() => IronmateStudio.ready);
    async function reset() {
      await page.evaluate(async () => {
        document.querySelector("#error").close();
        document.querySelector("#blank").click();
        await IronmateStudio.ready;
      });
      assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.length), 0);
    }
    async function snapshot() {
      return page.evaluate(() => JSON.stringify(IronmateStudio.scene));
    }
    async function normalized() {
      return page.evaluate(async () => {
        const layer = IronmateStudio.scene.layers.at(-1);
        const img = new Image(); img.src = layer.src; await img.decode();
        const cv = document.createElement("canvas"); cv.width = img.width; cv.height = img.height;
        const ctx = cv.getContext("2d"); ctx.drawImage(img, 0, 0);
        return { width: img.width, height: img.height, pixels: [...ctx.getImageData(0, 0, cv.width, cv.height).data] };
      });
    }
    async function scenario(name, config, code = null, expectedPixels = pixels) {
      await reset();
      const before = await snapshot();
      await page.evaluate(config => {
        window.clipboardCalls = { read: 0, readText: 0, getType: 0, arrayBuffer: 0 };
        const fail = name => { throw new DOMException("injected clipboard failure", name); };
        const clipboard = {};
        if (!config.noText) clipboard.readText = async () => {
          clipboardCalls.readText++; if (config.textError) fail(config.textError); return config.text || "";
        };
        if (!config.noRead) clipboard.read = async () => {
          clipboardCalls.read++; if (config.readError) fail(config.readError);
          return (config.items || []).map(item => ({
            types: item.formats.map(f => f.type),
            getType: async type => {
              clipboardCalls.getType++;
              const format = item.formats.find(f => f.type === type);
              if (format.error) fail(format.error);
              const blob = new Blob([Uint8Array.from(atob(format.base64 || ""), c => c.charCodeAt(0))], { type });
              if (format.oversized) Object.defineProperty(blob, "size", { value: 32 * 1024 * 1024 + 1 });
              const read = blob.arrayBuffer.bind(blob);
              blob.arrayBuffer = () => { clipboardCalls.arrayBuffer++; return read(); };
              return blob;
            },
          }));
        };
        Object.defineProperty(navigator, "clipboard", { configurable: true, value: config.absent ? undefined : clipboard });
      }, config);
      await page.evaluate(() => document.querySelector("#paste-image").onclick());
      if (code) {
        assert.equal(await page.locator("#error").getAttribute("data-code"), code, name);
        assert.equal(await page.locator("#error").isVisible(), true, name);
        assert.equal(await snapshot(), before, name + " must preserve scene");
      } else {
        assert.equal(await page.locator("#error").isVisible(), false, name);
        assert.equal(await page.evaluate(() => IronmateStudio.scene.layers.length), 1, name);
        if (expectedPixels) assert.deepEqual((await normalized()).pixels, expectedPixels, name);
      }
      checks.push(name);
      console.log(engine + ": " + name);
      return page.evaluate(() => clipboardCalls);
    }
    let calls = await scenario("ordinary-text-and-PNG", { text: "これは普通のメモです", items: [binary()] });
    assert.equal(calls.read, 1); assert.equal(calls.readText, 1);
    await scenario("base64-of-nonimage-and-PNG", { text: Buffer.from("ordinary text").toString("base64"), items: [binary()] });
    calls = await scenario("image-Base64-wins-over-binary", { text: uri, items: [binary(green)] });
    assert.equal(calls.read, 0);
    await scenario("raw-image-Base64", { text: image, noRead: true });
    await scenario("BOM-case-parameters-and-wrapping", { text: "\uFEFF DATA:IMAGE/PNG;charset=utf-8;BASE64,\n" + image + "\n" });
    calls = await scenario("invalid-image-data-URI-does-not-import-stale-PNG", { text: "data:image/png;base64,!!!", items: [binary()] }, "clipboard-invalid-image");
    assert.equal(calls.read, 0);
    await scenario("invalid-image-URI-header", { text: "data:image/png,abc", items: [binary()] }, "clipboard-invalid-image");
    await scenario("MIME-mismatch-text", { text: uri.replace("image/png", "image/jpeg"), items: [binary()] }, "clipboard-invalid-image");
    await scenario("unsupported-image-URI", { text: "data:image/gif;base64,R0lGODlh", items: [binary()] }, "clipboard-invalid-image");
    await scenario("recognized-raw-image-with-invalid-padding", { text: image + "=", items: [binary()] }, "clipboard-invalid-image");
    await scenario("undecodable-image-text", { text: "data:image/png;base64," + Buffer.from("89504e470d0a1a0a000000000000", "hex").toString("base64"), items: [binary()] }, "clipboard-invalid-image");
    await scenario("text-denied-image-readable", { textError: "NotAllowedError", items: [binary()] });
    await scenario("text-failed-image-readable", { textError: "UnknownError", items: [binary()] });
    await scenario("text-unsupported-image-readable", { textError: "NotSupportedError", items: [binary()] });
    await scenario("binary-only-API", { noText: true, items: [binary()] });
    await scenario("both-APIs-denied", { textError: "NotAllowedError", readError: "NotAllowedError" }, "clipboard-denied");
    await scenario("normal-text-image-denied", { text: "memo", readError: "NotAllowedError" }, "clipboard-denied");
    await scenario("security-error", { noText: true, readError: "SecurityError" }, "clipboard-denied");
    await scenario("API-absent", { absent: true }, "clipboard-unsupported");
    await scenario("read-methods-absent", { noText: true, noRead: true }, "clipboard-unsupported");
    await scenario("API-NotSupportedError", { noText: true, readError: "NotSupportedError" }, "clipboard-unsupported");
    await scenario("API-other-failure", { noText: true, readError: "UnknownError" }, "clipboard-read-failed");
    await scenario("text-only-no-image", { text: "memo", noRead: true }, "clipboard-no-image");
    calls = await scenario("empty-clipboard", {}, "clipboard-no-image");
    assert.equal(calls.readText, 1, "do not retry readText");
    await scenario("nonimage-items", { items: [{ formats: [{ type: "text/html" }] }] }, "clipboard-no-image");
    await scenario("later-item-after-getType-denial", { items: [{ formats: [{ type: "image/png", error: "NotAllowedError" }] }, binary()] });
    await scenario("later-format-after-corrupt-image", { items: [{ formats: [{ type: "image/jpeg", base64: image }, { type: "image/png", base64: image }] }] });
    await scenario("binary-MIME-mismatch", { items: [binary(image, "image/jpeg")] }, "clipboard-invalid-image");
    calls = await scenario("binary-over-32MiB-before-arrayBuffer", { items: [{ formats: [{ type: "image/png", base64: image, oversized: true }] }] }, "clipboard-invalid-image");
    assert.equal(calls.arrayBuffer, 0);
    // Exercise real decoded-byte ceiling (32MiB and +1), including raw text.
    const atLimit = Buffer.alloc(32 * 1024 * 1024); Buffer.from(image, "base64").copy(atLimit);
    await scenario("binary-exactly-32MiB", { items: [binary(atLimit.toString("base64"))] });
    await scenario("raw-Base64-exactly-32MiB", { text: atLimit.toString("base64") });
    const over = Buffer.concat([atLimit, Buffer.from([0])]).toString("base64");
    await scenario("raw-Base64-over-32MiB", { text: over, items: [binary()] }, "clipboard-invalid-image");
    await scenario("URI-Base64-over-32MiB", { text: "data:image/png;base64," + over }, "clipboard-invalid-image");
    // File and camera input paths still use the same strict import pipeline.
    for (const id of ["image", "camera-image"]) {
      await reset();
      await page.locator("#" + id).setInputFiles({ name: "rgba.png", mimeType: "image/png", buffer: Buffer.from(image, "base64") });
      await page.waitForFunction(() => IronmateStudio.scene.layers.length === 1);
      assert.deepEqual(await normalized(), { width: 3, height: 1, pixels });
      checks.push(id + "-file-input-RGBA-dimensions");
      const before = await snapshot();
      await page.evaluate(id => {
        Object.defineProperty(document.querySelector("#" + id), "files", { configurable: true, value: [] });
      }, id);
      await page.evaluate(id => document.querySelector("#" + id).onchange(), id);
      assert.equal(await snapshot(), before);
      checks.push(id + "-cancel-keeps-scene");
      await page.evaluate(id => delete document.querySelector("#" + id).files, id);
    }
    await reset();
    await page.fill("#import-base64", uri);
    await page.evaluate(() => document.querySelector("#import-base64-button").onclick());
    assert.deepEqual(await normalized(), { width: 3, height: 1, pixels });
    checks.push("explicit-Base64-input-preserved");
    const retained = await snapshot();
    await page.fill("#import-base64", "data:image/png;base64,!!!");
    await page.evaluate(() => document.querySelector("#import-base64-button").onclick());
    assert.equal(await page.locator("#error").isVisible(), true);
    assert.equal(await snapshot(), retained, "invalid explicit input preserves an existing image");
    checks.push("invalid-Base64-input-retains-existing-scene");
    // Browser-owned JPEG/WebP encoders -> real decoders, compare dimensions only.
    for (const mime of ["image/jpeg", "image/webp"]) {
      const encoded = await page.evaluate(mime => {
        const cv = document.createElement("canvas"); cv.width = 3; cv.height = 2;
        const ctx = cv.getContext("2d"); ctx.fillStyle = "#20a060"; ctx.fillRect(0, 0, 3, 2);
        return cv.toDataURL(mime);
      }, mime);
      assert(encoded.startsWith("data:" + mime + ";base64,"), "encoder supports " + mime);
      await scenario(mime + "-binary", { items: [binary(encoded.split(",")[1], mime)] }, null, null);
      const result = await normalized(); assert.equal(result.width, 3); assert.equal(result.height, 2);
    }
    await scenario("4MP-boundary-accepted-without-resize", { items: [binary(png(2048, 2048).toString("base64"))] }, null, null);
    const dimensions = await page.evaluate(async () => {
      const img = new Image(); img.src = IronmateStudio.scene.layers.at(-1).src; await img.decode();
      return [img.width, img.height];
    });
    assert.deepEqual(dimensions, [2048, 2048]);
    await scenario("over-4MP-rejected-without-scene-change", { items: [binary(png(2049, 2048).toString("base64"))] }, "clipboard-invalid-image");
    assert.match(await page.locator("#error-text").textContent(), /4MP/);
    // Genuine OS Clipboard API integration, Chromium only; other engines use
    // deterministic boundary doubles above, not claims of native OS success.
    let nativeClipboard = "not exercised";
    if (engine === "chromium") {
      await reset();
      await page.evaluate(() => delete navigator.clipboard);
      await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
      await page.evaluate(async ({ image }) => {
        const bytes = Uint8Array.from(atob(image), c => c.charCodeAt(0));
        await navigator.clipboard.write([new ClipboardItem({
          "text/plain": new Blob(["ordinary memo"], { type: "text/plain" }),
          "image/png": new Blob([bytes], { type: "image/png" }),
        })]);
      }, { image });
      await page.click("#paste-image");
      await page.waitForFunction(() => IronmateStudio.scene.layers.length === 1 || document.querySelector("#error").open);
      assert.equal(await page.locator("#error").isVisible(), false);
      assert.deepEqual((await normalized()).pixels, pixels);
      checks.push("native-Chromium-mixed-text-PNG");
      nativeClipboard = "ClipboardItem write + button read, mixed text/plain and image/png";
    }
    assert.deepEqual(errors, []); assert.deepEqual(remote, []);
    await page.screenshot({ path: path.join(output, engine + ".png") });
    fs.writeFileSync(path.join(output, engine + ".json"), JSON.stringify({
      engine, version: browser.version(), playwright: require(path.join(path.dirname(require.resolve(process.env.IRONMATE_PLAYWRIGHT_MODULE || "playwright")), "package.json")).version,
      hosting: "static /Ironmate/", clipboardMatrix: "injected API boundary, real UI/codec", nativeClipboard,
      checks, pageErrors: errors, externalRequests: remote, physicalAndroidIOS: "not tested",
    }, null, 2) + "\n");
    console.log(engine + " " + browser.version() + ": " + checks.length + " checks passed");
    await browser.close(); browser = null;
  }
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close(); server.kill(); fs.rmSync(site, { recursive: true, force: true });
});
