"use strict";
const assert = require("node:assert/strict");
const {test} = require("node:test");
const {decode} = require("../studio/ingress.cjs");
const png = Buffer.concat([Buffer.from("89504e470d0a1a0a", "hex"), Buffer.from("payload")]);
test("raw and data URI", () => {
  const b64 = png.toString("base64");
  assert.deepEqual(decode(b64).bytes, png);
  assert.deepEqual(decode("data:image/png;base64," + b64).bytes, png);
});
test("MIME mismatch and limit", () => {
  const b64 = png.toString("base64");
  assert.throws(() => decode("data:image/jpeg;base64," + b64));
  assert.throws(() => decode(b64, png.length - 1));
});
test("missing padding", () => {
  assert.throws(() => decode(png.toString("base64").replace(/=+$/, "")));
});
