"""Chunking: pieces follow the document's own structure and never exceed the size the embedding model can read."""
import re
from hub import retrieval

SENTENCE = 'พนักงานต้องยื่นคำขอผ่านระบบล่วงหน้าและได้รับอนุมัติจากหัวหน้างานก่อนวันลาทุกครั้ง '
COMBINING = re.compile('[ัิ-ฺ็-๎]')  # Thai vowels and tone marks that attach to the previous consonant


def paragraphs(count, sentences=5):
    return [f'ย่อหน้าที่ {i} ' + SENTENCE * sentences for i in range(count)]


def squash(text): return re.sub(r'\s+', '', text)


def test_chunks_end_at_paragraph_boundaries():
    parts = paragraphs(8)  # ~430 characters each, so two fit in a chunk and a fixed 900-character window would cut mid-sentence
    chunks = retrieval.split('\n\n'.join(parts))
    assert len(chunks) > 1
    whole = {squash(p) for p in parts}
    for chunk in chunks:
        assert all(squash(piece) in whole for piece in chunk.split('\n\n')), chunk[-80:]


def test_no_text_is_lost():
    parts = paragraphs(8)
    joined = ''.join(squash(c) for c in retrieval.split('\n\n'.join(parts)))
    assert all(squash(p) in joined for p in parts)


def test_a_heading_stays_with_the_text_it_introduces():
    sections = [f'## หัวข้อที่ {i}\n\n' + '\n\n'.join(paragraphs(2, 4)) for i in range(5)]
    chunks = retrieval.split('# เอกสาร\n\n' + '\n\n'.join(sections))
    for chunk in chunks:
        assert not re.search(r'## หัวข้อที่ \d+\s*$', chunk), 'a chunk ends with a heading whose text went to the next chunk'


def test_chunks_respect_the_character_limit():
    for text in ('\n\n'.join(paragraphs(10)), SENTENCE.replace(' ', '') * 60, 'word ' * 800):
        assert all(len(c) <= 900 for c in retrieval.split(text))


def test_chunks_respect_the_token_budget_of_short_context_models(monkeypatch):
    monkeypatch.setenv('EMBEDDING_MAX_TOKENS', '400')
    weight = lambda c: 2.2 if '฀' <= c <= '๿' else 1.5 if ord(c) > 0x2e80 else 0.4
    chunks = retrieval.split('\n\n'.join(paragraphs(6)))
    assert len(chunks) > 3 and all(sum(map(weight, c)) <= 400 for c in chunks)


def test_unbroken_thai_text_is_never_cut_in_front_of_a_vowel_or_tone_mark():
    chunks = retrieval.split(SENTENCE.replace(' ', '') * 60)  # no spaces or line breaks to split on
    assert len(chunks) > 1 and not any(COMBINING.match(c) for c in chunks)


def test_short_and_empty_text():
    assert retrieval.split('สั้น ๆ') == ['สั้น ๆ']
    assert retrieval.split('   \n\n  ') == []
