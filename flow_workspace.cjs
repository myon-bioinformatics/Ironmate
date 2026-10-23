"use strict";
/** Workspace persistence uses Python; patch semantics belong to locked web-ui. */
const path = require("node:path");
const {main, run} = require("./vendor/py_launch.cjs");
const {mapLaunchError, PY_LAUNCH} = require("./ironmate_py_launch.cjs");
const root = __dirname;
const PY_SCRIPT = path.join(root, "flow_workspace.py");
const MAX_INPUT_BYTES = 4 * 1024 * 1024;
const RESPONSE_MAX_BYTES = 4 * 1024 * 1024;
const ERR_PREFIX = "flow workspace Python process failed: ";
const WORKSPACE_LAUNCH = {...PY_LAUNCH, isolated: true};

function call(name, values, options = {}) {
  const input = Buffer.from(JSON.stringify(values), "utf8");
  try {
    const result = run(PY_SCRIPT, ["__node_bridge__", name], {
      ...WORKSPACE_LAUNCH,
      python: options.python,
      input,
      maxInputBytes: MAX_INPUT_BYTES,
      responseMaxBytes: RESPONSE_MAX_BYTES,
      timeout: 20000,
    });
    return JSON.parse(result.stdout.toString("utf8"));
  } catch (err) {
    mapLaunchError(err, ERR_PREFIX, "flow workspace failed", {responseMaxBytes: RESPONSE_MAX_BYTES});
  }
}

function importFlow(text, options) {
  // JSON text is passed without reserialization to preserve the source exactly.
  if (typeof text !== "string") throw Error("expected UTF-8 source text");
  return call("import_flow", [text], options);
}

function patchWorkspace(workspace, operations, options) {
  return call("patch_workspace", [workspace, operations], options);
}

function renderWorkspace(workspace, options = {}) {
  const state = call("validate_workspace", [workspace], options);
  return require("./flow_export.cjs").renderFlow(state.spec, options);
}

function patchAndRender(workspace, operations, options = {}) {
  const updated = patchWorkspace(workspace, operations, options);
  const image = renderWorkspace(updated, options);
  return {workspace: updated, image};
}

if (require.main === module) {
  main(PY_SCRIPT, WORKSPACE_LAUNCH);
}
module.exports = {importFlow, patchWorkspace, renderWorkspace, patchAndRender};
