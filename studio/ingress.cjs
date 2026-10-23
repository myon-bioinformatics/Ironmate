"use strict";
// Pure Node entry point; acquisition and user permissions stay in browser/OS adapters.
const MAX_BYTES = 32 * 1024 * 1024;
function sniff(bytes) {
  if (bytes.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex"))) return "image/png";
  if (bytes.subarray(0, 3).equals(Buffer.from("ffd8ff", "hex"))) return "image/jpeg";
  if (bytes.length >= 12 && bytes.toString("ascii", 0, 4) === "RIFF" &&
      bytes.toString("ascii", 8, 12) === "WEBP") return "image/webp";
  return null;
}
function decode(text, maxBytes = MAX_BYTES) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) throw Error("invalid limit");
  let value = String(text).replace(/^\uFEFF/, "").trim(), declared = null;
  const header = /^data:([a-z0-9.+-]+\/[a-z0-9.+-]+)?(?:;[a-z0-9.+-]+=[a-z0-9.+-]+)*;base64,/i.exec(value);
  if (header) {
    declared = header[1]?.toLowerCase() || null;
    if (declared === "image/jpg") declared = "image/jpeg";
    value = value.slice(header[0].length);
  } else if (/^data:/i.test(value)) throw Error("invalid data URI");
  if (declared && !["image/png", "image/jpeg", "image/webp"].includes(declared)) throw Error("unsupported MIME");
  const encoded = value.replace(/\s+/g, "");
  if (!encoded || encoded.length > 4 * Math.ceil(maxBytes / 3) ||
      encoded.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(encoded)) throw Error("invalid or oversized Base64");
  const bytes = Buffer.from(encoded, "base64");
  if (!bytes.length || bytes.length > maxBytes || bytes.toString("base64") !== encoded) throw Error("invalid image size or padding");
  const actual = sniff(bytes);
  if (!actual || (declared && declared !== actual)) throw Error("unsupported image or MIME mismatch");
  return {mimeType: actual, bytes};
}
module.exports = {MAX_BYTES, sniff, decode};

const INGRESS_HELP = `studio/ingress.cjs — validate clipboard image text

usage:
  node studio/ingress.cjs decode FILE
  node studio/ingress.cjs decode -

Success prints {"ok":true,"mime":"...","bytes":N} and does not write the
image bytes. A fixable problem exits 2. --json writes that problem as one
JSON object on stderr. A terminal with no pipe exits 2 instead of waiting.
`;

if (require.main === module) {
  const fs = require("node:fs");
  const {fail, wantsJson} = require("../ironmate_cli.cjs");
  const argv = process.argv.slice(2);
  const jsonMode = wantsJson(argv);
  const args = argv.filter((token) => token !== "--json");
  if (args.includes("--help") || args.includes("-h")) {
    process.stdout.write(INGRESS_HELP);
  } else if (args[0] !== "decode" || args.length !== 2) {
    fail("studio/ingress.cjs", "usage: studio/ingress.cjs decode FILE", "rerun with --help", jsonMode);
  } else if (args[1] === "-" && process.stdin.isTTY) {
    fail("studio/ingress.cjs", "stdin is a terminal", "pass a file or pipe text", jsonMode);
  } else {
    try {
      const raw = args[1] === "-" ? fs.readFileSync(0, "utf8") : fs.readFileSync(args[1], "utf8");
      const decoded = decode(raw);
      process.stdout.write(JSON.stringify({ok: true, mime: decoded.mimeType, bytes: decoded.bytes.length}) + "\n");
    } catch (error) {
      fail("studio/ingress.cjs", error.message, "rerun with --help", jsonMode);
    }
  }
}
