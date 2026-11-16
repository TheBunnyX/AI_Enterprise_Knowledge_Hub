"""Thai text for ReportLab PDFs: sunken vowels (สระจม) under ญ ฎ ฏ ฐ.

ReportLab does not shape text, so อุ / อู after those four letters would be drawn on top of their tails. The bundled Sarabun
fonts carry lowered copies of both vowels (scripts/patch_thai_fonts.py); sink() swaps them in. The PDF's ToUnicode map is
patched so copying or extracting text still yields the ordinary ุ / ู, which keeps generated PDFs searchable and indexable.
"""
import re
from pathlib import Path
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).parent / 'fonts'
_LOW = {'ุ': '', 'ู': ''}
_BACK = {ord(v): ord(k) for k, v in _LOW.items()}
_SINK = re.compile('([ญฎฏฐ])([ุู])')

def sink(text):
    """ญุ ญู ฎุ ฎู ฏุ ฏู ฐุ ฐู -> the same letters with the lowered vowel glyph."""
    return _SINK.sub(lambda m: m.group(1) + _LOW[m.group(2)], text)

_original = ttfonts.makeToUnicodeCMap
def _to_unicode(fontname, subset):
    return _original(fontname, [_BACK.get(v, v) for v in subset])
ttfonts.makeToUnicodeCMap = _to_unicode

def register_fonts():
    for name, file in (('Sarabun', 'Sarabun-Regular.ttf'), ('Sarabun-Bold', 'Sarabun-Bold.ttf')):
        if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
