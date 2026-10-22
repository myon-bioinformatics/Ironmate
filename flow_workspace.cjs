"use strict";
/** Workspace persistence uses Python; patch semantics belong to locked web-ui. */
const {spawnSync} = require("node:child_process");
const path = require("node:path");
const {main, resolvePython} = require("./vendor/py_launch.cjs");
const {mapLaunchError, PY_LAUNCH} = require("./ironmate_py_launch.cjs");
const root = __dirname;
const PY_SCRIPT = path.join(root, "flow_workspace.py");
const ERR_PREFIX = "flow workspace Python process failed: ";

function call(name, values, options = {}) {
  const input = Buffer.from(JSON.stringify(values), "utf8");
  if (input.length > 4 * 1024 * 1024) throw Error("workspace request exceeds 4MiB");
  const code = "import sys,json;sys.path.insert(0,sys.argv[1]);import flow_workspace as f;" +
    "v=json.load(sys.stdin);v=[v[0].encode(\"utf-8\")] if sys.argv[2]==\"import_flow\" else v;" +
    "result=getattr(f,sys.argv[2])(*v);" +
    "sys.stdout.buffer.write(f._json_bytes(result))";
  let resolved;
  try {
    resolved = resolvePython({...PY_LAUNCH, python: options.python});
  } catch (err) {
    mapLaunchError(err, ERR_PREFIX, "flow workspace failed");
  }
  const result = spawnSync(resolved.cmd, [...resolved.prefix, "-I", "-S", "-c", code, root, name],
    {input, timeout: 20000, maxBuffer: 4 * 1024 * 1024});
  if (result.error) throw Error(ERR_PREFIX + result.error.message);
  if (result.status !== 0) throw Error(result.stderr.toString("utf8").trim() || "flow workspace failed");
  return JSON.parse(result.stdout.toString("utf8"));
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
  main(PY_SCRIPT, PY_LAUNCH);
}
module.exports = {importFlow, patchWorkspace, renderWorkspace, patchAndRender};
