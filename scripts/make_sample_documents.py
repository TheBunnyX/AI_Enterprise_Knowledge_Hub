"""Build the starter PDF documents (with embedded images) shipped in apps/api/hub/sample_docs.

Needs Google Chrome (headless) for Thai text shaping. Run: python scripts/make_sample_documents.py
"""
import subprocess, sys, tempfile
from pathlib import Path

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
OUT = Path(__file__).resolve().parent.parent / 'apps' / 'api' / 'hub' / 'sample_docs'
FONT = "'Leelawadee UI','Tahoma',sans-serif"

def svg_page(w, h, body):
    return f'<html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff;font-family:{FONT}}}</style></head><body><svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">{body}</svg></body></html>'

def box(x, y, w, h, fill, text, color='#fff', size=22, stroke='none'):
    lines = text.split('\n')
    t = ''.join(f'<text x="{x+w/2}" y="{y+h/2+(i-(len(lines)-1)/2)*size*1.25+size*0.35}" text-anchor="middle" font-size="{size}" fill="{color}" font-weight="600">{l}</text>' for i, l in enumerate(lines))
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"/>{t}'

def arrow(x1, y1, x2, y2):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#475569" stroke-width="3" marker-end="url(#a)"/>'

DEFS = '<defs><marker id="a" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#475569"/></marker></defs>'

def figure_hybrid():
    days = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์']
    mode = [0, 1, 0, 1, 0]
    b = ['<rect width="900" height="330" fill="#f8fafc"/>', '<text x="450" y="40" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">ตารางการทำงานต่อสัปดาห์</text>']
    for i, (d, m) in enumerate(zip(days, mode)):
        x = 30 + i * 170
        b.append(box(x, 70, 150, 60, '#1e3a8a', d, size=22))
        b.append(box(x, 140, 150, 110, '#2563eb' if not m else '#0d9488', 'ทำงานที่\nสำนักงาน' if not m else 'ทำงานจาก\nที่บ้าน', size=21))
    b.append('<rect x="30" y="278" width="22" height="22" rx="4" fill="#2563eb"/><text x="62" y="296" font-size="20" fill="#334155">สำนักงาน (3 วัน)</text><rect x="260" y="278" width="22" height="22" rx="4" fill="#0d9488"/><text x="292" y="296" font-size="20" fill="#334155">ที่บ้าน (2 วัน)</text>')
    return svg_page(900, 330, ''.join(b)), (900, 330)

def figure_strategy():
    years = [('2025', 100), ('2026', 118), ('2027', 140), ('2028', 168)]
    b = ['<rect width="900" height="420" fill="#fff"/>', '<text x="450" y="38" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">เป้าหมายรายได้ (ดัชนี ปี 2025 = 100)</text>']
    for y in (0, 50, 100, 150):
        py = 360 - y * 1.7
        b.append(f'<line x1="90" y1="{py}" x2="860" y2="{py}" stroke="#e2e8f0"/><text x="78" y="{py+6}" text-anchor="end" font-size="18" fill="#64748b">{y}</text>')
    for i, (yr, v) in enumerate(years):
        x = 140 + i * 180; h = v * 1.7
        b.append(f'<rect x="{x}" y="{360-h}" width="110" height="{h}" rx="8" fill="{"#94a3b8" if i == 0 else "#2563eb"}"/><text x="{x+55}" y="{350-h}" text-anchor="middle" font-size="22" font-weight="700" fill="#0f172a">{v}</text><text x="{x+55}" y="392" text-anchor="middle" font-size="20" fill="#334155">{yr}</text>')
    return svg_page(900, 420, ''.join(b)), (900, 420)

