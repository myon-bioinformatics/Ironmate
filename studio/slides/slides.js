/* Native Open XML writer over the existing PptxGenJS-generated package shell. */
(function (root) {
  "use strict";
  const C =
    typeof module === "object" ? require("../studio.js") : root.StudioCore;
  const shell =
    typeof module === "object"
      ? require("./package.js")
      : root.IronmateSlideShell;
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
  if (typeof module === "object") module.exports = api;
  else root.IronmateSlides = api;
})(globalThis);

/* Slide document UI: browser only (Node requires this file for the model above and skips this part). */
if (typeof document !== "undefined") (function () {
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
