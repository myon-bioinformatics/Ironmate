/* Ironmate studio: the one browser script for every page (studio, tools, slides; brand needs none).
   Models first (composition, pixel-grid tools, slide shell, Open XML writer), then each page's UI. */
/* Composition model. Optional browser canvas metrics; no network/framework dependency. */
const StudioCore = (function (root) {
  "use strict";
  const SCHEMA = "ironmate-image-studio/1";
  const WORKSPACE_SCHEMA = "ironmate-studio-workspace/1";
  const WORKSPACE_MAX_BYTES = 32 * 1024 * 1024;
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
    if (
      [low, high].some(
        (v) =>
          !Number.isFinite(v) ||
          (Number.isInteger(v) && !Number.isSafeInteger(v)),
      )
    )
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
        ![
          "rect",
          "ellipse",
          "triangle",
          "text",
          "image",
          "heatmap",
          "arrow",
          "clock",
        ].includes(l.kind)
      )
        fail("レイヤーのIDまたは種類が不正です");
      ids.add(l.id);
      for (const f of ["x", "y"])
        if (!num(l[f], -8192, 8192)) fail("位置が不正です");
      for (const f of ["w", "h"])
        if (!num(l[f], 1, 8192)) fail("サイズが不正です");
      if (!num(l.rotation, -360, 360) || !num(l.opacity, 0, 1))
        fail("角度または不透明度が不正です");
      if (l.mono !== undefined && typeof l.mono !== "boolean")
        fail("単色設定が不正です");
      if (l.mono && !color(l.fill)) fail("単色の色が不正です");
      if (l.kind === "text") {
        if (l.wrap !== undefined && typeof l.wrap !== "boolean") fail("折り返しの指定が不正です");
        if (l.bold !== undefined && typeof l.bold !== "boolean") fail("太字の指定が不正です");
        if (l.font !== undefined && !["sans", "mono"].includes(l.font))
          fail("フォント設定が不正です");
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
        if (
          l.sampling !== undefined &&
          !["pixelated", "smooth"].includes(l.sampling)
        )
          fail("補間方式が不正です");
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
      if (l.kind === "arrow") {
        arrowGeometry(l.w, l.h, l.headSize, l.headPlacement);
        if (
          l.headStyle !== undefined &&
          !["triangle", "beginner"].includes(l.headStyle)
        )
          fail("矢羽根の形が不正です");
      }
      if (
        l.kind === "clock" &&
        (!Number.isInteger(l.hour) ||
          !num(l.hour, 0, 23) ||
          !Number.isInteger(l.minute) ||
          !num(l.minute, 0, 59))
      )
        fail("時計の時刻が不正です");
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
  function arrowGeometry(w, h, head = 28, placement = "tip") {
    if (
      !num(w, 1, 8192) ||
      !num(h, 1, 8192) ||
      !num(head, 1, 512) ||
      !["tip", "middle"].includes(placement)
    )
      fail("矢印の寸法が不正です");
    const size = Math.min(head, w, h),
      cx = placement === "middle" ? w / 2 : w - size / 2;
    return {
      line: [0, h / 2, w, h / 2],
      points: [
        [cx + size / 2, h / 2],
        [cx - size / 2, h / 2 + size / 2],
        [cx - size / 2, h / 2 - size / 2],
      ],
    };
  }
  function outputSize(scene, scale = 1) {
    if (!num(scale, 0.25, 8)) fail("出力倍率は0.25〜8です");
    const width = Math.round(scene.width * scale),
      height = Math.round(scene.height * scale);
    if (width > 8192 || height > 8192 || width * height > 16777216)
      fail("出力は各辺8192px・合計16MP以下にしてください");
    return { width, height };
  }
  function pngPayload(bytes) {
    const a = Uint8Array.from(bytes),
      signature = [137, 80, 78, 71, 13, 10, 26, 10];
    if (
      a.length < 8 ||
      a.length > 32 * 1024 * 1024 ||
      signature.some((v, i) => a[i] !== v)
    )
      fail("32MiB以下のPNGが必要です");
    let base64;
    if (typeof Buffer !== "undefined")
      base64 = Buffer.from(a).toString("base64");
    else {
      let binary = "";
      for (let i = 0; i < a.length; i += 8192)
        binary += String.fromCharCode(...a.subarray(i, i + 8192));
      base64 = btoa(binary);
    }
    return {
      base64,
      dataUri: "data:image/png;base64," + base64,
      mimeType: "image/png",
      bytes: a.length,
    };
  }
  function textFont(l) {
    return l.font === "mono"
      ? `${l.wrap ? "'MS Gothic', " : ""}ui-monospace, 'Noto Sans Mono', monospace`
      : "Meiryo, 'Noto Sans', 'Noto Color Emoji', sans-serif";
  }
  let textContext;
  function measureText(text, l) {
    // Node exports use conservative em estimates. Browser SVG and PPTX share
    // the actual installed font's metrics, including bold and kerning.
    if (textContext === undefined) {
      const canvas = root.document?.createElement("canvas");
      textContext = canvas?.getContext("2d") || null;
    }
    if (textContext) {
      textContext.font = `${l.bold ? 700 : 400} ${l.fontSize}px ${textFont(l)}`;
      return textContext.measureText(text).width;
    }
    return Array.from(text).reduce((n, c) => n + (/^[\x20-\x7e]$/.test(c) ? 0.65 : 1), 0) * l.fontSize;
  }
  const words = new Intl.Segmenter("ja", { granularity: "word" }),
    graphemes = new Intl.Segmenter("ja", { granularity: "grapheme" });
  function textLayout(l, measure = (text) => measureText(text, l)) {
    const paragraphs = l.text.replace(/\r\n?/g, "\n").split("\n");
    return paragraphs.map((paragraph) => {
      if (!l.wrap || !paragraph) return [paragraph];
      const lines = [];
      let line = "";
      const flush = () => { lines.push(line.replace(/[ \t]+$/, "")); line = ""; };
      for (const { segment: token } of words.segment(paragraph)) {
        if (!line && lines.length && /^[ \t]+$/.test(token)) continue;
        if (measure(line + token) <= l.w) { line += token; continue; }
        // Keep ordinary words intact; split a long word/URL at grapheme
        // boundaries. A single glyph wider than the box is never compressed.
        if (line) flush();
        if (lines.length && /^[ \t]+$/.test(token)) continue;
        if (measure(token) <= l.w) { line = token; continue; }
        for (const { segment: glyph } of graphemes.segment(token)) {
          if (line && measure(line + glyph) > l.w) flush();
          line += glyph;
        }
      }
      if (line || !lines.length) lines.push(line);
      return lines;
    });
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
        `<text xml:space="preserve" fill="${l.fill}" font-family="${textFont(l)}" font-size="${l.fontSize}" font-weight="${l.bold ? "700" : "400"}" dominant-baseline="text-before-edge">` +
        textLayout(l).flat()
          .map(
            (line, i) =>
              `<tspan x="0" y="${i * l.fontSize * 1.3}">${escape(line)}</tspan>`,
          )
          .join("") +
        "</text>";
    } else if (l.kind === "image")
      body = `<image href="${escape(imageSource(l))}" width="${l.w}" height="${l.h}" preserveAspectRatio="none" image-rendering="${l.sampling === "smooth" ? "auto" : "pixelated"}"/>`;
    else if (l.kind === "arrow") {
      const g = arrowGeometry(l.w, l.h, l.headSize, l.headPlacement);
      body = `<line x1="${g.line[0]}" y1="${g.line[1]}" x2="${g.line[2]}" y2="${g.line[3]}" stroke="${l.stroke}" stroke-width="${l.strokeWidth}"/>`;
      if (l.headStyle === "beginner") {
        const size = Math.min(l.headSize ?? 28, l.w, l.h),
          x = g.points[0][0] - size,
          y = l.h / 2 - size / 2;
        // The emoji points down; rotate -90 degrees to point along +x.
        // Alpha masking removes the font's embedded yellow/green colors.
        const id =
          "head-" +
          Array.from(l.id)
            .map((c) => c.codePointAt(0).toString(16))
            .join("-");
        body += `<svg x="${x}" y="${y}" width="${size}" height="${size}" viewBox="0 0 100 100"><defs><mask id="${id}" mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="100" height="100"><text x="50" y="50" text-anchor="middle" dominant-baseline="central" font-family="'Noto Color Emoji', 'Segoe UI Emoji', 'Apple Color Emoji', sans-serif" font-size="90" transform="rotate(-90 50 50)">🔰</text></mask></defs><rect width="100" height="100" fill="#000000" mask="url(#${id})"/></svg>`;
      } else
        body += `<polygon points="${g.points.map((p) => p.join(",")).join(" ")}" fill="${l.stroke}"/>`;
    } else if (l.kind === "clock") {
      const cx = l.w / 2,
        cy = l.h / 2,
        r = Math.max(0.1, Math.min(l.w, l.h) / 2 - l.strokeWidth),
        ink = l.stroke;
      const point = (a, k) => [
        cx + Math.sin(a) * r * k,
        cy - Math.cos(a) * r * k,
      ];
      const line = (p, q, width) =>
        `<line x1="${p[0]}" y1="${p[1]}" x2="${q[0]}" y2="${q[1]}" stroke="${ink}" stroke-width="${width}"/>`;
      body = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${l.fill}" stroke="${ink}" stroke-width="${l.strokeWidth}"/>`;
      for (let i = 0; i < 12; i++)
        body += line(
          point((i * Math.PI) / 6, 0.85),
          point((i * Math.PI) / 6, 0.96),
          l.strokeWidth,
        );
      body +=
        line(
          [cx, cy],
          point((((l.hour % 12) + l.minute / 60) * Math.PI) / 6, 0.52),
          l.strokeWidth * 1.5,
        ) +
        line([cx, cy], point((l.minute * Math.PI) / 30, 0.76), l.strokeWidth);
    } else if (l.kind === "heatmap") {
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
    if (l.mono && ["text", "image"].includes(l.kind)) {
      const id =
        "ink-" +
        Array.from(l.id)
          .map((c) => c.codePointAt(0).toString(16))
          .join("-");
      body = `<defs><mask id="${id}" mask-type="alpha" maskUnits="userSpaceOnUse" x="0" y="0" width="${l.w}" height="${l.h}">${body}</mask></defs><rect width="${l.w}" height="${l.h}" fill="${l.fill}" mask="url(#${id})"/>`;
    }
    return `<g data-layer="${escape(l.id)}" transform="translate(${l.x} ${l.y}) rotate(${l.rotation} ${l.w / 2} ${l.h / 2})" opacity="${l.opacity}">${body}</g>`;
  }
  function svg(scene, imageSource, scale = 1) {
    validate(scene);
    const size = outputSize(scene, scale);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${size.width}" height="${size.height}" viewBox="0 0 ${scene.width} ${scene.height}"><rect width="${scene.width}" height="${scene.height}" fill="${scene.background}"/>${scene.layers.map((l) => layerSVG(l, imageSource)).join("")}</svg>`;
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
    undo(steps = 1) {
      this.index = Math.max(0, this.index - steps);
      return this.current;
    }
    redo(steps = 1) {
      this.index = Math.min(this.items.length - 1, this.index + steps);
      return this.current;
    }
  }
  function workspaceShape(record) {
    if (record?.schema !== WORKSPACE_SCHEMA ||
        !Array.isArray(record.items) || record.items.length < 1 || record.items.length > 40 ||
        !Number.isInteger(record.index) || record.index < 0 || record.index >= record.items.length)
      fail("作業履歴の形式が不正です");
  }
  function workspaceSize(text) {
    const bytes = new TextEncoder().encode(text).length;
    if (bytes > WORKSPACE_MAX_BYTES) fail("作業履歴は32MiB以下にしてください。履歴を整理して再保存できます");
    return bytes;
  }
  function workspaceText(history) {
    const record = { schema: WORKSPACE_SCHEMA, items: history.items, index: history.index };
    workspaceShape(record);
    const parts = ['{"schema":' + JSON.stringify(WORKSPACE_SCHEMA) + ',"items":['];
    const tail = '],"index":' + record.index + '}';
    let bytes = workspaceSize(parts[0]) + workspaceSize(tail);
    // Validate/serialize one state at a time and stop before assembling an oversize record.
    for (let i = 0; i < record.items.length; i++) {
      const part = (i ? ',' : '') + JSON.stringify(validate(record.items[i]));
      bytes += workspaceSize(part);
      if (bytes > WORKSPACE_MAX_BYTES) fail("作業履歴は32MiB以下にしてください。履歴を整理して再保存できます");
      parts.push(part);
    }
    parts.push(tail);
    return parts.join('');
  }
  function workspaceHistory(text) {
    if (typeof text !== "string") fail("作業履歴の形式が不正です");
    workspaceSize(text);
    const record = JSON.parse(text);
    workspaceShape(record);
    const states = record.items.map(validate);
    const next = new History(states[0]);
    next.items = states;
    next.index = record.index;
    return next;
  }
  const api = {
    SCHEMA,
    WORKSPACE_SCHEMA,
    WORKSPACE_MAX_BYTES,
    PALETTE,
    clone,
    escape,
    heatColor,
    matrix,
    validate,
    mosaicRGBA,
    arrowGeometry,
    outputSize,
    pngPayload,
    textFont,
    measureText,
    textLayout,
    layerSVG,
    svg,
    History,
    workspaceText,
    workspaceHistory,
  };
  return api;
})(typeof globalThis !== "undefined" ? globalThis : this);

