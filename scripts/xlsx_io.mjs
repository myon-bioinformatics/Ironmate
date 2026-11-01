// Allowlisted workbook IO.
// Ironmate decides encodings, the cell spec, and the style XML.
// engine 'min' writes values, formulas, sheet names, and autofilter with Node built-ins only.
// engine 'exceljs' writes and reads the same subset with ExcelJS, the independent test oracle.
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { crc32, deflateRawSync } from 'node:zlib'

const require = createRequire(join(dirname(fileURLToPath(import.meta.url)), '../package.json'))

const [engine, mode, input, output] = process.argv.slice(2)
if (!['min', 'exceljs'].includes(engine) || !['write', 'read'].includes(mode) || !input || !output
  || (engine === 'min' && mode === 'read')) {
  throw new Error('usage: xlsx_io.mjs min write|exceljs write|read INPUT OUTPUT')
}

function columnName(index) {
  let name = ''
  let n = index
  while (n > 0) {
    const rem = (n - 1) % 26
    name = String.fromCharCode(65 + rem) + name
    n = Math.floor((n - 1) / 26)
  }
  return name
}

function cellOrNull(cell) {
  if (!cell || (cell.v == null && !cell.f)) return null
  return cell
}

const MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
const REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
const XML = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

// CR and CRLF become LF, characters XML 1.0 cannot hold are dropped (as ExcelJS does), markup is escaped.
function xmlText(value) {
  return String(value)
    .replace(/\r\n?/g, '\n')
    .replace(/[^\t\n -~\u0080-퟿-�\u{10000}-\u{10FFFF}]/gu, '')
    .replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])
}

function cellXml(ref, value) {
  if (value.f) return `<c r="${ref}"><f>${xmlText(value.f)}</f></c>`
  if (typeof value.v === 'number') {
    if (!Number.isFinite(value.v)) throw new Error(`${ref} is not a finite number`)
    return `<c r="${ref}"><v>${value.v}</v></c>`
  }
  if (typeof value.v === 'string') {
    return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlText(value.v)}</t></is></c>`
  }
  throw new Error(`${ref} has an unsupported value`)
}

function sheetXml(sheet) {
  const rows = []
  sheet.rows.forEach((row, r) => {
    const cells = []
    row.forEach((cell, c) => {
      const value = cellOrNull(cell)
      if (value) cells.push(cellXml(`${columnName(c + 1)}${r + 1}`, value))
    })
    if (cells.length) rows.push(`<row r="${r + 1}">${cells.join('')}</row>`)
  })
  const filter = sheet.autofilter ? `<autoFilter ref="${xmlText(sheet.autofilter)}"/>` : ''
  return `${XML}<worksheet xmlns="${MAIN}"><sheetData>${rows.join('')}</sheetData>${filter}</worksheet>`
}

// The smallest package Excel opens: styles.xml is a placeholder that Ironmate rewrites afterwards.
function packageParts(spec) {
  const sheets = spec.sheets
  if (!sheets.length) throw new Error('a workbook needs at least one sheet')
  const each = (make) => sheets.map((sheet, i) => make(sheet, i + 1)).join('')
  const rels = 'http://schemas.openxmlformats.org/package/2006/relationships'
  const sheetType = 'application/vnd.openxmlformats-officedocument.spreadsheetml'
  return [
    ['[Content_Types].xml', `${XML}<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">`
      + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      + '<Default Extension="xml" ContentType="application/xml"/>'
      + `<Override PartName="/xl/workbook.xml" ContentType="${sheetType}.sheet.main+xml"/>`
      + each((_, n) => `<Override PartName="/xl/worksheets/sheet${n}.xml" ContentType="${sheetType}.worksheet+xml"/>`)
      + `<Override PartName="/xl/styles.xml" ContentType="${sheetType}.styles+xml"/></Types>`],
    ['_rels/.rels', `${XML}<Relationships xmlns="${rels}">`
      + `<Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>`],
    ['xl/workbook.xml', `${XML}<workbook xmlns="${MAIN}" xmlns:r="${REL}"><sheets>`
      + each((sheet, n) => `<sheet name="${xmlText(sheet.name)}" sheetId="${n}" r:id="rId${n}"/>`)
      + '</sheets><calcPr calcId="171027"/></workbook>'],
    ['xl/_rels/workbook.xml.rels', `${XML}<Relationships xmlns="${rels}">`
      + each((_, n) => `<Relationship Id="rId${n}" Type="${REL}/worksheet" Target="worksheets/sheet${n}.xml"/>`)
      + `<Relationship Id="rId${sheets.length + 1}" Type="${REL}/styles" Target="styles.xml"/></Relationships>`],
    ['xl/styles.xml', `${XML}<styleSheet xmlns="${MAIN}"><fonts count="1"><font/></fonts>`
      + '<fills count="2"><fill><patternFill patternType="none"/></fill>'
      + '<fill><patternFill patternType="gray125"/></fill></fills>'
      + '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
      + '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
      + '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>'],
    ...sheets.map((sheet, i) => [`xl/worksheets/sheet${i + 1}.xml`, sheetXml(sheet)]),
  ]
}

