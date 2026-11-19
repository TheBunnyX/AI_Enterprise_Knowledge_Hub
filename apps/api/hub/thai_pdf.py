"""Thai text for ReportLab PDFs: sunken vowels (สระจม) under ญ ฎ ฏ ฐ, and tone marks stacked over upper vowels.

ReportLab does not shape text, so two things would be drawn on top of each other:
  - อุ / อู after ญ ฎ ฏ ฐ land on the tails of those letters;
  - a tone mark or thanthakhat over an upper vowel or ำ (นี้ ที่ ศักดิ์ น้ำ) is drawn at its normal height, inside the vowel.
The bundled Sarabun fonts carry lowered vowels and raised marks (scripts/patch_thai_fonts.py); shape() swaps them in. The PDF's
ToUnicode map is patched so copying or extracting text still yields the ordinary characters, which keeps generated PDFs
searchable and indexable.
"""
import re
from pathlib import Path
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.pdfbase.ttfonts import TTFont

FONT_DIR = Path(__file__).parent / 'fonts'
_LOW = {'ุ': '', 'ู': ''}
_UP = {'\u0e48': '\uf70a', '\u0e49': '\uf70b', '\u0e4a': '\uf70c', '\u0e4b': '\uf70d', '\u0e4c': '\uf70e'}  # ่ ้ ๊ ๋ ์ -> the same marks, raised to clear what is under them
_BACK = {ord(v): ord(k) for k, v in {**_LOW, **_UP}.items()}
_SINK = re.compile('([ญฎฏฐ])([ุู])')
_STACKED = re.compile('(?<=[ัิีึืํ])([่้๊๋์])')  # a mark right after an upper vowel or nikhahit
_BEFORE_AM = re.compile('([่้๊๋])(?=ำ)')           # น้ำ: the mark sits over the nikhahit that ำ carries

def sink(text):
    """ญุ ญู ฎุ ฎู ฏุ ฏู ฐุ ฐู -> the same letters with the lowered vowel glyph."""
    return _SINK.sub(lambda m: m.group(1) + _LOW[m.group(2)], text)

def raise_marks(text):
    """Tone marks / thanthakhat over an upper vowel (or over the ring of ำ) -> the raised glyph. Marks on a bare consonant stay."""
    text = _STACKED.sub(lambda m: _UP[m.group(1)], text)
    return _BEFORE_AM.sub(lambda m: _UP[m.group(1)], text)

def shape(text):
    """Everything the PDF writer needs in place of a shaping engine."""
    return sink(raise_marks(text))

_original = ttfonts.makeToUnicodeCMap
def _to_unicode(fontname, subset):
    return _original(fontname, [_BACK.get(v, v) for v in subset])
ttfonts.makeToUnicodeCMap = _to_unicode

def register_fonts():
    for name, file in (('Sarabun', 'Sarabun-Regular.ttf'), ('Sarabun-Bold', 'Sarabun-Bold.ttf')):
        if name not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / file)))
