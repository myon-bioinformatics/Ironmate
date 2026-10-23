"use strict";
/** Shared stderr contract for Ironmate Node CLIs. Exit 2 is fixable. */

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

module.exports = {fail, wantsJson};
