// studio_quality_browser.cjs
// Standalone: IRONMATE_CHROME=/path/to/chrome node tests/studio_quality_browser.cjs [output]
"use strict";
const fs = require('node:fs'), path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require(process.env.IRONMATE_PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
async function collect(page, out) {
  fs.mkdirSync(out, {recursive:true});
  const fixtures = [];
  for (const seed of [20261018, 20261019]) {
    for (const scenario of ['pixel-art', 'shapes', 'gradient']) {
      const sources = await page.evaluate(require('./studio_fixtures.cjs'), {seed,scenario});
      const name = `${scenario}-${seed}.png`;
      fs.writeFileSync(path.join(out,name), Buffer.from(sources.reference.split(',')[1],'base64'));
      fixtures.push({name:scenario,seed,file:name});
    }
  }
  // Reuse the checked-in default Image Studio render, without font/platform drift.
  fs.copyFileSync(path.join(root,'docs/evidence/image-studio/demo.png'),path.join(out,'studio-demo.png'));
  fixtures.push({name:'studio-demo',seed:null,file:'studio-demo.png'});
  fs.writeFileSync(path.join(out,'fixtures.json'),JSON.stringify({browser:page.context().browser().version(),fixtures},null,2));
  execFileSync(process.env.PYTHON || 'python', ['-S','scripts/quality_experiment.py','--fixtures',path.join(out,'fixtures.json'),'--out',out],{cwd:root,stdio:'inherit',timeout:600000});
}
module.exports = collect;
if (require.main === module) (async()=>{
  const browser = await chromium.launch({headless:true, executablePath:process.env.IRONMATE_CHROME || undefined,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
  try {
    const page = await browser.newPage();
    await collect(page,path.resolve(process.argv[2] || path.join(root,'build/studio-quality')));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