// ZIP with deflate, UTF-8 names, and a fixed timestamp so the same spec gives the same bytes.
function zip(parts) {
  if (parts.length > 0xffff) throw new Error('too many parts for a ZIP without ZIP64')
  const chunks = []
  const central = []
  let offset = 0
  for (const [name, text] of parts) {
    const data = Buffer.from(text, 'utf8')
    const packed = deflateRawSync(data)
    const label = Buffer.from(name, 'utf8')
    const crc = crc32(data)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0x0800, 6)
    local.writeUInt16LE(8, 8)
    local.writeUInt16LE(0x21, 12)
    local.writeUInt32LE(crc, 14)
    local.writeUInt32LE(packed.length, 18)
    local.writeUInt32LE(data.length, 22)
    local.writeUInt16LE(label.length, 26)
    const entry = Buffer.alloc(46)
    entry.writeUInt32LE(0x02014b50, 0)
    entry.writeUInt16LE(20, 4)
    entry.writeUInt16LE(20, 6)
    entry.writeUInt16LE(0x0800, 8)
    entry.writeUInt16LE(8, 10)
    entry.writeUInt16LE(0x21, 14)
    entry.writeUInt32LE(crc, 16)
    entry.writeUInt32LE(packed.length, 20)
    entry.writeUInt32LE(data.length, 24)
    entry.writeUInt16LE(label.length, 28)
    entry.writeUInt32LE(offset, 42)
    chunks.push(local, label, packed)
    central.push(entry, label)
    offset += local.length + label.length + packed.length
  }
  const directory = Buffer.concat(central)
  const end = Buffer.alloc(22)
  end.writeUInt32LE(0x06054b50, 0)
  end.writeUInt16LE(parts.length, 8)
  end.writeUInt16LE(parts.length, 10)
  end.writeUInt32LE(directory.length, 12)
  end.writeUInt32LE(offset, 16)
  if (offset + directory.length > 0xffffffff) throw new Error('workbook is too large for a ZIP without ZIP64')
  return Buffer.concat([...chunks, directory, end])
}

async function writeExcel(spec, outPath) {
  const ExcelJS = require('exceljs')
  const wb = new ExcelJS.Workbook()
  for (const sheet of spec.sheets) {
    const ws = wb.addWorksheet(sheet.name)
    sheet.rows.forEach((row, r) => {
      row.forEach((cell, c) => {
        const value = cellOrNull(cell)
        if (!value) return
        const target = ws.getCell(r + 1, c + 1)
        target.value = value.f ? { formula: value.f } : value.v
      })
    })
    if (sheet.autofilter) ws.autoFilter = sheet.autofilter
  }
  await wb.xlsx.writeFile(outPath)
}

function publicCell(raw) {
  if (!raw) return null
  const cell = {}
  if (raw.f) cell.f = String(raw.f).replace(/^=/, '')
  else if (raw.v != null && raw.v !== '') cell.v = typeof raw.v === 'number' ? raw.v : String(raw.v)
  if (raw.z && raw.z !== 'General') cell.z = raw.z
  if (raw.align) cell.align = raw.align
  if (raw.border) cell.border = raw.border
  return Object.keys(cell).length ? cell : null
}

function borderName(border) {
  if (!border) return undefined
  const sides = ['top', 'left', 'bottom', 'right']
  return sides.every((side) => border[side] && border[side].style === 'thin') ? 'thin' : undefined
}

function readExcel(path) {
  return (async () => {
    const ExcelJS = require('exceljs')
    const wb = new ExcelJS.Workbook()
    await wb.xlsx.readFile(path)
    const sheets = []
    wb.eachSheet((ws) => {
      let maxR = ws.dimensions ? ws.dimensions.bottom : 0
      let maxC = ws.dimensions ? ws.dimensions.right : 0
      const found = new Map()
      ws.eachRow({ includeEmpty: true }, (row, r) => {
        maxR = Math.max(maxR, r)
        row.eachCell({ includeEmpty: true }, (cell, c) => {
          maxC = Math.max(maxC, c)
          const value = cell.value
          const raw = {}
          if (value && typeof value === 'object' && value.formula) raw.f = value.formula
          else if (value != null && value !== '') raw.v = value
          if (cell.numFmt) raw.z = cell.numFmt
          if (cell.alignment && cell.alignment.horizontal) raw.align = cell.alignment.horizontal
          const border = borderName(cell.border)
          if (border) raw.border = border
          found.set(`${c},${r}`, publicCell(raw))
        })
      })
      const rows = []
      for (let r = 1; r <= maxR; r += 1) {
        const line = []
        for (let c = 1; c <= maxC; c += 1) line.push(found.get(`${c},${r}`) || null)
        rows.push(line)
      }
      let autofilter = null
      if (typeof ws.autoFilter === 'string') autofilter = ws.autoFilter
      else if (ws.autoFilter && ws.autoFilter.from && ws.autoFilter.to) {
        const from = ws.autoFilter.from
        const to = ws.autoFilter.to
        autofilter = `${columnName(from.column)}${from.row}:${columnName(to.column)}${to.row}`
      }
      const sheet = { name: ws.name, rows }
      if (autofilter) sheet.autofilter = autofilter
      sheets.push(sheet)
    })
    return { sheets }
  })()
}

if (mode === 'write') {
  const spec = JSON.parse(readFileSync(input, 'utf8'))
  if (engine === 'min') writeFileSync(output, zip(packageParts(spec)))
  else await writeExcel(spec, output)
} else {
  writeFileSync(output, JSON.stringify(await readExcel(input)))
}
