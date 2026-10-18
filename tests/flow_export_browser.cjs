"use strict";
// Real browser verification of generated SVG/PNG/Base64 and Canvas reuse.
const fs = require("node:fs"), path = require("node:path"), assert = require("node:assert/strict");
const http = require("node:http");
const {chromium} = require("playwright");
const root = path.resolve(__dirname,".."), dir = path.join(root,"build/test-results/flow-export");
(async()=>{
  let cjkFont=null;
  if(process.env.IRONMATE_FLOW_REQUIRE_CJK === "1") {
    cjkFont=require("node:child_process").execFileSync("fc-match",["-f","%{family}",":lang=ja"],{encoding:"utf8"});
    assert(/Noto.*CJK/i.test(cjkFont),'Japanese evidence requires Noto CJK, got '+cjkFont);
  }
  const allowed = new Set(['sample.html','sample.svg','sample.png','escaped.svg']);
  const server = http.createServer((req,res)=>{
    const name=req.url.slice(1);
    if(!allowed.has(name)){res.writeHead(404);return res.end();}
    res.setHeader('Content-Type',name.endsWith('.svg')?'image/svg+xml':name.endsWith('.png')?'image/png':'text/html; charset=utf-8');
    res.end(fs.readFileSync(path.join(dir,name)));
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  let browser;
  try {
  browser = await chromium.launch({executablePath:process.env.IRONMATE_CHROME || undefined,
    headless:true, args:process.env.IRONMATE_CHROME_NO_SANDBOX === "1" ? ["--no-sandbox"] : []});
    const page = await browser.newPage({viewport:{width:1400,height:1000},deviceScaleFactor:1});
    const errors=[], remote=[];
    page.on("pageerror",err=>errors.push(err.message));
    await page.route(/^https?:/,route=>{if(route.request().url().startsWith(origin+"/")) return route.continue();remote.push(route.request().url());return route.abort();});
    const base64=fs.readFileSync(path.join(dir,"sample.base64.txt"),"utf8");
    const uri=fs.readFileSync(path.join(dir,"sample.data-uri.txt"),"utf8");
    const html='<!doctype html><meta charset="utf-8"><title>web-ui → Ironmate formats</title>'+
      '<style>body{font:16px sans-serif;margin:24px;background:#e6eaf0}section{display:inline-block;vertical-align:top;margin:8px;padding:16px;background:white}img{display:block;max-width:620px}</style>'+
      '<h1>共通JSON → SVG / PNG / Base64 / PNG data URI</h1>'+
      ['SVG','PNG','Base64','PNG data URI'].map((name,i)=>'<section><h2>'+name+'</h2><img id="i'+i+'" src="'+['sample.svg','sample.png','data:image/png;base64,'+base64,uri][i]+'"></section>').join('');
    fs.writeFileSync(path.join(dir,"sample.html"),html);
    await page.goto(origin+"/sample.html");
    const images = await page.evaluate(async()=>{
      const list=[...document.images]; await Promise.all(list.map(img=>img.decode()));
      return list.map(img=>{
        const c=document.createElement('canvas');c.width=img.naturalWidth;c.height=img.naturalHeight;
        const ctx=c.getContext('2d');ctx.drawImage(img,0,0);
        return {width:c.width,height:c.height,data:Array.from(ctx.getImageData(0,0,c.width,c.height).data)};
      });
    });
    for(const img of images) assert(img.width>100 && img.height>100);
    // PNG and both transports are lossless. Vector re-rasterization can differ
    // in edge antialiasing; compare composited pixels and record that difference.
    for(const img of images.slice(2)) assert.deepEqual(img,images[1]);
    assert.equal(images[0].width,images[1].width);assert.equal(images[0].height,images[1].height);
    let difference=0, changed=0;
    for(let i=0;i<images[0].data.length;i+=4){
      let pixelChanged=false;
      for(let c=0;c<3;c++){
        const a=images[0].data,b=images[1].data;
        const x=255+(a[i+c]-255)*a[i+3]/255, y=255+(b[i+c]-255)*b[i+3]/255;
        difference+=Math.abs(x-y);if(Math.abs(x-y)>1) pixelChanged=true;
      }
      if(pixelChanged) changed++;
    }
    const mae=difference/(images[0].width*images[0].height*3);
    assert(mae<2, 'SVG/PNG white-composited mean error: '+mae);
    await page.screenshot({path:path.join(dir,"browser.png"),fullPage:true});
    await page.goto(origin+"/escaped.svg");
    assert.equal(await page.locator('script,foreignObject,image,a').count(),0);
    assert.equal(await page.evaluate(()=>window.__flow_injected),undefined);
    assert((await page.locator('text').allTextContents()).join(' ').includes('<img'));
    assert.deepEqual(errors,[]);assert.deepEqual(remote,[]);
    const report=JSON.parse(fs.readFileSync(path.join(dir,"report.json"),"utf8"));
    Object.assign(report,{browser:await browser.version(),png_transport_pixels_match:true,svg_png_white_composited_mae:mae,svg_png_changed_pixels:changed,
      image_count:images.length,cjk_font:cjkFont,page_errors:errors,remote_requests:remote});
    fs.writeFileSync(path.join(dir,"report.json"),JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify(report));
  } finally {if(browser) await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(err=>{console.error(err);process.exitCode=1;});
