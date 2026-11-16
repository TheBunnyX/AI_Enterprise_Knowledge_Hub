import io
from fastapi import HTTPException

async def read_validated(file):
    name=(file.filename or 'file').replace('\\','/').split('/')[-1]
    ext=name.rsplit('.',1)[-1].lower()
    if ext not in ('pdf','docx','pptx','xlsx','doc','xls','txt','md','csv','html','png','jpg','jpeg'): raise HTTPException(415,'รองรับ PDF, DOC, DOCX, PPTX, XLS, XLSX, TXT, MD, CSV, HTML, PNG และ JPG')
    data=await file.read(20*1024*1024+1)
    if not data or len(data)>20*1024*1024: raise HTTPException(413,'ขนาดไฟล์ต้องอยู่ระหว่าง 1 ไบต์ถึง 20 MB')
    from .antivirus import scan
    from starlette.concurrency import run_in_threadpool
    await run_in_threadpool(scan,data)
    if ext=='pdf' and not data.startswith(b'%PDF'): raise HTTPException(415,'รูปแบบ PDF ไม่ถูกต้อง')
    if ext in ('doc','xls') and not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')): raise HTTPException(415,'ไฟล์ Office รุ่นเก่าไม่ถูกต้อง')
    if ext in ('docx','pptx','xlsx'):
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist())>100*1024*1024: raise HTTPException(413,'ไฟล์เมื่อแตกข้อมูลใหญ่เกินไป')
                if '[Content_Types].xml' not in z.namelist(): raise HTTPException(415,'ไฟล์ Office ไม่ถูกต้อง')
        except zipfile.BadZipFile: raise HTTPException(415,'ไฟล์ Office ไม่ถูกต้อง')
    if ext in ('png','jpg','jpeg'):
        from PIL import Image
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width*image.height>25000000:raise HTTPException(413,'ภาพต้องไม่เกิน 25 ล้านพิกเซล')
                if image.format not in ('PNG','JPEG'):raise HTTPException(415,'รูปแบบภาพไม่ถูกต้อง')
                image.verify()
        except (OSError,ValueError):raise HTTPException(415,'ไม่สามารถอ่านรูปภาพได้')
    return name,data
