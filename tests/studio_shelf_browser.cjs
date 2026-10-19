/* Clipboard acquisition is mocked; all validation, DOM actions, Blob allocation,
 * data URI conversion, object URL lifecycle and image import run in Chromium. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
module.exports = async ({page, out}) => {
  const result = await page.evaluate(async () => {
    const check = (ok, message) => { if (!ok) throw new Error(message); };
    const $ = id => document.getElementById(id);
    const S = window.IronmateStudio;
    const max = 32 * 1024 * 1024;
    const cv = document.createElement("canvas");
    cv.width = cv.height = 2;
    cv.getContext("2d").fillRect(0, 0, 2, 2);
    const uri = cv.toDataURL("image/png");
    const bytes = Uint8Array.from(atob(uri.split(",")[1]), c => c.charCodeAt(0));
    const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, "clipboard");
    const create = URL.createObjectURL, revoke = URL.revokeObjectURL, originalAtob = window.atob;
    const created = [], released = [], copies = [], largeDecodes = [];
    const assertEmptyError = () => {
      check($("error").open, "invalid input must display an error");
      $("error").close();
    };
    const clear = () => $("shelf-clear").onclick();
    const note = async text => {
      $("shelf-input-text").value = text;
      await $("shelf-add-text").onclick();
    };
    const cardButton = (index, label) => Array.from($("shelf-items-container").children[index].querySelectorAll("button"))
      .find(button => button.textContent === label);
    const clip = (text, blob, types = ["image/png"]) => {
      Object.defineProperty(navigator, "clipboard", {configurable:true, value:{
        readText:async () => text,
        read:async () => blob ? [{types, getType:async () => blob}] : [],
        writeText:async text => copies.push(text),
      }});
    };
    const paddedImage = size => {
      const data = new Uint8Array(size);
      data.set(bytes.subarray(0, 8));
      return data;
    };
    URL.createObjectURL = blob => { const url = create.call(URL, blob); created.push(url); return url; };
    URL.revokeObjectURL = url => { released.push(url); return revoke.call(URL, url); };
    window.atob = text => { if (text.length > 16) largeDecodes.push(text.length); return originalAtob(text); };
    try {
      $("shelf-button").click();
      clear();
      // Both explicit and recognizable raw image failures remain errors, even if
      // another valid binary format is simultaneously offered by the clipboard.
      const invalid = [uri.replace("image/png", "image/jpeg"), uri.replace("image/png", "text/plain"),
        "data:image/png,broken", "data:image/png;base64,%%%", "data:",
        uri.split(",")[1].slice(0, -1) + "!"];
      for (const text of invalid) {
        await note(text); assertEmptyError(); check(S.shelfItems.length === 0, "bad text image became note");
        clip(text, new Blob([bytes], {type:"image/png"}));
        await $("shelf-paste-clip").onclick(); assertEmptyError();
        check(S.shelfItems.length === 0, "invalid image text fell back to binary or note");
      }
      let reads = 0;
      clip("", {size:max + 1, type:"image/png", arrayBuffer:async () => { reads++; return bytes.buffer; }});
      await $("shelf-paste-clip").onclick(); assertEmptyError();
      check(reads === 0, "oversized Blob allocated arrayBuffer");
      check(S.shelfItems.length === 0, "oversized Blob retained");
      // Exact decoded byte bounds before atob, including rounded Base64 lengths.
      for (const delta of [-1, 0, 1]) {
        clear();
        S.addShelfItem(paddedImage(max - bytes.length + delta), "image/png", null);
        const decodes = largeDecodes.length;
        await note(uri);
        if (delta > 0) {
          assertEmptyError(); check(S.shelfItems.length === 1, "aggregate overflow retained");
          check(largeDecodes.length === decodes, "over-budget Base64 decoded first");
        } else check(S.shelfItems.length === 2, "inclusive aggregate byte boundary rejected");
      }
      clear();
      // Aggregate Blob limit must also be checked before reading a small second item.
      S.addShelfItem(paddedImage(max - bytes.length + 1), "image/png", null);
      clip("", {size:bytes.length, type:"image/png", arrayBuffer:async () => { reads++; return bytes.buffer; }});
      await $("shelf-paste-clip").onclick(); assertEmptyError();
      check(reads === 0, "aggregate Blob overflow allocated arrayBuffer");
      clear();
      for (const blob of [new Blob([bytes], {type:"image/jpeg"}), new Blob(["invalid"], {type:"image/png"})]) {
        clip("", blob); await $("shelf-paste-clip").onclick(); assertEmptyError();
        check(S.shelfItems.length === 0, "invalid binary MIME or magic retained");
      }
      clip("note", new Blob(["gif"], {type:"image/gif"}), ["image/gif"]);
      await $("shelf-paste-clip").onclick(); assertEmptyError();
      check(S.shelfItems.length === 0, "unsupported binary image became note");
      // Reservations cover overlapping clipboard reads before the first resolves.
      let resolveRead, started;
      const ready = new Promise(resolve => { started = resolve; });
      clip("", {size:max, type:"image/png", arrayBuffer:() => new Promise(resolve => {
        resolveRead = resolve; started();
      })});
      const pending = $("shelf-paste-clip").onclick();
      await ready;
      await note(uri); assertEmptyError();
      check(S.shelfItems.length === 0, "concurrent text bypassed reserved bytes");
      clear(); // Pending work must not repopulate the cleared shelf.
      resolveRead(paddedImage(max).buffer);
      await pending; assertEmptyError();
      check(S.shelfItems.length === 0, "clear allowed an in-flight image to reappear");
      // Clearing during any clipboard acquisition await also cancels that operation.
      for (const stage of ["readText", "read", "getType"]) {
        let finish, reached;
        const acquired = new Promise(resolve => { reached = resolve; });
        const wait = () => new Promise(resolve => { finish = resolve; reached(); });
        let allocated = 0;
        const blob = {size:bytes.length, type:"image/png", arrayBuffer:async () => {
          allocated++; return bytes.buffer;
        }};
        const items = [{types:["image/png"], getType:stage === "getType" ? wait : async () => blob}];
        Object.defineProperty(navigator, "clipboard", {configurable:true, value:{
          readText:stage === "readText" ? wait : async () => "",
          read:stage === "read" ? wait : async () => items,
        }});
        const operation = $("shelf-paste-clip").onclick();
        await acquired; clear();
        finish(stage === "readText" ? uri : stage === "read" ? items : blob);
        await operation; assertEmptyError();
        check(S.shelfItems.length === 0 && allocated === 0, `clear failed during ${stage}`);
      }
      // 20 items accepted, 21st denied before URL allocation. Delete frees a slot.
      clip("", null);
      for (let i = 0; i < 20; i++) S.addShelfItem(bytes, "image/png", null, `image ${i}`);
      const urlsBefore = created.length;
      await note(uri); assertEmptyError();
      check(S.shelfItems.length === 20 && created.length === urlsBefore, "21st item allocated URL");
      const deletedUrl = S.shelfItems[1].dataUrl;
      cardButton(1, "削除").click();
      check(released.includes(deletedUrl) && S.shelfItems.length === 19, "delete failed to release URL");
      await note("日本語 🌱 note");
      await cardButton(0, "コピー").onclick();
      check(copies.at(-1) === "日本語 🌱 note", "plain note copy changed content");
      clear();
      // Binary clipboard + raw Base64 produce portable copies and still import.
      clip("", new Blob([bytes], {type:"image/png"}));
      await $("shelf-paste-clip").onclick();
      await note(uri.split(",")[1]);
      check(S.shelfItems.length === 2, "binary or raw Base64 image not retained");
      for (const index of [0, 1]) {
        await cardButton(index, "コピー").onclick();
        const copied = copies.at(-1);
        check(copied.startsWith("data:image/png;base64,"), "image copy is not portable data URI");
        check(copied === uri, "copied bytes differ from original image");
      }
      const layersBefore = S.scene.layers.length;
      await cardButton(1, "取り込み").onclick();
      check(S.scene.layers.length === layersBefore + 1, "shelf image import regressed");
      check(S.scene.layers.at(-1).src.startsWith("data:image/png;base64,"), "import retained blob URL");
      clear();
      // Text is budgeted as UTF-8, not UTF-16 code units.
      S.addShelfItem(paddedImage(max - 4), "image/png", null);
      await note("🌱"); check(S.shelfItems.length === 2, "UTF-8 exact boundary rejected");
      await note("a"); assertEmptyError();
      cardButton(0, "削除").click();
      await note("abcde"); assertEmptyError();
      await note("abcd"); check(S.shelfItems.length === 2, "delete did not restore byte budget");
      clear();
      // Permission errors only affect acquisition, never validation fallback.
      Object.defineProperty(navigator, "clipboard", {configurable:true, value:{
        readText:async () => { throw new Error("denied"); },
        read:async () => [{types:["image/png"], getType:async () => new Blob([bytes], {type:"image/png"})}],
        writeText:async text => copies.push(text),
      }});
      await $("shelf-paste-clip").onclick();
      check(S.shelfItems.length === 1, "binary-only clipboard failed after text permission denial");
      clear();
      check(created.length === released.length && new Set(released).size === released.length,
        "delete/clear/import did not revoke each created URL exactly once");
      return {checks:["aggregate-32MiB-inclusive", "pre-atob-budget", "pre-arrayBuffer-budget",
        "image-fail-closed", "binary-mime-magic", "concurrent-reservations", "clear-cancels-pending",
        "20-items", "delete-reclaims-budget", "portable-copy", "image-import", "utf8-notes",
        "binary-permission-fallback", "object-url-release"], objectUrls:created.length, released:released.length};
    } finally {
      clear();
      if ($("shelf-dialog").open) $("shelf-dialog").close();
      if ($("error").open) $("error").close();
      URL.createObjectURL = create; URL.revokeObjectURL = revoke; window.atob = originalAtob;
      if (clipboardDescriptor) Object.defineProperty(navigator, "clipboard", clipboardDescriptor);
      else delete navigator.clipboard;
    }
  });
  fs.writeFileSync(path.join(out, "shelf-result.json"), JSON.stringify(result, null, 2));
  console.log("Clipboard Shelf browser regressions passed:", result.checks.length);
};
