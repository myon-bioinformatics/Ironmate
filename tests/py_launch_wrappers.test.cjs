"use strict";
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {spawnSync} = require("node:child_process");
const {test} = require("node:test");

const ROOT = path.join(__dirname, "..");

function lockEntry() {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "vendor.lock.json"), "utf8"));
  const entry = lock.files.find((item) => item.destination === "vendor/py_launch.cjs");
  assert.ok(entry, "vendor.lock.json must list vendor/py_launch.cjs");
  return entry;
}

function resolveRealPython() {
  const result = spawnSync(PYTHON, ["-c", "import sys; print(sys.executable)"], {encoding: "utf8"});
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout.trim();
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
  const entry = lockEntry();
  const data = fs.readFileSync(path.join(ROOT, "vendor/py_launch.cjs"));
  assert.equal(crypto.createHash("sha256").update(data).digest("hex"), entry.sha256);
  assert.equal(crypto.createHash("sha1").update(Buffer.concat([
    Buffer.from(`blob ${data.length}\0`), data,
  ])).digest("hex"), entry.blob_sha);
  assert.equal(entry.commit, "384f5dd532076062f7833038764e9a62322c387c");
});

const PYTHON =
  process.env.PY_LAUNCH_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3");
const BIG_STDOUT = path.join(ROOT, "tests/fixtures/py_launch/big_stdout.py");

test("vendored run rejects input above maxInputBytes with EINPUTTOOLARGE", () => {
  const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  const input = "x".repeat(200);
  assert.throws(
    () => run(BIG_STDOUT, ["1"], {python: PYTHON, input, maxInputBytes: 100}),
    (err) => err.code === "EINPUTTOOLARGE" && /maxInputBytes/.test(err.message),
  );
});

test("vendored run maps responseMaxBytes overflow to ERESPONSETOOLARGE", () => {
  const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  assert.throws(
    () => run(BIG_STDOUT, ["200000"], {python: PYTHON, responseMaxBytes: 1024}),
    (err) => err.code === "ERESPONSETOOLARGE" && /responseMaxBytes/.test(err.message),
  );
});

test("ironmate mapLaunchError relabels EINPUTTOOLARGE for flow export", () => {
  const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  const err = Object.assign(
    new Error("py_launch: input exceeds maxInputBytes (100; got 200 bytes)"),
    {code: "EINPUTTOOLARGE"},
  );
  assert.throws(
    () => mapLaunchError(err, "flow Python process failed: ", "flow export failed"),
    (mapped) => mapped.code === "EINPUTTOOLARGE" &&
      mapped.message === "flow Python process failed: input exceeds maxInputBytes (100; got 200 bytes)",
  );
});

test("ironmate mapLaunchError relabels ERESPONSETOOLARGE for flow export", () => {
  const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  const err = Object.assign(
    new Error("py_launch: response exceeds responseMaxBytes (1024)"),
    {code: "ERESPONSETOOLARGE"},
  );
  assert.throws(
    () => mapLaunchError(err, "flow Python process failed: ", "flow export failed", {responseMaxBytes: 1024}),
    (mapped) => mapped.code === "ERESPONSETOOLARGE" &&
      mapped.message === "flow Python process failed: response exceeds responseMaxBytes (1024)",
  );
});

const PY_LAUNCH = {envVar: "IRONMATE_PYTHON", noSite: true};

function renderFlow(spec, options = {}) {
  const {format = "svg", scale = 1, background, mmdc, chrome, puppeteerConfig, python} = options;
  const input = Buffer.from(JSON.stringify(spec), "utf8");
  const args = ["--format", format];
  for (const [key, value] of [["--scale", scale], ["--background", background],
    ["--mmdc", mmdc], ["--chrome", chrome], ["--puppeteer-config", puppeteerConfig]]) {
    if (value !== undefined && value !== null) args.push(key, String(value));
  }
  try {
    const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    return run(path.join(ROOT, "flow_export.py"), args, {
      ...PY_LAUNCH,
      python,
      input,
      timeout: 180000,
    }).stdout;
  } catch (error) {
    const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    throw mapLaunchError("flow Python process failed: ", error);
  }
}

