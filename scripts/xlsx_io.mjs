// Allowlisted ExcelJS workbook IO.
// Ironmate decides encodings, the cell spec, and the style XML.
// This script only writes or reads values, formulas, sheet names, and autofilter.
import { createRequire } from 'node:module'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(join(dirname(fileURLToPath(import.meta.url)), '../package.json'))
const ExcelJS = require('exceljs')

const [engine, mode, input, output] = process.argv.slice(2)
if (engine !== 'exceljs' || !['write', 'read'].includes(mode) || !input || !output) {
  throw new Error('usage: xlsx_io.mjs exceljs write|read INPUT OUTPUT')
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

async function writeExcel(spec, outPath) {
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
  await writeExcel(JSON.parse(readFileSync(input, 'utf8')), output)
} else {
  writeFileSync(output, JSON.stringify(await readExcel(input)))
}
