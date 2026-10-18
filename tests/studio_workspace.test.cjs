/* studio_workspace.test.cjs */
"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const C = require("../studio/core.js");
const blank = () => ({schema:C.SCHEMA,width:64,height:64,background:"none",layers:[]});
const history = () => {
  const h = new C.History(blank());
  const next = h.current;
  next.background = "#123456";
  h.commit(next);
  h.undo();
  return h;
};

test("workspace restores selected index, redo branch, Unicode and detached state", () => {
  const h = history();
  h.items[1].source = {note:"🌱日本語"};
  const text = C.workspaceText(h);
  const restored = C.workspaceHistory(text);
  assert.equal(restored.index, 0);
  assert.deepEqual(restored.current, h.current);
  assert.deepEqual(restored.redo(), h.items[1]);
  restored.items[1].source.note = "changed";
  assert.equal(h.items[1].source.note, "🌱日本語");
  assert.equal(new TextEncoder().encode(text).length, new Blob([text]).size);
});

test("workspace validates index, schema, count and every scene before returning", () => {
  const record = JSON.parse(C.workspaceText(history()));
  for (const patch of [{schema:"wrong"},{index:-1},{index:2},{index:0.5},{items:[]},
    {items:Array(41).fill(blank())},{items:[blank(), {...blank(), width:-1}]}]) {
    assert.throws(() => C.workspaceHistory(JSON.stringify({...record,...patch})));
  }
  assert.throws(() => C.workspaceText({items:[blank()],index:1}));
  assert.throws(() => C.workspaceHistory(null));
});

test("reader applies inclusive 32MiB UTF-8 byte limit, not JS character count", () => {
  const text = C.workspaceText(history());
  const exact = text + " ".repeat(C.WORKSPACE_MAX_BYTES - Buffer.byteLength(text));
  assert.equal(Buffer.byteLength(exact), C.WORKSPACE_MAX_BYTES);
  assert.deepEqual(C.workspaceHistory(exact).current, blank());
  assert.throws(() => C.workspaceHistory(exact+" "), /32MiB/);
  // Remain below 32MiB in JS code units while exceeding it in UTF-8.
  const large = JSON.parse(text);
  large.items[0].source = "🌱".repeat(8_388_608);
  const multibyte = JSON.stringify(large);
  assert(multibyte.length < C.WORKSPACE_MAX_BYTES);
  assert(Buffer.byteLength(multibyte) > C.WORKSPACE_MAX_BYTES);
  assert.throws(() => C.workspaceHistory(multibyte), /32MiB/);
});

test("writer rejects repeated image history over budget and accepts current-state trimming", () => {
  const scene = blank();
  scene.layers.push({id:"img",kind:"image",x:0,y:0,w:64,h:64,rotation:0,opacity:1,
    src:"data:image/png;base64,"+"A".repeat(8_000_000),cell:1,levels:256});
  // This exercises the scene-string contract, not an image decoder.
  const h = new C.History(scene);
  h.items = Array(5).fill(scene);
  h.index = 2;
  assert.throws(() => C.workspaceText(h), /32MiB/);
  assert.equal(h.items.length, 5);
  const trimmed = new C.History(h.current);
  assert.deepEqual(C.workspaceHistory(C.workspaceText(trimmed)).current, h.current);
});
