"use strict";
/** Atomic JSON flow patches, matching the Python flow_patch.py contract. */
const fs = require("node:fs");
const {validate} = require("./flow.cjs");
const MAX_BYTES = 320 * 1024;
function patchFlow(spec, operations) {
  const result = validate(spec);
  if (!Array.isArray(operations) || operations.length > 64) throw Error("invalid patch array");
  for (const op of operations) {
    if (!op || typeof op !== "object" || Array.isArray(op) ||
        Object.keys(op).sort().join(",") !== "path,value" || typeof op.path !== "string")
      throw Error("invalid patch operation");
    if (op.path === "/title" || op.path === "/sources_label") {
      result[op.path.slice(1)] = op.value;
      continue;
    }
    const match = /^\/(sources|steps)\/(0|[1-9][0-9]*)\/(title|note)$/.exec(op.path);
    if (!match) throw Error("unsupported patch path");
    const group = result[match[1]], index = Number(match[2]);
    if (!Number.isSafeInteger(index) || index >= group.length) throw Error("patch index out of range");
    group[index][match[3]] = op.value;
  }
  return validate(result);
}
function applyDocument(document) {
  if (!document || typeof document !== "object" || Array.isArray(document) ||
      Object.keys(document).sort().join(",") !== "patch,spec") throw Error("invalid patch document");
  return patchFlow(document.spec, document.patch);
}
if (require.main === module) {
  try {
    const chunks = [];
    let total = 0;
    while (true) {
      const chunk = Buffer.allocUnsafe(Math.min(65536, MAX_BYTES + 1 - total));
      const count = fs.readSync(0, chunk, 0, chunk.length, null);
      if (!count) break;
      total += count;
      if (total > MAX_BYTES) throw Error("patch document exceeds byte budget");
      chunks.push(chunk.subarray(0, count));
    }
    const input = Buffer.concat(chunks, total);
    const pretty = process.argv.slice(2);
    if (pretty.length > 1 || (pretty.length && pretty[0] !== "--pretty")) throw Error("unknown arguments");
    const result = applyDocument(JSON.parse(new TextDecoder("utf-8", {fatal:true}).decode(input)));
    process.stdout.write(JSON.stringify(result, null, pretty.length ? 2 : undefined) + "\n");
  } catch (error) {
    process.stderr.write("flow patch: " + error.message + "\n");
    process.exitCode = 2;
  }
}
module.exports = {patchFlow, applyDocument};
