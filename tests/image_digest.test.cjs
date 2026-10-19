// image_digest.test.cjs
"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {buildDigest} = require("../image_digest.cjs");

test("Node builds the same one-page digest through the Python owner", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "digest-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  fs.copyFileSync(process.env.DIGEST_PNG, path.join(dir, "a.png"));
  const spec = {schema: "ironmate-image-digest-input/1", title: "Node digest", rows: ["home"], cols: ["chromium", "webkit"],
    cells: [{row: "home", col: "chromium", image: "a.png", status: "pass"}]};
  const info = buildDigest(spec, {base: dir, out: path.join(dir, "out")});
  assert.equal(info.schema, "ironmate-image-digest/1");
  assert.deepEqual(info.tile, [64, 128]);
  const page = fs.readFileSync(path.join(dir, "out", "digest.html"), "utf8");
  assert(page.includes("data:image/png;base64,") && page.includes("not run"));
  assert.throws(() => buildDigest(spec, {base: dir, out: path.join(dir, "o2"), tile: "big"}), /tile/);
  assert.throws(() => buildDigest({...spec, schema: "x"}, {base: dir, out: path.join(dir, "o3")}), /expected schema/);

  const fileOut = path.join(dir, "existing-file");
  fs.writeFileSync(fileOut, "keep");
  assert.throws(() => buildDigest(spec, {base: dir, out: fileOut}), /new or empty directory/);
  assert.equal(fs.readFileSync(fileOut, "utf8"), "keep");

  const large = path.join(dir, "large.png");
  fs.closeSync(fs.openSync(large, "w"));
  fs.truncateSync(large, 32 * 1024 * 1024 + 1);
  assert.throws(() => buildDigest({...spec, cells: [{...spec.cells[0], image: "large.png"}]},
    {base: dir, out: path.join(dir, "oversize")}), /larger than 32MiB/);
  assert(!fs.existsSync(path.join(dir, "oversize")));

  const inputRoot = path.join(dir, "input");
  fs.mkdirSync(inputRoot);
  try {
    fs.symlinkSync(path.join(dir, "a.png"), path.join(inputRoot, "outside.png"));
  } catch (error) {
    if (!["EPERM", "EACCES", "ENOSYS"].includes(error.code)) throw error;
    t.diagnostic("symlinks unavailable: " + error.code);
    return;
  }
  assert.throws(() => buildDigest({...spec, cells: [{...spec.cells[0], image: "outside.png"}]},
    {base: inputRoot, out: path.join(dir, "escape")}), /inside the input directory/);
  assert(!fs.existsSync(path.join(dir, "escape")));
});
