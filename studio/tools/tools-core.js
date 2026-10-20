/* Browser/Node shared operations. Pixel coordinates follow grid_tools.py. */
(function (root) {
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
  if (typeof module === "object") module.exports = api;
  else root.IronmateTools = api;
})(typeof globalThis === "object" ? globalThis : this);
