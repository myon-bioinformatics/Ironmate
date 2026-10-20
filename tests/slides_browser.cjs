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
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
