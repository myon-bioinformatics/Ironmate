"use strict";
/** Thin Node API. Python owns rendering, locked web-ui owns the JSON contract. */
const path = require("node:path");
const {run, main} = require("./vendor/py_launch.cjs");
const {mapLaunchError, PY_LAUNCH} = require("./ironmate_py_launch.cjs");
const PY_SCRIPT = path.join(__dirname, "flow_export.py");
const MAX_BYTES = 256 * 1024;
const formats = ["mermaid", "svg", "png", "base64", "data-uri"];
const ERR_PREFIX = "flow Python process failed: ";

function renderFlow(spec, options = {}) {
  const {format = "svg", scale = 1, background, mmdc, chrome, puppeteerConfig, python} = options;
  if (!formats.includes(format)) throw Error("unsupported flow output format");
  if (typeof scale !== "number" || !Number.isFinite(scale) || scale < .25 || scale > 8) throw Error("invalid scale");
  const input = Buffer.from(JSON.stringify(spec), "utf8");
  if (input.length > MAX_BYTES) throw Error("flow JSON exceeds 256KiB");
  const args = ["--format", format];
  for (const [key, value] of [["--scale", scale], ["--background", background],
    ["--mmdc", mmdc], ["--chrome", chrome], ["--puppeteer-config", puppeteerConfig]]) {
    if (value !== undefined && value !== null) args.push(key, String(value));
  }
  try {
    return run(PY_SCRIPT, args, {...PY_LAUNCH, python, input, maxBuffer: 48 * 1024 * 1024, timeout: 180000}).stdout;
  } catch (err) {
    mapLaunchError(err, ERR_PREFIX, "flow export failed");
  }
}

if (require.main === module) {
  main(PY_SCRIPT, PY_LAUNCH);
}
module.exports = {renderFlow};
