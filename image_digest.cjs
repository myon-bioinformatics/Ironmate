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

const HELP = `image_digest.cjs — one HTML page from a grid of images

usage:
  node image_digest.cjs INPUT.json --out DIR [--base DIR] [--max-bytes N] [--tile WxH] [--json]
  node image_digest.cjs INPUT.json DIR

--out, -o and --output are the same flag. INPUT.json may be - for stdin
(then --base is required). Success prints the digest.json fields as one JSON
object and exits 0. A fixable problem exits 2. --json writes that problem as
one JSON object on stderr and does not change the success payload.
`;

function parseDigestArgs(argv) {
  const opts = {json: false, help: false, positionals: [], out: undefined, base: undefined,
    maxBytes: 1000000, tile: "64x128"};
  const needsValue = new Set(["--out", "-o", "--output", "--base", "--max-bytes", "--tile"]);
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      opts.help = true;
      continue;
    }
    if (token === "--json") {
      opts.json = true;
      continue;
    }
    if (needsValue.has(token)) {
      const value = argv[++i];
      if (value === undefined) {
        const error = new Error(token + " needs a value");
        error.hint = "rerun with --help";
        throw error;
      }
      if (token === "--out" || token === "-o" || token === "--output") opts.out = value;
      else if (token === "--base") opts.base = value;
      else if (token === "--tile") opts.tile = value;
      else {
        if (!/^-?\d+$/.test(value)) {
          const error = new Error("--max-bytes must be an integer");
          error.hint = "example: --max-bytes 1000000";
          throw error;
        }
        opts.maxBytes = Number(value);
      }
      continue;
    }
    if (token.startsWith("-") && token !== "-") {
      const error = new Error("unknown flag " + token);
      error.hint = "rerun with --help";
      throw error;
    }
    opts.positionals.push(token);
  }
  return opts;
}

if (require.main === module) {
  const {fail, wantsJson} = require("./ironmate_cli.cjs");
  const fs = require("node:fs");
  let opts;
  try {
    opts = parseDigestArgs(process.argv.slice(2));
  } catch (error) {
    fail("image_digest.cjs", error.message, error.hint, wantsJson(process.argv.slice(2)));
  }
  if (opts.help) {
    process.stdout.write(HELP);
  } else {
    const input = opts.positionals[0];
    const positionalOut = opts.positionals[1];
    if (opts.positionals.length > 2) {
      fail("image_digest.cjs", "too many positional arguments", "rerun with --help", opts.json);
    }
    if (opts.out && positionalOut) {
      fail("image_digest.cjs", "pass the output directory once", "use --out or a positional directory, not both", opts.json);
    }
    const out = opts.out || positionalOut;
    if (!input || !out) {
      fail("image_digest.cjs", "INPUT.json and an output directory are required", "rerun with --help", opts.json);
    }
    if (input === "-" && !opts.base) {
      fail("image_digest.cjs", "--base is required when INPUT.json is -", "example: --base .", opts.json);
    }
    if (input === "-" && process.stdin.isTTY) {
      fail("image_digest.cjs", "stdin is a terminal", "pass a file or pipe JSON", opts.json);
    }
    try {
      const raw = input === "-" ? fs.readFileSync(0, "utf8") : fs.readFileSync(input, "utf8");
      let spec;
      try {
        spec = JSON.parse(raw);
      } catch (error) {
        fail("image_digest.cjs", "INPUT.json must be one JSON value: " + error.message, "check the file and retry", opts.json);
      }
      const info = buildDigest(spec, {base: opts.base || path.dirname(input), out, maxBytes: opts.maxBytes, tile: opts.tile});
      process.stdout.write(JSON.stringify(info) + "\n");
    } catch (error) {
      fail("image_digest.cjs", error.message, "rerun with --help", opts.json);
    }
  }
}
