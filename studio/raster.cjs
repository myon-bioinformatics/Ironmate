// CPU rasterization through installed Chrome and Node 22's built-in WebSocket.
// No Playwright/Puppeteer runtime dependency; input HTML comes from core.svg only.
"use strict";
const { spawn } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const [chrome, html, profile, widthText, heightText] = process.argv.slice(2);
const width = Number(widthText),
  height = Number(heightText);
if (typeof WebSocket === "undefined")
  throw new Error("PNG export requires Node.js 22 or newer");
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
      } catch {}
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
