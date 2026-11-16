"""Files the agent creates for a user (presentation, spreadsheet, CSV).

The model only supplies structured content; the server builds the file with python-pptx / openpyxl / csv. Files are
private to the user who asked, stored through storage.put, expire after RETENTION_DAYS and are checked on every download.
Cell text is neutralised against spreadsheet formula injection because it may originate from untrusted documents.
"""
import csv,io,re
from pathlib import Path
from datetime import datetime,timedelta,timezone
from urllib.parse import quote
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Mapped,mapped_column,Session
from .database import Base,db_session
from .models import Identity,User,Audit,now
from .auth import current_user
from . import storage

RETENTION_DAYS=7
MAX_SECTIONS=40;MAX_ITEMS=60;MAX_TABLE_ROWS=200;MAX_SLIDES=30;MAX_BULLETS=8;MAX_SHEETS=5;MAX_ROWS=2000;MAX_COLS=30;MAX_CELL=2000;MAX_TEXT=600
TYPES={'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','pdf':'application/pdf','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','csv':'text/csv; charset=utf-8'}

class GeneratedFile(Identity,Base):
    __tablename__='generated_files'
    tenant_id:Mapped[str]=mapped_column(index=True)
    user_id:Mapped[str]=mapped_column(index=True)
    conversation_id:Mapped[str]=mapped_column(default='')
    name:Mapped[str]
    kind:Mapped[str]
    size:Mapped[int]
    storage_key:Mapped[str]
    expires_at:Mapped[str]

class ToolError(Exception):pass

def safe_name(name,ext):
    base=re.sub(r'[\\/:*?"<>|\x00-\x1f]+',' ',str(name or '')).strip(' .')[:80] or 'file'
    return base if base.lower().endswith('.'+ext) else base+'.'+ext

def _text(v,limit=MAX_TEXT):return str(v if v is not None else '')[:limit]

def _cell(v,escape=True):
    """CSV: strings a spreadsheet would run as a formula get a leading apostrophe (xlsx stores them as text instead); real numbers stay numbers."""
    if isinstance(v,bool) or v is None:return '' if v is None else str(v)
    if isinstance(v,(int,float)):return v
    s=_text(v,MAX_CELL)
    if escape and s[:1] in ('=','+','-','@','\t','\r'):
        try:float(s.replace(',',''));return s
        except ValueError:return "'"+s
    return s

def build_pptx(args):
    from pptx import Presentation
    from pptx.util import Inches,Pt
    from pptx.dml.color import RGBColor
    slides=args.get('slides')
    if not isinstance(slides,list) or not slides:raise ToolError('ต้องมี slides อย่างน้อย 1 สไลด์')
    if len(slides)>MAX_SLIDES:raise ToolError(f'สไลด์ได้สูงสุด {MAX_SLIDES} แผ่น')
    prs=Presentation();prs.slide_width=Inches(13.333);prs.slide_height=Inches(7.5)
    FONT='Tahoma';DARK=RGBColor(0x1E,0x29,0x3B);ACCENT=RGBColor(0x25,0x63,0xEB)
    def style(par,size,color=DARK,bold=False):
        for r in par.runs:r.font.size=Pt(size);r.font.name=FONT;r.font.bold=bold;r.font.color.rgb=color
    title=_text(args.get('title'),120)
    if title:
        s=prs.slides.add_slide(prs.slide_layouts[6])
        box=s.shapes.add_textbox(Inches(1),Inches(2.4),Inches(11.3),Inches(1.6)).text_frame;box.word_wrap=True
        box.text=title;style(box.paragraphs[0],40,ACCENT,True)
        sub=_text(args.get('subtitle'),200)
        if sub:
            b2=s.shapes.add_textbox(Inches(1),Inches(4.1),Inches(11.3),Inches(1)).text_frame;b2.word_wrap=True;b2.text=sub;style(b2.paragraphs[0],20)
    for item in slides:
        if not isinstance(item,dict):raise ToolError('แต่ละสไลด์ต้องเป็นออบเจกต์ {title, bullets}')
        s=prs.slides.add_slide(prs.slide_layouts[6])
        tf=s.shapes.add_textbox(Inches(0.7),Inches(0.4),Inches(11.9),Inches(1.1)).text_frame;tf.word_wrap=True
        tf.text=_text(item.get('title'),120);style(tf.paragraphs[0],30,ACCENT,True)
        bullets=item.get('bullets') or []
        if not isinstance(bullets,list):bullets=[bullets]
        body=s.shapes.add_textbox(Inches(0.9),Inches(1.7),Inches(11.5),Inches(5.2)).text_frame;body.word_wrap=True
        for i,t in enumerate(bullets[:MAX_BULLETS]):
            p=body.paragraphs[0] if i==0 else body.add_paragraph()
            p.text='• '+_text(t);p.space_after=Pt(10);style(p,20)
        notes=_text(item.get('notes'),2000)
        if notes:s.notes_slide.notes_text_frame.text=notes
    out=io.BytesIO();prs.save(out);return out.getvalue()

