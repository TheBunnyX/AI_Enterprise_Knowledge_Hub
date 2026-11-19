"""Add "sunken vowel" and "stacked mark" glyphs to the bundled Sarabun fonts.

ReportLab does not run OpenType shaping (no GSUB/GPOS), so two things go wrong that a browser gets right:

  1. อุ / อู under ญ ฎ ฏ ฐ are drawn at their default height and collide with the long tails of those letters (สระจม).
     Fix: lowered copies of both vowels at U+F718 / U+F719.
  2. A tone mark or thanthakhat over an upper vowel (นี้ ที่ ผิ่ง ศักดิ์ น้ำ) is drawn at its normal height, i.e. on top of the
     vowel, so the two glyphs merge into a blob. A shaping engine lifts the mark; here the font carries raised copies of the five
     marks at U+F70A..U+F70E (the Thai private-use codes Windows/Tahoma use for "higher tone mark").

hub/thai_pdf.py substitutes the private-use codes and patches the PDF's ToUnicode map so copied or extracted text still yields the
ordinary characters. The original glyphs and code points are untouched, so the fonts remain a superset. Idempotent.

Run once after replacing the fonts:   uv run --with fonttools python scripts/patch_thai_fonts.py
"""
from pathlib import Path
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

FONTS = Path(__file__).resolve().parent.parent / 'apps/api/hub/fonts'
LOWER = {0x0E38: 0xF718, 0x0E39: 0xF719}  # อุ, อู -> lowered
TAILS = (0x0E0D, 0x0E0E, 0x0E0F, 0x0E10)  # ญ ฎ ฏ ฐ
RAISED = {0x0E48: 0xF70A, 0x0E49: 0xF70B, 0x0E4A: 0xF70C, 0x0E4B: 0xF70D, 0x0E4C: 0xF70E}  # ่ ้ ๊ ๋ ์ -> raised
UPPER = (0x0E31, 0x0E34, 0x0E35, 0x0E36, 0x0E37, 0x0E4D, 0x0E33)  # what the mark must clear: ั ิ ี ึ ื ํ and the ring of ำ (็ is not stacked under a tone mark)
GAP = 30  # units of clear air between the vowel's top and the raised mark


def add_copy(font, source, pua, dy, suffix):
    """A copy of glyph `source` moved by dy units, named <source>.<suffix> and reachable at code point `pua`."""
    cmap, glyf, hmtx, order = font.getBestCmap(), font['glyf'], font['hmtx'], font.getGlyphOrder()
    name = cmap[source] + '.' + suffix
    pen = TTGlyphPen(None)
    glyf[cmap[source]].draw(TransformPen(pen, (1, 0, 0, 1, 0, dy)), glyf)
    glyf.glyphs[name] = pen.glyph()
    order.append(name)
    hmtx.metrics[name] = (hmtx[cmap[source]][0], hmtx[cmap[source]][1])
    for table in font['cmap'].tables:
        if table.isUnicode():table.cmap[pua] = name
    font.setGlyphOrder(order)
    return name


for path in sorted(FONTS.glob('Sarabun-*.ttf')):
    font = TTFont(path)
    cmap, glyf = font.getBestCmap(), font['glyf']
    added = []
    for src, pua in LOWER.items():
        if pua in cmap:continue
        deepest = min(glyf[cmap[c]].yMin for c in TAILS)  # bottom of the longest tail
        drop = int(glyf[cmap[src]].yMax - (deepest - 40))  # top of the vowel ends 40 units below the longest tail
        added.append(add_copy(font, src, pua, -drop, 'low'))
    cmap = font.getBestCmap()
    clear = max(glyf[cmap[c]].yMax for c in UPPER)  # the highest thing a tone mark can sit on
    for src, pua in RAISED.items():
        if pua in cmap:continue
        lift = int(clear + GAP - glyf[cmap[src]].yMin)
        added.append(add_copy(font, src, pua, lift, 'up'))
    if not added:
        print(path.name, 'already patched');continue
    order = font.getGlyphOrder()
    font['maxp'].numGlyphs = len(order)
    if 'post' in font and getattr(font['post'], 'formatType', 0) == 2.0:
        font['post'].extraNames = [n for n in font['post'].extraNames] + [n for n in added if n not in font['post'].extraNames]
    font.save(path)
    print(path.name, 'patched:', ', '.join(added))
