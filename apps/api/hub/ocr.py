"""Local OCR: PaddleOCR PP-OCRv5; nothing is uploaded."""
import io,os,threading
from functools import lru_cache

# Tesseract-style codes accepted by OCR_LANGUAGES, mapped to PaddleOCR languages.
# The Thai model also reads Latin text, so tha+eng uses one pass.
LANGUAGES={'tha':'th','eng':'en','chi_sim':'ch','jpn':'japan','kor':'korean'}
_lock=threading.Lock()

def language():
    codes=[c for c in os.getenv('OCR_LANGUAGES','tha+eng').split('+') if c]
    for code in codes:
        if code not in LANGUAGES:raise ValueError('OCR_LANGUAGES ไม่รองรับ: '+code)
    mapped=[LANGUAGES[c] for c in codes]
    return next((m for m in mapped if m!='en'),'en')

@lru_cache(maxsize=2)
def engine(lang):
    try:from paddleocr import PaddleOCR
    except ImportError as e:raise ValueError('ต้องติดตั้ง paddleocr และ paddlepaddle ก่อนอ่านรูปภาพหรือเอกสารสแกน') from e
    return PaddleOCR(lang=lang,use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,enable_mkldnn=False)

def lines(image):
    """Return [(text, score, box)] in reading order; box is (left, top, right, bottom)."""
    import numpy as np
    result=[]
    with _lock:
        for page in engine(language()).predict(np.asarray(image.convert('RGB'))):
            for text,score,poly in zip(page['rec_texts'],page['rec_scores'],page['rec_polys']):
                if text.strip():result.append((text.strip(),float(score),(int(poly[:,0].min()),int(poly[:,1].min()),int(poly[:,0].max()),int(poly[:,1].max()))))
    return sorted(result,key=lambda r:(r[2][1]//20,r[2][0]))

def recognize(image):
    return '\n'.join(text for text,_,_ in lines(image))

def image_text(data,suffix='.png'):
    from PIL import Image
    image=Image.open(io.BytesIO(data))
    image.load()
    return recognize(image)

def pdf_page(data,page):
    try:import pypdfium2 as pdfium
    except ImportError as e:raise ValueError('ต้องติดตั้ง pypdfium2 เพื่ออ่าน PDF แบบสแกน') from e
    pdf=pdfium.PdfDocument(data)
    try:image=pdf[page-1].render(scale=2200/max(pdf[page-1].get_size())).to_pil()
    finally:pdf.close()
    return recognize(image)
