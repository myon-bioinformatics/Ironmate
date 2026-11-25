"""DRAgoWing matrix-to-scene importer (MIT). See docs/image-studio.md."""
import math


def heatmap_scene(source):
    """Import a numeric matrix or ONE Plotly heatmap trace; row zero is at top.

    This imports data, not Plotly layout/axis rendering. Keep source metadata so
    the scene is an editable composition, never a replacement research result.
    """
    if isinstance(source, list):
        trace = {'z': source}
    elif isinstance(source, dict) and isinstance(source.get('data'), list):
        traces = [t for t in source['data'] if isinstance(t, dict) and t.get('type') == 'heatmap']
        if len(traces) != 1:
            raise ValueError('exactly one heatmap trace required')
        trace = traces[0]
    else:
        trace = source
    if not isinstance(trace, dict):
        raise ValueError('matrix or heatmap object required')
    z = trace.get('z')
    if (not isinstance(z, list) or not z or not isinstance(z[0], list) or not z[0]
            or len(z) * len(z[0]) > 4096 or any(not isinstance(r, list) or len(r) != len(z[0]) for r in z)):
        raise ValueError('rectangular matrix of 1..4096 cells required')
    finite = [v for row in z for v in row if v is not None]
    def safe(v):
        if type(v) is int:
            return abs(v) <= 2**53-1
        return type(v) is float and math.isfinite(v) and (not v.is_integer() or abs(v) <= 2**53-1)
    if any(not safe(v) for v in finite):
        raise ValueError('finite JavaScript-safe numbers or null required')
    low, high = trace.get('zmin'), trace.get('zmax')
    low = min(finite, default=0) if low is None else low
    high = max(finite, default=1) if high is None else high
    if not safe(low) or not safe(high) or low > high:
        raise ValueError('finite JavaScript-safe color range with zmin <= zmax required')
    x, y = trace.get('x', list(range(len(z[0])))), trace.get('y', list(range(len(z))))
    if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(z[0]) or len(y) != len(z):
        raise ValueError('axis label counts do not match matrix')
    return {'schema': 'ironmate-image-studio/1', 'width': 1280, 'height': 720, 'background': '#FFFFFF',
            'layers': [{'id': 'heatmap', 'kind': 'heatmap', 'name': 'Heatmap', 'x': 80, 'y': 90,
                        'w': 1120, 'h': 520, 'rotation': 0, 'opacity': 1,
                        'z': z, 'xlabels': x, 'ylabels': y, 'low': low, 'high': high,
                        'levels': 0, 'labels': True}], 'source': source}
