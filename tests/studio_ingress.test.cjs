"use strict";
// 📋 Clipboard ingress from Node: studio_ingress.py through vendor/py_launch.cjs, no Node copy of the decoder.
const assert = require("node:assert/strict");
const path = require("node:path");
const {test} = require("node:test");
const {run} = require("../vendor/py_launch.cjs");
const SCRIPT = path.join(__dirname, "..", "studio_ingress.py");
const png = Buffer.concat([Buffer.from("89504e470d0a1a0a", "hex"), Buffer.from("payload")]);

function decode(text) {
  let res;
  try {
    res = run(SCRIPT, ["--json", "decode", "-"], {envVar: "IRONMATE_PYTHON", noSite: true, input: Buffer.from(text)});
  } catch (error) {
    if (error.status !== 2) throw error;
    return {status: 2, body: JSON.parse(error.stderr.toString())};
  }
  return {status: res.status, body: JSON.parse(res.stdout.toString())};
}

test("raw and data URI", () => {
  const b64 = png.toString("base64");
  for (const text of [b64, "data:image/png;base64," + b64]) {
    assert.deepEqual(decode(text), {status: 0, body: {ok: true, mime: "image/png", bytes: png.length}});
  }
});
test("MIME mismatch and missing padding exit 2", () => {
  const b64 = png.toString("base64");
  for (const text of ["data:image/jpeg;base64," + b64, Buffer.concat([png, Buffer.from("x")]).toString("base64").replace(/=+$/, "")]) {
    const {status, body} = decode(text);
    assert.equal(status, 2);
    assert.equal(body.ok, false);
  }
});
