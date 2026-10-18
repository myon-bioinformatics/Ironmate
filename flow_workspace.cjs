"use strict";
/** Workspace persistence uses Python; patch semantics belong to locked web-ui. */
const {spawnSync, spawn} = require("node:child_process");
const path = require("node:path");
const root = __dirname;
function call(name, values, options = {}) {
  const input = Buffer.from(JSON.stringify(values), "utf8");
  if (input.length > 4 * 1024 * 1024) throw Error("workspace request exceeds 4MiB");
  const code = "import sys,json;sys.path.insert(0,sys.argv[1]);import flow_workspace as f;" +
    "v=json.load(sys.stdin);v=[v[0].encode(\"utf-8\")] if sys.argv[2]==\"import_flow\" else v;" +
    "result=getattr(f,sys.argv[2])(*v);" +
    "sys.stdout.buffer.write(f._json_bytes(result))";
  const result = spawnSync(options.python || process.env.IRONMATE_PYTHON || "python3",
    ["-I", "-S", "-c", code, root, name], {input, timeout: 20000, maxBuffer: 4 * 1024 * 1024});
  if (result.error) throw Error("flow workspace process failed: " + result.error.message);
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
  const child = spawn(process.env.IRONMATE_PYTHON || "python3",
    ["-S", path.join(root, "flow_workspace.py"), ...process.argv.slice(2)], {stdio: "inherit"});
  child.on("error", error => {process.stderr.write(error.message + "\n"); process.exitCode = 2;});
  child.on("exit", code => {process.exitCode = code === null ? 2 : code;});
}
module.exports = {importFlow, patchWorkspace, renderWorkspace, patchAndRender};
