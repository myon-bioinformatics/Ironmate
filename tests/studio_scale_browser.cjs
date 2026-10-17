/* Delivery and reconstruction controls, with known source geometry. */
"use strict";
const fs = require("node:fs"),
  path = require("node:path"),
  assert = require("node:assert/strict"),
  { execFileSync } = require("node:child_process");
module.exports = async function ({ page, out, root, download }) {
  const load = async (scene, name) => {
    const file = path.join(out, name + ".json");
    fs.writeFileSync(file, JSON.stringify(scene));
    await page.setInputFiles("#open", file);
    await page.waitForFunction(
      (s) => JSON.stringify(IronmateStudio.scene) === JSON.stringify(s),
      scene,
    );
    await page.evaluate(() => IronmateStudio.ready);
  };
  const png = async () =>
    Buffer.from(
      await page.evaluate(async () => [
        ...new Uint8Array(await (await IronmateStudio.pngBlob()).arrayBuffer()),
      ]),
    );
  await page.setViewportSize({ width: 1600, height: 1100 });
  await page.click("#stamp-demo");
  await page.evaluate(() => IronmateStudio.ready);
  const stamps = await page.evaluate(() => IronmateStudio.scene);
  assert(
    stamps.layers.some((l) => l.kind === "arrow") &&
      stamps.layers.some((l) => l.kind === "clock"),
  );
  await page
    .locator("#layers button")
    .filter({ hasText: "直線＋中央" })
    .click();
  await page.selectOption("#arrow-placement", "tip");
  await page.evaluate(() => IronmateStudio.ready);
  assert.equal(
    await page.evaluate(
      () =>
        IronmateStudio.scene.layers.find((l) => l.kind === "arrow")
          .headPlacement,
    ),
    "tip",
  );
  await page.click("#undo");
  await page.evaluate(() => IronmateStudio.ready);
  await page.locator("#layers button").filter({ hasText: "10:10" }).click();
  await page.locator("#clock-time").fill("03:30");
  await page.locator("#clock-time").dispatchEvent("change");
  await page.evaluate(() => IronmateStudio.ready);
  assert.equal(
    await page.evaluate(
      () => IronmateStudio.scene.layers.find((l) => l.kind === "clock").hour,
    ),
    3,
  );
  await page.click("#undo");
  await page.evaluate(() => IronmateStudio.ready);
  await page.screenshot({
    path: path.join(out, "stamps-editor.png"),
    fullPage: true,
  });
  await download("#save", "stamps-scene.json");
  await download("#png", "stamps.png");
  await page.selectOption("#export-scale", "4");
  await download("#svg", "stamps-4x.svg");
  await download("#png", "stamps-4x.png");
  assert.equal(
    fs.readFileSync(path.join(out, "stamps-4x.png")).readUInt32BE(16),
    5120,
  );
  await page.selectOption("#export-scale", "1");
  const fixture =
    "data:image/png;base64," +
    fs.readFileSync(path.join(out, "fixture.png")).toString("base64");
  const mono = {
    schema: "ironmate-image-studio/1",
    width: 64,
    height: 64,
    background: "none",
    layers: [
      {
        id: "colored-image",
        kind: "image",
        name: "RGBA stamp",
        x: 0,
        y: 0,
        w: 64,
        h: 64,
        rotation: 0,
        opacity: 1,
        src: fixture,
        cell: 1,
        levels: 256,
      },
    ],
  };
  await load(mono, "mono-original");
  await page.locator("#layers button").first().click();
  await page.fill("#fill", "#01a060");
  await page.check("#monochrome");
  await page.evaluate(() => IronmateStudio.ready);
  const monoPixels = await page.evaluate(async () => {
    const image = await createImageBitmap(await IronmateStudio.pngBlob());
    const c = document.createElement("canvas");
    c.width = image.width;
    c.height = image.height;
    const t = c.getContext("2d");
    t.drawImage(image, 0, 0);
    return [
      ...t.getImageData(15, 15, 1, 1).data,
      ...t.getImageData(45, 15, 1, 1).data,
    ];
  });
  assert.deepEqual(
    monoPixels,
    [1, 160, 96, 255, 1, 160, 96, 255],
    "colored source becomes one requested color through an alpha mask",
  );
  await download("#save", "mono-scene.json");
  await download("#png", "mono.png");
  const runCLI = (format, name, extra = []) =>
    execFileSync(
      process.env.PYTHON || "python",
      [
        "-S",
        "image_studio.py",
        "--render",
        path.join(out, "mono-scene.json"),
        "--format",
        format,
        "--chrome",
        process.env.IRONMATE_CHROME,
        "-o",
        path.join(out, name),
        "--force",
        ...extra,
      ],
      {
        cwd: root,
        env: { ...process.env, IRONMATE_CHROME_NO_SANDBOX: "1" },
        timeout: 60000,
      },
    );
  const start = performance.now();
  runCLI("png", "cli.png");
  const cliMs = performance.now() - start;
  runCLI("base64", "cli.base64.txt", ["--data-uri"]);
  const encoded = fs.readFileSync(path.join(out, "cli.base64.txt"), "utf8");
  assert(encoded.startsWith("data:image/png;base64,"));
  assert.deepEqual(
    Buffer.from(encoded.split(",")[1], "base64"),
    fs.readFileSync(path.join(out, "cli.png")),
  );
  const cliSamples = await page.evaluate(async (uri) => {
    const img = new Image();
    img.src = uri;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = 64;
    c.height = 64;
    const t = c.getContext("2d");
    t.drawImage(img, 0, 0);
    return [...t.getImageData(15, 15, 1, 1).data];
  }, encoded);
  assert.deepEqual(cliSamples, [1, 160, 96, 255]);
  // A known vector original lets us measure, rather than assume, recovery quality.
  const shape = (id, kind, x, y, w, h, fill) => ({
    id,
    kind,
    x,
    y,
    w,
    h,
    fill,
    stroke: "none",
    strokeWidth: 0,
    rotation: 0,
    opacity: 1,
  });
  const reference = {
    schema: "ironmate-image-studio/1",
    width: 256,
    height: 256,
    background: "#FFFFFF",
    layers: [
      shape("circle", "ellipse", 19, 19, 217, 217, "#087D79"),
      shape("triangle", "triangle", 65, 50, 126, 151, "#EFBE4C"),
    ],
  };
  await load(reference, "scale-reference");
  const ref = await png();
  fs.writeFileSync(path.join(out, "scale-reference.png"), ref);
  const low = await page.evaluate(async () => {
    const bmp = await createImageBitmap(await IronmateStudio.pngBlob());
    const c = document.createElement("canvas");
    c.width = 16;
    c.height = 16;
    const t = c.getContext("2d");
    t.imageSmoothingEnabled = true;
    t.imageSmoothingQuality = "high";
    t.drawImage(bmp, 0, 0, 16, 16);
    return c.toDataURL("image/png");
  });
  const results = {
    fixture: "known vector circle and triangle -> 16x16 raster -> 256x256",
    gpu: "disabled in test browser and CLI",
    cli_single_64px_ms: cliMs,
    methods: {},
  };
  const buffers = { reference: ref };
  for (const method of ["pixelated", "smooth"]) {
    const scene = {
      ...reference,
      layers: [
        {
          ...shape("raster", "image", 0, 0, 256, 256, "#FFFFFF"),
          src: low,
          cell: 1,
          levels: 256,
          sampling: method,
        },
      ],
    };
    await load(scene, "scale-" + method);
    buffers[method] = await png();
    fs.writeFileSync(
      path.join(out, "scale-" + method + ".png"),
      buffers[method],
    );
  }
  await load(reference, "scale-vector-redraw");
  buffers.vector = await png();
  assert.deepEqual(
    buffers.vector,
    ref,
    "known retained vectors re-render exactly",
  );
  const comparison = await page.evaluate(
    async ({ ref, nearest, smooth, vector, low }) => {
      async function image(uri) {
        const im = new Image();
        im.src = uri;
        await im.decode();
        return im;
      }
      const decode = async (uri) => {
        const im = await image(uri),
          c = document.createElement("canvas");
        c.width = 256;
        c.height = 256;
        const t = c.getContext("2d");
        t.drawImage(im, 0, 0, 256, 256);
        return t.getImageData(0, 0, 256, 256).data;
      };
      const truth = await decode(ref),
        scores = {};
      for (const [name, uri] of Object.entries({ nearest, smooth, vector })) {
        const a = await decode(uri);
        let squared = 0,
          absolute = 0,
          n = 0;
        for (let i = 0; i < a.length; i++)
          if (i % 4 !== 3) {
            const d = a[i] - truth[i];
            squared += d * d;
            absolute += Math.abs(d);
            n++;
          }
        scores[name] = {
          rgb_mae: absolute / n,
          rgb_rmse: Math.sqrt(squared / n),
        };
      }
      const c = document.createElement("canvas");
      c.width = 1080;
      c.height = 340;
      const t = c.getContext("2d");
      t.fillStyle = "#f8f7f2";
      t.fillRect(0, 0, c.width, c.height);
      t.font = "16px sans-serif";
      const panels = [
        ["16x16 source", low],
        ["Nearest", nearest],
        ["Smooth", smooth],
        ["Vector redraw", vector],
      ];
      for (let i = 0; i < panels.length; i++) {
        t.fillStyle = "#163b3b";
        t.fillText(panels[i][0], 10 + i * 270, 25);
        t.imageSmoothingEnabled = false;
        t.drawImage(await image(panels[i][1]), 10 + i * 270, 42, 256, 256);
      }
      t.fillText(
        "Smoothing changes appearance; retained vectors preserve known geometry.",
        10,
        325,
      );
      return { scores, png: c.toDataURL("image/png") };
    },
    {
      ref: "data:image/png;base64," + buffers.reference.toString("base64"),
      nearest: "data:image/png;base64," + buffers.pixelated.toString("base64"),
      smooth: "data:image/png;base64," + buffers.smooth.toString("base64"),
      vector: "data:image/png;base64," + buffers.vector.toString("base64"),
      low,
    },
  );
  assert(
    comparison.scores.nearest.rgb_rmse > 0 &&
      comparison.scores.smooth.rgb_rmse > 0,
  );
  assert.equal(comparison.scores.vector.rgb_rmse, 0);
  assert.notDeepEqual(buffers.pixelated, buffers.smooth);
  results.methods = comparison.scores;
  fs.writeFileSync(
    path.join(out, "scale-comparison.png"),
    Buffer.from(comparison.png.split(",")[1], "base64"),
  );
  fs.writeFileSync(
    path.join(out, "scale-results.json"),
    JSON.stringify(results, null, 2),
  );
};
