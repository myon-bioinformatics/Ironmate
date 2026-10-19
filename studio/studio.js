/* Local-only UI; all output passes through the same SVG composition function. */
"use strict";
const C = window.StudioCore,
  $ = (id) => document.getElementById(id),
  copy = C.clone;
let serial = 0,
  tool = "select",
  selected = null,
  template = null,
  dirty = false,
  drag = null,
  paintSerial = 0;
const blank = () => ({
  schema: C.SCHEMA,
  width: 1280,
  height: 720,
  background: "#F8F7F2",
  layers: [],
});
let scene = blank(),
  history = new C.History(scene);
const images = new Map(),
  processed = new Map();
const uid = () => `layer-${Date.now()}-${++serial}`;
const selectedLayer = () => scene.layers.find((l) => l.id === selected);
const message = (text) => {
  $("status").textContent = text;
};
function error(e) {
  $("error-text").textContent = e.message || String(e);
  $("error").dataset.code = e.code || "";
  $("error").showModal();
}
function guarded(fn) {
  return async (...args) => {
    try {
      await fn(...args);
    } catch (e) {
      error(e);
    }
  };
}
function base(kind, x = 80, y = 80, w = 180, h = 120) {
  return { id: uid(), kind, name: kind, x, y, w, h, rotation: 0, opacity: 1 };
}
async function decoded(src) {
  if (!images.has(src))
    images.set(
      src,
      new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          if (img.naturalWidth * img.naturalHeight > 4194304) {
            reject(new Error("画像は4MP以下にしてください"));
            return;
          }
          resolve(img);
        };
        img.onerror = () => reject(new Error("画像を読み込めません"));
        img.src = src;
      }),
    );
  return images.get(src);
}
async function prepare(doc) {
  const sources = new Map();
  for (const l of doc.layers.filter((l) => l.kind === "image")) {
    const key = l.src + ":" + l.cell + ":" + l.levels;
    if (processed.has(key)) {
      sources.set(key, processed.get(key));
      continue;
    }
    const img = await decoded(l.src);
    if (l.cell === 1 && l.levels === 256) {
      processed.set(key, l.src);
      sources.set(key, l.src);
      continue;
    }
    const canvas = document.createElement("canvas");
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(img, 0, 0);
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height);
    data.data.set(
      C.mosaicRGBA(data.data, canvas.width, canvas.height, l.cell, l.levels),
    );
    ctx.putImageData(data, 0, 0);
    processed.set(key, canvas.toDataURL("image/png"));
    sources.set(key, processed.get(key));
    // Processed previews are disposable; the immutable source always remains in JSON.
    if (processed.size > 16) processed.delete(processed.keys().next().value);
  }
  return (l) => sources.get(l.src + ":" + l.cell + ":" + l.levels) || l.src;
}
function selectionSVG(l) {
  return `<g class="selection" transform="translate(${l.x} ${l.y}) rotate(${l.rotation} ${l.w / 2} ${l.h / 2})"><rect width="${l.w}" height="${l.h}" fill="none" stroke="#126fef" stroke-width="2" stroke-dasharray="8 5"/><rect class="handle" data-handle="resize" x="${l.w - 9}" y="${l.h - 9}" width="18" height="18" rx="3" fill="#126fef" stroke="white" stroke-width="2"/></g>`;
}
function updateHistoryTimeline() {
  const list = $("history-list");
  list.replaceChildren();
  history.items.forEach((state, index) => {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = (index === history.index ? "● " : "○ ") +
      "状態 " + (index + 1) + " / " + state.layers.length + "レイヤー";
    button.setAttribute("aria-current", index === history.index ? "step" : "false");
    button.onclick = () => {
      history.index = index;
      scene = history.current;
      selected = null;
      dirty = true;
      render().catch(error);
    };
    row.append(button);
    list.append(row);
  });
}
function updateInspector() {
  const l = selectedLayer();
  $("selection").textContent = l ? `${l.name || l.kind}` : "レイヤーを選択";
  for (const f of ["x", "y", "w", "h", "rotation", "opacity"]) {
    $(f).disabled = !l;
    $(f).value = l?.[f] ?? "";
  }
  $("monochrome").disabled = !["text", "image"].includes(l?.kind);
  $("monochrome").checked = l?.mono ?? false;
  $("sampling").disabled = l?.kind !== "image";
  $("sampling").value = l?.sampling ?? "pixelated";
  $("arrow-placement").disabled = l?.kind !== "arrow";
  $("arrow-placement").value = l?.headPlacement ?? "tip";
  $("arrow-style").disabled = l?.kind !== "arrow";
  $("arrow-style").value =
    l?.kind === "arrow" ? (l.headStyle ?? "triangle") : "beginner";
  if (l?.kind === "clock")
    $("clock-time").value =
      String(l.hour).padStart(2, "0") + ":" + String(l.minute).padStart(2, "0");
  $("font-family").disabled = l?.kind !== "text";
  $("font-family").value = l?.font ?? "sans";
  $("font-size").disabled = l?.kind !== "text";
  $("font-size").value = l?.fontSize ?? 48;
  $("cell").disabled = l?.kind !== "image";
  $("cell").value = l?.cell ?? 1;
  $("cell-value").textContent = `${l?.cell ?? 1} px`;
  $("levels").disabled = !["image", "heatmap"].includes(l?.kind);
  $("levels").value = l?.levels || 256;
  $("levels-value").textContent =
    l?.kind === "heatmap" && !l.levels ? "連続" : (l?.levels ?? 256);
  $("value-labels").disabled = l?.kind !== "heatmap";
  $("value-labels").checked = l?.labels ?? true;
  $("continuous").disabled = l?.kind !== "heatmap";
  for (const id of ["delete", "duplicate", "front", "back", "custom"])
    $(id).disabled = !l;
  $("undo").disabled = history.index === 0;
  $("redo").disabled = history.index === history.items.length - 1;
  $("size-note").textContent = `${scene.width} × ${scene.height}`;
  $("canvas-width").value = scene.width;
  $("canvas-height").value = scene.height;
  $("transparent").checked = scene.background === "none";
  if (scene.background !== "none") $("background").value = scene.background;
  updateHistoryTimeline();
  $("layers").replaceChildren();
  for (const layer of [...scene.layers].reverse()) {
    const button = document.createElement("button");
    button.textContent = layer.name || layer.kind;
    button.dataset.layerId = layer.id;
    if (layer.id === selected) button.classList.add("active");
    button.onclick = () => {
      selected = layer.id;
      if (layer.kind === "text") $("text").value = layer.text;
      render();
    };
    $("layers").append(button);
  }
}
async function render() {
  const n = ++paintSerial;
  const doc = copy(scene);
  const imageSource = await prepare(doc);
  if (n !== paintSerial) return;
  let svg = C.svg(doc, imageSource);
  const l = doc.layers.find((l) => l.id === selected);
  if (l) svg = svg.replace("</svg>", selectionSVG(l) + "</svg>");
  $("board").innerHTML = svg;
  $("board").style.aspectRatio = `${doc.width} / ${doc.height}`;
  updateInspector();
}
function change(fn) {
  const next = copy(scene);
  fn(next);
  C.validate(next);
  history.commit(next);
  scene = next;
  dirty = true;
  if (!selectedLayer()) selected = null;
  render().catch(error);
}
function add(layer) {
  if (scene.layers.length >= 100) throw new Error("レイヤーは100件までです");
  selected = layer.id;
  change((doc) => doc.layers.push(layer));
  message(`${layer.name || layer.kind}を追加しました`);
}
function setTool(value) {
  tool = value;
  document
    .querySelectorAll("[data-tool]")
    .forEach((b) => b.classList.toggle("active", b.dataset.tool === value));
}
function textLayer(text, x, y) {
  const size = 48,
    lines = text.split("\n");
  return {
    ...base(
      "text",
      x,
      y,
      Math.min(
        700,
        Math.max(
          120,
          Math.max(...lines.map((s) => Array.from(s).length)) * size,
        ),
      ),
      Math.max(70, lines.length * size * 1.3),
    ),
    name: "文字 / " + text.slice(0, 12),
    text,
    fill: $("fill").value,
    fontSize: size,
    font: $("font-family").value,
    mono: true,
  };
}
function place(x, y) {
  if (tool === "stamp") {
    if (template) {
      const l = copy(template);
      l.id = uid();
      l.x = x - l.w / 2;
      l.y = y - l.h / 2;
      add(l);
    } else add(textLayer($("text").value, x, y));
  } else if (tool === "text") add(textLayer($("text").value, x, y));
  else if (tool === "arrow")
    add({
      ...base("arrow", x, y, 200, 80),
      name: "直線＋矢羽根",
      fill: $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 4,
      headSize: 28,
      headPlacement: $("arrow-placement").value,
      headStyle: $("arrow-style").value,
    });
  else if (tool === "clock") {
    const [hour, minute] = $("clock-time").value.split(":").map(Number);
    add({
      ...base("clock", x, y, 160, 160),
      name: "時計 " + $("clock-time").value,
      hour,
      minute,
      fill: $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 3,
    });
  } else
    add({
      ...base(tool, x, y),
      name: { rect: "四角", ellipse: "丸", triangle: "三角" }[tool],
      fill: $("outline").checked ? "none" : $("fill").value,
      stroke: $("stroke").value,
      strokeWidth: 3,
    });
}
function point(e) {
  const svg = $("board").querySelector("svg");
  return new DOMPoint(e.clientX, e.clientY).matrixTransform(
    svg.getScreenCTM().inverse(),
  );
}
$("board").addEventListener(
  "pointerdown",
  guarded(async (e) => {
    if (e.button !== 0) return;
    const p = point(e),
      handle = e.target.closest("[data-handle]"),
      node = e.target.closest("[data-layer]");
    if (tool !== "select") {
      place(p.x, p.y);
      return;
    }
    if (!handle) selected = node?.dataset.layer ?? null;
    const l = selectedLayer();
    if (l) {
      drag = { point: p, layer: copy(l), resize: !!handle, changed: false };
      $("board").setPointerCapture(e.pointerId);
    }
    await render();
  }),
);
$("board").addEventListener("pointermove", (e) => {
  if (!drag) return;
  const p = point(e),
    dx = p.x - drag.point.x,
    dy = p.y - drag.point.y,
    l = selectedLayer();
  if (!l) return;
  const old = drag.layer;
  if (drag.resize) {
    const a = (old.rotation * Math.PI) / 180,
      c = Math.cos(a),
      s = Math.sin(a);
    l.w = Math.max(8, Math.min(8192, old.w + c * dx + s * dy));
    l.h = Math.max(8, Math.min(8192, old.h - s * dx + c * dy));
    const dw = l.w - old.w,
      dh = l.h - old.h;
    l.x = old.x + ((c - 1) * dw) / 2 - (s * dh) / 2;
    l.y = old.y + (s * dw) / 2 + ((c - 1) * dh) / 2;
    if (l.kind === "text")
      l.fontSize = Math.max(
        4,
        Math.min(512, old.fontSize * Math.min(l.w / old.w, l.h / old.h)),
      );
  } else {
    l.x = Math.max(-8192, Math.min(8192, old.x + dx));
    l.y = Math.max(-8192, Math.min(8192, old.y + dy));
  }
  drag.changed = drag.changed || Math.abs(dx) + Math.abs(dy) > 1;
  render().catch(error);
});
function finishDrag() {
  if (drag?.changed) {
    history.commit(scene);
    dirty = true;
    message("位置・サイズを変更しました");
  }
  drag = null;
  updateInspector();
}
$("board").addEventListener("pointerup", finishDrag);
$("board").addEventListener("pointercancel", () => {
  if (drag) {
    Object.assign(selectedLayer(), drag.layer);
    drag = null;
    render().catch(error);
  }
});
for (const button of document.querySelectorAll("[data-tool]"))
  button.onclick = () => setTool(button.dataset.tool);
