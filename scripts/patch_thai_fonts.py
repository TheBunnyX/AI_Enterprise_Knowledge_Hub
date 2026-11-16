"""Add "sunken vowel" glyphs (สระจม) to the bundled Sarabun fonts.

ReportLab does not run OpenType shaping, so อุ / อู under ญ ฎ ฏ ฐ are drawn at their default height and collide with the
long tails of those letters. This script adds lowered copies of both vowels at U+F718 / U+F719 (the Thai private-use
codes used by Windows/Tahoma for the same purpose); hub/thai_pdf.py substitutes them after those four consonants.
The original glyphs and code points are untouched, so the fonts remain a superset.

Run once after replacing the fonts:   uv run --with fonttools python scripts/patch_thai_fonts.py
"""
from pathlib import Path
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

FONTS = Path(__file__).resolve().parent.parent / 'apps/api/hub/fonts'
LOWER = {0x0E38: 0xF718, 0x0E39: 0xF719}  # อุ, อู -> lowered
TAILS = (0x0E0D, 0x0E0E, 0x0E0F, 0x0E10)  # ญ ฎ ฏ ฐ

for path in sorted(FONTS.glob('Sarabun-*.ttf')):
    font = TTFont(path)
    cmap, glyf, hmtx, order = font.getBestCmap(), font['glyf'], font['hmtx'], font.getGlyphOrder()
    if all(pua in cmap for pua in LOWER.values()):
        print(path.name, 'already patched');continue
    deepest = min(glyf[cmap[c]].yMin for c in TAILS)  # bottom of the longest tail
    for src, pua in LOWER.items():
        name = cmap[src] + '.low'
        g = glyf[cmap[src]]
        drop = int(g.yMax - (deepest - 40))  # top of the vowel ends 40 units below the longest tail
        pen = TTGlyphPen(None)
        g.draw(TransformPen(pen, (1, 0, 0, 1, 0, -drop)), glyf)
        new = pen.glyph()
        glyf.glyphs[name] = new
        order.append(name)
        hmtx.metrics[name] = (hmtx[cmap[src]][0], hmtx[cmap[src]][1])
        for table in font['cmap'].tables:
            if table.isUnicode():table.cmap[pua] = name
    font.setGlyphOrder(order)
    font['maxp'].numGlyphs = len(order)
    if 'post' in font and getattr(font['post'], 'formatType', 0) == 2.0:
        font['post'].extraNames = [n for n in font['post'].extraNames] + [n for n in order[-2:] if n not in font['post'].extraNames]
    font.save(path)
    print(path.name, 'patched; vowels lowered by', drop, 'units')
