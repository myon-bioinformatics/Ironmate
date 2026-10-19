"""Reference-scoped diagnostic selection; no perceptual or unknown-image oracle."""
from __future__ import annotations

import hashlib
import math
import time
from itertools import combinations

from image_compare import metrics as pixel_metrics, balance_score, select_candidates
from studio_alignment import translate_rgba, invert_translation
from studio_image_quality import compare_rgba, foreground_mask, reference_energy
from studio_shape_metrics import metrics as shape_metrics

# Positive direction means larger is better. Aligned overlap is diagnostic only.
DIRECTIONS = {'rgb_mae': -1, 'rgb_rmse': -1, 'balance_score': 1, 'iou': 1,
              'dice': 1, 'energy_dice': 1, 'near_field': 1, 'rgba_similarity': 1,
              'aligned_iou': 1, 'missing_foreground': -1, 'transform_cpu_ms': -1}
QUALITY_AXES = ('rgb_mae', 'rgb_rmse', 'iou', 'energy_dice', 'near_field')


def reference_key(image):
    w, h, data = image
    return f'{w}x{h}:'+hashlib.sha256(data).hexdigest()


def _pixels(image):
    return [tuple(image[2][i:i+4]) for i in range(0, len(image[2]), 4)]


def diagnostic_row(reference, candidate, index, *, mae_weight=0.5, recorded=None):
    """Use the frozen foreground protocol; optionally reuse verified recorded scores.

    Callers reusing recorded scores must validate their pixel hashes first. CPU for
    this complete diagnostic call includes input conversion, unlike recorded API
    groups; it is neither transform time nor a sum of overlapping API groups.
    """
    start = time.process_time_ns()
    errors = pixel_metrics(reference, candidate)
    w, h, _ = reference
    a, b = _pixels(reference), _pixels(candidate)
    am, bm = foreground_mask(a), foreground_mask(b)
    shape = shape_metrics(w, h, am, bm, reference_energy(a, w, h))
    rgba = 1-sum(abs(x-y) for x,y in zip(reference[2],candidate[2]))/(w*h*1020)
    if recorded is None:
        proxy = lambda pixels, mask: [(*p[:3], 255 if i in mask else 0) for i,p in enumerate(pixels)]
        fg = compare_rgba(w, h, proxy(a, am), proxy(b, bm), radius=2)
        alpha = compare_rgba(w, h, a, b, radius=0)['IoU']
    else:
        fg = recorded['foreground']
        if any(fg[k] != v for k,v in shape.items()) or rgba != recorded['rgba_similarity']:
            raise ValueError('recorded scores disagree with supplied pixels')
        alpha = recorded['alpha']['IoU']
    dx, dy = fg['Alignment_dx'], fg['Alignment_dy']
    moved = translate_rgba(w, h, b, dx, dy, fill=(255,255,255,255))
    back = invert_translation(w, h, moved['pixels'], dx, dy, fill=(255,255,255,255))
    row = {'index': index, 'reference_key': reference_key(reference), **errors,
           'balance_score': balance_score(errors['rgb_mae'], errors['rgb_rmse'], mae_weight),
           'iou': shape['IoU'], 'dice': shape['Dice'], 'energy_dice': shape['Energy_Dice'],
           'near_field': shape['Symmetric_Near_Field'], 'rgba_similarity': rgba,
           'alpha_iou': alpha, 'aligned_iou': fg['Aligned_IoU'],
           'alignment_dx': dx, 'alignment_dy': dy,
           'missing_foreground': len(am-bm), 'extra_foreground': len(bm-am),
           'registration_clipped_nonfill': moved['clipped_nonfill'],
           'registration_inverse_exact': back['pixels'] == b,
           # A comparison cannot reconstruct a transform's provenance.
           'source_clipped_nonfill': None, 'source_inverse_exact': None,
           'transform_cpu_ms': None}
    row['diagnostic_cpu_ms'] = (time.process_time_ns()-start)/1e6
    return row


def _pool(rows):
    if not rows:
        raise ValueError('candidate pool must not be empty')
    if len({r['reference_key'] for r in rows}) != 1:
        raise ValueError('compare only candidates with the same reference dimensions and RGBA hash')
    indices = [r['index'] for r in rows]
    if any(type(i) is not int or i < 0 for i in indices) or len(set(indices)) != len(indices):
        raise ValueError('candidate indices must be unique nonnegative integers')


def _value(row, metric):
    v = row.get(metric)
    if v is None:
        return None
    if type(v) not in (int, float) or not math.isfinite(v):
        raise ValueError('metrics must be finite numbers or null')
    return DIRECTIONS[metric]*v


