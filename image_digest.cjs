"use strict";
/** Thin Node API for image_digest.py: Python owns decoding, thumbnails and HTML. */
const path = require("node:path");
const {run} = require("./vendor/py_launch.cjs");
const {mapLaunchError, PY_LAUNCH} = require("./ironmate_py_launch.cjs");
const PY_SCRIPT = path.join(__dirname, "image_digest.py");
const MAX_INPUT = 8 * 1024 * 1024;
const ERR_PREFIX = "image digest Python process failed: ";

function buildDigest(spec, options = {}) {
  const {base, out, maxBytes = 1000000, tile = "64x128", python} = options;
  if (typeof base !== "string" || !base) throw Error("base directory is required");
  if (typeof out !== "string" || !out) throw Error("out directory is required");
  if (!Number.isInteger(maxBytes)) throw Error("maxBytes must be an integer");
  if (!/^\d+x\d+$/.test(tile)) throw Error("tile must look like 64x128");
  const input = Buffer.from(JSON.stringify(spec), "utf8");
  if (input.length > MAX_INPUT) throw Error("digest input exceeds 8MiB");
  const args = ["-", "--base", base, "--out", out, "--max-bytes", String(maxBytes), "--tile", tile];
  try {
    const result = run(PY_SCRIPT, args, {...PY_LAUNCH, python, input, maxBuffer: 4 * 1024 * 1024, timeout: 600000});
    return JSON.parse(String(result.stdout));
  } catch (err) {
    mapLaunchError(err, ERR_PREFIX, "image digest failed");
  }
}

module.exports = {buildDigest};

if (require.main === module) {
  const [input, out, base] = process.argv.slice(2);
  try {
    const fs = require("node:fs");
    if (!input || !out) throw Error("usage: image_digest.cjs INPUT.json OUT_DIR [BASE_DIR]");
    const spec = JSON.parse(fs.readFileSync(input, "utf8"));
    process.stdout.write(JSON.stringify(buildDigest(spec, {base: base || path.dirname(input), out})) + "\n");
  } catch (error) {
    process.stderr.write(`image digest: ${error.message}\n`);
    process.exitCode = 2;
  }
}
