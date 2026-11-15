// 🖼 Scene CLI: the same validated SVG renderer as the static browser editor, plus PNG through
// installed Chrome and Node's built-in WebSocket (no Playwright/Puppeteer runtime dependency).
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");

const HELP = `studio/render.cjs — validate a scene or write its SVG, or rasterize HTML to PNG

usage:
  node studio/render.cjs [SCENE.json] [--json]
  node studio/render.cjs < SCENE.json
  node studio/render.cjs png CHROME HTML PROFILE WIDTH HEIGHT

The JSON object is {"scene": {...}, "mode": "svg"|"validate", "scale": 1}.
mode defaults to svg. A terminal with no file exits 2 instead of waiting.
--json writes a fixable failure as one JSON object on stderr. Success
output stays SVG text, or the validated scene JSON when mode is validate.
png writes the PNG of a local HTML file on stdout. WIDTH and HEIGHT are
positive integers; a wrong argument list exits 2 before Chrome starts.
Remote http and https URLs are blocked.
`;

/** Fixable failure: one line (or one JSON object with --json) on stderr, exit 2. */
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

const argv = process.argv.slice(2);
const jsonMode = argv.includes("--json");
const fileArgs = argv.filter((token) => token !== "--json");

if (argv.includes("--help") || argv.includes("-h")) {
  process.stdout.write(HELP);
} else if (argv[0] === "png") {
  const args = argv.slice(1);
  const [chrome, html, profile, widthText, heightText] = args;
  const width = Number(widthText);
  const height = Number(heightText);
  if (args.length !== 5) {
    fail("studio/render.cjs png", "expected CHROME HTML PROFILE WIDTH HEIGHT", "rerun with --help", false);
  } else if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    fail("studio/render.cjs png", "WIDTH and HEIGHT must be positive integers", "example: 640 480", false);
  } else if (typeof WebSocket === "undefined") {
    fail("studio/render.cjs png", "PNG export requires Node.js 26 or newer", "use a Node.js build that provides a global WebSocket", false);
  } else {
    startRaster(chrome, html, profile, width, height);
  }
} else if (fileArgs.some((token) => token.startsWith("-") && token !== "-")) {
  fail("studio/render.cjs", "unknown flag " + fileArgs.find((token) => token.startsWith("-")), "rerun with --help", jsonMode);
} else if (fileArgs.length > 1) {
  fail("studio/render.cjs", "pass one scene JSON file, or pipe JSON on stdin", "rerun with --help", jsonMode);
} else if (fileArgs.length === 0 && process.stdin.isTTY) {
  fail("studio/render.cjs", "stdin is a terminal", "pass a scene JSON file or pipe JSON. rerun with --help", jsonMode);
} else {
  try {
    const raw = fileArgs.length === 1 ? fs.readFileSync(fileArgs[0], "utf8") : fs.readFileSync(0, "utf8");
    let request;
    try {
      request = JSON.parse(raw);
    } catch (error) {
      fail("studio/render.cjs", "scene JSON must be one JSON value: " + error.message, "pass a file or pipe one object", jsonMode);
    }
    if (!request || typeof request !== "object" || Array.isArray(request) || !request.scene) {
      fail("studio/render.cjs", "JSON must be an object with a scene field", "see --help for the object shape", jsonMode);
    }
    const Module = require("node:module");
    const bundlePath = path.join(__dirname, "..", "ironlib", "studio_bundle.py");
    const bundleSrc = fs.readFileSync(bundlePath, "utf8");
    const jsStart = bundleSrc.indexOf('STUDIO_JS = r"""') + 'STUDIO_JS = r"""'.length;
    const mod = new Module(bundlePath);
    mod._compile(bundleSrc.slice(jsStart, bundleSrc.indexOf('"""', jsStart)), path.join(__dirname, "studio.js"));
    const core = mod.exports;
    const scene = core.validate(request.scene);
    if (request.mode === undefined || request.mode === "svg") {
      process.stdout.write(core.svg(scene, undefined, request.scale ?? 1));
    } else if (request.mode === "validate") {
      process.stdout.write(JSON.stringify(scene));
    } else {
      fail("studio/render.cjs", "mode must be svg or validate", "omit mode for SVG", jsonMode);
    }
  } catch (error) {
    fail("studio/render.cjs", error.message, "rerun with --help", jsonMode);
  }
}

