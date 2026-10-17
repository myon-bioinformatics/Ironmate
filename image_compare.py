"""Reference-based MAE/RMSE tradeoff sweep; stdlib and existing PNG codecs only.

No reference means no objective ranking. Scores describe this fixture and the
explicit weight, not perceptual quality or recovered information.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from grid_output import write_output
from grid_png import to_png
from photo_grid import decode_png


def read_png(data):
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('PNG must be at most 32MiB')
    w, h, rows = decode_png(data, max_pixels=4194304)
    return w, h, b''.join(bytes(row) for row in rows)


def _same(a, b):
    if a[:2] != b[:2] or len(a[2]) != a[0] * a[1] * 4 or len(b[2]) != len(a[2]):
        raise ValueError('images must have the same nonempty RGBA dimensions')
    if not a[0] or not a[1]:
        raise ValueError('images must be nonempty')


def blend(left, right, numerator, denominator=10):
    """Interpolate existing pixels in premultiplied 8-bit sRGB; never infer detail."""
    _same(left, right)
    if type(denominator) is not int or not 2 <= denominator <= 100 or type(numerator) is not int or not 0 <= numerator <= denominator:
        raise ValueError('blend needs integer 0 <= numerator <= denominator, denominator 2..100')
    if numerator == 0:
        return left
    if numerator == denominator:
        return right
    out = bytearray(len(left[2]))
    a, b, k, n = left[2], right[2], numerator, denominator
    for i in range(0, len(a), 4):
        alpha = (n-k)*a[i+3] + k*b[i+3]
        out[i+3] = (alpha+n//2)//n
        for c in range(3):
            out[i+c] = (((n-k)*a[i+3]*a[i+c] + k*b[i+3]*b[i+c] + alpha//2)//alpha) if alpha else 0
    return left[0], left[1], bytes(out)


def metrics(reference, candidate, background=(255, 255, 255)):
    """RGB MAE/RMSE after compositing on the stated background; alpha separate."""
    _same(reference, candidate)
    if len(background) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in background):
        raise ValueError('background needs three integer bytes')
    a, b = reference[2], candidate[2]
    absolute = squared = alpha_error = exact = 0
    for i in range(0, len(a), 4):
        exact += a[i:i+4] == b[i:i+4]
        alpha_error += abs(a[i+3]-b[i+3])
        for c in range(3):
            av = (a[i+c]*a[i+3]+background[c]*(255-a[i+3])+127)//255
            bv = (b[i+c]*b[i+3]+background[c]*(255-b[i+3])+127)//255
            d = av-bv
            absolute += abs(d)
            squared += d*d
    count = reference[0]*reference[1]
    return {'rgb_mae': absolute/(count*3), 'rgb_rmse': math.sqrt(squared/(count*3)),
            'alpha_mae': alpha_error/count, 'exact_rgba_pixels': exact, 'pixels': count}


def balance_score(mae, rmse, mae_weight=0.5):
    if type(mae_weight) not in (int, float) or not math.isfinite(mae_weight) or not 0 <= mae_weight <= 1:
        raise ValueError('MAE weight must be finite and within 0..1')
    if any(not math.isfinite(x) or not 0 <= x <= 255 for x in (mae, rmse)):
        raise ValueError('errors must be finite byte-scale values')
    return 100*(1-(mae_weight*mae+(1-mae_weight)*rmse)/255)


def analyze(reference, nearest, smooth, steps=10, mae_weight=0.5, background=(255, 255, 255)):
    if type(steps) is not int or not 2 <= steps <= 100 or steps % 2:
        raise ValueError('steps must be an even integer within 2..100')
    balance_score(0, 0, mae_weight)
    _same(reference, nearest)
    _same(reference, smooth)
    if reference[0]*reference[1]*(steps+1) > 16777216:
        raise ValueError('sweep exceeds 16MP total candidate pixels; reduce image size or steps')
    images = [blend(nearest, smooth, k, steps) for k in range(steps+1)]
    rows = []
    for k, image in enumerate(images):
        row = {'index': k, 'smooth_fraction': k/steps, **metrics(reference, image, background)}
        row['balance_score'] = balance_score(row['rgb_mae'], row['rgb_rmse'], mae_weight)
        rows.append(row)
    mae = min(rows, key=lambda r: (r['rgb_mae'], r['rgb_rmse'], r['index']))
    rmse = min(rows, key=lambda r: (r['rgb_rmse'], r['rgb_mae'], r['index']))
    balanced = min(rows, key=lambda r: (-r['balance_score'], r['rgb_mae'], r['rgb_rmse'], r['index']))
    pareto = [r['index'] for r in rows if not any(
        s['rgb_mae'] <= r['rgb_mae'] and s['rgb_rmse'] <= r['rgb_rmse'] and
        (s['rgb_mae'] < r['rgb_mae'] or s['rgb_rmse'] < r['rgb_rmse']) for s in rows)]
    report = {'schema': 'ironmate-image-tradeoff/1', 'width': reference[0], 'height': reference[1],
              'background_rgb': list(background), 'mae_weight': mae_weight,
              'score_definition': '100*(1-(mae_weight*RGB_MAE+(1-mae_weight)*RGB_RMSE)/255)',
              'blend_definition': 'premultiplied 8-bit sRGB, integer rounding; 0=nearest, 1=smooth',
              'selection_scope': 'oracle on this reference only; not an unknown-image quality estimate',
              'roles': {'mae_priority': mae['index'], 'rmse_priority': rmse['index'],
                        'midpoint': steps//2, 'balanced': balanced['index']},
              'pareto_indices': pareto, 'candidates': rows}
    return report, images


def png(image):
    w, h, rgba = image
    palette, mapping, pixels = [], {}, []
    for y in range(h):
        line = []
        for x in range(w):
            i = (y*w+x)*4
            color = '#'+rgba[i:i+4].hex().upper()
            if color not in mapping:
                mapping[color] = len(palette)
                palette.append(color)
            line.append(mapping[color])
        pixels.append(line)
    return to_png({'schema': 'ironmate-pixel-grid/1', 'width': w, 'height': h, 'colors': palette, 'pixels': pixels})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--reference', required=True, type=Path)
    p.add_argument('--nearest', required=True, type=Path)
    p.add_argument('--smooth', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--steps', type=int, default=10)
    p.add_argument('--mae-weight', type=float, default=0.5)
    args = p.parse_args(argv)
    try:
        sources = {k: getattr(args, k).read_bytes() for k in ('reference', 'nearest', 'smooth')}
        report, images = analyze(*(read_png(sources[k]) for k in ('reference', 'nearest', 'smooth')),
                                 steps=args.steps, mae_weight=args.mae_weight)
        report['input_sha256'] = {k: hashlib.sha256(v).hexdigest() for k, v in sources.items()}
        if args.out.is_symlink() or (args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir()))):
            raise FileExistsError('output must be a new or empty directory')
        args.out.mkdir(parents=True, exist_ok=True)
        for row, image in zip(report['candidates'], images):
            row['file'] = f"variant-{row['index']:02d}.png"
            write_output(str(args.out/row['file']), png(image))
        for role, index in report['roles'].items():
            write_output(str(args.out/(role+'.png')), (args.out/f'variant-{index:02d}.png').read_bytes())
        write_output(str(args.out/'report.json'), (json.dumps(report, indent=2, allow_nan=False)+'\n').encode())
        print(json.dumps(report['roles']))
    except (OSError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
