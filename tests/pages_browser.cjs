/* Exercise the deployed Docker payload at the GitHub Pages /Ironmate/ subpath. */
"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const { spawnSync } = require("node:child_process");
const { chromium } = require(
  process.env.IRONMATE_PLAYWRIGHT_MODULE || "playwright",
);
const url = process.env.IRONMATE_PAGES_URL || "http://127.0.0.1:8080/Ironmate/";
const out = path.resolve("build/pages-evidence");
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
  });
  try {
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1100 },
      acceptDownloads: true,
    });
    const errors = [],
      requests = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("request", (r) => requests.push(r.url()));
    await page.goto(url);
    await page.waitForFunction(() => !!window.IronmateStudio);
    await page.click('a[href="tools/"]');
    await page.waitForFunction(() => !!window.IronmateWorkbench);
    assert.match(page.url(), /\/Ironmate\/tools\/$/);
    await page.screenshot({
      path: path.join(out, "desktop.png"),
      fullPage: true,
    });
    await page.selectOption("#mask", "cloud");
    await page.selectOption("#size", "23");
    await page.selectOption("#effect", "shadow");
    await page.selectOption("#palette", "C02");
    await page.click("#generate");
    let g = await page.evaluate(() => IronmateWorkbench.grid);
    assert.equal(g.width, 23);
    fs.writeFileSync(path.join(out, "grid.json"), JSON.stringify(g));
    await page.selectOption("#scale", "2");
    const download = async (id, filename) => {
      const pending = page.waitForEvent("download");
      await page.click("#" + id);
      await (await pending).saveAs(path.join(out, filename));
    };
    await download("grid-png", "grid.png");
    await download("grid-svg", "grid.svg");
    await download("grid-json", "download.json");
    await page.click("#grid-base64");
    await page.waitForFunction(() =>
      document
        .getElementById("base64-output")
        .value.startsWith("data:image/png;base64,"),
    );
    const dataURI = await page.inputValue("#base64-output");
    assert.deepEqual(
      Buffer.from(dataURI.split(",")[1], "base64"),
      fs.readFileSync(path.join(out, "grid.png")),
    );
    await page.fill("#width", "31");
    await page.fill("#height", "17");
    await page.click("#resize");
    assert.equal(
      (await page.evaluate(() => IronmateWorkbench.grid)).height,
      17,
    );
    await page.click("#undo-grid");
    assert.deepEqual(await page.evaluate(() => IronmateWorkbench.grid), g);
    await page.setInputFiles("#grid-file", {
      name: "bad.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"schema":"wrong"}'),
    });
    await page.waitForFunction(
      () => document.getElementById("message").dataset.error === "true",
    );
    assert.deepEqual(await page.evaluate(() => IronmateWorkbench.grid), g);
    // Use real PNG bytes and a hostile filename to cover thumbnail decoding and HTML escaping.
    const image = fs.readFileSync(path.join(out, "grid.png"));
    await page.setInputFiles("#images", [
      {
        name: "<img onerror=alert(1)>.png",
        mimeType: "image/png",
        buffer: image,
      },
      { name: "second.png", mimeType: "image/png", buffer: image },
    ]);
    await page.waitForFunction(
      () => !document.getElementById("digest-html").disabled,
    );
    await download("digest-png", "digest.png");
    await download("digest-html", "digest.html");
    const digest = fs.readFileSync(path.join(out, "digest.html"), "utf8");
    assert(digest.includes("&lt;img onerror=alert(1)&gt;.png"));
    assert(!digest.includes("<img onerror="));
    await page.setInputFiles("#capacity-file", {
      name: "seven.bin",
      mimeType: "application/octet-stream",
      buffer: Buffer.alloc(7),
    });
    assert.match(await page.textContent("#capacity-result"), /Base64 12文字/);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url + "tools/");
    await page.waitForFunction(() => !!window.IronmateWorkbench);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(out, "mobile.png"),
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert(
      requests.every(
        (r) =>
          r.startsWith(new URL(url).origin + "/") || /^(data|blob):/.test(r),
      ),
    );
    const check = spawnSync(
      process.env.PYTHON || "python",
      [
        "-S",
        "-c",
        `import json\nfrom pathlib import Path\nimport grid_tools,pixel_grid\np=Path('build/pages-evidence')\ng=json.loads((p/'grid.json').read_text())\nassert g==pixel_grid.render('cloud','C02','shadow',23)\nassert grid_tools.restore((p/'grid.png').read_bytes(),backend='stdlib')==g\nprint('Browser PNG -> Python grid restore: exact match')`,
      ],
      { encoding: "utf8" },
    );
    assert.equal(check.status, 0, check.stderr);
    console.log(check.stdout.trim());
    console.log(
      "Static Studio navigation, presets, PNG/SVG/JSON/Base64, resize/undo, invalid import, digest, filename escaping, capacity and mobile layout passed",
    );
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
