// Allowlisted PptxGenJS 4.0.1 package renderer.
// Ironmate replaces each slide part with the canonical OOXML mapping after this
// writes the package shell (content types, relationships, masters, slide count).
// This script does not patch OOXML.
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'

const require = createRequire(import.meta.url)
const PptxGenJS = require('pptxgenjs')

const FORBIDDEN = new Set(['beginArrowType', 'endArrowType', 'lineHead', 'lineTail'])

function rejectArrows(value, path) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => rejectArrows(item, `${path}[${index}]`))
    return
  }
  if (value && typeof value === 'object') {
    for (const key of Object.keys(value)) {
      if (FORBIDDEN.has(key)) {
        throw new Error(`built-in arrow styling is not reversible: ${key}`)
      }
      rejectArrows(value[key], `${path}.${key}`)
    }
  }
}

const specPath = process.argv[2]
const outPath = process.argv[3]
if (!specPath || !outPath) {
  throw new Error('usage: pptxgen_render.mjs SPEC.json OUTPUT.pptx')
}
const spec = JSON.parse(readFileSync(specPath, 'utf8'))
rejectArrows(spec, 'spec')
if (!Array.isArray(spec.slides) || spec.slides.length < 1) {
  throw new Error('spec.slides must contain at least one slide')
}

const pptx = new PptxGenJS()
const width = Number(spec.width ?? 10)
const height = Number(spec.height ?? 7.5)
pptx.defineLayout({ name: 'IRONMATE', width, height })
pptx.layout = 'IRONMATE'
for (const slideSpec of spec.slides) {
  const slide = pptx.addSlide()
  const color = slideSpec && slideSpec.background && slideSpec.background.color
  if (color) slide.background = { color: String(color).replace(/^#/, '') }
}
await pptx.writeFile({ fileName: outPath })
