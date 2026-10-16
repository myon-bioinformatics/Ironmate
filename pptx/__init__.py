"""Compatibility package so existing tests can keep ``from pptx import Presentation``.

This is not python-pptx. New packages are PptxGenJS shells with Ironmate's
canonical slide XML. Loaded packages are edited from that model, or left
byte-for-byte when nothing on the slide changed.
"""
from pptx.presentation import Presentation

__all__ = ['Presentation']
