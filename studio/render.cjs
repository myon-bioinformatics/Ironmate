// The CLI uses the same validated SVG renderer as the static browser editor.
"use strict";
const fs = require("node:fs"),
  core = require("./core.js");
try {
  const request = JSON.parse(fs.readFileSync(0, "utf8"));
  const scene = core.validate(request.scene);
  if (request.mode === "validate") process.stdout.write(JSON.stringify(scene));
  else process.stdout.write(core.svg(scene, undefined, request.scale ?? 1));
} catch (error) {
  process.stderr.write(error.message + "\n");
  process.exitCode = 2;
}
