"use strict";
/** Thin Node API. Python owns rendering, locked web-ui owns the JSON contract. */
const path = require("node:path");
const {run, main} = require("./vendor/py_launch.cjs");
const PY_SCRIPT = path.join(__dirname, "flow_export.py");
const PY_LAUNCH = {envVar: "IRONMATE_PYTHON", noSite: true};
const MAX_BYTES = 256 * 1024;
const formats = ["mermaid", "svg", "png", "base64", "data-uri"];

function mapLaunchError(err, spawnPrefix, failureFallback) {
  const msg = String(err.message || err);
  if (msg.startsWith("py_launch: Python process failed: ")) {
    throw Error(spawnPrefix + msg.slice("py_launch: Python process failed: ".length));
  }
  const spawn = msg.match(/^py_launch: ([^:]+): (spawnSync .+)$/);
  if (spawn) throw Error(spawnPrefix + spawn[2]);
  if (Object.hasOwn(err, "status") && err.status !== 0) {
    throw Error((err.stderr && err.stderr.toString("utf8").trim()) || failureFallback);
  }
  throw err;
}

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
    mapLaunchError(err, "flow Python process failed: ", "flow export failed");
  }
}

if (require.main === module) {
  main(PY_SCRIPT, PY_LAUNCH);
}
module.exports = {renderFlow};
