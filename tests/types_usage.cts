// Compile-only check (tsc --noEmit): the declarations accept real calls and reject wrong ones.
import flow = require("../flow_export.cjs");
import workspace = require("../flow_workspace.cjs");
import digest = require("../image_digest.cjs");
const spec: flow.FlowSpec = {sources: [{title: "a"}], steps: [{title: "b"}]};
const svg: Uint8Array = flow.renderFlow(spec, {format: "svg", scale: 2});
const ws: workspace.FlowWorkspace = workspace.importFlow(JSON.stringify(spec));
const out = workspace.patchAndRender(ws, [{path: "/steps/0/title", value: "c"}], {format: "png"});
const info: digest.DigestInfo = digest.buildDigest(
  {schema: "ironmate-image-digest-input/1", rows: ["home"], cols: ["chromium"],
   cells: [{row: "home", col: "chromium", image: "a.png", status: "pass"}]},
  {base: ".", out: "digest", tile: "64x128"});
// @ts-expect-error unknown format
flow.renderFlow(spec, {format: "gif"});
// @ts-expect-error base and out are required
digest.buildDigest({schema: "ironmate-image-digest-input/1", rows: [], cols: [], cells: []}, {});
void [svg, out.image, info.tile];
