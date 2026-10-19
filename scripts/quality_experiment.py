# quality_experiment.py
# __all__: 4
"""Deterministic Studio perturbations; stdlib only, exploratory scores, no quality winner."""
__all__ = ['perturb', 'evaluate', 'run', 'main']

import argparse, hashlib, html, json, platform, statistics, struct, sys, time, tracemalloc, zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from photo_grid import decode_png
from studio_alignment import invert_translation, translate_rgba
from studio_image_quality import compare_rgba, foreground_mask as _mask, reference_energy as _energy
from studio_shape_metrics import metrics


def _resize(pixels, width, height, new_width, new_height):
    # Explicit nearest-neighbor floor coordinates, not browser-dependent resampling.
    return [pixels[min(height-1,y*height//new_height)*width+min(width-1,x*width//new_width)]
            for y in range(new_height) for x in range(new_width)]


def _png(width, height, pixels):
    def chunk(tag, data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data))
    raw = b''.join(b'\0'+bytes(c for p in pixels[y*width:(y+1)*width] for c in p) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))
            +chunk(b'IDAT',zlib.compress(raw,9))+chunk(b'IEND',b''))


def _measure(fn, repeats):
    fn()  # untimed warmup
    cpu = []
    for _ in range(repeats):
        start = time.process_time_ns(); value = fn(); cpu.append((time.process_time_ns()-start)/1e6)
    tracemalloc.start()
    try:
        fn(); _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return value, {'cpu_ms_median':statistics.median(cpu),'cpu_ms_samples':cpu,
                   'python_peak_allocated_bytes':peak}


