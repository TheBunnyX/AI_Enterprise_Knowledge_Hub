"""Thai line breaking in generated PDFs: between dictionary words, never inside one."""
import sys
import pytest
from hub import generated

TEXT = 'พร้อมใบรับรองแพทย์ระบุกำหนดคลอด และส่วนที่เหลือเป็นไปตามสิทธิจากกองทุนประกันสังคม ลาแต่งงาน 5 วันทำงาน ใช้ภายใน 60 วันจากวันจดทะเบียนสมรส'
TEN = lambda t: len(t) * 10  # ten units a character


def breaks(lines):
    """Character offsets in the joined text where a line ends."""
    out, n = set(), 0
    for l in lines[:-1]:
        n += len(l); out.add(n)
    return out


def word_edges(text):
    edges, n = set(), 0
    for u in generated._units(text):
        n += len(u.rstrip()); edges.add(n)
    return edges


@pytest.mark.parametrize('width', [140, 180, 240, 320])  # the longest word here, ใบรับรองแพทย์, is 13 characters: 130 units
def test_lines_end_only_between_words(width):
    lines = generated.wrap_lines(TEXT, width, TEN)
    assert len(lines) > 1 and all(len(l) * 10 <= width for l in lines)
    joined = ''.join(lines)
    assert joined.replace(' ', '') == TEXT.replace(' ', '')  # nothing lost, only spaces at the breaks
    compact = TEXT.replace(' ', '')
    edges, n = set(), 0
    for u in generated._units(TEXT):  # a compound wider than the line may be cut between its own short words
        for sub in (generated._split_long(u) if TEN(u) > width else [u]):
            n += len(sub.replace(' ', '')); edges.add(n)
    cuts, n = set(), 0
    for l in lines[:-1]:
        n += len(l.replace(' ', '')); cuts.add(n)
    assert cuts <= edges, f'a line ended inside a word at width {width}: {sorted(cuts - edges)}'


def test_the_words_that_used_to_be_cut_stay_whole():
    for width in range(140, 320, 10):
        lines = generated.wrap_lines(TEXT, width, TEN)
        for a, b in zip(lines, lines[1:]):
            assert not (a.endswith('รับรอ') and b.startswith('งแพทย์'))
            assert not (a.endswith('ทะเบียนสม') and b.startswith('รส'))
            assert b[0] not in 'ะาำิีึืุู็่้๊๋์ๆ', (a, b)


def test_numbers_and_latin_words_are_not_split_and_trail_with_their_space():
    lines = generated.wrap_lines('ลาไม่เกิน 30 วันทำงาน ผ่านระบบ HR Portal ภายใน 2 วัน', 120, TEN)
    flat = ' '.join(lines)
    for token in ('30', 'HR', 'Portal', '2'):
        assert any(token in l.split() or l.startswith(token) or l.endswith(token) or f' {token} ' in l for l in lines), (token, lines)
    assert not any(l != l.rstrip() for l in lines)  # no trailing spaces
    assert flat.replace(' ', '') == 'ลาไม่เกิน30วันทำงานผ่านระบบHRPortalภายใน2วัน'


@pytest.mark.parametrize('width', [30, 50, 60, 90])
def test_when_a_word_cannot_fit_the_cut_still_avoids_marks_and_leading_vowels(width):
    lines = generated.wrap_lines(TEXT, width, TEN)
    assert all(len(l) * 10 <= width or len(l) == 1 for l in lines) and ''.join(lines).replace(' ', '') == TEXT.replace(' ', '')
    assert all(l[0] not in 'ะาำิีึืุู็่้๊๋์ๆ' for l in lines[1:]), lines
    assert all(l[-1] not in 'เแโใไ' for l in lines), lines


def test_a_word_wider_than_the_line_is_still_cut_so_nothing_overflows():
    lines = generated.wrap_lines('https://example.com/' + 'a' * 60, 100, TEN)
    assert all(len(l) * 10 <= 100 for l in lines) and ''.join(lines) == 'https://example.com/' + 'a' * 60


def test_without_the_dictionary_it_falls_back_to_cutting_before_consonants(monkeypatch):
    monkeypatch.setitem(sys.modules, 'pythainlp.tokenize', None)  # makes the import fail
    lines = generated.wrap_lines(TEXT, 90, TEN)
    assert len(lines) > 1 and all(len(l) * 10 <= 90 for l in lines)
    assert all(l[0] not in 'ะาำิีึืุู็่้๊๋์ๆ' for l in lines)  # at least never before a vowel or tone mark


def test_pdf_text_is_unchanged_by_the_new_breaking():
    import io
    from pypdf import PdfReader
    pdf = generated.build_pdf({'title': 'ทดสอบ', 'sections': [{'heading': 'ที่นี่', 'paragraphs': [TEXT * 2]}]})
    text = ''.join(PdfReader(io.BytesIO(pdf)).pages[0].extract_text().split())
    assert TEXT.replace(' ', '') in text.replace(' ', '')
