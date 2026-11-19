"""Tone marks over upper vowels (นี้ ที่ น้ำ ศักดิ์) in generated PDFs: raised so they no longer sit inside the vowel."""
import io, os, re
import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader
from hub import generated, thai_pdf

PUA = re.compile('[-]')


@pytest.mark.parametrize('word, expected', [
    ('นี้', 'นี'), ('ที่', 'ที'), ('ซึ่ง', 'ซึง'), ('เมื่อ', 'เมือ'), ('ผิ้ง', 'ผิง'),
    ('น้ำ', 'นำ'), ('ค่ำ', 'คำ'),                      # the mark sits over the nikhahit that ำ carries
    ('ศักดิ์', 'ศักดิ'), ('กะรัต์', 'กะรัต์'),                 # thanthakhat over an upper vowel is raised; over a consonant it stays
    ('ๆ ซั่ว', 'ๆ ซัว'),
])
def test_marks_over_an_upper_vowel_or_am_are_raised(word, expected):
    assert thai_pdf.raise_marks(word) == expected


@pytest.mark.parametrize('word', ['ต้อง', 'ก่อน', 'ไม้', 'ปู่', 'ผู้', 'ใช้', 'เก่า', 'ได้', 'น่า', 'เด็กๆ', 'English: so-so'])
def test_marks_on_a_bare_consonant_or_under_a_lower_vowel_are_left_alone(word):
    assert thai_pdf.raise_marks(word) == word


def test_shape_does_both_fixes_and_does_not_confuse_them():
    assert thai_pdf.shape('ญุ ผู้ นี้') == 'ญ ผู้ นี'


def test_generated_pdf_text_is_still_the_ordinary_text():
    text = 'เอกสารฉบับนี้ ที่ปรึกษา น้ำดื่ม ศักดิ์สิทธิ์ ซึ่ง เมื่อ ผู้ปั้น'
    pdf = generated.build_pdf({'title': 'ทดสอบ', 'sections': [{'heading': 'ที่นี่', 'paragraphs': [text]}]})
    extracted = ''.join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().split())
    assert not PUA.search(extracted), 'private-use codes leaked into the text layer'
    for word in ('นี้', 'ที่ปรึกษา', 'น้ำดื่ม', 'ศักดิ์สิทธิ์', 'ซึ่ง', 'เมื่อ'):
        assert word in extracted


def ink_runs(pdf_bytes, label=''):
    """Vertical runs of ink in the first line of a one-word PDF, top to bottom (a blob of touching glyphs is one run)."""
    page = pdfium.PdfDocument(pdf_bytes)[0]
    img = page.render(scale=8).to_pil().convert('L')
    w, h = img.size
    box = img.crop((0, int(h * .02), w, int(h * .15)))
    px = box.load()
    rows = [any(px[x, y] < 140 for x in range(box.width)) for y in range(box.height)]
    runs, start = [], None
    for y, on in enumerate(rows + [False]):
        if on and start is None: start = y
        if not on and start is not None: runs.append((start, y)); start = None
    runs = [r for r in runs if r[0] - runs[0][0] < 330]  # the title only, not the paragraph under it
    if os.getenv('THAI_MARKS_OUT'): img.crop((int(w * .08), int(h * .02), int(w * .3), int(h * .13))).save(os.getenv('THAI_MARKS_OUT') + '-' + label + '.png')  # for a human to look at
    return runs


def one_word_pdf(word):
    return generated.build_pdf({'title': word, 'sections': [{'heading': '', 'paragraphs': ['x']}]})


def test_the_tone_mark_is_drawn_clear_of_the_vowel_not_merged_with_it(monkeypatch):
    fixed = ink_runs(one_word_pdf('นี้'), 'fixed')
    assert len(fixed) == 3, fixed  # consonant | vowel | tone mark, with air between them
    monkeypatch.setattr(thai_pdf, 'shape', thai_pdf.sink)  # what it looked like before: marks at their normal height
    assert len(ink_runs(one_word_pdf('นี้'), 'before')) == 2  # the vowel and the mark merged into one blob