def perturb(width, height, pixels, kind, seed=20261018):
    """Return reference, candidate and exact recipe. Thin-line case has a labelled probe reference."""
    ref = list(pixels); out = list(ref); white = (255,255,255,255)
    recipe = {'kind':kind,'clipped_nonfill':0,'seed':seed,'reference_variant':'original'}
    if kind in ('shift_1px','edge_clip'):
        dx = 1 if kind == 'shift_1px' else max(2,width//8)
        moved = translate_rgba(width,height,ref,dx,0,fill=white)
        out = moved['pixels']; recipe.update(dx=dx,dy=0,clipped_nonfill=moved['clipped_nonfill'])
        back = invert_translation(width,height,out,dx,0,fill=white)['pixels']
        recipe['inverse_exact'] = back == ref
    elif kind == 'shrink_expand':
        nw,nh=max(1,width//4),max(1,height//4)
        out = _resize(_resize(ref,width,height,nw,nh),nw,nh,width,height)
        recipe.update(interpolation='nearest-floor',intermediate=[nw,nh])
    elif kind == 'enlarge_crop':
        nw,nh=width*5//4,height*5//4
        large = _resize(ref,width,height,nw,nh); ox,oy=(nw-width)//2,(nh-height)//2
        out = [large[(y+oy)*nw+x+ox] for y in range(height) for x in range(width)]
        recipe.update(interpolation='nearest-floor',intermediate=[nw,nh],crop_origin=[ox,oy])
    elif kind == 'mosaic':
        cell = 5
        for y in range(0,height,cell):
            for x in range(0,width,cell):
                ids=[yy*width+xx for yy in range(y,min(y+cell,height)) for xx in range(x,min(x+cell,width))]
                color=tuple(sum(ref[i][c] for i in ids)//len(ids) for c in range(4))
                for i in ids: out[i]=color
        recipe['cell']=cell
    elif kind == 'blur':
        # Clamp-to-edge box filter, integer floor, all four channels independently.
        for y in range(height):
            for x in range(width):
                ids=[min(height-1,max(0,y+dy))*width+min(width-1,max(0,x+dx)) for dy in (-1,0,1) for dx in (-1,0,1)]
                out[y*width+x]=tuple(sum(ref[i][c] for i in ids)//9 for c in range(4))
        recipe['kernel']='3x3 box, clamp, floor'
    elif kind == 'thin_line_loss':
        # Controlled 1px line on the existing source. Only its middle third is deleted.
        y=height//4; x0,x1=width//4,3*width//4
        for x in range(x0,x1): ref[y*width+x]=(0,0,0,255)
        out=list(ref)
        for x in range(x0+(x1-x0)//3,x0+2*(x1-x0)//3): out[y*width+x]=white
        recipe.update(reference_variant='original + black 1px horizontal probe',probe=[x0,y,x1,y],loss='middle third to white')
    elif kind == 'contour_dilate':
        mask=_mask(ref)
        for i in range(width*height):
            if i in mask: continue
            neighbors=[j for j in (i-1 if i%width else i,i+1 if i%width+1<width else i,i-width if i>=width else i,i+width if i+width<width*height else i) if j in mask]
            if neighbors: out[i]=ref[min(neighbors)]
    elif kind == 'color_change':
        out=[(255-r,255-g,255-b,a) for r,g,b,a in ref]
    elif kind != 'identity': raise ValueError('unknown perturbation')
    return ref,out,recipe


def evaluate(width, height, reference, candidate, repeats=3):
    """Measure the production APIs in separate groups; memory excludes prebuilt inputs."""
    a,b=_mask(reference),_mask(candidate); weights=_energy(reference,width,height)
    proxy=lambda pixels,mask:[(*p[:3],255 if i in mask else 0) for i,p in enumerate(pixels)]
    ar,br=proxy(reference,a),proxy(candidate,b)
    shape,sc=_measure(lambda:metrics(width,height,a,b,weights),repeats)
    alpha,ac=_measure(lambda:compare_rgba(width,height,reference,candidate,radius=2),repeats)
    fg,fc=_measure(lambda:compare_rgba(width,height,ar,br,radius=2),repeats)
    return {'alpha':alpha,'foreground':{**shape,**{k:v for k,v in fg.items() if k.startswith('Align')}},
            'rgba_similarity':alpha['RGBA_L1_Similarity'],
            'mask_pixels':{'reference':len(a),'candidate':len(b)},
            'cost':{'foreground_metrics':sc,'alpha_rgba_alignment':ac,'foreground_alignment':fc}}


def _dashboard(report, out):
    rows=report['cases']; metrics_=['IoU','Aligned_IoU','Dice','Energy_Dice','Symmetric_Near_Field']
    body=['<!doctype html><meta charset="utf-8"><title>Studio quality experiment</title><style>body{font:15px system-ui;margin:24px;color:#173b3b}table{border-collapse:collapse;font-size:12px}td,th{padding:5px;border:1px solid #ccd}img{width:110px;image-rendering:pixelated}svg{border:1px solid #ccd}button{margin:8px}</style><h1>Studio quality / compute observations</h1><p>Exploratory, no perceptual quality winner. Foreground: RGB distance from white >32 after alpha compositing. Alpha mask remains separate. null = undefined. Alignment radius = 2; shifts can clip. CPU timing excludes tracing; memory is traced Python allocations, not RSS. Images link to exact pixels.</p>']
    # Separate scatter panels, never combine different metrics into one winner score.
    for metric in ['IoU','Aligned_IoU','RGBA','Symmetric_Near_Field']:
        xmax=max(c['cost']['foreground_alignment']['cpu_ms_median'] for c in rows)
        dots=[]
        for c in rows:
            v=c['rgba_similarity'] if metric=='RGBA' else c['foreground'][metric]
            x=45+400*c['cost']['foreground_alignment']['cpu_ms_median']/max(xmax,1e-9); y=225-180*v
            memory=c['cost']['foreground_alignment']['python_peak_allocated_bytes']
            dots.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{2+min(memory/300000,5):.2f}" fill="{"#c44867" if c["width"]==128 else "#087d79"}" opacity=".65"><title>{html.escape(c["id"])}: {v:.6f}; {memory} allocated bytes; {c["png_bytes"]} PNG bytes</title></circle>')
        body.append(f'<h2>{metric}</h2><svg viewBox="0 0 500 270" width="500" role="img" aria-label="{metric} versus foreground alignment CPU"><path d="M45 30V225H460" fill="none" stroke="#456"/><text x="4" y="35">1.0</text><text x="4" y="225">0.0</text>{"".join(dots)}<text x="45" y="252">CPU ms: 0 → {xmax:.2f}; red=128px, teal=64px</text></svg>')
    body.append('<h2>Scores, cost and exact image pairs</h2><p>Click headers to sort. Size is compressed PNG bytes; raw bytes = width × height × 4. Boundary tolerance is not perceptual similarity.</p><table id="data"><thead><tr>'+''.join(f'<th onclick="sortTable({i})">{h}</th>' for i,h in enumerate(['case','reference','candidate','alpha IoU',*metrics_,'RGBA','dx,dy','clip','CPU ms¹','peak KiB¹','PNG bytes']))+'</tr></thead><tbody>')
    for c in rows:
        fg=c['foreground']; values=[c['id'],f'<a href="{c["reference_png"]}"><img src="{c["reference_png"]}" alt="reference"></a>',f'<a href="{c["candidate_png"]}"><img src="{c["candidate_png"]}" alt="candidate"></a>',c['alpha']['IoU'],*[fg[m] for m in metrics_],c['rgba_similarity'],f'{fg["Alignment_dx"]},{fg["Alignment_dy"]}',c['recipe']['clipped_nonfill'],c['cost']['foreground_alignment']['cpu_ms_median'],c['cost']['foreground_alignment']['python_peak_allocated_bytes']/1024,c['png_bytes']]
        body.append('<tr>'+''.join(f'<td>{v:.6f}</td>' if isinstance(v,float) else f'<td>{v if v is not None else "null"}</td>' for v in values)+'</tr>')
    body.append('</tbody></table><p>¹ Foreground alignment API group, including mask scoring and proxy RGBA. Not the cost of Aligned IoU alone. All three measured API groups and CPU samples are in results.json.</p><script>function sortTable(n){let b=document.querySelector("tbody"),r=[...b.rows];r.sort((a,c)=>{let x=a.cells[n].textContent,y=c.cells[n].textContent;return x!==""&&y!==""&&Number.isFinite(+x)&&Number.isFinite(+y)?+x-+y:x.localeCompare(y)});r.forEach(x=>b.appendChild(x))}</script>')
    (out/'dashboard.html').write_text('\n'.join(body),encoding='utf-8')


def run(fixtures, out, repeats=3):
    out=Path(out); out.mkdir(parents=True,exist_ok=True); images=out/'images'; images.mkdir(exist_ok=True)
    manifest=json.loads(Path(fixtures).read_text()); cases=[]
    kinds=['identity','shift_1px','shrink_expand','enlarge_crop','mosaic','blur','thin_line_loss','contour_dilate','color_change','edge_clip']
    for fixture in manifest['fixtures']:
        source=(Path(fixtures).parent/fixture['file']).read_bytes()
        width,height,rows=decode_png(source); pixels=[tuple(row[i:i+4]) for row in rows for i in range(0,len(row),4)]
        for size in ([64] if fixture['seed']==20261019 else [64,128]):
            # Preserve aspect ratio of the existing Studio demo.
            w,h=size,max(1,round(size*height/width)); ref=_resize(pixels,width,height,w,h)
            for kind in kinds:
                cpu=time.process_time_ns(); a,b,recipe=perturb(w,h,ref,kind,fixture['seed'])
                transform_ms=(time.process_time_ns()-cpu)/1e6
                key=f'{fixture["name"]}-{fixture["seed"]}-{size}-{kind}'
                result=evaluate(w,h,a,b,repeats); png=_png(w,h,b)
                refname=f'images/{key}-ref.png'; name=f'images/{key}.png'
                (out/refname).write_bytes(_png(w,h,a)); (out/name).write_bytes(png)
                cases.append({'id':key,'scenario':fixture['name'],'seed':fixture['seed'],'width':w,'height':h,
                              'recipe':recipe,'source_sha256':hashlib.sha256(source).hexdigest(),
                              'reference_sha256':hashlib.sha256(bytes(c for p in a for c in p)).hexdigest(),
                              'candidate_sha256':hashlib.sha256(bytes(c for p in b for c in p)).hexdigest(),
                              'reference_png':refname,'candidate_png':name,'png_bytes':len(png),'raw_rgba_bytes':w*h*4,
                              'transform_cpu_ms':transform_ms,**result})
            print(f'{fixture["name"]} seed={fixture["seed"]} {w}x{h}',flush=True)
    root=Path(__file__).resolve().parents[1]
    files=['studio_shape_metrics.py','studio_image_quality.py','studio_alignment.py','scripts/quality_experiment.py','tests/studio_fixtures.cjs','tests/studio_quality_browser.cjs']
    report={'schema':'ironmate-studio-quality/1','exploratory':True,'environment':{'python':sys.version,'platform':platform.platform(),'machine':platform.machine(),'browser':manifest['browser']},
            'protocol':{'seeds':[20261018,20261019],'alpha_threshold':0,'foreground_threshold':32,'alignment_radius':2,'cpu_repeats':repeats,'memory':'tracemalloc peak per warmed API call; prebuilt pixels/masks/weights excluded; not RSS','energy':'reference-only integer forward RGB edge differences after white compositing; zero denominator -> null','sizes':'64 and 128 longest-side pixels; second seed 64 only; demo aspect preserved','timing':'process_time_ns median, untraced; one warmup; tracing in separate pass; input/mask construction, IO and PNG encoding excluded from API costs'},
            'source_sha256':{f:hashlib.sha256((root/f).read_bytes()).hexdigest() for f in files},'cases':cases}
    (out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    _dashboard(report,out)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();run(args.fixtures,args.out)


if __name__=='__main__': main()
