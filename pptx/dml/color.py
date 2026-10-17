"""RGB colors and the explicit-RGB color type used by the edit CLIs."""


class MSO_COLOR_TYPE:
    RGB = 'rgb'


class RGBColor(tuple):
    def __new__(cls, r, g, b):
        return super().__new__(cls, (int(r), int(g), int(b)))

    def __str__(self):
        return f'{self[0]:02X}{self[1]:02X}{self[2]:02X}'

    @classmethod
    def from_string(cls, value):
        if not isinstance(value, str) or len(value) != 6 or any(c not in '0123456789abcdefABCDEF' for c in value):
            raise ValueError('RGBColor.from_string() requires an RGB hex string')
        return cls(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
