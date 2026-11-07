import io, subprocess, sys, tempfile, unittest
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

import png_zoom_gif


@unittest.skipIf(Image is None, 'optional Pillow codec unavailable')
class ZoomGifTests(unittest.TestCase):
    def png(self):
        image = Image.new('RGBA', (24, 16), (255, 0, 0, 255))
        image.paste((0, 255, 0, 255), (0, 8, 12, 16))
        image.putpixel((0, 15), (0, 0, 255, 255))
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        return buf.getvalue()

    def test_bottom_left_and_exact_reverse(self):
        frames = png_zoom_gif.zoom_frames(self.png(), zoom=2, steps=4)
        self.assertEqual(len(frames), 9)
        self.assertEqual(frames[4].getpixel((12, 8)), (0, 255, 0))
        for a, b in zip(frames, reversed(frames)):
            self.assertEqual(a.tobytes(), b.tobytes())

    def test_gif_decoded_frames_timing_and_endpoints(self):
        gif = Image.open(io.BytesIO(png_zoom_gif.to_gif(self.png(), zoom=2, steps=4)))
        frames, durations = [], []
        for i in range(gif.n_frames):
            gif.seek(i)
            frames.append(gif.convert('RGB').tobytes())
            durations.append(gif.info['duration'])
        self.assertEqual(gif.info['loop'], 0)
        self.assertEqual(sum(durations), 9 * 60 + 3 * 400)
        self.assertEqual(frames[0], frames[-1])
        self.assertNotEqual(frames[0], frames[len(frames) // 2])
        self.assertEqual(frames, frames[::-1])

    def test_alpha_compositing(self):
        image = Image.new('RGBA', (2, 2), (255, 0, 0, 128))
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        frame = png_zoom_gif.zoom_frames(buf.getvalue(), background=(0, 0, 0))[0]
        self.assertEqual(frame.getpixel((0, 0)), (128, 0, 0))

    def test_named_corners_and_ordered_route(self):
        image = Image.new('RGB', (40, 40))
        corners = [('bottom-left', (0, 20, 20, 40), (255, 0, 0)),
                   ('top-right', (20, 0, 40, 20), (0, 255, 0)),
                   ('bottom-right', (20, 20, 40, 40), (0, 0, 255)),
                   ('top-left', (0, 0, 20, 20), (255, 255, 0))]
        for _, box, color in corners:
            image.paste(color, box)
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        png = buf.getvalue()
        names = [name for name, _, _ in corners]
        frames = png_zoom_gif.zoom_frames(png, zoom=2, steps=4, anchors=names)
        self.assertEqual(len(frames), 33)
        for i, (name, _, color) in enumerate(corners):
            self.assertEqual(frames[i * 8 + 4].getpixel((20, 20)), color)
            self.assertEqual(frames[i * 8 + 8].tobytes(), frames[0].tobytes())
            single = png_zoom_gif.zoom_frames(png, zoom=2, steps=4, anchor=name)
            numeric = png_zoom_gif.zoom_frames(png, zoom=2, steps=4,
                                             anchor=png_zoom_gif.ANCHORS[name])
            self.assertEqual(single[4].tobytes(), numeric[4].tobytes())
        gif = Image.open(io.BytesIO(png_zoom_gif.to_gif(png, zoom=2, steps=4, anchors=names)))
        duration = 0
        for i in range(gif.n_frames):
            gif.seek(i)
            duration += gif.info['duration']
        self.assertEqual(duration, 33 * 60 + 9 * 400)
        self.assertEqual(gif.convert('RGB').tobytes(), image.tobytes())

    def test_invalid_routes(self):
        for options in ({'anchor': 'unknown'}, {'anchor': None}, {'anchors': []},
                        {'anchors': 'top-left'}, {'anchors': ['center'] * 17},
                        {'anchors': ['top-left', (2, 0)]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                png_zoom_gif.zoom_frames(self.png(), **options)

    def test_arrow_aliases_and_presentation_selectors(self):
        png = self.png()
        for arrow, name in png_zoom_gif.ARROW_ANCHORS.items():
            expected = png_zoom_gif.zoom_frames(png, steps=2, anchor=name)
            for suffix in ('', '\ufe0e', '\ufe0f'):
                with self.subTest(arrow=arrow, suffix=suffix):
                    actual = png_zoom_gif.zoom_frames(png, steps=2, anchor=arrow + suffix)
                    self.assertEqual([f.tobytes() for f in actual],
                                     [f.tobytes() for f in expected])
        with self.assertRaises(ValueError):
            png_zoom_gif.zoom_frames(png, anchor='↙️oops')

    def test_arrow_cli_sequence_and_single_focus(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'input.png'
            source.write_bytes(self.png())
            for i, args in enumerate((['--focus', '↗️'],
                                      ['--sequence', '↙️', '↘', 'top-left', '↗︎'])):
                target = Path(directory) / f'output{i}.gif'
                result = subprocess.run([sys.executable, str(Path(png_zoom_gif.__file__)),
                                         str(source), str(target), '--steps', '2', *args],
                                        capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                with Image.open(target) as gif:
                    self.assertGreater(gif.n_frames, 1)

    def test_invalid_options_and_input(self):
        for options in ({'zoom': float('nan')}, {'steps': 0}, {'anchor': (0, 2)},
                        {'duration_ms': 1}, {'hold_ms': -10}, {'loop': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                png_zoom_gif.to_gif(self.png(), **options)
        with self.assertRaises(ValueError):
            png_zoom_gif.to_gif(b'not a PNG')

    def test_identical_frames_validate_merged_duration(self):
        image = Image.new('RGB', (2, 2), 'red')
        buf = io.BytesIO()
        image.save(buf, format='PNG')
        with self.assertRaisesRegex(ValueError, 'merged identical frame duration'):
            png_zoom_gif.to_gif(buf.getvalue(), steps=2,
                                duration_ms=400000, hold_ms=0)
        gif = Image.open(io.BytesIO(png_zoom_gif.to_gif(
            buf.getvalue(), steps=2, duration_ms=131070, hold_ms=0)))
        self.assertEqual(gif.n_frames, 1)
        self.assertEqual(gif.info['duration'], 655350)