/* Browser/Node shared operations. Pixel coordinates follow grid_tools.py. */
const IronmateTools = (function (root) {
  "use strict";
  const SCHEMA = "ironmate-pixel-grid/1";
  function canonical(value) {
    const g = JSON.parse(JSON.stringify(value));
    if (
      !g ||
      g.schema !== SCHEMA ||
      !Number.isInteger(g.width) ||
      !Number.isInteger(g.height) ||
      g.width < 1 ||
      g.height < 1 ||
      g.width > 256 ||
      g.height > 256
    )
      throw Error("グリッドは1〜256セル／辺です。");
    if (
      !Array.isArray(g.colors) ||
      !g.colors.length ||
      g.colors.length > 65536 ||
      g.colors.some((c) => typeof c !== "string" || !/^#[0-9a-f]{8}$/i.test(c))
    )
      throw Error("色表は#RRGGBBAAで指定してください。");
    if (
      !Array.isArray(g.pixels) ||
      g.pixels.length !== g.height ||
      g.pixels.some(
        (r) =>
          !Array.isArray(r) ||
          r.length !== g.width ||
          r.some((i) => !Number.isInteger(i) || i < 0 || i >= g.colors.length),
      )
    )
      throw Error("色番号または行列の寸法が不正です。");
    return g;
  }
  function resize(value, width, height) {
    const g = canonical(value);
    if (
      ![width, height].every((n) => Number.isInteger(n) && n >= 1 && n <= 256)
    )
      throw Error("幅・高さは1〜256の整数です。");
    const pixels = Array.from({ length: height }, (_, y) =>
      Array.from(
        { length: width },
        (_, x) =>
          g.pixels[
            Math.min(g.height - 1, Math.floor(((y + 0.5) * g.height) / height))
          ][Math.min(g.width - 1, Math.floor(((x + 0.5) * g.width) / width))],
      ),
    );
    return { ...g, width, height, pixels, resampling: "nearest" };
  }
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  function svg(value, scale = 1) {
    const g = canonical(value);
    if (!Number.isInteger(scale) || scale < 1 || scale > 16)
      throw Error("倍率は1〜16です。");
    const cells = [];
    g.pixels.forEach((row, y) =>
      row.forEach((i, x) => {
        const c = g.colors[i],
          a = parseInt(c.slice(7), 16) / 255;
        if (a)
          cells.push(
            `<rect x="${x}" y="${y}" width="1" height="1" fill="${c.slice(0, 7)}" fill-opacity="${a}"/>`,
          );
      }),
    );
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${g.width * scale}" height="${g.height * scale}" viewBox="0 0 ${g.width} ${g.height}" shape-rendering="crispEdges">${cells.join("")}</svg>`;
  }
  function base64Length(bytes, prefix = false) {
    if (
      !Number.isSafeInteger(bytes) ||
      bytes < 0 ||
      bytes > Number.MAX_SAFE_INTEGER / 2
    )
      throw Error("ファイルサイズが大きすぎます。");
    return 4 * Math.ceil(bytes / 3) + (prefix ? 22 : 0);
  }
  function crc32(bytes) {
    let c = 0xffffffff;
    for (const b of bytes) {
      c ^= b;
      for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }
  function pngHeader(value) {
    const g = canonical(value),
      keys = [
        "schema",
        "width",
        "height",
        "colors",
        "mask",
        "palette",
        "effect",
        "resampling",
      ];
    return Object.fromEntries(
      keys
        .filter(
          (k) =>
            k in g &&
            (["schema", "width", "height", "colors"].includes(k) ||
              g[k] === null ||
              (typeof g[k] === "string" &&
                /^[A-Za-z0-9_./-]{1,64}$/.test(g[k]))),
        )
        .map((k) => [k, g[k]]),
    );
  }
  function pngChunk(type, body) {
    const out = new Uint8Array(body.length + 12),
      view = new DataView(out.buffer);
    view.setUint32(0, body.length);
    out.set(new TextEncoder().encode(type), 4);
    out.set(body, 8);
    view.setUint32(out.length - 4, crc32(out.subarray(4, out.length - 4)));
    return out;
  }
  const api = {
    canonical,
    resize,
    svg,
    esc,
    base64Length,
    pngHeader,
    pngChunk,
  };
  return api;
})(typeof globalThis === "object" ? globalThis : this);

/* <slide-shell> Generated by scripts/build_slide_shell.py using locked PptxGenJS 4.0.1. Do not edit by hand. */
const IronmateSlideShell = {"[Content_Types].xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"xml\" ContentType=\"application/xml\"/><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"jpeg\" ContentType=\"image/jpeg\"/><Default Extension=\"jpg\" ContentType=\"image/jpg\"/><Default Extension=\"svg\" ContentType=\"image/svg+xml\"/><Default Extension=\"png\" ContentType=\"image/png\"/><Default Extension=\"gif\" ContentType=\"image/gif\"/><Default Extension=\"m4v\" ContentType=\"video/mp4\"/><Default Extension=\"mp4\" ContentType=\"video/mp4\"/><Default Extension=\"vml\" ContentType=\"application/vnd.openxmlformats-officedocument.vmlDrawing\"/><Default Extension=\"xlsx\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\"/><Override PartName=\"/ppt/presentation.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml\"/><Override PartName=\"/ppt/notesMasters/notesMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesMaster+xml\"/><Override PartName=\"/ppt/slideMasters/slideMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml\"/><Override PartName=\"/ppt/slides/slide1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/><Override PartName=\"/ppt/presProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presProps+xml\"/><Override PartName=\"/ppt/viewProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml\"/><Override PartName=\"/ppt/theme/theme1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.theme+xml\"/><Override PartName=\"/ppt/tableStyles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml\"/><Override PartName=\"/ppt/slideLayouts/slideLayout1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml\"/><Override PartName=\"/ppt/notesSlides/notesSlide1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml\"/> <Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/> <Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/></Types>","_rels/.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>\n\t\t<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>\n\t\t<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"ppt/presentation.xml\"/>\n\t\t</Relationships>","docProps/app.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">\n\t<TotalTime>0</TotalTime>\n\t<Words>0</Words>\n\t<Application>Microsoft Office PowerPoint</Application>\n\t<PresentationFormat>On-screen Show (16:9)</PresentationFormat>\n\t<Paragraphs>0</Paragraphs>\n\t<Slides>1</Slides>\n\t<Notes>1</Notes>\n\t<HiddenSlides>0</HiddenSlides>\n\t<MMClips>0</MMClips>\n\t<ScaleCrop>false</ScaleCrop>\n\t<HeadingPairs>\n\t\t<vt:vector size=\"6\" baseType=\"variant\">\n\t\t\t<vt:variant><vt:lpstr>Fonts Used</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>2</vt:i4></vt:variant>\n\t\t\t<vt:variant><vt:lpstr>Theme</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>1</vt:i4></vt:variant>\n\t\t\t<vt:variant><vt:lpstr>Slide Titles</vt:lpstr></vt:variant>\n\t\t\t<vt:variant><vt:i4>1</vt:i4></vt:variant>\n\t\t</vt:vector>\n\t</HeadingPairs>\n\t<TitlesOfParts>\n\t\t<vt:vector size=\"4\" baseType=\"lpstr\">\n\t\t\t<vt:lpstr>Arial</vt:lpstr>\n\t\t\t<vt:lpstr>Calibri</vt:lpstr>\n\t\t\t<vt:lpstr>Office Theme</vt:lpstr>\n\t\t\t<vt:lpstr>Slide 1</vt:lpstr>\n\t\t</vt:vector>\n\t</TitlesOfParts>\n\t<Company>PptxGenJS</Company>\n\t<LinksUpToDate>false</LinksUpToDate>\n\t<SharedDoc>false</SharedDoc>\n\t<HyperlinksChanged>false</HyperlinksChanged>\n\t<AppVersion>16.0000</AppVersion>\n\t</Properties>","docProps/core.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">\n\t\t<dc:title>PptxGenJS Presentation</dc:title>\n\t\t<dc:subject>PptxGenJS Presentation</dc:subject>\n\t\t<dc:creator>PptxGenJS</dc:creator>\n\t\t<cp:lastModifiedBy>PptxGenJS</cp:lastModifiedBy>\n\t\t<cp:revision>1</cp:revision>\n\t\t<dcterms:created xsi:type=\"dcterms:W3CDTF\">2000-01-01T00:00:00Z</dcterms:created>\n\t\t<dcterms:modified xsi:type=\"dcterms:W3CDTF\">2000-01-01T00:00:00Z</dcterms:modified>\n\t</cp:coreProperties>","ppt/_rels/presentation.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"slideMasters/slideMaster1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" Target=\"slides/slide1.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster\" Target=\"notesMasters/notesMaster1.xml\"/><Relationship Id=\"rId4\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps\" Target=\"presProps.xml\"/><Relationship Id=\"rId5\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps\" Target=\"viewProps.xml\"/><Relationship Id=\"rId6\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"theme/theme1.xml\"/><Relationship Id=\"rId7\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles\" Target=\"tableStyles.xml\"/></Relationships>","ppt/notesMasters/_rels/notesMaster1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"../theme/theme1.xml\"/>\n\t\t</Relationships>","ppt/notesMasters/notesMaster1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:notesMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Header Placeholder 1\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"hdr\" sz=\"quarter\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"2971800\" cy=\"458788\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle><a:lvl1pPr algn=\"l\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Date Placeholder 2\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"dt\" idx=\"1\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"3884613\" y=\"0\"/><a:ext cx=\"2971800\" cy=\"458788\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle><a:lvl1pPr algn=\"r\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:fld id=\"{5282F153-3F37-0F45-9E97-73ACFA13230C}\" type=\"datetimeFigureOut\"><a:rPr lang=\"en-US\"/><a:t>7/23/19</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"4\" name=\"Slide Image Placeholder 3\"/><p:cNvSpPr><a:spLocks noGrp=\"1\" noRot=\"1\" noChangeAspect=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldImg\" idx=\"2\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"685800\" y=\"1143000\"/><a:ext cx=\"5486400\" cy=\"3086100\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:noFill/><a:ln w=\"12700\"><a:solidFill><a:prstClr val=\"black\"/></a:solidFill></a:ln></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"ctr\"/><a:lstStyle/><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"5\" name=\"Notes Placeholder 4\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"body\" sz=\"quarter\" idx=\"3\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"685800\" y=\"4400550\"/><a:ext cx=\"5486400\" cy=\"3600450\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\"/><a:lstStyle/><a:p><a:pPr lvl=\"0\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Click to edit Master text styles</a:t></a:r></a:p><a:p><a:pPr lvl=\"1\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Second level</a:t></a:r></a:p><a:p><a:pPr lvl=\"2\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Third level</a:t></a:r></a:p><a:p><a:pPr lvl=\"3\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Fourth level</a:t></a:r></a:p><a:p><a:pPr lvl=\"4\"/><a:r><a:rPr lang=\"en-US\"/><a:t>Fifth level</a:t></a:r></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"6\" name=\"Footer Placeholder 5\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"ftr\" sz=\"quarter\" idx=\"4\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"0\" y=\"8685213\"/><a:ext cx=\"2971800\" cy=\"458787\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"b\"/><a:lstStyle><a:lvl1pPr algn=\"l\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"7\" name=\"Slide Number Placeholder 6\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldNum\" sz=\"quarter\" idx=\"5\"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"3884613\" y=\"8685213\"/><a:ext cx=\"2971800\" cy=\"458787\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr vert=\"horz\" lIns=\"91440\" tIns=\"45720\" rIns=\"91440\" bIns=\"45720\" rtlCol=\"0\" anchor=\"b\"/><a:lstStyle><a:lvl1pPr algn=\"r\"><a:defRPr sz=\"1200\"/></a:lvl1pPr></a:lstStyle><a:p><a:fld id=\"{CE5E9CC1-C706-0F49-92D6-E571CC5EEA8F}\" type=\"slidenum\"><a:rPr lang=\"en-US\"/><a:t>\u2039#\u203a</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp></p:spTree><p:extLst><p:ext uri=\"{BB962C8B-B14F-4D97-AF65-F5344CB8AC3E}\"><p14:creationId xmlns:p14=\"http://schemas.microsoft.com/office/powerpoint/2010/main\" val=\"1024086991\"/></p:ext></p:extLst></p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/><p:notesStyle><a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr><a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr><a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr><a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr><a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr><a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr><a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr><a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr><a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr></p:notesStyle></p:notesMaster>","ppt/notesSlides/_rels/notesSlide1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t\t<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">\n\t\t\t<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster\" Target=\"../notesMasters/notesMaster1.xml\"/>\n\t\t\t<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" Target=\"../slides/slide1.xml\"/>\n\t\t</Relationships>","ppt/notesSlides/notesSlide1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:notes xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr><p:sp><p:nvSpPr><p:cNvPr id=\"2\" name=\"Slide Image Placeholder 1\"/><p:cNvSpPr><a:spLocks noGrp=\"1\" noRot=\"1\" noChangeAspect=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldImg\"/></p:nvPr></p:nvSpPr><p:spPr/></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"3\" name=\"Notes Placeholder 2\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"body\" idx=\"1\"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang=\"en-US\" dirty=\"0\"/><a:t></a:t></a:r><a:endParaRPr lang=\"en-US\" dirty=\"0\"/></a:p></p:txBody></p:sp><p:sp><p:nvSpPr><p:cNvPr id=\"4\" name=\"Slide Number Placeholder 3\"/><p:cNvSpPr><a:spLocks noGrp=\"1\"/></p:cNvSpPr><p:nvPr><p:ph type=\"sldNum\" sz=\"quarter\" idx=\"10\"/></p:nvPr></p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:fld id=\"{F7021451-1387-4CA6-816F-3879F97B5CBC}\" type=\"slidenum\"><a:rPr lang=\"en-US\"/><a:t>1</a:t></a:fld><a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp></p:spTree><p:extLst><p:ext uri=\"{BB962C8B-B14F-4D97-AF65-F5344CB8AC3E}\"><p14:creationId xmlns:p14=\"http://schemas.microsoft.com/office/powerpoint/2010/main\" val=\"1024086991\"/></p:ext></p:extLst></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>","ppt/presProps.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:presentationPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"/>","ppt/presentation.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:presentation xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"  saveSubsetFonts=\"1\" autoCompressPictures=\"0\"><p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst><p:sldIdLst><p:sldId id=\"256\" r:id=\"rId2\"/></p:sldIdLst><p:notesMasterIdLst><p:notesMasterId r:id=\"rId3\"/></p:notesMasterIdLst><p:sldSz cx=\"9144000\" cy=\"5143500\"/><p:notesSz cx=\"5143500\" cy=\"9144000\"/><p:defaultTextStyle><a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr><a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr><a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr><a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr><a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr><a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr><a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr><a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr><a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr></p:defaultTextStyle></p:presentation>","ppt/slideLayouts/_rels/slideLayout1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"../slideMasters/slideMaster1.xml\"/></Relationships>","ppt/slideLayouts/slideLayout1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n\t\t<p:sldLayout xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" preserve=\"1\">\n\t\t<p:cSld name=\"DEFAULT\"><p:bg><p:bgRef idx=\"1001\"><a:schemeClr val=\"bg1\"/></p:bgRef></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld>\n\t\t<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>","ppt/slideMasters/_rels/slideMaster1.xml.rels":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"../theme/theme1.xml\"/></Relationships>","ppt/slideMasters/slideMaster1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:sldMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap bg1=\"lt1\" tx1=\"dk1\" bg2=\"lt2\" tx2=\"dk2\" accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" hlink=\"hlink\" folHlink=\"folHlink\"/><p:sldLayoutIdLst><p:sldLayoutId id=\"2147483649\" r:id=\"rId1\"/></p:sldLayoutIdLst><p:hf sldNum=\"0\" hdr=\"0\" ftr=\"0\" dt=\"0\"/><p:txStyles> <p:titleStyle>  <a:lvl1pPr algn=\"ctr\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"0\"/></a:spcBef><a:buNone/><a:defRPr sz=\"4400\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mj-lt\"/><a:ea typeface=\"+mj-ea\"/><a:cs typeface=\"+mj-cs\"/></a:defRPr></a:lvl1pPr> </p:titleStyle> <p:bodyStyle>  <a:lvl1pPr marL=\"342900\" indent=\"-342900\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"3200\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr>  <a:lvl2pPr marL=\"742950\" indent=\"-285750\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2013\"/><a:defRPr sz=\"2800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr>  <a:lvl3pPr marL=\"1143000\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2400\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr>  <a:lvl4pPr marL=\"1600200\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2013\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr>  <a:lvl5pPr marL=\"2057400\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u00bb\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr>  <a:lvl6pPr marL=\"2514600\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr>  <a:lvl7pPr marL=\"2971800\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr>  <a:lvl8pPr marL=\"3429000\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr>  <a:lvl9pPr marL=\"3886200\" indent=\"-228600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:spcBef><a:spcPct val=\"20000\"/></a:spcBef><a:buFont typeface=\"Arial\" pitchFamily=\"34\" charset=\"0\"/><a:buChar char=\"\u2022\"/><a:defRPr sz=\"2000\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr> </p:bodyStyle> <p:otherStyle>  <a:defPPr><a:defRPr lang=\"en-US\"/></a:defPPr>  <a:lvl1pPr marL=\"0\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl1pPr>  <a:lvl2pPr marL=\"457200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl2pPr>  <a:lvl3pPr marL=\"914400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl3pPr>  <a:lvl4pPr marL=\"1371600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl4pPr>  <a:lvl5pPr marL=\"1828800\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl5pPr>  <a:lvl6pPr marL=\"2286000\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl6pPr>  <a:lvl7pPr marL=\"2743200\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl7pPr>  <a:lvl8pPr marL=\"3200400\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl8pPr>  <a:lvl9pPr marL=\"3657600\" algn=\"l\" defTabSz=\"914400\" rtl=\"0\" eaLnBrk=\"1\" latinLnBrk=\"0\" hangingPunct=\"1\"><a:defRPr sz=\"1800\" kern=\"1200\"><a:solidFill><a:schemeClr val=\"tx1\"/></a:solidFill><a:latin typeface=\"+mn-lt\"/><a:ea typeface=\"+mn-ea\"/><a:cs typeface=\"+mn-cs\"/></a:defRPr></a:lvl9pPr> </p:otherStyle></p:txStyles></p:sldMaster>","ppt/tableStyles.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<a:tblStyleLst xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" def=\"{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}\"/>","ppt/theme/theme1.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><a:theme xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" name=\"Office Theme\"><a:themeElements><a:clrScheme name=\"Office\"><a:dk1><a:sysClr val=\"windowText\" lastClr=\"000000\"/></a:dk1><a:lt1><a:sysClr val=\"window\" lastClr=\"FFFFFF\"/></a:lt1><a:dk2><a:srgbClr val=\"44546A\"/></a:dk2><a:lt2><a:srgbClr val=\"E7E6E6\"/></a:lt2><a:accent1><a:srgbClr val=\"4472C4\"/></a:accent1><a:accent2><a:srgbClr val=\"ED7D31\"/></a:accent2><a:accent3><a:srgbClr val=\"A5A5A5\"/></a:accent3><a:accent4><a:srgbClr val=\"FFC000\"/></a:accent4><a:accent5><a:srgbClr val=\"5B9BD5\"/></a:accent5><a:accent6><a:srgbClr val=\"70AD47\"/></a:accent6><a:hlink><a:srgbClr val=\"0563C1\"/></a:hlink><a:folHlink><a:srgbClr val=\"954F72\"/></a:folHlink></a:clrScheme><a:fontScheme name=\"Office\"><a:majorFont><a:latin typeface=\"Calibri Light\" panose=\"020F0302020204030204\"/><a:ea typeface=\"\"/><a:cs typeface=\"\"/><a:font script=\"Jpan\" typeface=\"\u6e38\u30b4\u30b7\u30c3\u30af Light\"/><a:font script=\"Hang\" typeface=\"\ub9d1\uc740 \uace0\ub515\"/><a:font script=\"Hans\" typeface=\"\u7b49\u7ebf Light\"/><a:font script=\"Hant\" typeface=\"\u65b0\u7d30\u660e\u9ad4\"/><a:font script=\"Arab\" typeface=\"Times New Roman\"/><a:font script=\"Hebr\" typeface=\"Times New Roman\"/><a:font script=\"Thai\" typeface=\"Angsana New\"/><a:font script=\"Ethi\" typeface=\"Nyala\"/><a:font script=\"Beng\" typeface=\"Vrinda\"/><a:font script=\"Gujr\" typeface=\"Shruti\"/><a:font script=\"Khmr\" typeface=\"MoolBoran\"/><a:font script=\"Knda\" typeface=\"Tunga\"/><a:font script=\"Guru\" typeface=\"Raavi\"/><a:font script=\"Cans\" typeface=\"Euphemia\"/><a:font script=\"Cher\" typeface=\"Plantagenet Cherokee\"/><a:font script=\"Yiii\" typeface=\"Microsoft Yi Baiti\"/><a:font script=\"Tibt\" typeface=\"Microsoft Himalaya\"/><a:font script=\"Thaa\" typeface=\"MV Boli\"/><a:font script=\"Deva\" typeface=\"Mangal\"/><a:font script=\"Telu\" typeface=\"Gautami\"/><a:font script=\"Taml\" typeface=\"Latha\"/><a:font script=\"Syrc\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Orya\" typeface=\"Kalinga\"/><a:font script=\"Mlym\" typeface=\"Kartika\"/><a:font script=\"Laoo\" typeface=\"DokChampa\"/><a:font script=\"Sinh\" typeface=\"Iskoola Pota\"/><a:font script=\"Mong\" typeface=\"Mongolian Baiti\"/><a:font script=\"Viet\" typeface=\"Times New Roman\"/><a:font script=\"Uigh\" typeface=\"Microsoft Uighur\"/><a:font script=\"Geor\" typeface=\"Sylfaen\"/><a:font script=\"Armn\" typeface=\"Arial\"/><a:font script=\"Bugi\" typeface=\"Leelawadee UI\"/><a:font script=\"Bopo\" typeface=\"Microsoft JhengHei\"/><a:font script=\"Java\" typeface=\"Javanese Text\"/><a:font script=\"Lisu\" typeface=\"Segoe UI\"/><a:font script=\"Mymr\" typeface=\"Myanmar Text\"/><a:font script=\"Nkoo\" typeface=\"Ebrima\"/><a:font script=\"Olck\" typeface=\"Nirmala UI\"/><a:font script=\"Osma\" typeface=\"Ebrima\"/><a:font script=\"Phag\" typeface=\"Phagspa\"/><a:font script=\"Syrn\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syrj\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syre\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Sora\" typeface=\"Nirmala UI\"/><a:font script=\"Tale\" typeface=\"Microsoft Tai Le\"/><a:font script=\"Talu\" typeface=\"Microsoft New Tai Lue\"/><a:font script=\"Tfng\" typeface=\"Ebrima\"/></a:majorFont><a:minorFont><a:latin typeface=\"Calibri\" panose=\"020F0502020204030204\"/><a:ea typeface=\"\"/><a:cs typeface=\"\"/><a:font script=\"Jpan\" typeface=\"\u6e38\u30b4\u30b7\u30c3\u30af\"/><a:font script=\"Hang\" typeface=\"\ub9d1\uc740 \uace0\ub515\"/><a:font script=\"Hans\" typeface=\"\u7b49\u7ebf\"/><a:font script=\"Hant\" typeface=\"\u65b0\u7d30\u660e\u9ad4\"/><a:font script=\"Arab\" typeface=\"Arial\"/><a:font script=\"Hebr\" typeface=\"Arial\"/><a:font script=\"Thai\" typeface=\"Cordia New\"/><a:font script=\"Ethi\" typeface=\"Nyala\"/><a:font script=\"Beng\" typeface=\"Vrinda\"/><a:font script=\"Gujr\" typeface=\"Shruti\"/><a:font script=\"Khmr\" typeface=\"DaunPenh\"/><a:font script=\"Knda\" typeface=\"Tunga\"/><a:font script=\"Guru\" typeface=\"Raavi\"/><a:font script=\"Cans\" typeface=\"Euphemia\"/><a:font script=\"Cher\" typeface=\"Plantagenet Cherokee\"/><a:font script=\"Yiii\" typeface=\"Microsoft Yi Baiti\"/><a:font script=\"Tibt\" typeface=\"Microsoft Himalaya\"/><a:font script=\"Thaa\" typeface=\"MV Boli\"/><a:font script=\"Deva\" typeface=\"Mangal\"/><a:font script=\"Telu\" typeface=\"Gautami\"/><a:font script=\"Taml\" typeface=\"Latha\"/><a:font script=\"Syrc\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Orya\" typeface=\"Kalinga\"/><a:font script=\"Mlym\" typeface=\"Kartika\"/><a:font script=\"Laoo\" typeface=\"DokChampa\"/><a:font script=\"Sinh\" typeface=\"Iskoola Pota\"/><a:font script=\"Mong\" typeface=\"Mongolian Baiti\"/><a:font script=\"Viet\" typeface=\"Arial\"/><a:font script=\"Uigh\" typeface=\"Microsoft Uighur\"/><a:font script=\"Geor\" typeface=\"Sylfaen\"/><a:font script=\"Armn\" typeface=\"Arial\"/><a:font script=\"Bugi\" typeface=\"Leelawadee UI\"/><a:font script=\"Bopo\" typeface=\"Microsoft JhengHei\"/><a:font script=\"Java\" typeface=\"Javanese Text\"/><a:font script=\"Lisu\" typeface=\"Segoe UI\"/><a:font script=\"Mymr\" typeface=\"Myanmar Text\"/><a:font script=\"Nkoo\" typeface=\"Ebrima\"/><a:font script=\"Olck\" typeface=\"Nirmala UI\"/><a:font script=\"Osma\" typeface=\"Ebrima\"/><a:font script=\"Phag\" typeface=\"Phagspa\"/><a:font script=\"Syrn\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syrj\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Syre\" typeface=\"Estrangelo Edessa\"/><a:font script=\"Sora\" typeface=\"Nirmala UI\"/><a:font script=\"Tale\" typeface=\"Microsoft Tai Le\"/><a:font script=\"Talu\" typeface=\"Microsoft New Tai Lue\"/><a:font script=\"Tfng\" typeface=\"Ebrima\"/></a:minorFont></a:fontScheme><a:fmtScheme name=\"Office\"><a:fillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"110000\"/><a:satMod val=\"105000\"/><a:tint val=\"67000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"105000\"/><a:satMod val=\"103000\"/><a:tint val=\"73000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"105000\"/><a:satMod val=\"109000\"/><a:tint val=\"81000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:satMod val=\"103000\"/><a:lumMod val=\"102000\"/><a:tint val=\"94000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:satMod val=\"110000\"/><a:lumMod val=\"100000\"/><a:shade val=\"100000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:lumMod val=\"99000\"/><a:satMod val=\"120000\"/><a:shade val=\"78000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill></a:fillStyleLst><a:lnStyleLst><a:ln w=\"6350\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln><a:ln w=\"12700\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln><a:ln w=\"19050\" cap=\"flat\" cmpd=\"sng\" algn=\"ctr\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/><a:miter lim=\"800000\"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst><a:outerShdw blurRad=\"57150\" dist=\"19050\" dir=\"5400000\" algn=\"ctr\" rotWithShape=\"0\"><a:srgbClr val=\"000000\"><a:alpha val=\"63000\"/></a:srgbClr></a:outerShdw></a:effectLst></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"><a:tint val=\"95000\"/><a:satMod val=\"170000\"/></a:schemeClr></a:solidFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:tint val=\"93000\"/><a:satMod val=\"150000\"/><a:shade val=\"98000\"/><a:lumMod val=\"102000\"/></a:schemeClr></a:gs><a:gs pos=\"50000\"><a:schemeClr val=\"phClr\"><a:tint val=\"98000\"/><a:satMod val=\"130000\"/><a:shade val=\"90000\"/><a:lumMod val=\"103000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:shade val=\"63000\"/><a:satMod val=\"120000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"5400000\" scaled=\"0\"/></a:gradFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements><a:objectDefaults/><a:extraClrSchemeLst/><a:extLst><a:ext uri=\"{05A4C25C-085E-4340-85A3-A5531E510DB2}\"><thm15:themeFamily xmlns:thm15=\"http://schemas.microsoft.com/office/thememl/2012/main\" name=\"Office Theme\" id=\"{62F939B6-93AF-4DB8-9C6B-D6C7DFDC589F}\" vid=\"{4A3C46E8-61CC-4603-A589-7422A47A8E4A}\"/></a:ext></a:extLst></a:theme>","ppt/viewProps.xml":"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\r\n<p:viewPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:normalViewPr horzBarState=\"maximized\"><p:restoredLeft sz=\"15611\"/><p:restoredTop sz=\"94610\"/></p:normalViewPr><p:slideViewPr><p:cSldViewPr snapToGrid=\"0\" snapToObjects=\"1\"><p:cViewPr varScale=\"1\"><p:scale><a:sx n=\"136\" d=\"100\"/><a:sy n=\"136\" d=\"100\"/></p:scale><p:origin x=\"216\" y=\"312\"/></p:cViewPr><p:guideLst/></p:cSldViewPr></p:slideViewPr><p:notesTextViewPr><p:cViewPr><p:scale><a:sx n=\"1\" d=\"1\"/><a:sy n=\"1\" d=\"1\"/></p:scale><p:origin x=\"0\" y=\"0\"/></p:cViewPr></p:notesTextViewPr><p:gridSpacing cx=\"76200\" cy=\"76200\"/></p:viewPr>"};
/* </slide-shell> */

/* Native Open XML writer over the existing PptxGenJS-generated package shell. */
const IronmateSlides = (function (root) {
  "use strict";
  const C = StudioCore;
  const shell = IronmateSlideShell;
  const SCHEMA = "ironmate-slide-deck/1",
    LIMIT = 32 * 1024 * 1024;
  const encoder = new TextEncoder(),
    clone = C.clone;
  function validate(deck) {
    if (
      !deck ||
      deck.schema !== SCHEMA ||
      !Array.isArray(deck.slides) ||
      deck.slides.length < 1 ||
      deck.slides.length > 20
    )
      throw Error("スライドは1〜20枚です。");
    let bytes = 0;
    const slides = deck.slides.map((scene) => {
      bytes += encoder.encode(JSON.stringify(scene)).length;
      if (bytes > LIMIT) throw Error("全スライドは32MiB以下にしてください。");
      const checked = C.validate(scene);
      for (const layer of checked.layers)
        if (layer.kind === "text" && !layer.mono && layer.wrap === undefined)
          layer.wrap = true;
      return checked;
    });
    if (
      slides.some(
        (s) => s.width !== slides[0].width || s.height !== slides[0].height,
      )
    )
      throw Error("全スライドを同じ幅・高さにしてください。");
    const title = typeof deck.title === "string" ? deck.title : "Ironmate";
    if (title.length > 200) throw Error("資料名は200文字以下です。");
    return { schema: SCHEMA, title, slides };
  }
  function deckText(deck) {
    const text = JSON.stringify(validate(deck));
    if (encoder.encode(text).length > LIMIT)
      throw Error("全スライドは32MiB以下にしてください。");
    return text;
  }
  function parse(text) {
    if (typeof text !== "string" || encoder.encode(text).length > LIMIT)
      throw Error("全スライドJSONは32MiB以下です。");
    return validate(JSON.parse(text));
  }
  function template(
    width = 1280,
    height = 720,
    title = "スライドのタイトル",
    body = "ここに本文を入力します。",
  ) {
    const text = (id, value, x, y, w, h, size, bold) => ({
      id,
      kind: "text",
      name: id,
      x,
      y,
      w,
      h,
      rotation: 0,
      opacity: 1,
      text: value,
      fill: "#000000",
      fontSize: Math.max(4, size),
      font: "sans",
      mono: false,
      bold,
      wrap: true,
    });
    return C.validate({
      schema: C.SCHEMA,
      width,
      height,
      background: "#FFFFFF",
      layers: [
        text(
          "title",
          title,
          width * 0.075,
          height * 0.08,
          width * 0.85,
          height * 0.16,
          width * 0.045,
          true,
        ),
        text(
          "body",
          body,
          width * 0.075,
          height * 0.3,
          width * 0.85,
          height * 0.55,
          width * 0.027,
          false,
        ),
      ],
    });
  }
  function xml(value) {
    for (const c of String(value)) {
      const n = c.codePointAt(0);
      if (
        (n < 32 && ![9, 10, 13].includes(n)) ||
        (n >= 0xd800 && n <= 0xdfff) ||
        n === 0xfffe ||
        n === 0xffff
      )
        throw Error("PPTXに保存できない制御文字が含まれています。");
    }
    return C.escape(value);
  }
  const A = "http://schemas.openxmlformats.org/drawingml/2006/main",
    P = "http://schemas.openxmlformats.org/presentationml/2006/main",
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    REL = "http://schemas.openxmlformats.org/package/2006/relationships";
  const declaration = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>';
  function crc(bytes) {
    let c = 0xffffffff;
    for (const b of bytes) {
      c ^= b;
      for (let i = 0; i < 8; i++) c = (c >>> 1) ^ (c & 1 ? 0xedb88320 : 0);
    }
    return (c ^ 0xffffffff) >>> 0;
  }
  function zip(files) {
    const entries = Object.entries(files).map(([name, data]) => ({
      name: encoder.encode(name),
      data: typeof data === "string" ? encoder.encode(data) : data,
    }));
    let size = 22;
    for (const e of entries) {
      if (!(e.data instanceof Uint8Array)) throw Error("ZIPデータが不正です。");
      size += 76 + 2 * e.name.length + e.data.length;
    }
    if (size > LIMIT) throw Error("PPTXは32MiB以下にしてください。");
    const out = new Uint8Array(size),
      v = new DataView(out.buffer);
    let offset = 0;
    const central = [];
    const word = (p, n) => v.setUint16(p, n, true),
      dword = (p, n) => v.setUint32(p, n, true),
      date = (20 << 9) | (1 << 5) | 1;
    for (const e of entries) {
      const start = offset,
        sum = crc(e.data);
      dword(offset, 0x04034b50);
      word(offset + 4, 20);
      word(offset + 6, 0x800);
      word(offset + 8, 0);
      word(offset + 12, date);
      dword(offset + 14, sum);
      dword(offset + 18, e.data.length);
      dword(offset + 22, e.data.length);
      word(offset + 26, e.name.length);
      out.set(e.name, offset + 30);
      out.set(e.data, offset + 30 + e.name.length);
      offset += 30 + e.name.length + e.data.length;
      central.push({ ...e, start, sum });
    }
    const cd = offset;
    for (const e of central) {
      dword(offset, 0x02014b50);
      word(offset + 4, 20);
      word(offset + 6, 20);
      word(offset + 8, 0x800);
      word(offset + 10, 0);
      word(offset + 14, date);
      dword(offset + 16, e.sum);
      dword(offset + 20, e.data.length);
      dword(offset + 24, e.data.length);
      word(offset + 28, e.name.length);
      dword(offset + 42, e.start);
      out.set(e.name, offset + 46);
      offset += 46 + e.name.length;
    }
    dword(offset, 0x06054b50);
    word(offset + 8, entries.length);
    word(offset + 10, entries.length);
    dword(offset + 12, offset - cd);
    dword(offset + 16, cd);
    return out;
  }
  function isNative(layer) {
    return (
      ["rect", "ellipse", "triangle"].includes(layer.kind) ||
      (layer.kind === "text" && !layer.mono) ||
      (layer.kind === "arrow" && layer.headStyle !== "beginner")
    );
  }
  async function exportPptx(input, imageForLayer) {
    const deck = validate(input),
      files = { ...shell };
    let imageNumber = 0,
      totalNative = 0,
      totalImages = 0;
    const unit =
        9144000 / Math.max(deck.slides[0].width, deck.slides[0].height),
      emu = (n) => Math.round(n * unit);
    const slideIds = [],
      presRels = [];
    for (let number = 1; number <= deck.slides.length; number++) {
      const scene = deck.slides[number - 1],
        parts = [],
        rels = [
          `<Relationship Id="rIdLayout" Type="${R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>`,
        ];
      let nextId = 2;
      const nv = (id, name, tx = false) =>
        `<p:nvSpPr><p:cNvPr id="${id}" name="${xml(name)}"/><p:cNvSpPr${tx ? ' txBox="1"' : ""}/><p:nvPr/></p:nvSpPr>`;
      const transform = (l) =>
        `<a:xfrm rot="${Math.round(l.rotation * 60000)}"><a:off x="${emu(l.x)}" y="${emu(l.y)}"/><a:ext cx="${emu(l.w)}" cy="${emu(l.h)}"/></a:xfrm>`;
      const fill = (color, opacity) =>
        color === "none"
          ? "<a:noFill/>"
          : `<a:solidFill><a:srgbClr val="${color.slice(1).toUpperCase()}"><a:alpha val="${Math.round(opacity * 100000)}"/></a:srgbClr></a:solidFill>`;
      const line = (l) =>
        `<a:ln w="${emu(l.strokeWidth)}">${l.strokeWidth ? fill(l.stroke, l.opacity) : "<a:noFill/>"}<a:prstDash val="solid"/></a:ln>`;
      for (const layer of scene.layers) {
        const l = clone(layer),
          name = l.name || l.id;
        if (l.kind === "text" && !l.mono) {
          const size = Math.round((l.fontSize * unit) / 127),
            font = l.font === "mono" ? "MS Gothic" : "Meiryo";
          if (size < 100 || size > 400000)
            throw Error(
              "PPTXの文字サイズが1〜4000ptの範囲を超えています。キャンバスまたは文字サイズを調整してください。",
            );
          const properties = `<a:rPr lang="ja-JP" sz="${size}" b="${l.bold ? 1 : 0}">${fill(l.fill, l.opacity)}<a:latin typeface="${font}"/><a:ea typeface="${font}"/></a:rPr>`;
          // Explicit input newlines remain paragraphs; measured soft wraps are
          // editable line breaks. Preserve the source text only in deck JSON.
          const paragraphs = C.textLayout(l)
            .map(
              (lines) =>
                `<a:p><a:pPr><a:lnSpc><a:spcPts val="${Math.round(size * 1.3)}"/></a:lnSpc><a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft></a:pPr>${lines.map(t => `<a:r>${properties}<a:t xml:space="preserve">${xml(t)}</a:t></a:r>`).join(`<a:br>${properties}</a:br>`)}<a:endParaRPr lang="ja-JP" sz="${size}"/></a:p>`,
            )
            .join("");
          parts.push(
            `<p:sp>${nv(nextId++, name, true)}<p:spPr>${transform(l)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="${l.wrap ? "square" : "none"}" lIns="0" tIns="0" rIns="0" bIns="0" anchor="t" vertOverflow="overflow"><a:noAutofit/></a:bodyPr><a:lstStyle/>${paragraphs}</p:txBody></p:sp>`,
          );
          totalNative++;
        } else if (["rect", "ellipse", "triangle"].includes(l.kind)) {
          const kind = {
            rect: "rect",
            ellipse: "ellipse",
            triangle: "triangle",
          }[l.kind];
          parts.push(
            `<p:sp>${nv(nextId++, name)}<p:spPr>${transform(l)}<a:prstGeom prst="${kind}"><a:avLst/></a:prstGeom>${fill(l.fill, l.opacity)}${line(l)}</p:spPr></p:sp>`,
          );
          totalNative++;
        } else if (l.kind === "arrow" && l.headStyle !== "beginner") {
          const geometry = C.arrowGeometry(
              l.w,
              l.h,
              l.headSize,
              l.headPlacement,
            ),
            groupId = nextId++,
            shaftId = nextId++,
            headId = nextId++,
            points = geometry.points;
          const gTransform = `<a:xfrm rot="${Math.round(l.rotation * 60000)}"><a:off x="${emu(l.x)}" y="${emu(l.y)}"/><a:ext cx="${emu(l.w)}" cy="${emu(l.h)}"/><a:chOff x="0" y="0"/><a:chExt cx="${emu(l.w)}" cy="${emu(l.h)}"/></a:xfrm>`;
          const local = { ...l, x: 0, y: 0, rotation: 0 },
            shaft = { ...local, y: l.h / 2, h: 0 };
          const custom = `<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/><a:pathLst><a:path w="${emu(l.w)}" h="${emu(l.h)}"><a:moveTo><a:pt x="${emu(points[0][0])}" y="${emu(points[0][1])}"/></a:moveTo>${points
            .slice(1)
            .map(
              (p) =>
                `<a:lnTo><a:pt x="${emu(p[0])}" y="${emu(p[1])}"/></a:lnTo>`,
            )
            .join("")}<a:close/></a:path></a:pathLst></a:custGeom>`;
          parts.push(
            `<p:grpSp><p:nvGrpSpPr><p:cNvPr id="${groupId}" name="${xml(name)}"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr>${gTransform}</p:grpSpPr><p:sp>${nv(shaftId, "Arrow shaft")}<p:spPr>${transform(shaft)}<a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>${line(l)}</p:spPr></p:sp><p:sp>${nv(headId, "Arrow head")}<p:spPr>${transform(local)}${custom}${fill(l.fill, l.opacity)}<a:ln><a:noFill/></a:ln></p:spPr></p:sp></p:grpSp>`,
          );
          totalNative += 2;
        } else {
          if (typeof imageForLayer !== "function")
            throw Error(
              "画像化が必要なレイヤーがあります。ブラウザから書き出してください。",
            );
          const bytes = await imageForLayer(l, scene);
          if (
            !(bytes instanceof Uint8Array) ||
            bytes.length < 8 ||
            ![137, 80, 78, 71, 13, 10, 26, 10].every((b, i) => bytes[i] === b)
          )
            throw Error("埋め込み画像はPNGが必要です。");
          const media = `image${++imageNumber}.png`,
            rid = `rIdImage${imageNumber}`;
          files["ppt/media/" + media] = bytes;
          rels.push(
            `<Relationship Id="${rid}" Type="${R}/image" Target="../media/${media}"/>`,
          );
          parts.push(
            `<p:pic><p:nvPicPr><p:cNvPr id="${nextId++}" name="${xml(name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="${rid}"><a:alphaModFix amt="${Math.round(l.opacity * 100000)}"/></a:blip><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr>${transform(l)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>`,
          );
          totalImages++;
        }
      }
      files[`ppt/slides/slide${number}.xml`] =
        declaration +
        `<p:sld xmlns:a="${A}" xmlns:r="${R}" xmlns:p="${P}"><p:cSld name="Slide ${number}"><p:bg><p:bgPr>${scene.background === "none" ? "<a:noFill/>" : `<a:solidFill><a:srgbClr val="${scene.background.slice(1)}"/></a:solidFill>`}<a:effectLst/></p:bgPr></p:bg><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>${parts.join("")}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>`;
      files[`ppt/slides/_rels/slide${number}.xml.rels`] =
        declaration +
        `<Relationships xmlns="${REL}">${rels.join("")}</Relationships>`;
      slideIds.push(
        `<p:sldId id="${255 + number}" r:id="rIdBrowserSlide${number}"/>`,
      );
      presRels.push(
        `<Relationship Id="rIdBrowserSlide${number}" Type="${R}/slide" Target="slides/slide${number}.xml"/>`,
      );
    }
    files["ppt/presentation.xml"] = files["ppt/presentation.xml"]
      .replace(
        /<p:sldIdLst>[\s\S]*?<\/p:sldIdLst>/,
        `<p:sldIdLst>${slideIds.join("")}</p:sldIdLst>`,
      )
      .replace(
        /<p:sldSz[^>]*\/>/,
        `<p:sldSz cx="${emu(deck.slides[0].width)}" cy="${emu(deck.slides[0].height)}"/>`,
      );
    files["ppt/_rels/presentation.xml.rels"] = files[
      "ppt/_rels/presentation.xml.rels"
    ]
      .replace(/<Relationship\b[^>]*Type="[^"]*\/slide"[^>]*\/>/g, "")
      .replace("</Relationships>", presRels.join("") + "</Relationships>");
    files["[Content_Types].xml"] = files["[Content_Types].xml"]
      .replace(/<Override\b[^>]*PartName="\/ppt\/slides\/[^"]*"[^>]*\/>/g, "")
      .replace(
        "</Types>",
        deck.slides
          .map(
            (_, i) =>
              `<Override PartName="/ppt/slides/slide${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>`,
          )
          .join("") + "</Types>",
      );
    files["docProps/core.xml"] = files["docProps/core.xml"].replace(
      /<dc:title>[\s\S]*?<\/dc:title>/,
      `<dc:title>${xml(deck.title)}</dc:title>`,
    );
    files["docProps/app.xml"] =
      declaration +
      `<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Ironmate</Application><Slides>${deck.slides.length}</Slides><Notes>0</Notes><HiddenSlides>0</HiddenSlides></Properties>`;
    return {
      data: zip(files),
      native: totalNative,
      images: totalImages,
      slides: deck.slides.length,
    };
  }
  const api = {
    SCHEMA,
    LIMIT,
    validate,
    deckText,
    parse,
    template,
    zip,
    isNative,
    exportPptx,
  };
  return api;
})(globalThis);

/* Node: require("./studio/studio.js") is the composition model, with .tools, .slides and .slideShell beside it.
   Browser: the same objects as globals, then each page's UI below runs only on the page that names it in data-page. */
if (typeof module === "object" && module.exports)
  module.exports = Object.assign({}, StudioCore, {tools: IronmateTools, slides: IronmateSlides, slideShell: IronmateSlideShell});
else Object.assign(globalThis, {StudioCore, IronmateTools, IronmateSlides, IronmateSlideShell});

/* Image Studio UI (data-page~="studio"): browser only. */
if (typeof document !== "undefined" && document.body && (document.body.dataset.page || "").split(" ").includes("studio")) (function () {
/* Local-only UI; all output passes through the same SVG composition function. */
"use strict";
const C = window.StudioCore,
  $ = (id) => document.getElementById(id),
  copy = (value) => {
    const doc = C.clone(value);
    if (document.body.dataset.mode === "slides")
      for (const l of doc.layers || [])
        if (l.kind === "text" && !l.mono && l.wrap === undefined) l.wrap = true;
    return doc;
  };
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
  $("undo").disabled = $("undo-2").disabled = history.index === 0;
  $("redo").disabled = $("redo-2").disabled = history.index === history.items.length - 1;
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
    mono: document.body.dataset.mode !== "slides",
    wrap: document.body.dataset.mode === "slides",
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
// ↶ ↷ move one state, ⏪ ⏩ two (data-steps); History clamps at both ends.
for (const [id, move] of [["undo", "undo"], ["undo-2", "undo"], ["redo", "redo"], ["redo-2", "redo"]])
  $(id).onclick = () => {
    scene = history[move](Number($(id).dataset.steps || 1));
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
// An example button only shows its GIF: nothing is loaded, so pressing one by mistake changes nothing.
let example = null;
for (const button of document.querySelectorAll(".examples [data-gif]"))
  button.onclick = () => {
    example = example === button.id ? null : button.id;
    $("example-view").hidden = !example;
    for (const other of document.querySelectorAll(".examples [data-gif]")) other.setAttribute("aria-expanded", String(other.id === example));
    if (example) {
      $("example-gif").src = button.dataset.gif;
      $("example-gif").alt = button.textContent.trim();
    }
  };
window.addEventListener("beforeunload", (e) => {
  if (dirty && document.body.dataset.mode !== "slides") {
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
  get selectedId() { return selected; },
  async replaceScene(value) {
    const next = C.validate(value);
    await prepare(next);
    scene = next; history = new C.History(next); selected = null; dirty = true;
    await render();
  },
  async imageSource(value) { return prepare(C.validate(value)); },
  patchSelected(properties) {
    if (!selectedLayer()) throw new Error("先にレイヤーを選択してください");
    change(doc => Object.assign(doc.layers.find(l => l.id === selected), properties));
  },
  get shelfItems() { return shelfItems.map(item => ({ ...item })); },
  addShelfItem,
};
scene = demo();
history = new C.History(scene);
render().catch(error);
})();

/* Tools page UI (data-page~="tools"): browser only. */
if (typeof document !== "undefined" && document.body && (document.body.dataset.page || "").split(" ").includes("tools")) (function () {
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
})();

/* Slide document UI (data-page~="slides"): browser only. */
if (typeof document !== "undefined" && document.body && (document.body.dataset.page || "").split(" ").includes("slides")) (function () {
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
})();