function importFlow(raw, options = {}) {
  const input = Buffer.from(typeof raw === "string" ? raw : JSON.stringify(raw), "utf8");
  try {
    const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    const res = run(path.join(ROOT, "flow_workspace.py"), ["import", "-"], {
      ...PY_LAUNCH,
      python: options.python,
      input,
      maxInputBytes: 256 * 1024,
      timeout: 30000,
    });
    return JSON.parse(res.stdout);
  } catch (error) {
    const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    throw mapLaunchError("flow workspace Python process failed: ", error);
  }
}

function patchWorkspace(workspace, operations, options = {}) {
  const input = Buffer.from(JSON.stringify({workspace, patch: operations}), "utf8");
  try {
    const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    const res = run(path.join(ROOT, "flow_workspace.py"), ["patch", "-"], {
      ...PY_LAUNCH,
      python: options.python,
      input,
      timeout: 30000,
    });
    return JSON.parse(res.stdout);
  } catch (error) {
    const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    throw mapLaunchError("flow workspace Python process failed: ", error);
  }
}

function buildDigest(spec, options = {}) {
  const {base, out, tile, python} = options;
  if (!out) throw Error("out directory required");
  const args = ["-", "--out", out];
  if (base) args.push("--base", base);
  if (tile) args.push("--tile", Array.isArray(tile) ? tile.join("x") : String(tile));
  const input = Buffer.from(JSON.stringify(spec), "utf8");
  try {
    const {run} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    const res = run(path.join(ROOT, "image_digest.py"), args, {
      ...PY_LAUNCH,
      python,
      input,
      timeout: 30000,
    });
    return JSON.parse(res.stdout);
  } catch (error) {
    const {mapLaunchError} = require(path.join(ROOT, "vendor/py_launch.cjs"));
    throw mapLaunchError("image digest Python process failed: ", error);
  }
}

test("per-tool wrappers are dropped in favor of direct vendor/py_launch.cjs", () => {
  for (const name of [
    "flow_export.cjs", "flow_export.d.cts",
    "flow_workspace.cjs", "flow_workspace.d.cts",
    "image_digest.cjs", "image_digest.d.cts",
    "ironmate_cli.cjs", "ironmate_cli.d.cts",
    "studio/ingress.cjs", "studio/ingress.d.cts",
  ]) {
    assert.ok(!fs.existsSync(path.join(ROOT, name)), `${name} should not exist`);
  }
});