def _sheets(args,escape=True):
    sheets=args.get('sheets')
    if not isinstance(sheets,list) or not sheets:raise ToolError('ต้องมี sheets อย่างน้อย 1 ชีต {name, columns, rows}')
    if len(sheets)>MAX_SHEETS:raise ToolError(f'ชีตได้สูงสุด {MAX_SHEETS}')
    out=[]
    for sh in sheets:
        if not isinstance(sh,dict):raise ToolError('แต่ละชีตต้องเป็นออบเจกต์')
        cols=sh.get('columns') or [];rows=sh.get('rows') or []
        if not isinstance(cols,list) or not isinstance(rows,list):raise ToolError('columns และ rows ต้องเป็นรายการ')
        if len(cols)>MAX_COLS or len(rows)>MAX_ROWS:raise ToolError(f'ใหญ่เกินไป (สูงสุด {MAX_COLS} คอลัมน์, {MAX_ROWS} แถว)')
        width=max([len(cols)]+[len(r) for r in rows if isinstance(r,list)] or [0])
        data=[[_cell(c,escape) for c in cols]]+[[_cell(c,escape) for c in (r if isinstance(r,list) else [r])] for r in rows]
        out.append((re.sub(r'[\[\]:*?/\\]','_',_text(sh.get('name') or 'Sheet',31)) or 'Sheet',data,width))
    return out

def build_xlsx(args):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb=Workbook();wb.remove(wb.active)
    for name,data,_ in _sheets(args,False):
        ws=wb.create_sheet(name)
        for r,row in enumerate(data,1):
            for c,v in enumerate(row,1):
                cell=ws.cell(row=r,column=c,value=v)
                if isinstance(v,str):cell.data_type='s'  # never a formula
                if r==1:cell.font=Font(bold=True)
        ws.freeze_panes='A2'
    out=io.BytesIO();wb.save(out);return out.getvalue()

def build_csv(args):
    sheets=_sheets(args);out=io.StringIO();w=csv.writer(out)
    for row in sheets[0][1]:w.writerow(row)
    return ('﻿'+out.getvalue()).encode('utf-8')  # BOM so Excel reads Thai correctly


def _sections(args):
    """Validated document content: title + sections [{heading, paragraphs, bullets, table:{columns, rows}}]."""
    secs=args.get('sections')
    if not isinstance(secs,list) or not secs:raise ToolError('ต้องมี sections อย่างน้อย 1 ส่วน {heading, paragraphs, bullets, table}')
    if len(secs)>MAX_SECTIONS:raise ToolError(f'ส่วนของเอกสารได้สูงสุด {MAX_SECTIONS}')
    out=[]
    for sec in secs:
        if not isinstance(sec,dict):raise ToolError('แต่ละส่วนต้องเป็นออบเจกต์')
        def items(key):
            v=sec.get(key) or []
            if not isinstance(v,list):v=[v]
            return [_text(x,4000) for x in v[:MAX_ITEMS]]
        table=sec.get('table')
        if table is not None:
            if not isinstance(table,dict) or not isinstance(table.get('columns'),list) or not isinstance(table.get('rows') or [],list):raise ToolError('table ต้องเป็น {columns, rows}')
            cols=[_text(c,200) for c in table['columns'][:12]]
            rows=[[_text(c,500) for c in (r if isinstance(r,list) else [r])][:len(cols)] for r in (table.get('rows') or [])[:MAX_TABLE_ROWS]]
            table=(cols,rows)
        out.append({'heading':_text(sec.get('heading'),200),'paragraphs':items('paragraphs'),'bullets':items('bullets'),'table':table})
    return _text(args.get('title'),200),out

