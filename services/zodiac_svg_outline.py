"""Turn zodiac text in a generated SVG into deterministic vector outlines.

All PNG charts use these outlines. The bundled STIX-derived font is licensed under
SIL OFL (assets/fonts/OFL.txt), and fonttools is a runtime dependency.
"""

from functools import lru_cache
from pathlib import Path
import re

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont


_FONT_PATH = Path(__file__).resolve().parents[1] / "assets/fonts/astro-symbols.ttf"
_ZODIAC_TEXT = re.compile(r'<text\b([^>]*)>([♈♉♊♋♌♍♎♏♐♑♒♓])</text>')


@lru_cache(maxsize=1)
def _outlines():
    font = TTFont(_FONT_PATH)
    try:
        glyphs = font.getGlyphSet()
        cmap = font.getBestCmap()
        units_per_em = font["head"].unitsPerEm
        result = {}
        for sign in "♈♉♊♋♌♍♎♏♐♑♒♓":
            glyph = glyphs[cmap[ord(sign)]]
            path = SVGPathPen(glyphs)
            bounds = BoundsPen(glyphs)
            glyph.draw(path)
            glyph.draw(bounds)
            left, bottom, right, top = bounds.bounds
            result[sign] = (path.getCommands(), (left + right) / 2, (bottom + top) / 2)
        return units_per_em, result
    finally:
        font.close()


def outline_zodiac_text(svg: str) -> str:
    """Replace only standalone zodiac characters; preserve other SVG text."""
    units_per_em, outlines = _outlines()

    def replace(match):
        attrs, sign = match.groups()

        def value(name):
            found = re.search(rf'\b{re.escape(name)}="([^"]+)"', attrs)
            if found is None:
                raise ValueError(f"zodiac SVG text missing {name}")
            return found.group(1)

        x, y = float(value("x")), float(value("y"))
        size, color = float(value("font-size")), value("fill")
        path, center_x, center_y = outlines[sign]
        scale = size / units_per_em
        return (f'<path class="zodiac-outline" d="{path}" fill="{color}" '
                f'transform="translate({x:g},{y:g}) scale({scale:g},{-scale:g}) '
                f'translate({-center_x:g},{-center_y:g})"/>')

    return _ZODIAC_TEXT.sub(replace, svg)
