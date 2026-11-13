"use strict";
/** Shared stderr contract for Ironmate Node CLIs (exit 2 is fixable), and their settings for vendored py_launch.cjs. */

const {mapLaunchError} = require("./vendor/py_launch.cjs");

/** How the Node wrappers start Python: IRONMATE_PYTHON picks the interpreter, -S keeps site off. */
const PY_LAUNCH = {envVar: "IRONMATE_PYTHON", noSite: true};

function fail(tool, message, hint, jsonMode) {
  const text = String(message || "failed").trim() || "failed";
  if (jsonMode) {
    const payload = {ok: false, tool, error: text, exit: 2};
    if (hint) payload.hint = hint;
    process.stderr.write(JSON.stringify(payload) + "\n");
  } else {
    process.stderr.write(tool + ": " + text + "\n");
    if (hint) process.stderr.write("hint: " + hint + "\n");
  }
  process.exit(2);
}

function wantsJson(argv) {
  return argv.includes("--json");
}

module.exports = {fail, wantsJson, mapLaunchError, PY_LAUNCH};
