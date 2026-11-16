from PIL import Image
from hub import ocr, retrieval


def test_recognize_joins_ppocr_lines(monkeypatch):
    monkeypatch.setattr(ocr, 'lines', lambda image: [('a', 1.0, (0, 0, 1, 1)), ('b', 1.0, (0, 5, 1, 6))])
    assert ocr.recognize(Image.new('RGB', (10, 10))) == 'a\nb'


def test_lexical_tokens_ignore_thai_tone_marks():
    assert retrieval.lexical_tokens('ฝ่าย ที่โทร') == retrieval.lexical_tokens('ฝาย ทีโทร')
