"""Join recorded Studio diagnostics with existing MAE/RMSE selection; stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import image_compare as compare
from scripts import quality_experiment as experiment
from studio_candidate_selection import diagnostic_row, reference_key, summarize, rank_relations, enrich_sweep

ROOT = Path(__file__).resolve().parents[1]


def load_image(path):
    return compare.read_png(path.read_bytes())


def recorded_groups(folder):
    recorded = json.loads((folder/'results.json').read_text(encoding='utf-8'))
    if recorded['schema'] != 'ironmate-studio-quality/1':
        raise ValueError('unsupported evidence schema')
    groups = defaultdict(list)
    for case in recorded['cases']:
        ref, candidate = (load_image(folder/case[k]) for k in ('reference_png', 'candidate_png'))
        for image, field in ((ref,'reference_sha256'), (candidate,'candidate_sha256')):
            if image[:2] != (case['width'],case['height']) or hashlib.sha256(image[2]).hexdigest() != case[field]:
                raise ValueError('recorded pixel hash or dimensions disagree')
        key = (case['scenario'],case['seed'],reference_key(ref))
        row = diagnostic_row(ref,candidate,len(groups[key]),recorded=case)
        row.update(id=case['id'], kind=case['recipe']['kind'],
                   recipe=case['recipe'], recorded_api_cost=case['cost'],
                   transform_cpu_ms=case['transform_cpu_ms'])
        if case['recipe']['kind'] in ('shift_1px','edge_clip'):
            row['source_clipped_nonfill'] = case['recipe']['clipped_nonfill']
            row['source_inverse_exact'] = case['recipe']['inverse_exact']
        # Enlargement/crop has no translation counter. Do not turn its zero into losslessness.
        if case['recipe']['kind'] == 'enlarge_crop':
            nw,nh = case['recipe']['intermediate']
            row['crop_discarded_canvas_pixels'] = nw*nh-ref[0]*ref[1]
        groups[key].append(row)
    result = []
    for (scenario,seed,key),rows in groups.items():
        competing = [r for r in rows if r['kind'] != 'identity']
        result.append({'scenario': scenario, 'seed': seed, 'reference_key': key,
                       'candidates': rows, 'rank_relations': rank_relations(rows),
                       'mae_relations': rank_relations(rows,'rgb_mae'),
                       'selection_excludes': 'identity only; probe references are separate singleton groups',
                       'selection': summarize(competing)})
    return result


def sweep(reference, nearest, smooth, *, name, timing=None):
    start = time.process_time_ns()
    report, images = compare.analyze(reference,nearest,smooth)
    elapsed = (time.process_time_ns()-start)/1e6
    enrich_sweep(report,images,reference)
    # analyze includes blend generation AND RGB metrics; never label it transform-only time.
    report['sweep_cpu_ms_including_rgb_metrics'] = elapsed
    report['name'] = name
    report['pixel_sha256'] = {k:reference_key(v) for k,v in
                             [('reference',reference),('nearest',nearest),('smooth',smooth)]}
    if timing:
        report['endpoint_transform_cpu_ms'] = timing
    return report


def resampling_sweeps(folder):
    """Reuse frozen browser endpoints, plus a known-reference reduction experiment.

    Reduction uses an explicit block-constant 2x reference. This synthetic prior
    favors exact lattice methods and must not be generalized to natural images.
    """
    original = ROOT/'docs/evidence/studio-delivery/tradeoff-original'
    result = [sweep(*(load_image(original/(k+'.png')) for k in ('reference','nearest','smooth')),
                    name='existing-browser-upscale-256')]
    manifest = json.loads((folder/'fixtures.json').read_text())
    for fixture in manifest['fixtures']:
        if fixture['seed'] != 20261018 or fixture['name'] == 'studio-demo':
            continue
        source = load_image(folder/fixture['file'])
        pixels = [tuple(source[2][i:i+4]) for i in range(0,len(source[2]),4)]
        pixels = experiment._resize(pixels,*source[:2],64,64)
        ref = (64,64,bytes(c for p in pixels for c in p))
        # The known high-resolution source is 2x block replication. Both reducers
        # receive the same blurred source; the exact low-resolution reference is fixed.
        high = experiment._resize(pixels,64,64,128,128)
        _,degraded,_ = experiment.perturb(128,128,high,'blur',fixture['seed'])
        start = time.process_time_ns()
        nearest = experiment._resize(degraded,128,128,64,64)
        nearest_ms = (time.process_time_ns()-start)/1e6
        start = time.process_time_ns()
        area = [tuple(sum(degraded[(y*2+dy)*128+x*2+dx][c]
                          for dy in (0,1) for dx in (0,1))//4 for c in range(4))
                for y in range(64) for x in range(64)]
        area_ms = (time.process_time_ns()-start)/1e6
        image = lambda p:(64,64,bytes(c for pixel in p for c in pixel))
        r = sweep(ref,image(nearest),image(area),name='synthetic-reduction-'+fixture['name'],
                  timing={'nearest_floor':nearest_ms,'area_2x2_floor':area_ms})
        r['reduction_protocol'] = 'reference 64 -> block replicate 128 -> 3x3 blur -> floor nearest or 2x2 area reduce 64; blend endpoints; not browser resampling'
        r['blend_definition'] = r['blend_definition'].replace('smooth','area')
        r['source_sha256'] = hashlib.sha256((folder/fixture['file']).read_bytes()).hexdigest()
        result.append(r)
    return result


def run(folder, out):
    folder,out = Path(folder),Path(out)
    if out.is_symlink() or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        raise ValueError('output must be a new or empty directory')
    groups = recorded_groups(folder)
    sweeps = resampling_sweeps(folder)
    totals = {m:{k:sum(g['rank_relations'][m][k] for g in groups)
                  for k in groups[0]['rank_relations'][m]} for m in groups[0]['rank_relations']}
    files = ['image_compare.py','studio_candidate_selection.py','studio_image_quality.py',
             'studio_alignment.py','studio_shape_metrics.py','scripts/quality_selection_experiment.py']
    report = {'schema':'ironmate-quality-selection/1', 'exploratory':True,
              'scope':'reference oracle; no perceptual preference or universal best candidate',
              'environment':{'python':sys.version,'platform':platform.platform()},
              'recorded_results_sha256':hashlib.sha256((folder/'results.json').read_bytes()).hexdigest(),
              'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
              'protocol':{'grouping':'scenario, seed, width, height, exact reference RGBA hash',
                          'legacy_mae_weight':0.5,'pair_reversal':'signed utility difference product < -1e-12; ties excluded',
                          'cost':'recorded transform single CPU sample; three recorded warmed API groups overlap and must not be summed; new full diagnostic CPU separate',
                          'pareto':'quality axes omit Dice, RGBA, registration and cost; optional cost Pareto adds recorded transform CPU; null axes excluded',
                          'source_clipping':'only translation provenance known; other recipes null; registration clipping separate'},
              'totals':totals, 'groups':groups, 'sweeps':sweeps}
    out.mkdir(parents=True,exist_ok=True)
    (out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=ROOT/'docs/evidence/studio-quality')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    run(args.evidence,args.out)


if __name__ == '__main__':
    main()