def figure_security():
    b = [DEFS, '<rect width="900" height="300" fill="#f8fafc"/>', '<text x="450" y="38" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">ขั้นตอนการแจ้งเหตุข้อมูลรั่วไหล</text>']
    steps = [('พบเหตุ\nผิดปกติ', '#dc2626'), ('แจ้งทีม\nIT Security', '#ea580c'), ('ประเมิน\nและกักกัน', '#ca8a04'), ('แก้ไข\nและกู้คืน', '#0d9488'), ('สรุปบทเรียน\nและรายงาน', '#2563eb')]
    for i, (t, c) in enumerate(steps):
        x = 25 + i * 175
        b.append(box(x, 100, 140, 120, c, t, size=21))
        if i < len(steps) - 1: b.append(arrow(x + 142, 160, x + 172, 160))
    b.append('<text x="450" y="268" text-anchor="middle" font-size="19" fill="#475569">แจ้งภายใน 24 ชั่วโมงหลังพบเหตุ</text>')
    return svg_page(900, 300, ''.join(b)), (900, 300)

def figure_ai():
    b = ['<rect width="900" height="330" fill="#f8fafc"/>', '<text x="450" y="38" text-anchor="middle" font-size="26" font-weight="700" fill="#0f172a">ระดับความอ่อนไหวของข้อมูลกับการใช้ AI</text>']
    rows = [('#16a34a', 'ข้อมูลสาธารณะ', 'ใช้กับ AI ที่องค์กรอนุมัติได้'), ('#ca8a04', 'ข้อมูลภายใน', 'ใช้ได้เฉพาะระบบ AI ขององค์กร'), ('#dc2626', 'ข้อมูลลับ / ข้อมูลส่วนบุคคล', 'ห้ามส่งไปยังบริการภายนอก')]
    for i, (c, t, d) in enumerate(rows):
        y = 70 + i * 82
        b.append(f'<circle cx="70" cy="{y+30}" r="26" fill="{c}"/><text x="125" y="{y+26}" font-size="24" font-weight="700" fill="#0f172a">{t}</text><text x="125" y="{y+56}" font-size="20" fill="#475569">{d}</text>')
    return svg_page(900, 330, ''.join(b)), (900, 330)

def page(title, subtitle, fig, intro, sections, rows=None, note=''):
    secs = ''.join(f'<h2>{h}</h2>' + ''.join(f'<p>{p}</p>' for p in ps) for h, ps in sections)
    table = ''
    if rows:
        table = '<table>' + ''.join(('<tr>' + ''.join(f'<{"th" if i == 0 else "td"}>{c}</{"th" if i == 0 else "td"}>' for c in r) + '</tr>') for i, r in enumerate(rows)) + '</table>'
    return f'''<!doctype html><html lang="th"><head><meta charset="utf-8"><title>{title}</title><style>
@page{{size:A4;margin:18mm 16mm}}
body{{font-family:{FONT};color:#0f172a;font-size:12.5pt;line-height:1.65;font-feature-settings:"ccmp" 0,"locl" 0;font-variant-ligatures:none}}
.top{{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid #2563eb;padding-bottom:8px;margin-bottom:14px}}
.brand{{font-weight:700;color:#1e3a8a;font-size:11pt}} .meta{{color:#64748b;font-size:10pt}}
h1{{font-size:24pt;margin:6px 0 2px;color:#0f172a}} .sub{{color:#475569;margin:0 0 12px}}
h2{{font-size:15pt;color:#1e3a8a;margin:18px 0 4px}} p{{margin:4px 0 8px}}
img{{width:100%;border:1px solid #e2e8f0;border-radius:10px;margin:10px 0 4px}}
.cap{{color:#64748b;font-size:10pt;text-align:center;margin-bottom:8px}}
table{{width:100%;border-collapse:collapse;margin:8px 0}} th,td{{border:1px solid #cbd5e1;padding:6px 10px;text-align:left}} th{{background:#eff6ff}}
.foot{{margin-top:22px;border-top:1px solid #e2e8f0;padding-top:8px;color:#64748b;font-size:10pt}}
</style></head><body>
<div class="top"><span class="brand">AI Knowledge Hub · เอกสารองค์กร</span><span class="meta">{note}</span></div>
<h1>{title}</h1><p class="sub">{subtitle}</p><p>{intro}</p>
<img src="{fig}"><div class="cap">ภาพที่ 1 · {subtitle}</div>
{secs}{table}
<div class="foot">เอกสารฉบับนี้เป็นเอกสารภายในขององค์กร ใช้งานภายในหน่วยงานที่ได้รับอนุญาตเท่านั้น</div>
</body></html>'''

