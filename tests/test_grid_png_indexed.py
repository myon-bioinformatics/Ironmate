"""Stdlib contracts for optional reduced-bit PNG output."""
import base64
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grid_png
import pillow_min
import pixel_grid


class IndexedPngTests(unittest.TestCase):
    def test_all_depths_odd_width_scaling_alpha_and_palette_order(self):
        for count, depth in ((1, 1), (2, 1), (3, 2), (4, 2), (5, 4), (16, 4), (17, 8), (256, 8)):
            colors = ['#%02X%02X%02X%02X' % (i, 255-i, i, (i*31) & 255) for i in range(count)]
            art = {'width': 13, 'height': 3, 'colors': colors,
                   'pixels': [[(x+y) % count for x in range(13)] for y in range(3)]}
            for scale in (1, 3):
                data = grid_png.to_png(art, scale, indexed=True)
                self.assertEqual(struct.unpack('>IIBBBBB', data[16:29])[2:4], (depth, 3))
                expected = b''.join(bytes.fromhex(colors[v][1:]) * scale
                    for row in art['pixels'] for _ in range(scale) for v in row)
                self.assertEqual(pillow_min.open_bytes(data).tobytes(), expected)
                self.assertEqual(data, grid_png.to_png(art, scale, indexed=True))
                self.assertEqual(base64.b64decode(grid_png.to_base64(art, scale, indexed=True)), data)

    def test_procedural_masks_and_legacy_default(self):
        for mask in pixel_grid.MASKS:
            art = pixel_grid.render(mask, 'C02', 'shadow', 16)
            legacy = grid_png.to_png(art)
            self.assertEqual(legacy, grid_png.to_png(art, indexed=False))
            self.assertEqual(legacy[24:26], b'\x08\x06')
            self.assertEqual(pillow_min.open_bytes(legacy).tobytes(),
                pillow_min.open_bytes(grid_png.to_png(art, indexed=True, meta=True)).tobytes())

    def test_invalid_palette_index_and_mode(self):
        art = pixel_grid.render('circle', size=8)
        for colors in ([], ['#000000FF'] * 257):
            with self.assertRaises(ValueError):
                grid_png.to_png(dict(art, colors=colors), indexed=True)
        with self.assertRaises(ValueError):
            grid_png.to_png(art, indexed=1)
        art['pixels'][0][0] = 999
        with self.assertRaises(ValueError):
            grid_png.to_png(art, indexed=True)

    def test_cli_without_site_packages(self):
        art = pixel_grid.render('circle', size=8)
        r = subprocess.run([sys.executable, '-S', str(Path(grid_png.__file__)), '-', '--indexed'],
            input=json.dumps(art).encode(), capture_output=True, check=True)
        self.assertEqual(pillow_min.open_bytes(r.stdout).tobytes(),
            pillow_min.open_bytes(grid_png.to_png(art)).tobytes())


if __name__ == '__main__':
    unittest.main()
