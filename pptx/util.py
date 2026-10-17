"""EMU length values compatible with the subset of python-pptx tests still call."""
EMU_PER_INCH = 914400
EMU_PER_PT = 12700


class Emu(int):
    @property
    def pt(self):
        return self / EMU_PER_PT

    @property
    def inches(self):
        return self / EMU_PER_INCH

    @property
    def emu(self):
        return int(self)


def Inches(value):
    return Emu(int(round(float(value) * EMU_PER_INCH)))


def Pt(value):
    return Emu(int(round(float(value) * EMU_PER_PT)))


def EmuLength(value):
    return Emu(int(value))
