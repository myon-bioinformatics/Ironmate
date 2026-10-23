"use strict";
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {test} = require("node:test");

const ROOT = path.join(__dirname, "..");

function lockEntry() {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "vendor.lock.json"), "utf8"));
  const entry = lock.files.find((item) => item.destination === "vendor/py_launch.cjs");
  assert.ok(entry, "vendor.lock.json must list vendor/py_launch.cjs");
  return entry;
}

function writeFakePython(dir) {
  const marker = path.join(dir, "marker.txt");
  const fake = path.join(dir, "fake-python");
  fs.writeFileSync(fake, `#!/usr/bin/env python3
import sys
marker = ${JSON.stringify(marker)}
if "-c" in sys.argv:
    i = sys.argv.index("-c")
    if i + 1 < len(sys.argv) and "version_info" in sys.argv[i + 1]:
        print("3.12")
        raise SystemExit(0)
open(marker, "w", encoding="utf-8").write("ran")
raise SystemExit(0)
`, {encoding: "utf8", mode: 0o755});
  return {fake, marker};
}

test("vendored py_launch.cjs matches vendor.lock.json", () => {
  const entry = lockEntry();
  const data = fs.readFileSync(path.join(ROOT, "vendor/py_launch.cjs"));
  assert.equal(crypto.createHash("sha256").update(data).digest("hex"), entry.sha256);
  assert.equal(crypto.createHash("sha1").update(Buffer.concat([
    Buffer.from(`blob ${data.length}\0`), data,
  ])).digest("hex"), entry.blob_sha);
  assert.equal(entry.commit, "173124231fc171c251e35caef1fa67e76d0f8bae");
});

const PYTHON =
  process.env.PY_LAUNCH_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
const BIG_STDOUT = path.join(ROOT, "tests/fixtures/py_launch/big_stdout.py");

test("vendored run rejects input above maxInputBytes with EINPUTTOOLARGE", () => {
  const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  const input = "x".repeat(200);
  assert.throws(
    () => run(BIG_STDOUT, ["1"], {python: PYTHON, input, maxInputBytes: 100}),
    (err) => err.code === "EINPUTTOOLARGE" && /maxInputBytes/.test(err.message),
  );
});

test("vendored run maps responseMaxBytes overflow to ERESPONSETOOLARGE", () => {
  const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  assert.throws(
    () => run(BIG_STDOUT, ["200000"], {python: PYTHON, responseMaxBytes: 1024}),
    (err) => err.code === "ERESPONSETOOLARGE" && /responseMaxBytes/.test(err.message),
  );
});

test("ironmate mapLaunchError relabels EINPUTTOOLARGE for flow export", () => {
  const {mapLaunchError} = require(path.join(ROOT, "ironmate_py_launch.cjs"));
  const err = Object.assign(
    new Error("py_launch: input exceeds maxInputBytes (100; got 200 bytes)"),
    {code: "EINPUTTOOLARGE"},
  );
  assert.throws(
    () => mapLaunchError(err, "flow Python process failed: ", "flow export failed"),
    (mapped) => mapped.code === "EINPUTTOOLARGE" &&
      mapped.message === "flow Python process failed: input exceeds maxInputBytes (100; got 200 bytes)",
  );
});

test("ironmate mapLaunchError relabels ERESPONSETOOLARGE for flow export", () => {
  const {mapLaunchError} = require(path.join(ROOT, "ironmate_py_launch.cjs"));
  const err = Object.assign(
    new Error("py_launch: response exceeds responseMaxBytes (1024)"),
    {code: "ERESPONSETOOLARGE"},
  );
  assert.throws(
    () => mapLaunchError(err, "flow Python process failed: ", "flow export failed", {responseMaxBytes: 1024}),
    (mapped) => mapped.code === "ERESPONSETOOLARGE" &&
      mapped.message === "flow Python process failed: response exceeds responseMaxBytes (1024)",
  );
});

test("wrappers share ironmate_py_launch.cjs", () => {
  for (const name of ["flow_export.cjs", "flow_workspace.cjs", "image_digest.cjs"]) {
    const src = fs.readFileSync(path.join(ROOT, name), "utf8");
    assert.match(src, /require\("\.\/ironmate_py_launch\.cjs"\)/);
    assert.match(src, /require\("\.\/vendor\/py_launch\.cjs"\)/);
  }
});

test("flow_export maps missing interpreter to flow Python process failed", () => {
  const {renderFlow} = require(path.join(ROOT, "flow_export.cjs"));
  assert.throws(
    () => renderFlow({}, {format: "mermaid", python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("flow Python process failed: ") && /ENOENT|spawnSync/.test(err.message),
  );
});

test("image_digest maps missing interpreter to image digest Python process failed", () => {
  const {buildDigest} = require(path.join(ROOT, "image_digest.cjs"));
  assert.throws(
    () => buildDigest({schema: "ironmate-image-digest-input/1", rows: [], cols: [], cells: []},
      {base: ROOT, out: os.tmpdir(), python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("image digest Python process failed: "),
  );
});

test("flow_workspace maps missing interpreter to flow workspace Python process failed", () => {
  const {importFlow} = require(path.join(ROOT, "flow_workspace.cjs"));
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  assert.throws(
    () => importFlow(raw, {python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("flow workspace Python process failed: "),
  );
});

test("flow_export CLI exits 2 when IRONMATE_PYTHON is unusable", () => {
  const result = spawnSync(process.execPath, [path.join(ROOT, "flow_export.cjs"), "--format", "mermaid"],
    {env: {...process.env, IRONMATE_PYTHON: "/missing/ironmate-python"}, input: "{}"});
  assert.equal(result.status, 2);
});

test("IRONMATE_PYTHON is used before system python3 for flow_export", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-fake-py-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const {fake, marker} = writeFakePython(dir);
  const prev = process.env.IRONMATE_PYTHON;
  process.env.IRONMATE_PYTHON = fake;
  t.after(() => {
    if (prev === undefined) delete process.env.IRONMATE_PYTHON;
    else process.env.IRONMATE_PYTHON = prev;
  });
  const {renderFlow} = require(path.join(ROOT, "flow_export.cjs"));
  try {
    renderFlow(JSON.parse(fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8")), {format: "mermaid"});
  } catch {
    // script may fail after interpreter spawn; marker proves which binary ran
  }
  assert.equal(fs.readFileSync(marker, "utf8"), "ran");
});
