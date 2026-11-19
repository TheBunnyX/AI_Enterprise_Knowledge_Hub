"""ClamD INSTREAM protocol: scan before any persistence, parser or OCR.

A Super Admin can switch scanning off (Security page) for a deployment that does not run ClamAV. The switch lives in the
`settings` table so it takes effect in every process (API, workers) within CACHE_SECONDS, without a restart. Scanning is on
unless someone explicitly turned it off, and an unreadable setting counts as on.
"""
import os,socket,struct,time
from fastapi import HTTPException

CACHE_SECONDS=5.
_cache={'at':0.,'value':True}

def enabled():
    """False only when an admin switched scanning off."""
    if time.monotonic()-_cache['at']<CACHE_SECONDS:return _cache['value']
    value=_cache['value']
    try:
        from sqlalchemy import select
        from .database import SessionLocal
        from .feature_models import Setting
        with SessionLocal() as db:
            row=db.scalar(select(Setting).where(Setting.key=='antivirus'))
            value=bool((row.value or {}).get('enabled',True)) if row else True
    except Exception:pass  # the database did not answer: keep the last known value (on, if there is none)
    _cache.update(at=time.monotonic(),value=value)
    return value

def set_enabled(db,value):
    from sqlalchemy import select
    from .feature_models import Setting
    row=db.scalar(select(Setting).where(Setting.key=='antivirus'))
    if not row:row=Setting(key='antivirus');db.add(row)
    row.value={'enabled':bool(value)};db.commit()
    _cache.update(at=time.monotonic(),value=bool(value))

def forget():
    """Drop the cached value (tests, and a database that was just replaced)."""
    _cache.update(at=0.,value=True)

def ping():
    host=os.getenv('CLAMAV_HOST','')
    if not host:return {'status':'not_configured'}
    if not enabled():return {'status':'disabled'}
    with socket.create_connection((host,int(os.getenv('CLAMAV_PORT','3310'))),timeout=5) as sock:
        sock.sendall(b'zPING\0');reply=sock.recv(100)
    if not reply.startswith(b'PONG'):raise ConnectionError('ClamAV not ready')
    return {'status':'healthy'}

def scan(data):
    if not enabled():return 'disabled'
    host=os.getenv('CLAMAV_HOST','')
    if not host:
        if os.getenv('CLAMAV_REQUIRED','false').lower()=='true':raise HTTPException(503,'ยังไม่มีบริการตรวจไวรัส จึงยังรับไฟล์ไม่ได้')
        return 'not_configured'
    try:
        with socket.create_connection((host,int(os.getenv('CLAMAV_PORT','3310'))),timeout=45) as sock:
            sock.sendall(b'zINSTREAM\0')
            for offset in range(0,len(data),65536):
                chunk=data[offset:offset+65536];sock.sendall(struct.pack('!I',len(chunk))+chunk)
            sock.sendall(struct.pack('!I',0));reply=b''
            while b'\0' not in reply and len(reply)<4096:
                part=sock.recv(4096)
                if not part:break
                reply+=part
        if b' FOUND' in reply:
            try:
                from .alerts import publish
                import hashlib
                publish('malware:'+hashlib.sha256(data).hexdigest(),'ปฏิเสธไฟล์ที่ตรวจพบอันตราย','ไฟล์ไม่ถูกจัดเก็บหรือส่งเข้า parser',severity='critical')
            except Exception:pass
            raise HTTPException(422,'ตรวจพบไฟล์อันตราย ระบบปฏิเสธไฟล์และไม่ได้จัดเก็บเนื้อหา')
        if not reply.rstrip(b'\0\n').endswith(b' OK'):raise ConnectionError('Scanner rejected stream')
        return 'clean'
    except HTTPException:raise
    except (OSError,ConnectionError):raise HTTPException(503,'บริการตรวจไวรัสไม่พร้อมใช้งาน กรุณาลองใหม่เมื่อบริการกลับมาทำงาน')