test("flow_export maps missing interpreter to flow Python process failed", () => {
  assert.throws(
    () => renderFlow({}, {format: "mermaid", python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("flow Python process failed: ") && /ENOENT|spawnSync/.test(err.message),
  );
});

test("image_digest maps missing interpreter to image digest Python process failed", () => {
  assert.throws(
    () => buildDigest({schema: "ironmate-image-digest-input/1", rows: [], cols: [], cells: []},
      {base: ROOT, out: os.tmpdir(), python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("image digest Python process failed: "),
  );
});

test("flow_workspace maps missing interpreter to flow workspace Python process failed", () => {
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  assert.throws(
    () => importFlow(raw, {python: "/missing/ironmate-python"}),
    (err) => err.message.startsWith("flow workspace Python process failed: "),
  );
});

test("direct py_launch exits 2 when IRONMATE_PYTHON is unusable", () => {
  const result = spawnSync(process.execPath, [path.join(ROOT, "vendor/py_launch.cjs"), "--env-var", "IRONMATE_PYTHON", "--", path.join(ROOT, "flow_export.py"), "--format", "mermaid"],
    {env: {...process.env, IRONMATE_PYTHON: "/missing/ironmate-python"}, input: "{}"});
  assert.equal(result.status, 2);
});

test("IRONMATE_PYTHON is used before system python3 for flow_export", (t) => {
  if (process.platform === "win32") {
    t.skip("extensionless shebang fake interpreters are not executable as IRONMATE_PYTHON on Windows");
    return;
  }
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-fake-py-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const {fake, marker} = writeFakePython(dir);
  const prev = process.env.IRONMATE_PYTHON;
  process.env.IRONMATE_PYTHON = fake;
  t.after(() => {
    if (prev === undefined) delete process.env.IRONMATE_PYTHON;
    else process.env.IRONMATE_PYTHON = prev;
  });
  try {
    renderFlow(JSON.parse(fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8")), {format: "mermaid"});
  } catch {
    // script may fail after interpreter spawn; marker proves which binary ran
  }
  assert.equal(fs.readFileSync(marker, "utf8"), "ran");
});

test("IRONMATE_PYTHON on Windows resolves to a real python.exe without .cmd shims", (t) => {
  if (process.platform !== "win32") {
    t.skip("Windows-only IRONMATE_PYTHON executable path coverage");
    return;
  }
  const real = resolveRealPython();
  assert.ok(fs.existsSync(real));
  assert.ok(real.toLowerCase().endsWith(".exe"));
  assert.ok(!/\.(cmd|bat)$/i.test(real));
  const {resolvePython} = require(path.join(ROOT, "vendor/py_launch.cjs"));
  const prev = process.env.IRONMATE_PYTHON;
  process.env.IRONMATE_PYTHON = real;
  t.after(() => {
    if (prev === undefined) delete process.env.IRONMATE_PYTHON;
    else process.env.IRONMATE_PYTHON = prev;
  });
  const resolved = resolvePython(PY_LAUNCH);
  assert.equal(path.resolve(resolved.cmd), path.resolve(real));
});

test("flow_workspace rejects oversize stdin with EINPUTTOOLARGE", () => {
  const chunk = "x".repeat(4 * 1024 * 1024);
  assert.throws(
    () => importFlow(chunk),
    (err) => err.code === "EINPUTTOOLARGE" &&
      err.message.startsWith("flow workspace Python process failed: ") &&
      /maxInputBytes/.test(err.message),
  );
});

test("flow_workspace ignores PYTHONPATH shadowing of stdlib xml under isolated mode", (t) => {
  const shadowDir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-xml-shadow-"));
  t.after(() => fs.rmSync(shadowDir, {recursive: true, force: true}));
  fs.writeFileSync(path.join(shadowDir, "xml.py"), "raise RuntimeError('PYTHONPATH shadowed stdlib xml')\n");
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  const child = spawnSync(
    process.execPath,
    [path.join(ROOT, "vendor/py_launch.cjs"), "--env-var", "IRONMATE_PYTHON", "--", path.join(ROOT, "flow_workspace.py"), "import", "-"],
    {env: {...process.env, PYTHONPATH: shadowDir}, input: raw, encoding: "utf8"},
  );
  assert.equal(child.status, 0, child.stderr || child.stdout);
});

test("flow_workspace isolated mode still imports sibling Ironmate modules", () => {
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  const workspace = importFlow(raw);
  assert.equal(workspace.schema, "ironmate-flow/1");
  assert.ok(workspace.spec && typeof workspace.spec === "object");
  const patched = patchWorkspace(workspace, []);
  assert.equal(patched.schema, "ironmate-flow/1");
  assert.deepEqual(patched.spec, workspace.spec);
});

test("flow_workspace patch preserves non-ASCII labels through isolated utf-8 child", () => {
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  const workspace = importFlow(raw);
  const value = "日本語ラベル & <text>";
  const patched = patchWorkspace(workspace, [{path: "/steps/0/title", value}]);
  assert.equal(patched.spec.steps[0].title, value);
});

test("IRONMATE_PYTHON interpreter choice is unaffected by isolated child PYTHONPATH", (t) => {
  if (process.platform === "win32") {
    t.skip("extensionless shebang fake interpreters are not executable as IRONMATE_PYTHON on Windows");
    return;
  }
  const shadowDir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-xml-shadow-"));
  t.after(() => fs.rmSync(shadowDir, {recursive: true, force: true}));
  fs.writeFileSync(path.join(shadowDir, "xml.py"), "raise RuntimeError('PYTHONPATH shadowed stdlib xml')\n");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "ironmate-fake-py-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const {fake, marker} = writeFakePython(dir);
  const prevIronmate = process.env.IRONMATE_PYTHON;
  const prevPythonPath = process.env.PYTHONPATH;
  process.env.IRONMATE_PYTHON = fake;
  process.env.PYTHONPATH = shadowDir;
  t.after(() => {
    if (prevIronmate === undefined) delete process.env.IRONMATE_PYTHON;
    else process.env.IRONMATE_PYTHON = prevIronmate;
    if (prevPythonPath === undefined) delete process.env.PYTHONPATH;
    else process.env.PYTHONPATH = prevPythonPath;
  });
  const raw = fs.readFileSync(path.join(ROOT, "examples/flow.json"), "utf8");
  try {
    importFlow(raw);
  } catch {
    // fake interpreter exits before returning JSON; marker proves which binary ran
  }
  assert.equal(fs.readFileSync(marker, "utf8"), "ran");
});

// Behavioral regressions for the source-identical shared parent launcher.
const LAUNCHER = path.join(ROOT, "vendor/py_launch.cjs");
const {spawn} = require("node:child_process");

test("launcher keeps Node 26 minimum without an upper bound", () => {
  const {assertNodeVersion} = require(LAUNCHER);
  for (const version of ["26.0.0", "26.1.0", "99.0.0"]) assertNodeVersion(version);
  assert.throws(() => assertNodeVersion("22.0.0"),
    (error) => error.code === "ENODEVERSION" && /Node 26\+/.test(error.message));
});

test("launcher main reports missing interpreter as one JSON error", () => {
  const missing = path.join(ROOT, "missing-python-for-launcher-test");
  const result = spawnSync(process.execPath, ["-e",
    `require(${JSON.stringify(LAUNCHER)}).main("unused.py", {python: ${JSON.stringify(missing)}});`],
  {encoding: "utf8", timeout: 10000, env: {...process.env, PY_LAUNCH_ERROR_FORMAT: "json"}});
  assert.ifError(result.error);
  assert.equal(result.status, 2);
  assert.equal(result.stdout, "");
  const error = JSON.parse(result.stderr);
  assert.equal(error.ok, false);
  assert.equal(error.code, "ENOINTERPRETER");
  assert.equal(error.exit_code, 2);
  assert.match(error.hint, /Python 3\.9\+/);
});

function withSiteHook(t, mode, flags) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vendored-launcher-site-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const marker = path.join(dir, "hook-ran");
  const script = path.join(dir, "echo.py");
  fs.writeFileSync(path.join(dir, "sitecustomize.py"),
    'import os\nwith open(os.environ["PY_LAUNCH_SITE_MARKER"], "w") as out:\n    out.write("ran")\nraise SystemExit(42)\n');
  fs.writeFileSync(script, 'import sys\nprint(" ".join(sys.argv[1:]))\n');
  const opts = JSON.stringify({python: PYTHON, ...flags});
  const calls = {
    resolve: `launcher.resolvePython(${opts}); console.log("safe");`,
    run: `process.stdout.write(launcher.run(${JSON.stringify(script)}, ["safe"], ${opts}).stdout);`,
    main: `launcher.main(${JSON.stringify(script)}, {...${opts}, argv: ["safe"]});`,
  };
  const result = spawnSync(process.execPath,
    ["-e", `const launcher = require(${JSON.stringify(LAUNCHER)}); ${calls[mode]}`],
    {encoding: "utf8", timeout: 10000, killSignal: "SIGKILL",
      env: {...process.env, PYTHONPATH: dir, PY_LAUNCH_SITE_MARKER: marker}});
  assert.ifError(result.error);
  return {result, hookRan: fs.existsSync(marker)};
}

test("interpreter discovery leaves default site startup enabled", (t) => {
  const {result, hookRan} = withSiteHook(t, "resolve", {});
  assert.equal(hookRan, true);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /not suitable/);
});

for (const flags of [{noSite: true}, {isolated: true}, {noSite: true, isolated: true}]) {
  for (const mode of ["resolve", "run", "main"]) {
    test(`${mode} suppresses sitecustomize during discovery and execution: ${JSON.stringify(flags)}`, (t) => {
      const {result, hookRan} = withSiteHook(t, mode, flags);
      assert.equal(hookRan, false, "the version probe must also suppress sitecustomize");
      assert.equal(result.status, 0, result.stderr);
      assert.equal(result.stdout.trim(), "safe");
    });
  }
}

test("launcher preserves interpreter prefix before probe isolation flags", (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vendored-launcher-prefix-"));
  t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
  const probe = path.join(dir, "probe.cjs");
  fs.writeFileSync(probe, `require("node:assert/strict").deepEqual(process.argv.slice(2, -1), ["-S", "-I", "-c"]); console.log("3.12");`);
  const {resolvePython} = require(LAUNCHER);
  const result = resolvePython({candidates: [{cmd: process.execPath, prefix: [probe]}], noSite: true, isolated: true});
  assert.equal(result.cmd, process.execPath);
});

for (const interruptFirst of [false, true]) {
  for (const jsonErrors of [false, true]) {
    test(`launcher forwards SIGTERM${interruptFirst ? " after ignored SIGINT" : ""} (${jsonErrors ? "JSON" : "text"})`,
      {skip: process.platform === "win32", timeout: 15000}, async (t) => {
        const dir = fs.mkdtempSync(path.join(os.tmpdir(), "vendored-launcher-signal-"));
        t.after(() => fs.rmSync(dir, {recursive: true, force: true}));
        const script = path.join(dir, "ignore_sigint.py");
        fs.writeFileSync(script, 'import signal, time\ndef ignore_interrupt(_signal, _frame):\n    print("IGNORED SIGINT", flush=True)\nsignal.signal(signal.SIGINT, ignore_interrupt)\nprint("READY", flush=True)\nwhile True:\n    time.sleep(60)\n');
        const opts = {python: PYTHON, jsonErrors, noSite: true};
        const child = spawn(process.execPath,
          ["-e", `require(${JSON.stringify(LAUNCHER)}).main(${JSON.stringify(script)}, ${JSON.stringify(opts)});`],
          {detached: true, stdio: ["ignore", "pipe", "pipe"], env: {...process.env, PY_LAUNCH_ERROR_FORMAT: ""}});
        let stdout = "", stderr = "", sentFirst = false, sentTerm = false, timedOut = false, spawnError;
        const killGroup = () => {
          if (!child.pid) return;
          try { process.kill(-child.pid, "SIGKILL"); }
          catch (error) { if (error.code !== "ESRCH") throw error; }
        };
        const closed = new Promise((resolve) => child.once("close", (code, signal) => resolve({code, signal})));
        const timer = setTimeout(() => { timedOut = true; killGroup(); }, 7500);
        child.on("error", (error) => { spawnError = error; });
        child.stderr.on("data", (chunk) => { stderr += chunk; });
        child.stdout.on("data", (chunk) => {
          stdout += chunk;
          if (!sentFirst && stdout.includes("READY\n")) {
            sentFirst = true;
            if (interruptFirst) child.kill("SIGINT");
            else { sentTerm = true; child.kill("SIGTERM"); }
          }
          if (interruptFirst && !sentTerm && stdout.includes("IGNORED SIGINT\n")) {
            sentTerm = true;
            child.kill("SIGTERM");
          }
        });
        try {
          const {code, signal} = await closed;
          assert.ifError(spawnError);
          assert.equal(timedOut, false, `launcher did not terminate: ${stdout}; ${stderr}`);
          assert.equal(sentTerm, true);
          assert.equal(code, 2);
          assert.equal(signal, null);
          if (jsonErrors) {
            const payload = JSON.parse(stderr);
            assert.equal(payload.code, "ESIGNAL");
            assert.equal(payload.exit_code, 2);
            assert.match(payload.message, /SIGTERM/);
          } else assert.match(stderr, /terminated by signal SIGTERM/);
        } finally { clearTimeout(timer); killGroup(); }
      });
  }
}