for (const button of [...$("emojis").children, ...$("kaomojis").children])
  button.onclick = () => {
    $("text").value = button.textContent;
    if (button.textContent === "🔰") $("fill").value = "#000000";
    template = null;
    setTool("stamp");
    $("stamp-note").textContent = `${button.textContent}をキャンバスに押せます`;
  };
$("text").oninput = () => {
  template = null;
};
$("custom").onclick = () => {
  const l = selectedLayer();
  if (l) {
    template = copy(l);
    setTool("stamp");
    $("stamp-note").textContent = `「${l.name || l.kind}」を繰り返し押せます`;
  }
};
$("undo").onclick = () => {
  scene = history.undo();
  dirty = true;
  selected = null;
  render().catch(error);
};
$("redo").onclick = () => {
  scene = history.redo();
  dirty = true;
  selected = null;
  render().catch(error);
};
$("duplicate").onclick = guarded(() => {
  const l = copy(selectedLayer());
  l.id = uid();
  l.x += 24;
  l.y += 24;
  add(l);
});
$("delete").onclick = () => {
  if (selected)
    change((doc) => {
      doc.layers = doc.layers.filter((l) => l.id !== selected);
    });
};
for (const [id, delta] of [
  ["front", 1],
  ["back", -1],
])
  $(id).onclick = () =>
    change((doc) => {
      const i = doc.layers.findIndex((l) => l.id === selected),
        j = Math.max(0, Math.min(doc.layers.length - 1, i + delta));
      if (i >= 0)
        [doc.layers[i], doc.layers[j]] = [doc.layers[j], doc.layers[i]];
    });
