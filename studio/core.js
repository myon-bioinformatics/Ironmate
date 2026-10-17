/* Independent composition model. No DOM, network, framework or Dart dependency. */
(function (root) {
  "use strict";
  const SCHEMA = "ironmate-image-studio/1";
  const PALETTE = ["#440154", "#3B528B", "#21918C", "#5EC962", "#FDE725"];
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const escape = (x) =>
    String(x).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&apos;",
        })[c],
    );
  const num = (v, lo, hi) =>
    typeof v === "number" && Number.isFinite(v) && v >= lo && v <= hi;
  const color = (c) =>
    typeof c === "string" && /^(#[0-9a-f]{6}|none)$/i.test(c);
  const fail = (message) => {
    throw new Error(message);
  };
  function heatColor(v, lo, hi, levels = 0) {
    if (v === null) return "none";
    if (
      ![v, lo, hi].every(Number.isFinite) ||
      lo > hi ||
      !Number.isInteger(levels) ||
      (levels !== 0 && (levels < 2 || levels > 256))
    )
      fail("色の範囲または段階数が不正です");
    let t = hi === lo ? 0.5 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    if (levels) t = Math.round(t * (levels - 1)) / (levels - 1);
    const p = t * 4,
      i = Math.min(3, Math.floor(p));
    const a = PALETTE[i].match(/\w\w/g).map((x) => parseInt(x, 16));
    const b = PALETTE[i + 1].match(/\w\w/g).map((x) => parseInt(x, 16));
    return (
      "#" +
      a
        .map((x, j) =>
          Math.round(x + (b[j] - x) * (p - i))
            .toString(16)
            .padStart(2, "0"),
        )
        .join("")
        .toUpperCase()
    );
  }
  function matrix(source) {
    let t;
    if (Array.isArray(source)) t = { z: source };
    else if (Array.isArray(source?.data)) {
      const traces = source.data.filter((t) => t.type === "heatmap");
      if (traces.length !== 1) fail("heatmapトレースは1つにしてください");
      t = traces[0];
    } else t = source;
    const z = t?.z,
      cols = z?.[0]?.length;
    if (
      !Array.isArray(z) ||
      !cols ||
      z.length * cols > 4096 ||
      z.some((r) => !Array.isArray(r) || r.length !== cols)
    )
      fail("1〜4096セルの長方形の数値行列が必要です");
    const values = z.flat().filter((v) => v !== null);
    if (
      values.some(
        (v) =>
          !Number.isFinite(v) ||
          (Number.isInteger(v) && !Number.isSafeInteger(v)),
      )
    )
      fail("有限の数値またはnullを指定してください（巨大な整数は非対応）");
    const low = t.zmin ?? (values.length ? Math.min(...values) : 0),
      high = t.zmax ?? (values.length ? Math.max(...values) : 1);
    if ([low, high].some(v => !Number.isFinite(v) || (Number.isInteger(v) && !Number.isSafeInteger(v))))
      fail("色の範囲には有限の安全な数値を指定してください");
    heatColor(low, low, high);
    const xlabels = t.x ?? Array.from({ length: cols }, (_, i) => i),
      ylabels = t.y ?? Array.from({ length: z.length }, (_, i) => i);
    if (
      !Array.isArray(xlabels) ||
      !Array.isArray(ylabels) ||
      xlabels.length !== cols ||
      ylabels.length !== z.length
    )
      fail("軸ラベルの数が一致しません");
    return {
      z: clone(z),
      xlabels: clone(xlabels),
      ylabels: clone(ylabels),
      low,
      high,
      levels: 0,
      labels: true,
    };
  }
  function validate(scene) {
    if (
      scene?.schema !== SCHEMA ||
      !Number.isInteger(scene.width) ||
      !Number.isInteger(scene.height) ||
      !num(scene.width, 64, 4096) ||
      !num(scene.height, 64, 4096) ||
      scene.width * scene.height > 4194304 ||
      !color(scene.background) ||
      !Array.isArray(scene.layers) ||
      scene.layers.length > 100
    )
      fail("シーンの形式・サイズが不正です（最大100レイヤー、4MP）");
    const ids = new Set();
    let imageBytes = 0;
    for (const l of scene.layers) {
      if (
        !l ||
        typeof l.id !== "string" ||
        l.id.length > 100 ||
        ids.has(l.id) ||
        !["rect", "ellipse", "triangle", "text", "image", "heatmap"].includes(
          l.kind,
        )
      )
        fail("レイヤーのIDまたは種類が不正です");
      ids.add(l.id);
      for (const f of ["x", "y"])
        if (!num(l[f], -8192, 8192)) fail("位置が不正です");
      for (const f of ["w", "h"])
        if (!num(l[f], 1, 8192)) fail("サイズが不正です");
      if (!num(l.rotation, -360, 360) || !num(l.opacity, 0, 1))
        fail("角度または不透明度が不正です");
      if (l.kind === "text") {
        if (
          typeof l.text !== "string" ||
          l.text.length > 2000 ||
          !num(l.fontSize, 4, 512) ||
          !color(l.fill)
        )
          fail("テキストが不正です");
      } else if (l.kind === "image") {
        if (
          typeof l.src !== "string" ||
          l.src.length > 12000000 ||
          !/^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(l.src)
        )
          fail("画像は埋め込みPNGが必要です");
        imageBytes += l.src.length;
        if (imageBytes > 20000000)
          fail("シーンの画像合計は20MB以下にしてください");
        if (
          !Number.isInteger(l.cell) ||
          !num(l.cell, 1, 512) ||
          !Number.isInteger(l.levels) ||
          !num(l.levels, 2, 256)
        )
          fail("モザイク設定が不正です");
      } else if (l.kind === "heatmap") {
        matrix({
          z: l.z,
          x: l.xlabels,
          y: l.ylabels,
          zmin: l.low,
          zmax: l.high,
        });
        heatColor(l.low, l.low, l.high, l.levels);
      } else if (
        !color(l.fill) ||
        !color(l.stroke) ||
        !num(l.strokeWidth, 0, 64)
      )
        fail("図形の色または線幅が不正です");
    }
    return clone(scene);
  }
  function mosaicRGBA(data, width, height, cell, levels = 256) {
    if (
      !Number.isInteger(width) ||
      !Number.isInteger(height) ||
      width < 1 ||
      height < 1 ||
      width * height > 4194304 ||
      data.length !== width * height * 4 ||
      !Number.isInteger(cell) ||
      cell < 1 ||
      cell > 512 ||
      !Number.isInteger(levels) ||
      levels < 2 ||
      levels > 256
    )
      fail("モザイク入力が不正です");
    const out = new Uint8ClampedArray(data.length);
    for (let y = 0; y < height; y += cell)
      for (let x = 0; x < width; x += cell) {
        const endX = Math.min(width, x + cell),
          endY = Math.min(height, y + cell),
          sums = [0, 0, 0];
        let alpha = 0,
          count = 0;
        for (let j = y; j < endY; j++)
          for (let i = x; i < endX; i++) {
            const n = (j * width + i) * 4,
              a = data[n + 3];
            alpha += a;
            count++;
            for (let c = 0; c < 3; c++) sums[c] += data[n + c] * a;
          }
        const rgba = sums.map((s) =>
          Math.round(
            (Math.round(
              ((alpha ? Math.round(s / alpha) : 0) / 255) * (levels - 1),
            ) /
              (levels - 1)) *
              255,
          ),
        );
        rgba.push(Math.round(alpha / count));
        for (let j = y; j < endY; j++)
          for (let i = x; i < endX; i++) out.set(rgba, (j * width + i) * 4);
      }
    return out;
  }
  function layerSVG(l, imageSource = (x) => x.src) {
    let body = "";
    if (["rect", "ellipse", "triangle"].includes(l.kind)) {
      const attrs = `fill="${l.fill}" stroke="${l.stroke}" stroke-width="${l.strokeWidth}"`;
      if (l.kind === "rect")
        body = `<rect width="${l.w}" height="${l.h}" ${attrs}/>`;
      if (l.kind === "ellipse")
        body = `<ellipse cx="${l.w / 2}" cy="${l.h / 2}" rx="${l.w / 2}" ry="${l.h / 2}" ${attrs}/>`;
      if (l.kind === "triangle")
        body = `<polygon points="${l.w / 2},0 ${l.w},${l.h} 0,${l.h}" ${attrs}/>`;
    } else if (l.kind === "text") {
      body =
        `<text fill="${l.fill}" font-family="Meiryo, 'Noto Sans', 'Noto Color Emoji', sans-serif" font-size="${l.fontSize}" dominant-baseline="text-before-edge">` +
        l.text
          .split("\n")
          .map(
            (line, i) =>
              `<tspan x="0" y="${i * l.fontSize * 1.3}">${escape(line)}</tspan>`,
          )
          .join("") +
        "</text>";
    } else if (l.kind === "image")
      body = `<image href="${escape(imageSource(l))}" width="${l.w}" height="${l.h}" preserveAspectRatio="none"/>`;
    else if (l.kind === "heatmap") {
      const left = 90,
        top = 28,
        right = 24,
        bottom = 56,
        cw = Math.max(1, l.w - left - right) / l.z[0].length,
        ch = Math.max(1, l.h - top - bottom) / l.z.length;
      for (let y = 0; y < l.z.length; y++) {
        for (let x = 0; x < l.z[y].length; x++) {
          const v = l.z[y][x],
            title = `${l.ylabels[y]} / ${l.xlabels[x]}: ${v === null ? "欠測" : v}`;
          body += `<rect x="${left + x * cw}" y="${top + y * ch}" width="${cw}" height="${ch}" fill="${heatColor(v, l.low, l.high, l.levels)}"><title>${escape(title)}</title></rect>`;
          if (l.labels && cw >= 35 && ch >= 24 && v !== null)
            body += `<text x="${left + (x + 0.5) * cw}" y="${top + (y + 0.5) * ch}" text-anchor="middle" dominant-baseline="central" font-family="Meiryo,sans-serif" font-size="12" fill="#111827" stroke="#FFFFFF" stroke-width="2" paint-order="stroke">${escape(v)}</text>`;
        }
        body += `<text x="${left - 10}" y="${top + (y + 0.5) * ch}" text-anchor="end" dominant-baseline="central" font-family="Meiryo,sans-serif" font-size="12">${escape(l.ylabels[y])}</text>`;
      }
      for (let x = 0; x < l.z[0].length; x++)
        body += `<text x="${left + (x + 0.5) * cw}" y="${l.h - bottom + 20}" text-anchor="middle" font-family="Meiryo,sans-serif" font-size="12">${escape(l.xlabels[x])}</text>`;
      body += `<text x="${left}" y="${l.h - 5}" font-family="Meiryo,sans-serif" font-size="12">${escape(l.low)} → ${escape(l.high)} ・ ${l.levels ? l.levels + "段階" : "連続色"} ・ 欠測は透明</text>`;
    }
    return `<g data-layer="${escape(l.id)}" transform="translate(${l.x} ${l.y}) rotate(${l.rotation} ${l.w / 2} ${l.h / 2})" opacity="${l.opacity}">${body}</g>`;
  }
  function svg(scene, imageSource) {
    validate(scene);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${scene.width}" height="${scene.height}" viewBox="0 0 ${scene.width} ${scene.height}"><rect width="100%" height="100%" fill="${scene.background}"/>${scene.layers.map((l) => layerSVG(l, imageSource)).join("")}</svg>`;
  }
  class History {
    constructor(scene) {
      this.items = [validate(scene)];
      this.index = 0;
    }
    get current() {
      return clone(this.items[this.index]);
    }
    commit(scene) {
      const next = validate(scene);
      if (JSON.stringify(next) === JSON.stringify(this.items[this.index]))
        return;
      this.items = this.items.slice(0, this.index + 1);
      this.items.push(next);
      if (this.items.length > 40) this.items.shift();
      this.index = this.items.length - 1;
    }
    undo() {
      this.index = Math.max(0, this.index - 1);
      return this.current;
    }
    redo() {
      this.index = Math.min(this.items.length - 1, this.index + 1);
      return this.current;
    }
  }
  const api = {
    SCHEMA,
    PALETTE,
    clone,
    escape,
    heatColor,
    matrix,
    validate,
    mosaicRGBA,
    layerSVG,
    svg,
    History,
  };
  if (typeof module !== "undefined") module.exports = api;
  else root.StudioCore = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
