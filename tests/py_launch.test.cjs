"use strict";
// Ironmate's Python tools called from Node through the shared vendor/py_launch.cjs (no per-tool .cjs wrappers).
// The launcher's own behaviour is tested once in the parent repository (tests/py_launch.test.cjs there).
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {test} = require("node:test");

const ROOT = path.join(__dirname, "..");
const LAUNCHER = path.join(ROOT, "vendor/py_launch.cjs");
const {call, run, resolvePython} = require(LAUNCHER);
const PY = {envVar: "IRONMATE_PYTHON", noSite: true};
const WORKSPACE = {...PY, isolated: true};
const FLOW = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
const PYTHON = process.env.IRONMATE_PYTHON || process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

function withEnv(t, values) {
  const previous = Object.fromEntries(Object.keys(values).map((key) => [key, process.env[key]]));
  Object.assign(process.env, values);
  t.after(() => {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  });
}

function writeFakePython(dir) {
  const marker = path.join(dir, "marker.txt");
  const fake = path.join(dir, "fake-python");
  fs.writeFileSync(fake, `#!/usr/bin/env python3
import sys
marker = ${JSON.stringify(marker)}
if "-c" in sys.argv:
    i = sys.argv.index("-c")
    if i + 1 < len(sys.argv) and "version_info" in sys.argv[i + 1]:
        print("3.12")
        raise SystemExit(0)
open(marker, "w", encoding="utf-8").write("ran")
raise SystemExit(0)
`, {encoding: "utf8", mode: 0o755});
  return {fake, marker};
}

test("vendored py_launch.cjs matches vendor.lock.json", () => {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "vendor.lock.json"), "utf8"));
  const entry = lock.files.find((item) => item.destination === "vendor/py_launch.cjs");
  assert.ok(entry, "vendor.lock.json must list vendor/py_launch.cjs");
  const digest = crypto.createHash("sha256").update(fs.readFileSync(LAUNCHER)).digest("hex");
  assert.equal(digest, entry.sha256);
});

test("no per-tool Node wrapper is left at the repository root", () => {
  const wrappers = fs.readdirSync(ROOT).filter((name) => /\.(cjs|d\.cts)$/.test(name));
  assert.deepEqual(wrappers, []);
});

test("flow_export.py runs from the launcher CLI with stdin, like the Python CLI", () => {
  const viaNode = spawnSync(process.execPath, [LAUNCHER, "--env-var", "IRONMATE_PYTHON", "--", path.join(ROOT, "flow_export.py"),
    "--format", "mermaid"], {input: FLOW, encoding: "utf8"});
  assert.equal(viaNode.status, 0, viaNode.stderr);
  const viaPython = spawnSync(PYTHON, ["-S", path.join(ROOT, "flow_export.py"), "--format", "mermaid"], {input: FLOW, encoding: "utf8"});
  assert.equal(viaPython.status, 0, viaPython.stderr);
  assert.equal(viaNode.stdout, viaPython.stdout);
});

test("IRONMATE_PYTHON is used before system python3", (t) => {
  if (process.platform === "win32") {
    t.skip("extensionless shebang fake interpreters are not executable as IRONMATE_PYTHON on Windows");
    return;
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-fake-py-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const {fake, marker} = writeFakePython(dir);
  withEnv(t, {IRONMATE_PYTHON: fake});
  try {
    run(path.join(ROOT, "flow_export.py"), ["--format", "mermaid"], {...PY, input: FLOW});
  } catch {
    // the fake interpreter exits without output; the marker proves which binary ran
  }
  assert.equal(fs.readFileSync(marker, "utf8"), "ran");
});

test("IRONMATE_PYTHON on Windows resolves to a real python.exe without .cmd shims", (t) => {
  if (process.platform !== "win32") {
    t.skip("Windows-only IRONMATE_PYTHON executable path coverage");
    return;
  }
  const found = spawnSync(PYTHON, ["-c", "import sys; print(sys.executable)"], {encoding: "utf8"});
  assert.equal(found.status, 0, found.stderr || found.stdout);
  const real = found.stdout.trim();
  assert.ok(real.toLowerCase().endsWith(".exe") && !/\.(cmd|bat)$/i.test(real));
  withEnv(t, {IRONMATE_PYTHON: real});
  assert.equal(path.resolve(resolvePython(PY).cmd), path.resolve(real));
});

test("flow_workspace functions are called by name and keep non-ASCII labels", () => {
  const script = path.join(ROOT, "flow_workspace.py");
  const workspace = call(script, "import_flow", [FLOW], WORKSPACE);
  assert.equal(workspace.schema, "ironmate-flow/1");
  assert.ok(workspace.spec && typeof workspace.spec === "object");
  assert.deepEqual(call(script, "patch_workspace", [workspace, []], WORKSPACE).spec, workspace.spec);
  const value = "日本語ラベル & é 🌱 <text>";
  const patched = call(script, "patch_workspace", [workspace, [{path: "/steps/0/title", value}]], WORKSPACE);
  assert.equal(patched.spec.steps[0].title, value);
  const state = call(script, "validate_workspace", [patched], WORKSPACE);
  const image = run(path.join(ROOT, "flow_export.py"), ["--format", "mermaid"], {...PY, input: JSON.stringify(state.spec)});
  assert.match(image.stdout.toString("utf8"), /日本語ラベル/);
});

test("isolated calls ignore PYTHONPATH shadowing of stdlib xml", (t) => {
  const shadowDir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-xml-shadow-"));
  t.after(() => fs.rmSync(shadowDir, {recursive: true, force: true}));
  fs.writeFileSync(path.join(shadowDir, "xml.py"), "raise RuntimeError('PYTHONPATH shadowed stdlib xml')\n");
  withEnv(t, {PYTHONPATH: shadowDir});
  assert.equal(call(path.join(ROOT, "flow_workspace.py"), "import_flow", [FLOW], WORKSPACE).schema, "ironmate-flow/1");
});

test("a missing IRONMATE_PYTHON fails the call instead of falling back", (t) => {
  withEnv(t, {IRONMATE_PYTHON: path.join(os.tmpdir(), "missing", "ironmate-python")});
  assert.throws(() => call(path.join(ROOT, "flow_workspace.py"), "import_flow", [FLOW], WORKSPACE));
});
