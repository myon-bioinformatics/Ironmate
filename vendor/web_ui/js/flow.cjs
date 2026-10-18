"use strict";
/** Node CommonJS flow wrapper. No browser, npm package or Python subprocess required. */
const fs = require("node:fs");
const MAX_BYTES = 256 * 1024;
function label(value, required = true, max = 240) {
  if (typeof value !== "string" || value.length > max || /[\x00-\x1f\x7f]/.test(value) ||
      (required && !value.trim())) throw new Error("invalid label");
  return value;
}
function cards(value) {
  if (!Array.isArray(value) || value.length < 1 || value.length > 8) throw new Error("invalid cards");
  return value.map(item => {
    if (!item || typeof item !== "object" || Array.isArray(item) ||
        !Object.prototype.hasOwnProperty.call(item, "title") ||
        Object.keys(item).some(k => !["title", "note"].includes(k))) throw new Error("invalid card");
    return {title: label(item.title, true, 120), note: label(item.note ?? "", false)};
  });
}
function validate(spec) {
  if (!spec || typeof spec !== "object" || Array.isArray(spec) ||
      Object.keys(spec).some(k => !["title", "sources_label", "sources", "steps"].includes(k)))
    throw new Error("invalid flow");
  return {title: label(spec.title ?? "", true, 120),
    sources_label: label(spec.sources_label ?? "Sources", true, 120),
    sources: cards(spec.sources), steps: cards(spec.steps)};
}
const htmlEscape = value => value.replace(/&/g, "&amp;").replace(/</g, "&lt;")
  .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#x27;");
function cardHtml(card) {
  return '<div class="ui-flow-card"><strong class="ui-flow-card-title">' +
    htmlEscape(card.title) + '</strong>' +
    (card.note ? '<span class="ui-flow-card-note">' + htmlEscape(card.note) + '</span>' : "") + '</div>';
}
function flowHtml(spec) {
  const data = validate(spec);
  const sources = data.sources.map(c => '<li class="ui-flow-source">' + cardHtml(c) + '</li>').join("");
  const steps = data.steps.map(c => '<li class="ui-flow-step">' + cardHtml(c) + '</li>').join("");
  return '<figure class="ui-flow" aria-label="' + htmlEscape(data.title) +
    '"><figcaption class="ui-flow-caption">' + htmlEscape(data.title) +
    '</figcaption><ul class="ui-flow-sources" aria-label="' + htmlEscape(data.sources_label) +
    '">' + sources + '</ul><div class="ui-flow-arrow" aria-hidden="true">↓</div>' +
    '<ol class="ui-flow-steps">' + steps + '</ol></figure>';
}
function mermaidEscape(value) {
  const entities = {'"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;",
    "[": "#91;", "]": "#93;", "\\": "#92;"};
  return [...value].map(c => entities[c] ?? c).join("");
}
function flowMermaid(spec) {
  const data = validate(spec);
  const lines = ["```mermaid", "flowchart TB",
    '    subgraph input["' + mermaidEscape(data.sources_label) + '"]', "        direction LR"];
  data.sources.forEach((c, i) => lines.push('        S' + i + '["' +
    mermaidEscape(c.title) + (c.note ? "<br/>" + mermaidEscape(c.note) : "") + '"]'));
  lines.push("    end");
  data.steps.forEach((c, i) => lines.push('    T' + i + '["' +
    mermaidEscape(c.title) + (c.note ? "<br/>" + mermaidEscape(c.note) : "") + '"]'));
  data.sources.forEach((_, i) => lines.push("    S" + i + " --> T0"));
  for (let i = 1; i < data.steps.length; i++) lines.push("    T" + (i - 1) + " --> T" + i);
  return lines.join("\n") + "\n```\n";
}
function flowDocument(spec, theme = "github-like") {
  if (!["modern", "github-like"].includes(theme)) throw new Error("invalid theme");
  const data = validate(spec);
  const css = ["tokens.css", "base.css", "components.css", "flow.css"]
    .map(p => '<link rel="stylesheet" href="./css/' + p + '">').join("") +
    '<link rel="stylesheet" href="./css/themes/' + theme + '.css">';
  return '<!doctype html>\n<html lang="ja"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1"><title>' +
    htmlEscape(data.title) + '</title>' + css + '</head><body data-ui-theme="' +
    theme + '"><main class="ui-page">' + flowHtml(data) + '</main></body></html>\n';
}
function main(argv = process.argv.slice(2)) {
  const flag = argv.indexOf("--format");
  const format = flag < 0 ? "html" : argv[flag + 1];
  if (!["html", "mermaid", "fragment"].includes(format) ||
      (flag >= 0 && (argv.length !== 2 || flag !== 0)) ||
      (flag < 0 && argv.length)) throw Error("usage: node js/flow.cjs [--format html|mermaid|fragment]");
  const input = fs.readFileSync(0);
  if (input.length > MAX_BYTES) throw Error("flow JSON exceeds 256KiB");
  const data = JSON.parse(input.toString("utf8"));
  process.stdout.write(format === "mermaid" ? flowMermaid(data) :
    format === "fragment" ? flowHtml(data) + "\n" : flowDocument(data));
}
if (require.main === module) {
  try { main(); } catch (err) { process.stderr.write("flow: " + err.message + "\n"); process.exitCode = 2; }
}
module.exports = {validate, flowHtml, flowMermaid, flowDocument};
