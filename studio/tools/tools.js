"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    C = IronmateTools,
    catalog = IronmateCatalog;
  let grid,
    previous = null,
    images = [];
  const status = (text, error = false) => {
    $("message").textContent = text;
    $("message").dataset.error = error;
  };
  const action = (id, fn) =>
    $(id).addEventListener("click", () =>
      Promise.resolve()
        .then(fn)
        .catch((e) => status(e.message, true)),
    );
  const choose = (id, items) => {
    $(id).replaceChildren(
      ...items.map(([value, text]) => new Option(text, value)),
    );
  };
  choose(
    "mask",
    catalog.masks.map((x) => [
      x,
      {
        triangle: "三角",
        diamond: "ひし形",
        cloud: "雲",
        circle: "丸",
        rock: "岩",
      }[x],
    ]),
  );
  $("mask").value = "cloud";
  choose(
    "size",
    catalog.sizes.map((x) => [x, `${x} × ${x}`]),
  );
  $("size").value = 32;
  choose(
    "effect",
    catalog.effects.map((x) => [
      x,
      {
        normal: "通常",
        shadow: "影",
        highlight: "ハイライト",
        outline: "輪郭",
      }[x],
    ]),
  );
  choose(
    "palette",
    Object.keys(catalog.palettes).map((x) => [
      x,
      `${x} / ${catalog.labels[x]}`,
    ]),
  );
  function draw() {
    const canvas = $("grid");
    canvas.width = grid.width;
    canvas.height = grid.height;
    const ctx = canvas.getContext("2d"),
      data = ctx.createImageData(grid.width, grid.height);
    grid.pixels.forEach((row, y) =>
      row.forEach((i, x) => {
        const color = grid.colors[i];
        for (let k = 0; k < 4; k++)
          data.data[(y * grid.width + x) * 4 + k] = parseInt(
            color.slice(1 + k * 2, 3 + k * 2),
            16,
          );
      }),
    );
    ctx.putImageData(data, 0, 0);
    // CSS scales the canvas; the backing pixels remain the original grid.
    $("width").value = grid.width;
    $("height").value = grid.height;
    $("grid-info").textContent =
      `${grid.width} × ${grid.height} cells · ${grid.colors.length} colors`;
    choose(
      "ink",
      grid.colors.map((c, i) => [i, `${i} / ${c}`]),
    );
    $("ink").value = Math.min(1, grid.colors.length - 1);
    $("base64-output").value = "";
  }
  function update(value) {
    const next = C.canonical(value);
    previous = grid;
    grid = next;
    draw();
  }
  function generate() {
    const mask = $("mask").value,
      effect = $("effect").value,
      size = Number($("size").value),
      palette = $("palette").value;
    const rows = catalog.grids[`${mask}/${effect}/${size}`];
    update({
      schema: "ironmate-pixel-grid/1",
      mask,
      effect,
      palette,
      width: size,
      height: size,
      colors: catalog.palettes[palette],
      pixels: rows.map((r) => Array.from(r, Number)),
      resampling: "procedural_mask",
    });
    status(
      "Python版のプリセットから生成しました。クリックで色番号を編集できます。",
    );
  }
  const save = (data, type, name) => {
    const url = URL.createObjectURL(new Blob([data], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  };
  async function png() {
    const scale = Number($("scale").value),
      g = C.canonical(grid),
      width = g.width * scale,
      height = g.height * scale;
    // Direct RGBA encoding preserves hidden RGB in transparent cells, unlike Canvas exports.
    if (!globalThis.CompressionStream)
      throw Error(
        "PNG出力にはCompressionStream対応ブラウザが必要です。JSON / SVG保存を利用できます。",
      );
    const bytes = new Uint8Array(height * (1 + 4 * width));
    for (let y = 0; y < height; y++)
      for (let x = 0; x < width; x++) {
        const color =
          g.colors[g.pixels[Math.floor(y / scale)][Math.floor(x / scale)]];
        for (let k = 0; k < 4; k++)
          bytes[y * (width * 4 + 1) + 1 + x * 4 + k] = parseInt(
            color.slice(1 + 2 * k, 3 + 2 * k),
            16,
          );
      }
    const compressed = await new Response(
      new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate")),
    ).arrayBuffer();
    const ihdr = new Uint8Array(13),
      view = new DataView(ihdr.buffer);
    view.setUint32(0, width);
    view.setUint32(4, height);
    ihdr[8] = 8;
    ihdr[9] = 6;
    const metadata =
      "ironmate\0" +
      JSON.stringify(C.pngHeader(g)).replace(
        /[\u007f-\uffff]/g,
        (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"),
      );
    return new Blob(
      [
        new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]),
        C.pngChunk("IHDR", ihdr),
        C.pngChunk("tEXt", new TextEncoder().encode(metadata)),
        C.pngChunk("IDAT", new Uint8Array(compressed)),
        C.pngChunk("IEND", new Uint8Array()),
      ],
      { type: "image/png" },
    );
  }
  action("generate", generate);
  action("resize", () => {
    update(C.resize(grid, Number($("width").value), Number($("height").value)));
    status("最近傍でサイズ変更しました。縮小は不可逆です。");
  });
  action("recolor", () => {
    if (grid.colors.length > 5)
      throw Error("配色IDの置換は5役割までのグリッドに対応します。");
    update({
      ...grid,
      palette: $("palette").value,
      colors: catalog.palettes[$("palette").value],
    });
    status("色番号を保持して配色を変更しました。");
  });
  action("undo-grid", () => {
    if (previous) {
      [grid, previous] = [previous, grid];
      draw();
      status("ひとつ前の状態に戻しました。");
    }
  });
  action("grid-json", () =>
    save(
      JSON.stringify(grid, null, 2),
      "application/json",
      "ironmate-grid.json",
    ),
  );
  action("grid-svg", () =>
    save(
      C.svg(grid, Number($("scale").value)),
      "image/svg+xml",
      "ironmate-grid.svg",
    ),
  );
  action("grid-png", async () =>
    save(await png(), "image/png", "ironmate-grid.png"),
  );
  action("grid-base64", async () => {
    const blob = await png(),
      bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let i = 0; i < bytes.length; i += 16384)
      binary += String.fromCharCode(...bytes.subarray(i, i + 16384));
    $("base64-output").value = "data:image/png;base64," + btoa(binary);
    status(
      `PNG ${blob.size.toLocaleString()} bytes / data URI ${C.base64Length(blob.size, true).toLocaleString()}文字。選択してコピーできます。`,
    );
  });
  $("grid").addEventListener("click", (e) => {
    const bounds = e.currentTarget.getBoundingClientRect(),
      x = Math.min(
        grid.width - 1,
        Math.floor(((e.clientX - bounds.left) * grid.width) / bounds.width),
      ),
      y = Math.min(
        grid.height - 1,
        Math.floor(((e.clientY - bounds.top) * grid.height) / bounds.height),
      ),
      ink = $("ink").value;
    const next = C.canonical(grid);
    next.pixels[y][x] = Number(ink);
    next.resampling = "edited";
    update(next);
    $("ink").value = ink;
    status("セルを編集しました。");
  });
  $("grid-file").addEventListener("change", async (e) => {
    try {
      const file = e.target.files[0];
      if (!file) return;
      if (file.size > 4 * 1024 * 1024) throw Error("JSONは4MiB以下です。");
      update(JSON.parse(await file.text()));
      status("グリッドJSONを読み込みました。");
    } catch (err) {
      status(err.message, true);
    } finally {
      e.target.value = "";
    }
  });
  $("capacity-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f)
      $("capacity-result").textContent =
        `${f.name}: ${f.size.toLocaleString()} bytes → 標準Base64 ${C.base64Length(f.size).toLocaleString()}文字 / PNG data URIなら ${C.base64Length(f.size, true).toLocaleString()}文字。画像かどうかの判定・圧縮後サイズの推定はしません。`;
  });
  let imageGeneration = 0;
  $("images").addEventListener("change", async (e) => {
    const generation = ++imageGeneration,
      files = Array.from(e.target.files);
    if (!files.length) return;
    $("digest-png").disabled = true;
    $("digest-html").disabled = true;
    try {
      if (
        files.length > 20 ||
        files.some((f) => f.size > 8 * 1024 * 1024) ||
        files.reduce((s, f) => s + f.size, 0) > 32 * 1024 * 1024
      )
        throw Error("画像は20枚、1枚8MiB、合計32MiB以下です。");
      const next = [];
      for (const file of files) {
        if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
          throw Error("PNG / JPEG / WebPを選んでください。");
        const url = URL.createObjectURL(file),
          image = new Image();
        try {
          image.src = url;
          await image.decode();
          if (image.naturalWidth * image.naturalHeight > 4194304)
            throw Error("1画像4MP以下です。");
          const ratio = Math.min(
              1,
              512 / Math.max(image.naturalWidth, image.naturalHeight),
            ),
            canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(image.naturalWidth * ratio));
          canvas.height = Math.max(1, Math.round(image.naturalHeight * ratio));
          canvas
            .getContext("2d")
            .drawImage(image, 0, 0, canvas.width, canvas.height);
          next.push({
            name: file.name,
            src: canvas.toDataURL("image/png"),
            canvas,
          });
        } finally {
          URL.revokeObjectURL(url);
        }
      }
      if (generation !== imageGeneration) return;
      images = next;
      $("image-list").replaceChildren(
        ...images.map((item) => {
          const figure = document.createElement("figure"),
            image = new Image(),
            caption = document.createElement("figcaption");
          image.src = item.src;
          image.alt = item.name;
          caption.textContent = item.name;
          figure.append(image, caption);
          return figure;
        }),
      );
      status(
        `${images.length}枚を読み込みました。表示用サムネイルに縮小しています。`,
      );
    } catch (err) {
      if (generation === imageGeneration) status(err.message, true);
    } finally {
      if (generation === imageGeneration) {
        $("digest-png").disabled = !images.length;
        $("digest-html").disabled = !images.length;
      }
      e.target.value = "";
    }
  });
  action("digest-png", async () => {
    const columns = Number($("columns").value),
      canvas = document.createElement("canvas");
    canvas.width = columns * 288;
    canvas.height = Math.ceil(images.length / columns) * 260;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#f2f6f3";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "14px sans-serif";
    images.forEach((item, i) => {
      const x = (i % columns) * 288,
        y = Math.floor(i / columns) * 260,
        ratio = Math.min(256 / item.canvas.width, 210 / item.canvas.height);
      ctx.drawImage(
        item.canvas,
        x + 16 + (256 - item.canvas.width * ratio) / 2,
        y + 12 + (210 - item.canvas.height * ratio) / 2,
        item.canvas.width * ratio,
        item.canvas.height * ratio,
      );
      ctx.fillStyle = "#183d42";
      ctx.fillText(item.name, x + 16, y + 244, 256);
    });
    const blob = await new Promise((resolve) =>
      canvas.toBlob(resolve, "image/png"),
    );
    if (!blob) throw Error("一覧PNGを生成できませんでした。");
    save(blob, "image/png", "ironmate-digest.png");
  });
  action("digest-html", () => {
    const columns = Number($("columns").value),
      html = `<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'"><title>Ironmate Image Digest</title><style>body{font:14px system-ui;background:#f2f6f3;color:#183d42;margin:24px}.grid{display:grid;grid-template-columns:repeat(${columns},minmax(0,1fr));gap:16px}figure{margin:0;padding:16px;background:white;overflow-wrap:anywhere}img{width:100%;height:210px;object-fit:contain}@media(max-width:600px){.grid{grid-template-columns:1fr}}</style><h1>Ironmate Image Digest</h1><div class="grid">${images.map((i) => `<figure><img src="${i.src}" alt="${C.esc(i.name)}"><figcaption>${C.esc(i.name)}</figcaption></figure>`).join("")}</div></html>`;
    save(html, "text/html", "ironmate-digest.html");
  });
  generate();
  window.IronmateWorkbench = {
    get grid() {
      return C.canonical(grid);
    },
    png,
  };
})();
