"""ClamD INSTREAM protocol: scan before any persistence, parser or OCR."""
import os,socket,struct
from fastapi import HTTPException

def ping():
    host=os.getenv('CLAMAV_HOST','')
    if not host:return {'status':'not_configured'}
    with socket.create_connection((host,int(os.getenv('CLAMAV_PORT','3310'))),timeout=5) as sock:
        sock.sendall(b'zPING\0');reply=sock.recv(100)
    if not reply.startswith(b'PONG'):raise ConnectionError('ClamAV not ready')
    return {'status':'healthy'}

def scan(data):
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
