"use strict";
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const {test} = require("node:test");

const ROOT = path.join(__dirname, "..");

function lockEntry() {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "vendor.lock.json"), "utf8"));
  const entry = lock.files.find((item) => item.destination === "vendor/py_launch.cjs");
  assert.ok(entry, "vendor.lock.json must list vendor/py_launch.cjs");
  return entry;
}

test("vendored py_launch.cjs matches vendor.lock.json", () => {
  const entry = lockEntry();
  const data = fs.readFileSync(path.join(ROOT, "vendor/py_launch.cjs"));
  assert.equal(crypto.createHash("sha256").update(data).digest("hex"), entry.sha256);
  assert.equal(crypto.createHash("sha1").update(Buffer.concat([
    Buffer.from(`blob ${data.length}\0`), data,
  ])).digest("hex"), entry.blob_sha);
  assert.equal(entry.commit, "2ea31034ca3caa60ed769806baf750d75e296552");
});

test("flow_export.cjs delegates Python launch to vendor/py_launch.cjs", () => {
  const src = fs.readFileSync(path.join(ROOT, "flow_export.cjs"), "utf8");
  assert.match(src, /require\("\.\/vendor\/py_launch\.cjs"\)/);
  assert.match(src, /\brun\(/);
  assert.match(src, /\bmain\(/);
  assert.doesNotMatch(src, /require\("node:child_process"\)/);
});

test("image_digest.cjs delegates Python launch to vendor/py_launch.cjs", () => {
  const src = fs.readFileSync(path.join(ROOT, "image_digest.cjs"), "utf8");
  assert.match(src, /require\("\.\/vendor\/py_launch\.cjs"\)/);
  assert.match(src, /\brun\(/);
  assert.doesNotMatch(src, /require\("node:child_process"\)/);
});

test("flow_workspace.cjs delegates interpreter resolution to vendor/py_launch.cjs", () => {
  const src = fs.readFileSync(path.join(ROOT, "flow_workspace.cjs"), "utf8");
  assert.match(src, /require\("\.\/vendor\/py_launch\.cjs"\)/);
  assert.match(src, /\bresolvePython\(/);
  assert.match(src, /\bmain\(/);
  assert.doesNotMatch(src, /spawnSync\([^)]*process\.env\.IRONMATE_PYTHON/);
});
