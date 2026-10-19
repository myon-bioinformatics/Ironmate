"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {buildDigest} = require("../image_digest.cjs");

test("Node builds the same one-page digest through the Python owner", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "digest-"));
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
});