def build_docx(args):
    from docx import Document
    from docx.shared import Pt
    from docx.oxml.ns import qn
    title,secs=_sections(args)
    doc=Document()
    for st in ('Normal','Title','Heading 1','List Bullet'):
        f=doc.styles[st].font;f.name='Tahoma'
        rpr=doc.styles[st].element.get_or_add_rPr();fonts=rpr.find(qn('w:rFonts'))
        if fonts is None:
            from docx.oxml import OxmlElement
            fonts=OxmlElement('w:rFonts');rpr.append(fonts)
        for a in ('w:ascii','w:hAnsi','w:cs','w:eastAsia'):fonts.set(qn(a),'Tahoma')
    doc.styles['Normal'].font.size=Pt(12)
    if title:doc.add_heading(title,0)
    for sec in secs:
        if sec['heading']:doc.add_heading(sec['heading'],1)
        for t in sec['paragraphs']:doc.add_paragraph(t)
        for t in sec['bullets']:doc.add_paragraph(t,style='List Bullet')
        if sec['table']:
            cols,rows=sec['table'];tb=doc.add_table(rows=1,cols=max(len(cols),1));tb.style='Table Grid'
            for i,c in enumerate(cols):
                tb.rows[0].cells[i].text=c
                for r in tb.rows[0].cells[i].paragraphs[0].runs:r.font.bold=True
            for row in rows:
                cells=tb.add_row().cells
                for i,c in enumerate(row[:len(cols)]):cells[i].text=c
    out=io.BytesIO();doc.save(out);return out.getvalue()

FONT_DIR=Path(__file__).parent/'fonts'
_THAI_BASE=lambda c:'\u0e01'<=c<='\u0e2e'
_LEADING=lambda c:c in '\u0e40\u0e41\u0e42\u0e43\u0e44'

def wrap_lines(text,width,measure):
    """Greedy line breaking for mixed Thai/Latin text. Thai has no spaces, so a break is allowed before a consonant or
    leading vowel (never before a vowel/tone mark, never right after a leading vowel); Latin breaks only at spaces."""
    units=[];cur=''
    for i,c in enumerate(text):
        prev=text[i-1] if i else ''
        thai_break=cur and (_THAI_BASE(c) or _LEADING(c)) and not _LEADING(prev) and ('\u0e00'<=prev<='\u0e7f')
        space_break=cur and prev==' ' and c!=' '
        latin_to_thai=cur and (_THAI_BASE(c) or _LEADING(c)) and prev not in ('',) and not ('\u0e00'<=prev<='\u0e7f') and prev!=' '
        if thai_break or space_break or latin_to_thai:units.append(cur);cur=''
        cur+=c
    if cur:units.append(cur)
    lines=[];line=''
    for u in units:
        if line and measure(line+u)>width:lines.append(line.rstrip());line=u.lstrip() if u.strip() else ''
        else:line+=u
        while measure(line)>width and len(line)>1:  # a single unit wider than the line (long URL/number)
            cut=len(line)
            while cut>1 and measure(line[:cut])>width:cut-=1
            lines.append(line[:cut]);line=line[cut:]
    if line.strip():lines.append(line.rstrip())
    return lines or ['']

