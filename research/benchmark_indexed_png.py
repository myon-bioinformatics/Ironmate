"""Reproducible RGBA/indexed PNG comparison; emits JSON to stdout."""
import importlib.util
import hashlib, json, platform, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pixel_grid
from ironlib import grid_output


def load_vendored(name, relpath):
    """Load a vendored file by path under a repo-unique name (cli_args README: Loading a vendored copy)."""
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / relpath)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


pillow_min = load_vendored("ironmate_pillow_min", "vendor/pillow_min.py")


def main():
    records = []
    for size in (16, 64, 256):
        for mask in ('circle', 'cloud', 'rock'):
            art = pixel_grid.render(mask, 'C02', 'shadow', size)
            outputs = {}
            for indexed in (False, True):
                samples = []
                grid_output.to_png(art, indexed=indexed)
                for _ in range(7):
                    start = time.perf_counter_ns()
                    data = grid_output.to_png(art, indexed=indexed)
                    samples.append(time.perf_counter_ns() - start)
                outputs['indexed' if indexed else 'rgba'] = {
                    'bytes': len(data), 'samples_ns': samples,
                    'median_ns': statistics.median(samples), 'sha256': hashlib.sha256(data).hexdigest(),
                }
            a = pillow_min.open_bytes(grid_output.to_png(art)).tobytes()
            b = pillow_min.open_bytes(grid_output.to_png(art, indexed=True)).tobytes()
            assert a == b
            records.append({'size': size, 'mask': mask, 'rgba_pixels_sha256': hashlib.sha256(a).hexdigest(), **outputs})
    print(json.dumps({'python': sys.version, 'platform': platform.platform(),
        'repeats': 7, 'palette': 'C02', 'effect': 'shadow', 'scale': 1,
        'dependencies_added': 0, 'records': records}, indent=2))


if __name__ == '__main__':
    main()
