"use strict";
/** Thin Node API. Python owns rendering, locked web-ui owns the JSON contract. */
const {spawnSync} = require("node:child_process");
const path = require("node:path");
const MAX_BYTES = 256 * 1024;
const formats = ["mermaid", "svg", "png", "base64", "data-uri"];
function renderFlow(spec, options = {}) {
  const {format = "svg", scale = 1, background, mmdc, chrome, puppeteerConfig,
    python = process.env.IRONMATE_PYTHON || "python3"} = options;
  if (!formats.includes(format)) throw Error("unsupported flow output format");
  if (typeof scale !== "number" || !Number.isFinite(scale) || scale < .25 || scale > 8) throw Error("invalid scale");
  const input = Buffer.from(JSON.stringify(spec), "utf8");
  if (input.length > MAX_BYTES) throw Error("flow JSON exceeds 256KiB");
  const args = ["-S", path.join(__dirname, "flow_export.py"), "--format", format];
  for (const [key, value] of [["--scale", scale], ["--background", background],
    ["--mmdc", mmdc], ["--chrome", chrome], ["--puppeteer-config", puppeteerConfig]]) {
    if (value !== undefined && value !== null) args.push(key, String(value));
  }
  const result = spawnSync(python, args, {input, maxBuffer: 48 * 1024 * 1024, timeout: 180000});
  if (result.error) throw Error("flow Python process failed: " + result.error.message);
  if (result.status !== 0) throw Error(result.stderr.toString("utf8").trim() || "flow export failed");
  return result.stdout; // Always Buffer, including UTF-8 text formats.
}
if (require.main === module) {
  // Pass CLI arguments through unchanged; stream stdin/stdout instead of buffering.
  const {spawn} = require("node:child_process");
  const child = spawn(process.env.IRONMATE_PYTHON || "python3",
    ["-S", path.join(__dirname, "flow_export.py"), ...process.argv.slice(2)], {stdio: "inherit"});
  child.on("error", err => {process.stderr.write("flow: " + err.message + "\n"); process.exitCode = 2;});
  child.on("exit", code => {process.exitCode = code === null ? 2 : code;});
}
module.exports = {renderFlow};