DOCS = [
    ('hybrid-working', 'นโยบายการทำงานแบบยืดหยุ่น (Hybrid Working).pdf', figure_hybrid,
     page('นโยบายการทำงานแบบยืดหยุ่น', 'ตารางการทำงานต่อสัปดาห์แบบ Hybrid', 'FIG',
          'นโยบายนี้กำหนดหลักเกณฑ์การทำงานแบบยืดหยุ่นของพนักงานประจำ เพื่อสร้างสมดุลระหว่างการทำงานและชีวิตส่วนตัว โดยยังคงประสิทธิภาพของทีม',
          [('1. การทำงานจากที่บ้าน', ['พนักงานสามารถทำงานจากที่บ้านได้ 2 วันต่อสัปดาห์ โดยต้องขออนุมัติจากหัวหน้างานล่วงหน้าอย่างน้อย 1 วัน และต้องเข้าร่วมประชุมทีมตามกำหนดเสมอ']),
           ('2. เวลาทำงาน', ['เวลาเข้างานยืดหยุ่นระหว่าง 08:00–10:00 น. และต้องทำงานให้ครบ 8 ชั่วโมงต่อวัน']),
           ('3. การลาพักร้อน', ['พนักงานประจำมีสิทธิลาพักร้อน 10 วันต่อปีหลังผ่านทดลองงาน ต้องยื่นคำขอล่วงหน้าอย่างน้อย 3 วันทำการ ผ่านระบบ HR'])],
          [['หัวข้อ', 'เงื่อนไข'], ['ทำงานจากที่บ้าน', '2 วันต่อสัปดาห์'], ['เวลาเข้างาน', '08:00–10:00 น.'], ['ชั่วโมงทำงาน', '8 ชั่วโมงต่อวัน'], ['ลาพักร้อน', '10 วันต่อปี ยื่นล่วงหน้า 3 วันทำการ']],
          'ฝ่ายทรัพยากรบุคคล')),
    ('strategy', 'แผนกลยุทธ์องค์กร 2026–2028.pdf', figure_strategy,
     page('แผนกลยุทธ์องค์กร 2026–2028', 'เป้าหมายรายได้รายปี', 'FIG',
          'แผนกลยุทธ์ฉบับนี้กำหนดทิศทางองค์กรสามปีข้างหน้า มุ่งเติบโตอย่างยั่งยืนควบคู่กับการพัฒนาเทคโนโลยีและบุคลากร',
          [('ยุทธศาสตร์ที่ 1 · ขยายฐานลูกค้า', ['ขยายฐานลูกค้าและเพิ่มรายได้ในตลาดหลัก โดยพัฒนาคุณภาพบริการและสร้างความสัมพันธ์กับลูกค้าอย่างต่อเนื่อง']),
           ('ยุทธศาสตร์ที่ 2 · เทคโนโลยี AI', ['พัฒนาผลิตภัณฑ์และบริการด้วยเทคโนโลยี AI นำระบบอัตโนมัติมาเพิ่มประสิทธิภาพการทำงาน']),
           ('ยุทธศาสตร์ที่ 3 · บุคลากร', ['เสริมสร้างศักยภาพองค์กรและบุคลากร ด้วยการพัฒนาทักษะดิจิทัลและวัฒนธรรมการเรียนรู้'])],
          [['ปี', 'ดัชนีรายได้เป้าหมาย'], ['2025 (ฐาน)', '100'], ['2026', '118'], ['2027', '140'], ['2028', '168']],
          'ฝ่ายกลยุทธ์')),
    ('security', 'คู่มือความปลอดภัยในการทำงาน.pdf', figure_security,
     page('คู่มือความปลอดภัยในการทำงาน', 'ขั้นตอนการแจ้งเหตุข้อมูลรั่วไหล', 'FIG',
          'คู่มือนี้สรุปแนวปฏิบัติด้านความปลอดภัยของข้อมูลสำหรับพนักงานทุกคน',
          [('1. รหัสผ่านและ API key', ['ห้ามเปิดเผยรหัสผ่านและ API key ในเอกสารหรือช่องสนทนา และห้ามใช้รหัสผ่านร่วมกัน']),
           ('2. ข้อมูลลูกค้า', ['ข้อมูลลูกค้าที่เป็นความลับต้องจัดเก็บในคลังความรู้ที่จำกัดสิทธิ์เท่านั้น']),
           ('3. เมื่อเกิดเหตุ', ['หากพบเหตุการณ์ข้อมูลรั่วไหล ให้แจ้งทีม IT Security ทันที ภายใน 24 ชั่วโมงหลังพบเหตุ และไม่ลบหลักฐานที่เกี่ยวข้อง'])],
          [['เหตุการณ์', 'การปฏิบัติ'], ['รหัสผ่านรั่วไหล', 'เปลี่ยนรหัสผ่านทันทีและแจ้ง IT Security'], ['พบไฟล์ลับถูกแชร์ผิดคน', 'ยกเลิกการแชร์และแจ้งเจ้าของข้อมูล'], ['อุปกรณ์สูญหาย', 'แจ้งภายใน 24 ชั่วโมง']],
          'ความปลอดภัย')),
    ('ai-guideline', 'แนวทางการใช้ AI ภายในองค์กร.pdf', figure_ai,
     page('แนวทางการใช้ AI ภายในองค์กร', 'ระดับความอ่อนไหวของข้อมูลกับการใช้ AI', 'FIG',
          'แนวทางนี้ช่วยให้พนักงานใช้เครื่องมือ AI ได้อย่างปลอดภัยและน่าเชื่อถือ',
          [('1. ตรวจสอบก่อนนำไปใช้', ['ตรวจสอบแหล่งอ้างอิงและความถูกต้องก่อนนำคำตอบจาก AI ไปใช้ทุกครั้ง']),
           ('2. ข้อมูลส่วนบุคคล', ['ห้ามส่งข้อมูลส่วนบุคคลที่อ่อนไหวไปยังผู้ให้บริการที่ไม่ได้รับอนุมัติ']),
           ('3. ความรับผิดชอบ', ['ผู้ใช้เป็นผู้รับผิดชอบต่อเนื้อหาที่นำไปเผยแพร่ แม้สร้างด้วย AI'])],
          [['ระดับข้อมูล', 'ใช้กับ AI ได้หรือไม่'], ['สาธารณะ', 'ได้ ผ่าน AI ที่องค์กรอนุมัติ'], ['ภายใน', 'ได้ เฉพาะระบบ AI ขององค์กร'], ['ลับ / ส่วนบุคคล', 'ห้ามส่งไปบริการภายนอก']],
          'เทคโนโลยีสารสนเทศ')),
]

def chrome(*args):
    subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for slug, filename, figure, html in DOCS:
            fig_html, (w, h) = figure()
            (tmp / f'{slug}-fig.html').write_text(fig_html, encoding='utf-8')
            png = tmp / f'{slug}.png'
            chrome(f'--screenshot={png}', f'--window-size={w},{h}', '--force-device-scale-factor=2', (tmp / f'{slug}-fig.html').as_uri())
            doc = tmp / f'{slug}.html'
            doc.write_text(html.replace('src="FIG"', f'src="{png.as_uri()}"'), encoding='utf-8')
            chrome(f'--print-to-pdf={OUT / filename}', '--no-pdf-header-footer', doc.as_uri())
            print('wrote', OUT / filename)

if __name__ == '__main__':
    sys.exit(main())
