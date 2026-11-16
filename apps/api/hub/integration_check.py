"""Exercise deployed API, Celery, PostgreSQL, SeaweedFS, Qdrant and citations."""
import io, json, time
from uuid import uuid4
import httpx
from .database import SessionLocal
from .models import Document
from .storage import get
from .retrieval import COLLECTION, embed
from qdrant_client import QdrantClient, models
import os

def main():
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=30) as c:
        c.post('/api/auth/login',json={'email':os.environ['INTEGRATION_EMAIL'],'password':os.environ['INTEGRATION_PASSWORD']}).raise_for_status()
        kb=c.get('/api/knowledge-bases').json()[0]['id']
        marker='integration-'+str(uuid4())
        # Generate a real text PDF with a valid page map, no paid provider needed.
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        w=PdfWriter();p=w.add_blank_page(width=595,height=842)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 50 750 Td ({marker} paid leave policy is 10 days annually.) Tj ET'.encode())
        p[NameObject('/Contents')]=w._add_object(stream);f=io.BytesIO();w.write(f);raw=f.getvalue()
        r=c.post('/api/documents',data={'knowledge_base_id':kb},files={'file':('integration-policy.pdf',raw,'application/pdf')});r.raise_for_status();id=r.json()['id']
        for _ in range(60):
            d=c.get('/api/documents/'+id).json()
            if d['status']!='processing':break
            time.sleep(.5)
        assert d['status']=='ready',d
        assert d['pages'][0]['page']==1 and marker in d['pages'][0]['text']
        with SessionLocal() as db:
            record=db.get(Document,id);tenant=record.tenant_id
            assert get(record.storage_key)==raw
        q=QdrantClient(url=os.environ['QDRANT_URL'])
        points=q.query_points(COLLECTION,query=embed(marker),query_filter=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value=tenant)),models.FieldCondition(key='document_id',match=models.MatchValue(value=id))]),limit=5).points
        assert points and points[0].payload['tenant_id']==tenant
        other=q.query_points(COLLECTION,query=embed(marker),query_filter=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value='other-tenant'))]),limit=5).points
        assert not other
        assert any(x['document_id']==id for x in c.get('/api/search',params={'q':marker}).json())
        r=c.post('/api/chat',json={'question':marker,'document_ids':[id]});r.raise_for_status()
        events=[json.loads(l) for l in r.text.splitlines()]
        assert events[0]['citations'][0]['document_id']==id
        assert c.get('/api/documents/'+id+'/download').content==raw
        assert c.get('/api/analytics').json()['requests']>=1
        assert c.get('/api/audit').json()
        from PIL import Image, ImageDraw, ImageFont
        image=Image.new('RGB',(1300,160),'white');draw=ImageDraw.Draw(image)
        font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
        draw.text((25,45),'Annual leave policy: 12 days per year. OCRTEST',fill='black',font=font)
        image_file=io.BytesIO();image.save(image_file,format='PNG')
        r=c.post('/api/documents',data={'knowledge_base_id':kb},files={'file':('ocr-integration.png',image_file.getvalue(),'image/png')});r.raise_for_status();ocr_id=r.json()['id']
        for _ in range(60):
            result=c.get('/api/documents/'+ocr_id).json()
            if result['status']!='processing':break
            time.sleep(.5)
        assert result['status']=='ready',result
        assert '12 days' in ' '.join(p['text'] for p in result['pages'])
        print(json.dumps({'result':'PASS','checks':['PostgreSQL persistence','Celery PDF ingestion','PaddleOCR image OCR','SeaweedFS S3 round trip','Qdrant tenant-filtered indexing and search','hybrid retrieval','streamed demo answer','page-1 citation','authenticated download','usage and audit logs']}))
if __name__=='__main__':main()
