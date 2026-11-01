// ExcelJS smoke test (GHSA-g3hv-75wg-m249: minimatch is overridden to ^11).
// glob@7 is broken under minimatch 11. ExcelJS's current path does not reach it;
// this smoke fails if a future change makes the xlsx/CSV path reach it.
'use strict'
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const ExcelJS = require('exceljs')
const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'exceljs-smoke-'))
const f = (n) => path.join(dir, n)
;(async () => {
  const wb = new ExcelJS.Workbook()
  const ws = wb.addWorksheet('S')
  ws.addRow(['a', 1, new Date(Date.UTC(2026, 0, 2))])
  ws.getCell('D1').value = { formula: 'B1*2', result: 2 }
  ws.mergeCells('E1:F1')
  await wb.xlsx.writeFile(f('rt.xlsx'))
  const buf = await wb.xlsx.writeBuffer()
  const r = new ExcelJS.Workbook()
  await r.xlsx.readFile(f('rt.xlsx'))
  const s = r.getWorksheet('S')
  assert.equal(s.getCell('A1').value, 'a')
  assert.equal(s.getCell('B1').value, 1)
  assert.equal(s.getCell('D1').value.formula, 'B1*2')
  assert.ok(s.getCell('F1').isMerged)
  const rb = new ExcelJS.Workbook(); await rb.xlsx.load(buf)
  assert.equal(rb.getWorksheet('S').getCell('A1').value, 'a')
  console.log('ok round-trip')

  const sw = new ExcelJS.stream.xlsx.WorkbookWriter({ filename: f('st.xlsx') })
  const sws = sw.addWorksheet('X')
  for (let i = 1; i <= 100; i++) sws.addRow([i, `r${i}`]).commit()
  await sw.commit()
  let n = 0
  const rd = new ExcelJS.stream.xlsx.WorkbookReader(f('st.xlsx'), {})
  for await (const sheet of rd) for await (const row of sheet) n++
  assert.equal(n, 100)
  console.log('ok streaming writer/reader')

  const cw = new ExcelJS.Workbook()
  cw.addWorksheet('C').addRows([['x', 'y'], ['1', 'あ,い']])
  await cw.csv.writeFile(f('c.csv'))
  const cr = new ExcelJS.Workbook()
  const cs = await cr.csv.readFile(f('c.csv'))
  assert.equal(cs.getCell('B2').value, 'あ,い')
  console.log('ok csv')
  fs.rmSync(dir, { recursive: true, force: true })
})().catch((e) => { console.error(e); process.exit(1) })
