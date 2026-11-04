import io
import unittest

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

    def test_invalid_options_and_input(self):
        for options in ({'zoom': float('nan')}, {'steps': 0}, {'anchor': (0, 2)},
                        {'duration_ms': 1}, {'hold_ms': -10}, {'loop': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                png_zoom_gif.to_gif(self.png(), **options)
        with self.assertRaises(ValueError):
            png_zoom_gif.to_gif(b'not a PNG')
