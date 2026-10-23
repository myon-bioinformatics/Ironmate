// The CLI uses the same validated SVG renderer as the static browser editor.
"use strict";
const fs = require("node:fs");
const core = require("./core.js");
const {fail, wantsJson} = require("../ironmate_cli.cjs");

const HELP = `studio/render.cjs — validate a scene or write its SVG

usage:
  node studio/render.cjs [SCENE.json] [--json]
  node studio/render.cjs < SCENE.json

The JSON object is {"scene": {...}, "mode": "svg"|"validate", "scale": 1}.
mode defaults to svg. A terminal with no file exits 2 instead of waiting.
--json writes a fixable failure as one JSON object on stderr. Success
output stays SVG text, or the validated scene JSON when mode is validate.
`;

const argv = process.argv.slice(2);
const jsonMode = wantsJson(argv);
const fileArgs = argv.filter((token) => token !== "--json");

if (argv.includes("--help") || argv.includes("-h")) {
  process.stdout.write(HELP);
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
