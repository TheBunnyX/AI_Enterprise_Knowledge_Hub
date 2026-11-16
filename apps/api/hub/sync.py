"""Automatic sync: pull each source's file, and when its content changed add it as a new version so the RAG index follows.

Everything after the download is the normal upload path (validation, antivirus, version history, ingest), so a synced file
gets exactly the checks and the processing an uploaded one does. Failures are recorded on the source, never raised.
"""
import asyncio, hashlib, ipaddress, re, secrets, socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, unquote, urljoin
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from .database import SessionLocal, scope_to_tenant
from .models import Audit, Document
from .feature_models import DocumentState, DocumentVersion
from .sync_models import KBSource
from . import storage

MAX_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
MIN_INTERVAL = 15  # minutes
BLOCKED_NAMES = ('localhost',)
BLOCKED_SUFFIXES = ('.local', '.internal', '.localhost', '.lan', '.home.arpa')


def _now(): return datetime.now(timezone.utc)


def check_url(url):
    """Syntax and literal-address checks that need no network. Raises ValueError with a reason fit for the user."""
    parts = urlsplit(url.strip())
    if parts.scheme != 'https': raise ValueError('ใช้ได้เฉพาะลิงก์ https')
    if parts.username or parts.password: raise ValueError('ลิงก์ห้ามมีชื่อผู้ใช้หรือรหัสผ่าน')
    host = (parts.hostname or '').lower().rstrip('.')
    if not host: raise ValueError('ลิงก์ไม่ถูกต้อง')
    if host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES): raise ValueError('ไม่อนุญาตให้ใช้ที่อยู่ภายในเครือข่าย')
    try: address = ipaddress.ip_address(host)
    except ValueError: return
    if not address.is_global: raise ValueError('ไม่อนุญาตให้ใช้ที่อยู่ภายในเครือข่าย')


def _resolve_public(host):
    """The addresses a name points to right now; any private one refuses the whole fetch (the name may have been repointed)."""
    for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0]).is_global: raise ValueError('ลิงก์ชี้ไปยังที่อยู่ภายในเครือข่าย')


def _filename(response, url):
    disposition = response.headers.get('content-disposition', '')
    found = re.search(r"filename\*=UTF-8''([^;]+)", disposition) or re.search(r'filename="?([^";]+)"?', disposition)
    name = unquote(found.group(1)) if found else unquote(urlsplit(url).path.rsplit('/', 1)[-1])
    return name or 'document'


def fetch(url):
    """Download one file: (name, bytes). Redirects are followed by hand so every hop is checked like the first URL."""
    with httpx.Client(timeout=30, follow_redirects=False, headers={'User-Agent': 'knowledge-hub-sync'}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url); _resolve_public(urlsplit(url).hostname)
            with client.stream('GET', url) as response:
                if response.is_redirect: url = urljoin(url, response.headers.get('location', '')); continue
                if response.status_code != 200: raise ValueError(f'ต้นทางตอบกลับ {response.status_code}')
                data = bytearray()
                for part in response.iter_bytes():
                    data += part
                    if len(data) > MAX_BYTES: raise ValueError('ไฟล์ต้นทางใหญ่เกิน 20 MB')
                return _filename(response, url), bytes(data)
    raise ValueError('ลิงก์เปลี่ยนเส้นทางมากเกินไป')


class _Upload:
    def __init__(self, name, data): self.filename, self._data = name, data
    async def read(self, n=-1): return self._data


def _validate(name, data):
    from .uploads import read_validated
    try: return asyncio.run(read_validated(_Upload(name, data)))
    except HTTPException as e: raise ValueError(e.detail)


def sync_source(source_id):
    """Check one source now. Returns 'updated', 'unchanged' or 'error'; the outcome is also stored on the source."""
    with SessionLocal() as db:
        source = db.get(KBSource, source_id)
        if not source: return 'error'
        tenant = source.tenant_id
    with SessionLocal() as db:
        scope_to_tenant(db, tenant)
        source = db.get(KBSource, source_id)
        try:
            status, document_id = _apply(db, source)
            source.last_status, source.last_error = status, ''
            if document_id: source.document_id = document_id
        except Exception as e:  # a broken source must never stop the others
            db.rollback(); source = db.get(KBSource, source_id)
            status, source.last_status, source.last_error = 'error', 'error', str(e)[:300] or e.__class__.__name__
        source.last_checked = _now().isoformat(); db.commit()
        document_id = source.document_id
    if status == 'updated' and document_id:
        from .jobs import schedule_ingest
        schedule_ingest(document_id, None, retry=True)
    return status


def _apply(db, source):
    """Returns (status, document id to remember). Stores the new content only when it differs from the last sync."""
    name, data = fetch(source.url)
    name, data = _validate(name, data)
    digest = hashlib.sha256(data).hexdigest()
    if digest == source.content_sha: return 'unchanged', ''
    document = db.get(Document, source.document_id) if source.document_id else None
    if document and db.scalar(select(DocumentState).where(DocumentState.document_id == document.id, DocumentState.deleted_at != '')): document = None
    other = db.scalar(select(Document).where(Document.tenant_id == source.tenant_id, Document.sha256 == digest))
    if other and (not document or other.id != document.id):
        source.content_sha = digest  # the same bytes already live in the organisation; keep watching for the next change
        return 'unchanged', ''
    key = f'{source.tenant_id}/{secrets.token_hex(16)}'; storage.put(key, data)
    if document:
        db.add(DocumentVersion(tenant_id=document.tenant_id, document_id=document.id, version=document.version, name=document.name, size=document.size, sha256=document.sha256, storage_key=document.storage_key))
        document.name, document.size, document.sha256, document.storage_key = name, len(data), digest, key
        document.version += 1; document.status = 'processing'; document.error = ''
    else:
        document = Document(tenant_id=source.tenant_id, knowledge_base_id=source.knowledge_base_id, name=name, sha256=digest, size=len(data), storage_key=key)
        db.add(document); db.flush()
    source.content_sha = digest
    db.add(Audit(tenant_id=source.tenant_id, user_id='', actor='ซิงก์อัตโนมัติ', action='ซิงก์เอกสาร', detail=document.name))
    return 'updated', document.id


def run_due():
    """Sync every enabled source whose interval has passed. Returns how many were checked."""
    due = []
    with SessionLocal() as db:  # trusted system context: sources of every tenant
        for s in db.scalars(select(KBSource).where(KBSource.enabled == True)):
            if not s.last_checked or _now() >= datetime.fromisoformat(s.last_checked) + timedelta(minutes=max(s.interval_minutes, MIN_INTERVAL)): due.append(s.id)
    for id in due: sync_source(id)
    return len(due)
