"use strict";
// Every top-level *.cjs module ships a .d.cts whose exported names match the runtime exports.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const root = path.join(__dirname, "..");
for (const file of fs.readdirSync(root).filter((f) => f.endsWith(".cjs")).sort()) {
  test(`${file} has matching .d.cts`, () => {
    const types = path.join(root, file.replace(/\.cjs$/, ".d.cts"));
    assert.ok(fs.existsSync(types), `missing ${path.basename(types)}`);
    const declared = [...fs.readFileSync(types, "utf8").matchAll(/^export (?:function|const) ([A-Za-z_$][\w$]*)/gm)]
      .map((m) => m[1]);
    assert.deepEqual([...new Set(declared)].sort(), Object.keys(require(path.join(root, file))).sort());
  });
}