def pareto_indices(rows, axes=QUALITY_AXES):
    """Strict dominance on explicit axes; null is excluded, never filled with zero."""
    _pool(rows)
    if not axes or any(a not in DIRECTIONS for a in axes):
        raise ValueError('unknown or empty Pareto axes')
    complete = [(r['index'], [_value(r,a) for a in axes]) for r in rows]
    valid = [(i,v) for i,v in complete if all(x is not None for x in v)]
    return {'axes': list(axes), 'indices': [i for i,v in valid if not any(
        all(a >= b for a,b in zip(other,v)) and any(a > b for a,b in zip(other,v))
        for j,other in valid if i != j)],
        'undefined_indices': [i for i,v in complete if any(x is None for x in v)]}


def select_quality(rows, objective='balance_score', *, max_missing_foreground=None,
                   max_source_clipped_nonfill=None):
    """Explicit objective + optional raw-mask/loss constraints; no silent fallback.

    Unknown source clipping fails a requested clipping constraint. A mask miss is
    not an exact lost-information count. Alignment never clears either constraint.
    """
    _pool(rows)
    if objective not in DIRECTIONS:
        raise ValueError('unknown selection objective')
    for limit in (max_missing_foreground, max_source_clipped_nonfill):
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError('limits must be nonnegative integers')
    eligible, excluded = [], []
    for row in rows:
        reasons = []
        for field, limit in [('missing_foreground', max_missing_foreground),
                             ('source_clipped_nonfill', max_source_clipped_nonfill)]:
            value = row.get(field)
            if limit is not None and (value is None or value > limit):
                reasons.append(field+' unknown or above limit')
        if _value(row, objective) is None:
            reasons.append(objective+' undefined')
        if reasons:
            excluded.append({'index': row['index'], 'reasons': reasons})
        else:
            eligible.append(row)
    def order(row):
        secondary = ((row['rgb_rmse'],) if objective == 'rgb_mae' else
                     (row['rgb_mae'],) if objective == 'rgb_rmse' else
                     (row['rgb_mae'], row['rgb_rmse']) if objective == 'balance_score' else ())
        return (-_value(row, objective), *secondary, row['index'])
    ranked = sorted(eligible, key=order)
    tied = [r['index'] for r in ranked if _value(r, objective) == _value(ranked[0], objective)] if ranked else []
    return {'objective': objective, 'direction': 'max' if DIRECTIONS[objective] == 1 else 'min',
            'max_missing_foreground': max_missing_foreground,
            'max_source_clipped_nonfill': max_source_clipped_nonfill,
            'selected_index': ranked[0]['index'] if ranked else None,
            'tied_indices': tied, 'tie_break': ('legacy MAE/RMSE secondary errors then index'
                if objective in ('rgb_mae','rgb_rmse','balance_score') else 'lowest candidate index'),
            'excluded': excluded}


def summarize(rows):
    _pool(rows)
    return {'legacy': select_candidates(rows),
            'by_metric': {m: select_quality(rows, m) for m in DIRECTIONS},
            'quality_pareto': pareto_indices(rows),
            'cost_pareto': pareto_indices(rows, (*QUALITY_AXES, 'transform_cpu_ms'))}


def rank_relations(rows, left='iou'):
    """Same-reference pair counts; signed-utility product < -1e-12 is reversal.

    Near ties are recorded separately; exact score ordering is used by selection.
    """
    _pool(rows)
    result = {}
    for right in DIRECTIONS:
        counts = {'pairs': 0, 'undefined': 0, 'reversed': 0, 'agreed': 0, 'tie_or_near_tie': 0}
        for a,b in combinations(rows,2):
            counts['pairs'] += 1
            values = [_value(r,m) for r,m in ((a,left),(b,left),(a,right),(b,right))]
            if any(v is None for v in values):
                counts['undefined'] += 1
                continue
            product = (values[0]-values[1])*(values[2]-values[3])
            counts['reversed' if product < -1e-12 else 'agreed' if product > 1e-12 else 'tie_or_near_tie'] += 1
        result[right] = counts
    return result


def enrich_sweep(report, images, reference):
    """Opt-in diagnostics; legacy roles, PNGs and error definition stay unchanged."""
    if report['background_rgb'] != [255,255,255]:
        raise ValueError('foreground quality protocol requires white background')
    # Registration is costly; keep this diagnostic path deliberately bounded.
    if reference[0]*reference[1]*len(images) > 1_048_576:
        raise ValueError('quality diagnostics exceed 1MP total candidate pixels')
    rows = [diagnostic_row(reference, image, k, mae_weight=report['mae_weight'])
            for k,image in enumerate(images)]
    report['quality'] = {'schema': 'ironmate-candidate-quality/1',
                         'protocol': 'white composite; foreground distance >32; reference forward edge weights; alignment radius 2',
                         'scope': 'reference oracle, not human preference; no universal quality winner',
                         'candidates': rows, 'summary': summarize(rows), 'rank_relations': rank_relations(rows)}