def build_pdf(args):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from xml.sax.saxutils import escape
    title,secs=_sections(args)
    from .thai_pdf import register_fonts,sink
    register_fonts()
    body=ParagraphStyle('b',fontName='Sarabun',fontSize=12,leading=19,spaceAfter=6)
    h1=ParagraphStyle('h',parent=body,fontName='Sarabun-Bold',fontSize=16,leading=24,spaceBefore=10,textColor=colors.HexColor('#1d4ed8'))
    ttl=ParagraphStyle('t',parent=body,fontName='Sarabun-Bold',fontSize=24,leading=34,spaceAfter=14)
    cell=ParagraphStyle('c',parent=body,fontSize=10.5,leading=16,spaceAfter=0)
    page_w=A4[0]-4*cm
    def para(text,style,width,indent=0):
        lines=wrap_lines(text,width-indent,lambda t:pdfmetrics.stringWidth(t,style.fontName,style.fontSize))
        return Paragraph('<br/>'.join(escape(sink(l)) for l in lines),style)
    story=[]
    if title:story.append(para(title,ttl,page_w))
    for sec in secs:
        if sec['heading']:story.append(para(sec['heading'],h1,page_w))
        for t in sec['paragraphs']:story.append(para(t,body,page_w))
        for t in sec['bullets']:
            st=ParagraphStyle('l',parent=body,leftIndent=16,bulletIndent=4);p=para(t,st,page_w,16)
            p.bulletText='•';story.append(p)
        if sec['table']:
            cols,rows=sec['table'];n=max(len(cols),1);cw=page_w/n
            def c(t,bold=False):
                st=ParagraphStyle('x',parent=cell,fontName='Sarabun-Bold' if bold else 'Sarabun');return para(t,st,cw-10)
            data=[[c(x,True) for x in cols]]+[[c(x) for x in (r+['']*(n-len(r)))] for r in rows]
            tb=Table(data,colWidths=[cw]*n,repeatRows=1)
            tb.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#94a3b8')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2e8f0')),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story+= [tb,Spacer(1,8)]
    out=io.BytesIO()
    SimpleDocTemplate(out,pagesize=A4,leftMargin=2*cm,rightMargin=2*cm,topMargin=2*cm,bottomMargin=2*cm,title=title or 'document').build(story)
    return out.getvalue()

BUILDERS={'pptx':build_pptx,'xlsx':build_xlsx,'csv':build_csv,'docx':build_docx,'pdf':build_pdf}

def create(db,u_id,tenant_id,conversation_id,kind,args):
    """Build, store and register one file. Raises ToolError with a message the model can act on."""
    if kind not in BUILDERS:raise ToolError('ชนิดไฟล์ไม่รองรับ')
    data=BUILDERS[kind](args)
    if len(data)>10*1024*1024:raise ToolError('ไฟล์ใหญ่เกิน 10 MB')
    name=safe_name(args.get('filename') or args.get('title'),kind)
    cutoff=now()
    for old in db.scalars(select(GeneratedFile).where(GeneratedFile.user_id==u_id,GeneratedFile.expires_at<cutoff)):
        try:storage.remove(old.storage_key)
        except Exception:pass
        db.delete(old)
    f=GeneratedFile(tenant_id=tenant_id,user_id=u_id,conversation_id=conversation_id or '',name=name,kind=kind,size=len(data),storage_key='',expires_at=(datetime.now(timezone.utc)+timedelta(days=RETENTION_DAYS)).isoformat())
    db.add(f);db.flush();f.storage_key=f'{tenant_id}/generated/{u_id}/{f.id}'
    storage.put(f.storage_key,data)
    owner=db.get(User,u_id)
    db.add(Audit(tenant_id=tenant_id,user_id=u_id,actor=owner.name if owner else '',action='Agent สร้างไฟล์',detail=name[:100]));db.commit()
    return f

router=APIRouter(prefix='/api/files')

@router.get('')
def mine(u:User=Depends(current_user),db:Session=Depends(db_session)):
    rows=db.scalars(select(GeneratedFile).where(GeneratedFile.user_id==u.id,GeneratedFile.tenant_id==u.tenant_id,GeneratedFile.expires_at>=now()).order_by(GeneratedFile.created_at.desc()).limit(50)).all()
    return [{'id':f.id,'name':f.name,'kind':f.kind,'size':f.size,'expires_at':f.expires_at,'created_at':f.created_at} for f in rows]

@router.get('/{file_id}')
def download(file_id:str,u:User=Depends(current_user),db:Session=Depends(db_session)):
    f=db.scalar(select(GeneratedFile).where(GeneratedFile.id==file_id,GeneratedFile.user_id==u.id,GeneratedFile.tenant_id==u.tenant_id))
    if not f:raise HTTPException(404,'ไม่พบไฟล์')
    if f.expires_at<now():raise HTTPException(410,'ไฟล์หมดอายุแล้ว กรุณาให้ AI สร้างใหม่')
    return Response(storage.get(f.storage_key),media_type=TYPES[f.kind],headers={'Content-Disposition':f"attachment; filename*=UTF-8''{quote(f.name)}",'X-Content-Type-Options':'nosniff','Cache-Control':'private, no-store'})