function startRaster(chrome, html, profile, width, height) {
let child, socket, timer;
const pending = new Map(),
  events = new Map();
let id = 0;
function call(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const n = ++id;
    pending.set(n, { resolve, reject });
    socket.send(
      JSON.stringify({
        id: n,
        method,
        params,
        ...(sessionId ? { sessionId } : {}),
      }),
    );
  });
}
function event(method, sessionId) {
  return new Promise((resolve) =>
    events.set(method + ":" + sessionId, resolve),
  );
}
const deadline = new Promise((_, reject) => {
  timer = setTimeout(
    () => reject(new Error("Chrome rasterization timed out")),
    30000,
  );
});
(async () => {
  const work = (async () => {
    const args = [
      "--headless",
      "--disable-gpu",
      "--remote-debugging-port=0",
      "--remote-debugging-address=127.0.0.1",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-background-networking",
      "--disable-component-update",
      "--user-data-dir=" + profile,
      "about:blank",
    ];
    if (process.env.IRONMATE_CHROME_NO_SANDBOX === "1")
      args.unshift("--no-sandbox");
    child = spawn(chrome, args, { stdio: ["ignore", "ignore", "pipe"] });
    const url = await new Promise((resolve, reject) => {
      let text = "";
      child.on("error", reject);
      child.on("exit", (code) => reject(new Error("Chrome exited " + code)));
      child.stderr.on("data", (chunk) => {
        text += chunk;
        const m = text.match(/DevTools listening on (ws:\/\/[^\s]+)/);
        if (m) resolve(m[1]);
        if (text.length > 100000) text = text.slice(-20000);
      });
    });
    socket = new WebSocket(url);
    socket.addEventListener("message", (e) => {
      const m = JSON.parse(e.data);
      if (m.id) {
        const p = pending.get(m.id);
        pending.delete(m.id);
        if (p)
          m.error ? p.reject(new Error(m.error.message)) : p.resolve(m.result);
      } else {
        const key = m.method + ":" + m.sessionId;
        const resolve = events.get(key);
        if (resolve) {
          events.delete(key);
          resolve(m.params);
        }
      }
    });
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener(
        "error",
        () => reject(new Error("Chrome control socket failed")),
        { once: true },
      );
    });
    const { targetId } = await call("Target.createTarget", {
      url: "about:blank",
    });
    const { sessionId } = await call("Target.attachToTarget", {
      targetId,
      flatten: true,
    });
    await call("Page.enable", {}, sessionId);
    await call("Network.enable", {}, sessionId);
    await call(
      "Network.setBlockedURLs",
      { urls: ["http://*", "https://*"] },
      sessionId,
    );
    await call(
      "Emulation.setDeviceMetricsOverride",
      { width, height, deviceScaleFactor: 1, mobile: false },
      sessionId,
    );
    await call(
      "Emulation.setDefaultBackgroundColorOverride",
      { color: { r: 0, g: 0, b: 0, a: 0 } },
      sessionId,
    );
    const loaded = event("Page.loadEventFired", sessionId);
    await call("Page.navigate", { url: pathToFileURL(html).href }, sessionId);
    await loaded;
    const ready = await call(
      "Runtime.evaluate",
      {
        expression: "document.fonts.ready.then(()=>true)",
        awaitPromise: true,
        returnByValue: true,
      },
      sessionId,
    );
    if (ready.exceptionDetails) throw new Error("Font preparation failed");
    const shot = await call(
      "Page.captureScreenshot",
      {
        format: "png",
        captureBeyondViewport: true,
        clip: { x: 0, y: 0, width, height, scale: 1 },
      },
      sessionId,
    );
    process.stdout.write(Buffer.from(shot.data, "base64"));
  })();
  await Promise.race([work, deadline]);
})()
  .catch((e) => {
    process.stderr.write(e.message + "\n");
    process.exitCode = 2;
  })
  .finally(async () => {
    clearTimeout(timer);
    if (socket?.readyState === WebSocket.OPEN) {
      try {
        await Promise.race([
          call("Browser.close"),
          new Promise((resolve) => setTimeout(resolve, 1000)),
        ]);
      } catch (closeError) {
        const detail = closeError && closeError.message ? closeError.message : closeError;
        process.stderr.write("studio/render.cjs png: browser close failed: " + detail + "\n");
      }
      socket.close();
    }
    if (child && child.exitCode === null) {
      await new Promise((resolve) => {
        const timer = setTimeout(resolve, 1000);
        child.once("exit", () => {
          clearTimeout(timer);
          resolve();
        });
      });
      if (child.exitCode === null) child.kill();
    }
  });
}
