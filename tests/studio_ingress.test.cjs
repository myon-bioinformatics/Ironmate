"use strict";
const assert = require("node:assert/strict");
const path = require("node:path");
const {test} = require("node:test");
const {run} = require("../vendor/py_launch.cjs");

const ROOT = path.resolve(__dirname, "..");
const PY_SCRIPT = path.join(ROOT, "studio_ingress.py");
const png = Buffer.concat([Buffer.from("89504e470d0a1a0a", "hex"), Buffer.from("payload")]);

function decodeViaPy(text) {
  const res = run(PY_SCRIPT, ["decode", "-"], {
    envVar: "IRONMATE_PYTHON",
    noSite: true,
    input: Buffer.from(text),
  });
  if (res.status !== 0) throw Error(res.stderr || "decode failed");
  return JSON.parse(res.stdout);
}

test("raw and data URI", () => {
  const b64 = png.toString("base64");
  assert.deepEqual(decodeViaPy(b64), {ok: true, mime: "image/png", bytes: png.length});
  assert.deepEqual(decodeViaPy("data:image/png;base64," + b64), {ok: true, mime: "image/png", bytes: png.length});
});
test("MIME mismatch and invalid input", () => {
  const b64 = png.toString("base64");
  assert.throws(() => decodeViaPy("data:image/jpeg;base64," + b64));
});
test("missing padding", () => {
  assert.throws(() => decodeViaPy(Buffer.concat([png, Buffer.from("x")]).toString("base64").replace(/=+$/, "")));
});