for (const f of ["x", "y", "w", "h", "rotation", "opacity"])
  $(f).onchange = guarded(() => {
    if (selectedLayer())
      change((doc) => {
        doc.layers.find((l) => l.id === selected)[f] = Number($(f).value);
      });
  });
$("font-size").onchange = guarded(() => {
  if (selectedLayer()?.kind === "text")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).fontSize = Number(
        $("font-size").value,
      );
    });
});
$("apply-text").onclick = guarded(() => {
  if (!selectedLayer()) return;
  change((doc) => {
    const l = doc.layers.find((l) => l.id === selected);
    if (l.kind === "text") {
      l.text = $("text").value;
      l.font = $("font-family").value;
      l.fill = $("fill").value;
      l.mono = $("monochrome").checked;
    } else if (l.kind === "image") {
      l.fill = $("fill").value;
      l.mono = $("monochrome").checked;
    } else if (
      ["rect", "ellipse", "triangle", "arrow", "clock"].includes(l.kind)
    ) {
      l.fill = $("outline").checked ? "none" : $("fill").value;
      l.stroke = $("stroke").value;
    }
  });
});
$("font-family").onchange = () => {
  if (selectedLayer()?.kind === "text")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).font = $("font-family").value;
    });
};
$("monochrome").onchange = () => {
  if (["text", "image"].includes(selectedLayer()?.kind))
    change((doc) => {
      const l = doc.layers.find((l) => l.id === selected);
      l.mono = $("monochrome").checked;
      l.fill = $("fill").value;
    });
};
$("sampling").onchange = () => {
  if (selectedLayer()?.kind === "image")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).sampling = $("sampling").value;
    });
};
$("arrow-style").onchange = () => {
  if (selectedLayer()?.kind === "arrow")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).headStyle =
        $("arrow-style").value;
    });
};
$("arrow-placement").onchange = () => {
  if (selectedLayer()?.kind === "arrow")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).headPlacement =
        $("arrow-placement").value;
    });
};
$("clock-time").onchange = guarded(() => {
  if (selectedLayer()?.kind === "clock")
    change((doc) => {
      const l = doc.layers.find((l) => l.id === selected);
      [l.hour, l.minute] = $("clock-time").value.split(":").map(Number);
    });
});
for (const [id, field] of [
  ["cell", "cell"],
  ["levels", "levels"],
])
  $(id).onchange = guarded(() => {
    if (selectedLayer())
      change((doc) => {
        doc.layers.find((l) => l.id === selected)[field] = Number($(id).value);
      });
  });
