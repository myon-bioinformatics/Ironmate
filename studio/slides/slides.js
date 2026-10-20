/* Multi-slide document state around the existing Image Studio editor. */
"use strict";
(async () => {
  const C = window.StudioCore,
    D = window.IronmateSlides,
    E = window.IronmateStudio,
    byId = (id) => document.getElementById(id);
  let deck = { schema: D.SCHEMA, title: "Ironmate", slides: [D.template()] },
    active = 0,
    saved = "",
    busy = false;
  const note = (message, error = false) => {
    byId("deck-status").textContent = message;
    byId("deck-status").dataset.error = error;
  };
  function snapshot() {
    const next = C.clone(deck);
    next.slides[active] = E.scene;
    return D.validate(next);
  }
  function selectList() {
    const select = byId("slide-select");
    select.replaceChildren(
      ...deck.slides.map(
        (s, i) =>
          new Option(
            `${i + 1} / ${s.layers.find((l) => l.kind === "text")?.text.slice(0, 24) || "白紙"}`,
            i,
          ),
      ),
    );
    select.value = active;
    byId("slide-delete").disabled = deck.slides.length === 1;
    byId("slide-up").disabled = active === 0;
    byId("slide-down").disabled = active === deck.slides.length - 1;
  }
  async function commit(next, index) {
    const checked = D.validate(next);
    await E.replaceScene(checked.slides[index]);
    deck = checked;
    active = index;
    selectList();
    note(
      `${active + 1} / ${deck.slides.length} 枚目を編集中。全体の保存は「全スライドJSON保存」を使います。`,
    );
  }
  function action(id, fn) {
    byId(id).addEventListener("click", async () => {
      if (busy) return;
      busy = true;
      try {
        await fn();
      } catch (e) {
        note(e.message, true);
      } finally {
        busy = false;
      }
    });
  }
  function save(name, data, mime) {
    const url = URL.createObjectURL(new Blob([data], { type: mime })),
      a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }
  const bytesFromData = (uri) =>
    Uint8Array.from(atob(uri.split(",")[1]), (c) => c.charCodeAt(0));
  async function imageForLayer(layer, scene) {
    const imageSource = await E.imageSource(scene);
    if (layer.kind === "image" && !layer.mono)
      return bytesFromData(imageSource(layer));
    const l = { ...layer, x: 0, y: 0, rotation: 0, opacity: 1 },
      scale = Math.min(2, Math.sqrt(4194304 / (l.w * l.h))),
      canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(l.w * scale));
    canvas.height = Math.max(1, Math.round(l.h * scale));
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}" viewBox="0 0 ${l.w} ${l.h}">${C.layerSVG(l, imageSource)}</svg>`;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" })),
      image = new Image();
    try {
      image.src = url;
      await image.decode();
      canvas.getContext("2d").drawImage(image, 0, 0);
      const blob = await new Promise((resolve) =>
        canvas.toBlob(resolve, "image/png"),
      );
      if (!blob) throw Error("画像レイヤーを出力できませんでした。");
      return new Uint8Array(await blob.arrayBuffer());
    } finally {
      URL.revokeObjectURL(url);
    }
  }
  await E.ready;
  await E.replaceScene(deck.slides[0]);
  selectList();
  saved = D.deckText(deck);
  byId("fill").value = "#000000";
  byId("stroke").value = "#000000";
  byId("arrow-style").value = "triangle";
  action("slide-add", async () => {
    const next = snapshot();
    if (next.slides.length >= 20) throw Error("スライドは最大20枚です。");
    const current = next.slides[0];
    next.slides.splice(active + 1, 0, {
      schema: C.SCHEMA,
      width: current.width,
      height: current.height,
      background: "#FFFFFF",
      layers: [],
    });
    await commit(next, active + 1);
  });
  action("slide-duplicate", async () => {
    const next = snapshot();
    if (next.slides.length >= 20) throw Error("スライドは最大20枚です。");
    next.slides.splice(active + 1, 0, C.clone(next.slides[active]));
    await commit(next, active + 1);
  });
  action("slide-delete", async () => {
    if (deck.slides.length === 1) return;
    if (!confirm("このスライドを削除しますか？")) return;
    const next = snapshot();
    next.slides.splice(active, 1);
    await commit(next, Math.min(active, next.slides.length - 1));
  });
  for (const [id, delta] of [
    ["slide-up", -1],
    ["slide-down", 1],
  ])
    action(id, async () => {
      const next = snapshot(),
        index = active + delta;
      if (index < 0 || index >= next.slides.length) return;
      [next.slides[active], next.slides[index]] = [
        next.slides[index],
        next.slides[active],
      ];
      await commit(next, index);
    });
  byId("slide-select").addEventListener("change", async (e) => {
    if (busy) {
      e.target.value = active;
      return;
    }
    busy = true;
    try {
      const next = snapshot();
      await commit(next, Number(e.target.value));
    } catch (err) {
      e.target.value = active;
      note(err.message, true);
    } finally {
      busy = false;
    }
  });
  action("slide-template", async () => {
    const next = E.scene,
      added = D.template(
        next.width,
        next.height,
        byId("slide-title").value,
        byId("slide-body").value,
      ).layers;
    added.forEach((l, i) => (l.id = "template-" + Date.now() + "-" + i));
    next.layers.push(...added);
    C.validate(next);
    await E.replaceScene(next);
    note(
      "タイトルと本文を追加しました。レイヤーを選択して文字・位置・サイズを変更できます。",
    );
  });
  action("slide-arrow", async () => {
    const next = E.scene;
    next.layers.push({
      id: "arrow-" + Date.now(),
      kind: "arrow",
      name: "矢印",
      x: next.width * 0.2,
      y: next.height * 0.65,
      w: next.width * 0.5,
      h: next.height * 0.1,
      rotation: 0,
      opacity: 1,
      fill: "#000000",
      stroke: "#000000",
      strokeWidth: 4,
      headSize: 28,
      headPlacement: "tip",
      headStyle: "triangle",
    });
    await E.replaceScene(next);
    note("編集可能な直線と三角の矢羽根を追加しました。");
  });
  action("slide-bold", () => {
    const layer = E.scene.layers.find((l) => l.id === E.selectedId);
    if (layer?.kind !== "text")
      throw Error("先に文字レイヤーを選択してください。");
    E.patchSelected({ bold: !layer.bold });
  });
  byId("font-sample").addEventListener("change", (e) => {
    if (e.target.value) byId("slide-body").value = e.target.value;
  });
  action("deck-save", () => {
    const next = snapshot(),
      text = D.deckText(next);
    save("ironmate-slides.json", text, "application/json");
    deck = next;
    saved = text;
    selectList();
    note("全スライドの編集用JSONを保存しました。");
  });
  byId("deck-open").addEventListener("change", async (e) => {
    if (busy) {
      e.target.value = "";
      return;
    }
    const file = e.target.files[0];
    if (!file) return;
    busy = true;
    try {
      if (file.size > D.LIMIT) throw Error("JSONは32MiB以下です。");
      const next = D.parse(await file.text());
      for (const scene of next.slides) await E.imageSource(scene);
      if (
        D.deckText(snapshot()) !== saved &&
        !confirm("現在の未保存のスライドを置き換えますか？")
      )
        return;
      await commit(next, 0);
      saved = D.deckText(next);
      note("全スライドを読み込みました。");
    } catch (err) {
      note(err.message, true);
    } finally {
      busy = false;
      e.target.value = "";
    }
  });
  action("deck-pptx", async () => {
    note("PPTXを作成しています…");
    const current = snapshot(),
      result = await D.exportPptx(current, imageForLayer);
    save(
      "ironmate-slides.pptx",
      result.data,
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    );
    note(
      `${result.slides}枚のPPTXを保存しました。編集可能な要素 ${result.native}、画像レイヤー ${result.images}。再編集用には全スライドJSONも保存してください。`,
    );
  });
  window.addEventListener("beforeunload", (e) => {
    let dirty = true;
    try {
      dirty = D.deckText(snapshot()) !== saved;
    } catch {}
    if (dirty) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
  window.IronmateSlideEditor = {
    get deck() {
      return snapshot();
    },
    get active() {
      return active;
    },
    get ready() {
      return !busy;
    },
  };
})().catch((e) => {
  const status = document.getElementById("deck-status");
  if (status) {
    status.textContent = e.message;
    status.dataset.error = true;
  }
});