$("value-labels").onchange = () => {
  if (selectedLayer()?.kind === "heatmap")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).labels =
        $("value-labels").checked;
    });
};
$("continuous").onclick = () => {
  if (selectedLayer()?.kind === "heatmap")
    change((doc) => {
      doc.layers.find((l) => l.id === selected).levels = 0;
    });
};
$("background").onchange = () =>
  change((doc) => {
    doc.background = $("background").value;
  });
$("transparent").onchange = () =>
  change((doc) => {
    doc.background = $("transparent").checked ? "none" : $("background").value;
  });
$("canvas-size").onclick = guarded(() =>
  change((doc) => {
    doc.width = Number($("canvas-width").value);
    doc.height = Number($("canvas-height").value);
  }),
);
function download(name, data, type) {
  const url = URL.createObjectURL(
    data instanceof Blob ? data : new Blob([data], { type }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  message(`${name}を書き出しました`);
}
$("save-workspace").onclick = guarded(async () => {
  const serialized = C.workspaceText(history);
  download("ironmate-workspace.json", serialized, "application/json");
  message("作業履歴を保存しました");
});
$("open-workspace").onchange = guarded(async () => {
  const input = $("open-workspace");
  const file = input.files?.[0];
  if (!file) return;
  try {
    if (file.size > C.WORKSPACE_MAX_BYTES) throw new Error("作業履歴は32MiB以下にしてください");
    const next = C.workspaceHistory(await file.text());
    // Decode every state's images before replacing the editable workspace.
    const sources = new Set(next.items.flatMap(state => state.layers
      .filter(layer => layer.kind === "image").map(layer => layer.src)));
    for (const src of sources) await decoded(src);
    history = next;
    scene = next.current;
    selected = null;
    dirty = true;
    await render();
    message("作業履歴を復元しました");
  } finally { input.value = ""; }
});
$("trim-history").onclick = guarded(async () => {
  if (!window.confirm("現在の状態だけ残して、過去の作業履歴を削除しますか？")) return;
  history = new C.History(scene);
  dirty = true;
  await render();
  message("現在の画像・レイヤーを残して履歴を整理しました");
});
$("save").onclick = () => {
  download(
    "ironmate-scene.json",
    JSON.stringify(C.validate(scene), null, 2),
    "application/json",
  );
  dirty = false;
};
$("svg").onclick = guarded(async () => {
  const doc = copy(scene),
    imageSource = await prepare(doc);
  download(
    "ironmate-image.svg",
    C.svg(doc, imageSource, Number($("export-scale").value)),
    "image/svg+xml",
  );
});
async function pngBlob(scale = Number($("export-scale").value)) {
  const doc = copy(scene),
    imageSource = await prepare(doc);
  const size = C.outputSize(doc, scale);
  const source = C.svg(doc, imageSource, scale),
    url = URL.createObjectURL(new Blob([source], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise((resolve, reject) => {
      img.onload = resolve;
      img.onerror = () => reject(new Error("SVGの画像化に失敗しました"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;
    canvas.getContext("2d").drawImage(img, 0, 0);
    return await new Promise((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(new Error("PNG出力に失敗しました"))),
        "image/png",
      ),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}
$("png").onclick = guarded(async () =>
  download("ironmate-image.png", await pngBlob(), "image/png"),
);
let clipboardPayload = null;
function showBase64() {
  if (clipboardPayload)
    $("base64-text").value = clipboardPayload[$("base64-mode").value];
}
$("base64").onclick = guarded(async () => {
  clipboardPayload = C.pngPayload(
    new Uint8Array(await (await pngBlob()).arrayBuffer()),
  );
  showBase64();
  $("base64-status").textContent =
    `PNG ${clipboardPayload.bytes.toLocaleString()} bytes ・ 32MiB以下`;
  $("base64-dialog").showModal();
});
$("base64-mode").onchange = showBase64;
$("copy-base64").onclick = async () => {
  try {
    await navigator.clipboard.writeText($("base64-text").value);
    $("base64-status").textContent =
      "コピーしました。Flutterのクリップボード欄へ貼り付けられます。";
  } catch {
    $("base64-text").focus();
    $("base64-text").select();
    $("base64-status").textContent =
      "自動コピーが使えません。選択した文字をコピーするか、テキスト保存を使ってください。";
  }
};
$("download-base64").onclick = () =>
  download("ironmate-image.base64.txt", $("base64-text").value, "text/plain");
$("open").onchange = guarded(async () => {
  const file = $("open").files[0];
  if (!file) return;
  if (file.size > 20000000) throw new Error("JSONは20MB以下にしてください");
  const next = C.validate(JSON.parse(await file.text()));
  await prepare(next);
  // Loading is an undoable edit; an existing composition is never silently lost.
  history.commit(next);
  scene = next;
  selected = null;
  dirty = false;
  await render();
  message("JSONを読み込みました（戻すで前の編集へ戻れます）");
  $("open").value = "";
});
// Keep acquisition (picker, camera capture, clipboard) separate from normalization.
async function importImageBytes(bytes, declaredMime, name = "取り込み画像") {
  if (!(bytes instanceof Uint8Array) || !bytes.length || bytes.length > 32 * 1024 * 1024)
    throw new Error("画像は32MiB以下にしてください");
  const mime = sniffImageMime(bytes);
  if (!mime || (declaredMime && declaredMime.toLowerCase() !== mime))
    throw new Error("画像形式またはMIME宣言が実データと一致しません");
  const blob = new Blob([bytes], { type: mime });
  const url = URL.createObjectURL(blob);
  try {
    const img = await decoded(url);
    const cv = document.createElement("canvas");
    cv.width = img.naturalWidth;
    cv.height = img.naturalHeight;
    cv.getContext("2d").drawImage(img, 0, 0);
    const w = Math.min(700, scene.width * 0.65);
    add({
      ...base("image", 80, 90, w, (w * img.naturalHeight) / img.naturalWidth),
      name, src: cv.toDataURL("image/png"),
      cell: 1, levels: 256, sampling: "pixelated", mono: false,
    });
    setTool("select");
    message(mime + "を取り込みました");
  } finally {
    URL.revokeObjectURL(url);
    images.delete(url);
  }
}
function sniffImageMime(bytes) {
  if ([137,80,78,71,13,10,26,10].every((v,i)=>bytes[i]===v)) return "image/png";
  if (bytes[0]===255&&bytes[1]===216&&bytes[2]===255) return "image/jpeg";
  if (bytes.length>=12&&[82,73,70,70].every((v,i)=>bytes[i]===v)
      &&[87,69,66,80].every((v,i)=>bytes[i+8]===v)) return "image/webp";
  return null;
}
function imageBase64(text, maxBytes = 32 * 1024 * 1024) {
  let value = text.replace(/^\uFEFF/, "").trim();
  const header = /^data:([a-z0-9.+-]+\/[a-z0-9.+-]+)?(?:;[a-z0-9.+-]+=[a-z0-9.+-]+)*;base64,/i.exec(value);
  let mime = null;
  if (header) {
    mime = header[1]?.toLowerCase() || null;
    if (mime === "image/jpg") mime = "image/jpeg";
    value = value.slice(header[0].length);
  } else if (/^data:/i.test(value)) throw new Error("data URIが不正です");
  if (mime && !["image/png", "image/jpeg", "image/webp"].includes(mime))
    throw new Error("対応していない画像MIMEです");
  const compact = value.replace(/\s+/g, "");
  if (!compact || compact.length > 4 * Math.ceil(maxBytes / 3)
      || compact.length % 4 || !/^[A-Za-z0-9+/]*={0,2}$/.test(compact))
    throw new Error("Base64形式または容量が不正です");
  const size = compact.length / 4 * 3 - (compact.endsWith("==") ? 2 : compact.endsWith("=") ? 1 : 0);
  if (size > maxBytes) throw new Error("画像は残り容量以下にしてください");
  const binary = atob(compact);
  const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
  if (btoa(binary) !== compact)
    throw new Error("Base64のパディングまたは容量が不正です");
  const actual = sniffImageMime(bytes);
  if (!actual || (mime && mime !== actual))
    throw new Error("画像形式またはMIME宣言が実データと一致しません");
  return { bytes, mime: actual };
}
async function importPickedFile(input) {
  const file = input.files?.[0];
  if (!file) return; // A cancelled picker is not a failed import.
  try {
    if (file.size > 32 * 1024 * 1024) throw new Error("画像は32MiB以下にしてください");
    await importImageBytes(new Uint8Array(await file.arrayBuffer()), file.type || null, file.name);
  } finally { input.value = ""; }
}
$("image").onchange = guarded(() => importPickedFile($("image")));
$("camera-image").onchange = guarded(() => importPickedFile($("camera-image")));
$("import-base64-button").onclick = guarded(async () => {
  const { bytes, mime } = imageBase64($("import-base64").value);
  await importImageBytes(bytes, mime, "Base64画像");
});
function clipboardError(code, message, cause) {
  return Object.assign(new Error(message), { code, cause });
}
function clipboardImageText(text) {
  const value = text.replace(/^\uFEFF/, "").trim();
  const explicit = /^data:image(?:\/|[;,]|$)/i.test(value);
  // A raw image signature also makes malformed/oversized Base64 an image error.
  // Inspect only a small prefix; do not decode an unbounded clipboard string.
  const prefix = value.replace(/\s+/g, "").slice(0, 16);
  const rawImage = /^[A-Za-z0-9+/]{16}$/.test(prefix) &&
    sniffImageMime(Uint8Array.from(atob(prefix), c => c.charCodeAt(0)));
  try {
    const payload = imageBase64(value);
    if (sniffImageMime(payload.bytes)) return payload;
    if (explicit) throw new Error("PNG・JPEG・WebP画像ではありません");
  } catch (e) {
    if (explicit || rawImage)
      throw clipboardError("clipboard-invalid-image", "クリップボードの画像テキストが不正です: " + e.message, e);
  }
  return null; // Ordinary text, even if it happens to be valid Base64.
}
$("paste-image").onclick = guarded(async () => {
  const clipboard = navigator.clipboard;
  if (!clipboard || (typeof clipboard.readText !== "function" && typeof clipboard.read !== "function"))
    throw clipboardError("clipboard-unsupported", "このブラウザにはクリップボード読取APIがありません。ファイル選択またはBase64入力を利用してください");
  const failures = [];
  if (typeof clipboard.readText === "function") {
    let text = "";
    try { text = await clipboard.readText(); }
    catch (e) { failures.push(e); }
    const payload = clipboardImageText(text);
    if (payload) {
      // Explicit/recognized image text wins over a possibly stale binary image.
      // Validation/decode failures must not silently import different content.
      try { return await importImageBytes(payload.bytes, payload.mime, "クリップボードBase64"); }
      catch (e) { throw clipboardError("clipboard-invalid-image", e.message, e); }
    }
  }
  if (typeof clipboard.read === "function") {
    let items = [];
    try { items = await clipboard.read(); }
    catch (e) { failures.push(e); }
    for (const item of items) {
      for (const type of item.types.filter(t => ["image/png", "image/jpeg", "image/webp"].includes(t))) {
        try {
          const blob = await item.getType(type);
          if (blob.size > 32 * 1024 * 1024) throw new Error("画像は32MiB以下にしてください");
          return await importImageBytes(new Uint8Array(await blob.arrayBuffer()), type, "クリップボード画像");
        } catch (e) {
          // Other representations/items may still contain a usable image.
          failures.push(e.name === "NotAllowedError" || e.name === "SecurityError" || e.name === "NotSupportedError"
            ? e : clipboardError("clipboard-invalid-image", e.message, e));
        }
      }
    }
  }
  const denied = failures.find(e => ["NotAllowedError", "SecurityError"].includes(e.name));
  if (denied)
    throw clipboardError("clipboard-denied", "クリップボードの読み取りが許可されていません。権限を確認するか、ファイル選択またはBase64入力を利用してください", denied);
  const invalid = failures.find(e => e.code === "clipboard-invalid-image");
  if (invalid) throw invalid;
  if (failures.length) {
    const unsupported = failures.every(e => e.name === "NotSupportedError");
    throw clipboardError(unsupported ? "clipboard-unsupported" : "clipboard-read-failed",
      unsupported ? "このブラウザではクリップボードの読み取りに対応していません" : "クリップボードの取得に失敗しました。再試行するかファイル選択を利用してください", failures[0]);
  }
  throw clipboardError("clipboard-no-image", "クリップボードにPNG・JPEG・WebP画像または画像Base64テキストがありません");
});
function addMatrix(source) {
  add({
    ...base(
      "heatmap",
      80,
      100,
      Math.min(1050, scene.width - 100),
      Math.min(480, scene.height - 120),
    ),
    name: "ヒートマップ",
    ...C.matrix(source),
    source: copy(source),
  });
  setTool("select");
}
$("heatmap").onclick = guarded(() => addMatrix(JSON.parse($("matrix").value)));
$("matrix-file").onchange = guarded(async () => {
  const file = $("matrix-file").files[0];
  if (!file) return;
  if (file.size > 2000000) throw new Error("行列JSONは2MB以下にしてください");
  addMatrix(JSON.parse(await file.text()));
  $("matrix-file").value = "";
});
$("blank").onclick = () => {
  change((doc) => {
    doc.layers = [];
  });
  selected = null;
  message("新しいキャンバス（戻すで復帰できます）");
};
function demo() {
  const doc = blank();
  doc.layers.push({
    ...base("text", 64, 40, 900, 60),
    name: "タイトル",
    text: "小さな部品から、大きな表現へ。",
    fill: "#163B3B",
    fontSize: 38,
  });
  doc.layers.push({
    ...base("text", 68, 105, 900, 40),
    name: "サブタイトル",
    text: "STAMP / COLOR / MATRIX     —     Ironmate Image Studio",
    fill: "#56766D",
    fontSize: 17,
  });
  doc.layers.push({
    ...base("rect", 68, 178, 1144, 430),
    name: "白いカード",
    fill: "#FFFFFF",
    stroke: "#D6DFD2",
    strokeWidth: 1,
  });
  doc.layers.push({
    ...base("heatmap", 90, 220, 680, 350),
    name: "色の行列",
    ...C.matrix({
      z: [
        [2, 3, 4, 6, 8, 9, 10],
        [1, 3, 5, 7, 9, null, 12],
        [2, 4, 6, 8, 10, 12, 14],
        [0, 2, 5, 8, 11, 14, 16],
      ],
      x: ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"],
      y: ["A", "B", "C", "D"],
    }),
  });
  doc.layers.push({
    ...base("triangle", 890, 264, 170, 150),
    name: "三角のスタンプ",
    fill: "none",
    stroke: "#EFBE4C",
    strokeWidth: 7,
  });
  doc.layers.push({
    ...base("text", 910, 294, 140, 90),
    name: "絵文字スタンプ",
    text: "🌱",
    fill: "#163B3B",
    fontSize: 70,
  });
  doc.layers.push({
    ...base("text", 840, 445, 320, 100),
    name: "カスタム文字",
    text: "色を置く。\nかたちが生まれる。",
    fill: "#163B3B",
    fontSize: 25,
  });
  doc.layers.push({
    ...base("text", 70, 646, 1100, 35),
    name: "フッター",
    text: "01  COMPOSE                         02  EXPLORE COLOR                         03  EXPORT",
    fill: "#71887C",
    fontSize: 14,
  });
  return doc;
}
$("demo").onclick = () => {
  const next = demo();
  history.commit(next);
  scene = next;
  selected = null;
  dirty = true;
  render().catch(error);
  message("独自の合成サンプルです。データは説明用の架空値です。");
};
function stampDemo() {
  const d = blank();
  const text = (id, text, x, y, w, h, size, fill) => ({
    ...base("text", x, y, w, h),
    id,
    name: text,
    text,
    fontSize: size,
    fill,
    mono: true,
  });
  d.layers = [
    text(
      "title",
      "STAMP LAB / 色を変えて、重ねる。",
      60,
      45,
      1160,
      70,
      38,
      "#163B3B",
    ),
    {
      ...base("rect", 60, 150, 1160, 420),
      name: "カード",
      fill: "#FFFFFF",
      stroke: "#D6DFD2",
      strokeWidth: 1,
    },
    {
      ...base("clock", 100, 210, 230, 230),
      name: "10:10の時計",
      hour: 10,
      minute: 10,
      fill: "#F8F7F2",
      stroke: "#087D79",
      strokeWidth: 4,
    },
    {
      ...base("arrow", 390, 260, 230, 80),
      name: "直線＋中央の矢羽根",
      headSize: 40,
      headPlacement: "middle",
      headStyle: "beginner",
      fill: "#EFBE4C",
      stroke: "#D59C22",
      strokeWidth: 6,
    },
    text("face", "(・∀・)", 710, 225, 450, 105, 68, "#D05B78"),
    text("emoji", "🌱", 750, 365, 160, 130, 100, "#087D79"),
    text("emoji2", "❤️", 990, 365, 180, 130, 100, "#D05B78"),
    text(
      "footer",
      "CLOCK     →     LINE + TRIANGLE     →     TEXT / EMOJI / KAOMOJI",
      65,
      635,
      1150,
      50,
      18,
      "#56766D",
    ),
  ];
  return d;
}
$("stamp-demo").onclick = () => {
  scene = stampDemo();
  history.commit(scene);
  selected = null;
  dirty = true;
  render().catch(error);
  message("時計も顔文字も、保持した図形・文字を拡大して再描画します。");
};
window.addEventListener("beforeunload", (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = "";
  }
});
// --- Clipboard Shelf ---
const shelfItems = [];
const SHELF_MAX_BYTES = 32 * 1024 * 1024;
let shelfReservedBytes = 0, shelfReservedCount = 0, shelfGeneration = 0;
function shelfRemaining() {
  return SHELF_MAX_BYTES - shelfReservedBytes - shelfItems.reduce((sum, item) => sum + item.size, 0);
}
function checkShelfCapacity(size) {
  if (shelfItems.length + shelfReservedCount >= 20)
    throw new Error("シェルフの項目は最大20件までです");
  if (size > shelfRemaining()) throw new Error("シェルフ全体は32MiB以下にしてください");
}
function shelfTextSize(text) {
  const remaining = shelfRemaining();
  if (text.length > remaining) throw new Error("シェルフ全体は32MiB以下にしてください");
  let size = 0;
  for (const char of text) {
    const code = char.codePointAt(0);
    size += code <= 0x7f ? 1 : code <= 0x7ff ? 2 : code <= 0xffff ? 3 : 4;
    if (size > remaining) throw new Error("シェルフ全体は32MiB以下にしてください");
  }
  return size;
}
function isImageText(text) {
  if (/^data:/i.test(text)) return true;
  let prefix = "";
  for (const char of text) {
    if (!/\s/.test(char)) prefix += char;
    if (prefix.length === 16) break;
  }
  if (prefix.startsWith("iVBORw0KGg") || prefix.startsWith("/9j/")) return true;
  try { return !!sniffImageMime(Uint8Array.from(atob(prefix), c => c.charCodeAt(0))); }
  catch { return false; }
}
function addShelfText(text, label) {
  const value = text.replace(/^\uFEFF/, "").trim();
  if (!value) throw new Error("テキストを入力してください");
  checkShelfCapacity(0);
  if (isImageText(value)) {
    const { bytes, mime } = imageBase64(value, shelfRemaining());
    addShelfItem(bytes, mime, null, label);
  } else addShelfItem(null, null, value, label);
}
function checkShelfGeneration(generation) {
  if (generation !== shelfGeneration) throw new Error("シェルフはクリアされました");
}
async function addShelfBlob(blob, mime, generation) {
  checkShelfGeneration(generation);
  if (blob.type && blob.type.toLowerCase() !== mime)
    throw new Error("画像MIMEが一致しません");
  if (!blob.size) throw new Error("画像が空です");
  checkShelfCapacity(blob.size); // Must precede arrayBuffer(), including in-flight additions.
  shelfReservedBytes += blob.size;
  shelfReservedCount++;
  let bytes;
  try { bytes = new Uint8Array(await blob.arrayBuffer()); }
  finally { shelfReservedBytes -= blob.size; shelfReservedCount--; }
  checkShelfGeneration(generation);
  addShelfItem(bytes, mime, null, "クリップボード画像");
}
async function shelfCopyText(item) {
  if (!item.bytes) return item.rawText;
  // FileReader produces a portable data URI, never the preview's transient blob URL.
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(new Blob([item.bytes], { type: item.mime }));
  });
}
function releaseShelfItem(item) {
  if (item.dataUrl) URL.revokeObjectURL(item.dataUrl);
}
function updateShelfBadge() {
  if ($("shelf-button")) $("shelf-button").textContent = `クリップボード・シェルフ (${shelfItems.length})`;
}
function renderShelf() {
  updateShelfBadge();
  const container = $("shelf-items-container");
  if (!container) return;
  container.replaceChildren();
  if (!shelfItems.length) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "シェルフは空です。「クリップボードから追加」またはテキスト入力からデータを追加できます。";
    container.append(empty);
    return;
  }
  shelfItems.forEach((item, index) => {
    const card = document.createElement("div");
    card.className = "shelf-card";

    const info = document.createElement("div");
    info.className = "shelf-card-info";

    if (item.dataUrl) {
      const img = document.createElement("img");
      img.className = "shelf-thumb";
      img.src = item.dataUrl;
      img.alt = item.label;
      info.append(img);
    }

    const details = document.createElement("div");
    details.className = "shelf-details";
    const title = document.createElement("strong");
    title.textContent = `${index + 1}. ${item.label}`;
    const sub = document.createElement("span");
    sub.textContent = `${item.mime || "text"} ・ ${item.sizeText}`;
    details.append(title, sub);
    info.append(details);

    const actions = document.createElement("div");
    actions.className = "shelf-card-actions";

    if (item.bytes) {
      const btnImport = document.createElement("button");
      btnImport.textContent = "取り込み";
      btnImport.onclick = guarded(async () => {
        await importImageBytes(item.bytes, item.mime, item.label);
        $("shelf-dialog").close();
      });
      actions.append(btnImport);
    }

    const btnCopy = document.createElement("button");
    btnCopy.textContent = "コピー";
    btnCopy.onclick = guarded(async () => {
      await navigator.clipboard.writeText(await shelfCopyText(item));
      if ($("shelf-status")) $("shelf-status").textContent = `「${item.label}」をクリップボードにコピーしました`;
    });
    actions.append(btnCopy);

    const btnDel = document.createElement("button");
    btnDel.textContent = "削除";
    btnDel.onclick = () => {
      const current = shelfItems.indexOf(item);
      if (current !== -1) releaseShelfItem(shelfItems.splice(current, 1)[0]);
      renderShelf();
    };
    actions.append(btnDel);

    card.append(info, actions);
    container.append(card);
  });
}
function addShelfItem(bytes, mime, rawText, label = "シェルフ項目") {
  // This is also the final gate for binary callers and rechecks after async reads.
  const size = bytes ? bytes.length : shelfTextSize(rawText || "");
  checkShelfCapacity(size);
  if (bytes) {
    const actual = bytes instanceof Uint8Array && sniffImageMime(bytes);
    if (!actual || (mime && mime.toLowerCase() !== actual))
      throw new Error("画像形式またはMIME宣言が実データと一致しません");
    mime = actual;
    rawText = null; // Avoid retaining another full Base64 copy of an image.
  } else if (mime || isImageText((rawText || "").trim())) {
    throw new Error("画像入力には検証済みデータが必要です");
  }
  let dataUrl = null;
  if (bytes && mime) {
    const blob = new Blob([bytes], { type: mime });
    dataUrl = URL.createObjectURL(blob);
  }
  const sizeText = bytes ? `${bytes.length.toLocaleString()} bytes` : `${(rawText || "").length} chars`;
  shelfItems.unshift({
    id: uid(),
    bytes,
    mime,
    rawText,
    dataUrl,
    label,
    sizeText,
    size,
  });
  renderShelf();
}
if ($("shelf-button")) {
  $("shelf-button").onclick = () => {
    renderShelf();
    $("shelf-dialog").showModal();
  };
}
if ($("shelf-clear")) {
  $("shelf-clear").onclick = () => {
    shelfGeneration++;
    shelfItems.forEach(releaseShelfItem);
    shelfItems.length = 0;
    renderShelf();
    if ($("shelf-status")) $("shelf-status").textContent = "シェルフをクリアしました";
  };
}
if ($("shelf-paste-clip")) {
  $("shelf-paste-clip").onclick = guarded(async () => {
    if (!navigator.clipboard) throw new Error("Clipboard APIが使用できません");
    const generation = shelfGeneration;
    checkShelfCapacity(0);
    let text = "";
    if (navigator.clipboard.readText) {
      // A denied text permission may still allow a binary clipboard image.
      try { text = await navigator.clipboard.readText(); } catch { /* try binary API */ }
      checkShelfGeneration(generation);
      if (text.trim() && isImageText(text.trim())) {
        addShelfText(text, "クリップボードBase64");
        if ($("shelf-status")) $("shelf-status").textContent = "クリップボードのBase64画像を追加しました";
        return;
      }
    }
    if (navigator.clipboard.read) {
      let items = [];
      try { items = await navigator.clipboard.read(); }
      catch (e) { if (!text.trim()) throw e; }
      checkShelfGeneration(generation);
      for (const item of items) {
        const type = item.types.find(t => ["image/png", "image/jpeg", "image/webp"].includes(t));
        if (type) {
          const blob = await item.getType(type);
          await addShelfBlob(blob, type, generation);
          if ($("shelf-status")) $("shelf-status").textContent = "クリップボードの画像を追加しました";
          return;
        }
        if (item.types.some(t => t.startsWith("image/")))
          throw new Error("対応していない画像MIMEです");
      }
    }
    if (text.trim()) {
      addShelfText(text, "クリップボードテキスト");
      if ($("shelf-status")) $("shelf-status").textContent = "テキスト項目を追加しました";
    } else {
      throw new Error("クリップボードに画像またはテキストがありません");
    }
  });
}
if ($("shelf-add-text")) {
  $("shelf-add-text").onclick = guarded(async () => {
    const val = ($("shelf-input-text").value || "").trim();
    if (!val) throw new Error("テキストを入力してください");
    addShelfText(val, "入力項目");
    if ($("shelf-status")) $("shelf-status").textContent = "項目を追加しました";
    $("shelf-input-text").value = "";
  });
}

// Read-only snapshots and export entry point also make browser regression tests observable.
window.IronmateStudio = {
  get scene() {
    return copy(scene);
  },
  get ready() {
    return render();
  },
  pngBlob,
  get shelfItems() { return shelfItems.map(item => ({ ...item })); },
  addShelfItem,
};
scene = demo();
history = new C.History(scene);
render().catch(error);
