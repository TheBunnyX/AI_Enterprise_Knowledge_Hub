"""Document parsing, chunking, indexing and hybrid search. Each embedding version has its own collection, so spaces never mix."""
import hashlib, io, math, os, re, secrets
from collections import Counter
from sqlalchemy import select, delete
from .database import SessionLocal
from .models import Chunk, Document, KnowledgeBase
from . import storage

from . import embeddings, multimodal
COLLECTION = embeddings.specification()['collection']
def tokens(text):
    s = re.sub(r'\s+', '', text.lower())
    return re.findall(r'[a-z0-9]{2,}', text.lower()) + [s[i:i+3] for i in range(max(0,len(s)-2))]

_TONES=re.compile('[่-๋]')  # Thai tone marks: PP-OCRv5 often drops them (ฝ่าย->ฝาย)

def lexical_tokens(text):
    return tokens(_TONES.sub('',text))

def embed(text):
    v = [0.] * 256
    for t,n in Counter(tokens(text)).items():
        h = hashlib.sha256(t.encode()).digest()
        v[int.from_bytes(h[:2],'big') % 256] += n * (1 if h[2] % 2 else -1)
    norm = math.sqrt(sum(x*x for x in v)) or 1
    return [x/norm for x in v]

def parse(name, data):
    ext = name.rsplit('.',1)[-1].lower()
    f = io.BytesIO(data)
    if ext == 'pdf':
        from pypdf import PdfReader
        reader=PdfReader(f)
        if len(reader.pages)>200:raise ValueError('PDF ต้องไม่เกิน 200 หน้า')
        from .ocr import pdf_page
        return [(i+1,(p.extract_text().replace(chr(0),'').replace('ํา','ำ').strip()) or pdf_page(data,i+1)) for i,p in enumerate(reader.pages)]
    if ext == 'docx':
        from docx import Document as Word
        d=Word(f)
        return [(1,'\n'.join([p.text for p in d.paragraphs]+[' | '.join(c.text for c in r.cells) for t in d.tables for r in t.rows]))]
    if ext == 'pptx':
        from pptx import Presentation
        return [(i+1,'\n'.join(s.text for s in p.shapes if s.has_text_frame)) for i,p in enumerate(Presentation(f).slides)]
    if ext == 'xlsx':
        from openpyxl import load_workbook
        w=load_workbook(f,read_only=True,data_only=True)
        return [(i+1,s.title+'\n'+'\n'.join(' | '.join(str(v or '') for v in r) for r in s.values)) for i,s in enumerate(w)]
    if ext == 'xls':
        import xlrd
        w=xlrd.open_workbook(file_contents=data,on_demand=True)
        return [(i+1,s.name+chr(10)+chr(10).join(' | '.join(str(v) for v in s.row_values(r)) for r in range(s.nrows))) for i,s in enumerate(w.sheets())]
    if ext == 'doc':
        import subprocess,tempfile
        with tempfile.NamedTemporaryFile(suffix='.doc') as t:
            t.write(data);t.flush()
            r=subprocess.run(['antiword','-m','UTF-8.txt',t.name],capture_output=True,timeout=60)
        if r.returncode:raise ValueError('อ่านไฟล์ DOC ไม่สำเร็จ')
        return [(1,r.stdout.decode('utf-8','replace'))]
    if ext in ('png','jpg','jpeg'):
        from .ocr import image_text
        return [(1,image_text(data,'.'+ext))]
    text=data.decode('utf-8-sig')
    if ext == 'html': text=re.sub('<[^>]+>', ' ', text)
    return [(1,text)]

# Where a chunk may end, best first: before a heading, between paragraphs, at a line break, at a space, and as a last
# resort inside unbroken Thai text - but only in front of a consonant or leading vowel, never in front of a vowel or tone
# mark that belongs to the previous consonant.
SEPARATORS=[r'\n+(?=#{1,6} )',r'\n\n+',r'\n',' ',r'(?<![เ-ไ])(?=[ก-ฮ])|(?=[เ-ไ])','']

def _weight(text):
    """Rough token cost for models with short contexts: Thai is ~2 tokens per character, CJK ~1.5, Latin ~0.4."""
    return sum(2.2 if '฀'<=c<='๿' else 1.5 if ord(c)>0x2e80 else 0.4 for c in text)

def split(text):
    """Cut text into chunks that follow the document's structure (LangChain's recursive splitter), so a passage is not
    cut mid-sentence when a paragraph or line boundary is available. Chunks hold up to 900 characters with about 200 of
    overlap; EMBEDDING_MAX_TOKENS switches the size to a token budget for embedding models with short contexts."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    limit=int(os.getenv('EMBEDDING_MAX_TOKENS','0'))
    splitter=RecursiveCharacterTextSplitter(separators=SEPARATORS,is_separator_regex=True,keep_separator='start',
        chunk_size=limit or 900,chunk_overlap=limit//5 if limit else 200,length_function=_weight if limit else len,strip_whitespace=True)
    return [part for part in splitter.split_text(text) if part.strip()]

def qdrant():
    from qdrant_client import QdrantClient
    return QdrantClient(url=os.environ['QDRANT_URL'])

_indexed=set()
def ensure_collection(client):
    """Create the collection if needed and index the payload fields every search filters on (tenant, document)."""
    from qdrant_client import models
    if not client.collection_exists(COLLECTION): client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=embeddings.specification()['dimensions'],distance=models.Distance.COSINE))
    if COLLECTION in _indexed: return
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        for field in ('tenant_id','document_id'):
            try: client.create_payload_index(COLLECTION,field,models.PayloadSchemaType.KEYWORD)
            except Exception: pass  # an index only speeds filtering up; searching works without it
    _indexed.add(COLLECTION)

def ingest(document_id,raise_errors=False):
    """Parse, chunk, embed and index one document. A failure is recorded on the document; with raise_errors it is also
    raised, so the task queue can retry a transient outage instead of reporting the task as completed."""
    with SessionLocal() as db:
        d=db.get(Document,document_id)
        if not d: return
        failure=None
        try:
            raw=storage.get(d.storage_key)
            pages=parse(d.name,raw)
            chunks=[]
            for page,text in pages:
                for part in split(text):
                    chunks.append(Chunk(tenant_id=d.tenant_id,document_id=d.id,page=page,text=part,embedding_version=embeddings.specification()['version']))
            # Multimodal RAG: each picture becomes a chunk whose text is a vision-model description and whose vector is the picture itself.
            kb=db.get(KnowledgeBase,d.knowledge_base_id)  # pictures are indexed only in libraries that opted in
            for page,picture,description,vector in (multimodal.index_pictures(d.name,raw) if multimodal.enabled() and kb and kb.multimodal else []):
                key=f'{d.tenant_id}/chunk-images/{d.id}/{secrets.token_hex(8)}.jpg'; storage.put(key,picture)
                chunks.append(Chunk(tenant_id=d.tenant_id,document_id=d.id,page=page,text=f'[ภาพในหน้า {page}] '+description,kind='image',image_key=key,mm_embedding=vector,embedding_version=embeddings.specification()['version']))
            if not chunks: raise ValueError('ไม่พบข้อความที่อ่านได้ เอกสารสแกนต้องทำ OCR ก่อนอัปโหลด')
            vectors=embeddings.batch([c.text for c in chunks],d.tenant_id)
            for c,v in zip(chunks,vectors):c.embedding=v
            for old in db.scalars(select(Chunk.image_key).where(Chunk.document_id==d.id,Chunk.kind=='image')):
                try:
                    if old:storage.remove(old)
                except Exception: pass  # an orphaned picture file is harmless
            db.execute(delete(Chunk).where(Chunk.document_id==d.id))
            db.add_all(chunks); db.flush()
            if os.getenv('QDRANT_URL'):
                from qdrant_client import models
                client=qdrant(); ensure_collection(client)
                client.delete(COLLECTION,models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value=d.tenant_id)),models.FieldCondition(key='document_id',match=models.MatchValue(value=d.id))])),wait=True)
                client.upsert(COLLECTION,[models.PointStruct(id=c.id,vector=c.embedding,payload={'tenant_id':d.tenant_id,'document_id':d.id,'knowledge_base_id':d.knowledge_base_id}) for c in chunks],wait=True)
                if multimodal.enabled(): index_picture_vectors(client,d,[c for c in chunks if c.kind=='image'])
            d.status='ready'; d.error=''
        except Exception as e:
            failure=e
            db.rollback(); d=db.get(Document,document_id); d.status='failed'; d.error=str(e)[:400]
        db.commit()
    if failure is not None and raise_errors: raise failure

def ensure_picture_collection(client):
    from qdrant_client import models
    name=multimodal.collection()
    if not client.collection_exists(name): client.create_collection(name,vectors_config=models.VectorParams(size=multimodal.settings()['dims'],distance=models.Distance.COSINE))
    return name

def index_picture_vectors(client,d,pictures):
    """Picture vectors live in their own collection (another vector space); the document's old points are replaced."""
    from qdrant_client import models
    name=ensure_picture_collection(client)
    client.delete(name,models.FilterSelector(filter=models.Filter(must=[models.FieldCondition(key='document_id',match=models.MatchValue(value=d.id))])))
    if pictures: client.upsert(name,[models.PointStruct(id=c.id,vector=c.mm_embedding,payload={'tenant_id':d.tenant_id,'document_id':d.id,'knowledge_base_id':d.knowledge_base_id}) for c in pictures],wait=True)

def has_pictures(db,tenant_id,docs):
    stmt=select(Chunk.id).where(Chunk.tenant_id==tenant_id,Chunk.kind=='image')
    if len(docs)<=IN_LIMIT: stmt=stmt.where(Chunk.document_id.in_(list(docs)))
    return db.scalar(stmt.limit(1)) is not None

def picture_hits(db,tenant_id,query,docs):
    """[(similarity, chunk id)] of the pictures closest to the question in the multimodal vector space."""
    qv=multimodal.embed_text(query)
    if os.getenv('QDRANT_URL'):
        from qdrant_client import models
        client=qdrant()
        if not client.collection_exists(multimodal.collection()): return []
        allowed=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value=tenant_id)),models.FieldCondition(key='document_id',match=models.MatchAny(any=list(docs)))])
        return [(p.score,str(p.id)) for p in client.query_points(multimodal.collection(),query=qv,query_filter=allowed,limit=20).points]
    stmt=select(Chunk.id,Chunk.document_id,Chunk.mm_embedding).where(Chunk.tenant_id==tenant_id,Chunk.kind=='image')
    if len(docs)<=IN_LIMIT: stmt=stmt.where(Chunk.document_id.in_(list(docs)))
    hits=[(sum(a*b for a,b in zip(qv,r.mm_embedding)),r.id) for r in db.execute(stmt) if r.document_id in docs and r.mm_embedding and len(r.mm_embedding)==len(qv)]
    return sorted(hits,key=lambda x:x[0],reverse=True)[:20]

IN_LIMIT=500  # above this many documents the scope is checked in Python instead of a long SQL IN list

CROSS_POOL=int(os.getenv('CROSS_LANGUAGE_POOL','20'))  # candidates the reranker sees for a question without Thai letters
THAI_LETTERS=re.compile(r'[\u0e00-\u0e7f]')

def cross_language(query):
    """True for a question without Thai letters while a reranker is configured. Dense similarity between an English question and Thai
    passages is low (the 0.80 cut-off drops the right chunk), but the multilingual reranker scores them well, so such questions
    keep more dense candidates and leave the verdict to the reranker, whose floor still rejects meaningless queries."""
    return os.getenv('CROSS_LANGUAGE_SEARCH','true').lower()=='true' and bool(os.getenv('RERANK_MODEL')) and not THAI_LETTERS.search(query or '')

DEPARTMENT_BOOST=1.2  # score multiplier for passages from the user's own department's knowledge bases

def searchable_documents(db,tenant_id,kb_id=None,document_ids=None,user=None):
    """Ready, undeleted documents this search may touch, narrowed to what the user may read: {id: row(name, version, knowledge_base_id)}."""
    from .policies import deleted_ids, visible_documents
    stmt=select(Document.id,Document.name,Document.name_en,Document.version,Document.knowledge_base_id).where(Document.tenant_id==tenant_id,Document.status=='ready',~Document.id.in_(deleted_ids()))
    if kb_id: stmt=stmt.where(Document.knowledge_base_id==kb_id)
    if document_ids: stmt=stmt.where(Document.id.in_(document_ids))
    docs={r.id:r for r in db.execute(stmt)}
    if user is not None:
        readable=set(visible_documents(db,user)); docs={k:v for k,v in docs.items() if k in readable}
    return docs

def search(db, tenant_id, query, kb_id=None, document_ids=None, mode='hybrid', limit=10, user=None, relaxed=False, per_doc=None, pool=None):
    """Hybrid retrieval: BM25 over tone-insensitive trigrams (sparse) and embedding similarity (dense), fused by reciprocal rank.

    Only documents the user may read are considered, and that same list filters the vector store, so its top hits are
    never spent on passages the user cannot see. Stored embeddings are read only when there is no vector store."""
    spec=embeddings.specification()
    docs=searchable_documents(db,tenant_id,kb_id,document_ids,user)
    use_sparse=mode!='semantic'; use_dense=mode!='keyword'
    cross=cross_language(query) and not relaxed  # a question in another language than the passages: let the reranker judge more candidates
    vector_store=use_dense and bool(os.getenv('QDRANT_URL'))
    qv=embeddings.batch([query],tenant_id,'query')[0] if use_dense else None
    scope=[Chunk.tenant_id==tenant_id,Chunk.embedding_version==spec['version']]
    chunks={}; kinds={}; sparse=[]; dense=[]; pictures=[]  # chunks: id -> (document_id, page, text); kinds: id -> 'text' | 'image'
    if docs and (use_sparse or not vector_store):
        local_dense=use_dense and not vector_store
        stmt=select(Chunk.id,Chunk.document_id,Chunk.page,Chunk.text,Chunk.kind,*([Chunk.embedding] if local_dense else [])).where(*scope)
        if len(docs)<=IN_LIMIT: stmt=stmt.where(Chunk.document_id.in_(list(docs)))
        terms=list(dict.fromkeys(lexical_tokens(query))) if use_sparse else []; wanted=set(terms)
        stats=[]; frequency=Counter(); total=0
        for row in db.execute(stmt):
            if row.document_id not in docs: continue
            chunks[row.id]=(row.document_id,row.page,row.text); kinds[row.id]=row.kind
            if use_sparse:
                found=lexical_tokens(row.text+' '+docs[row.document_id].name)
                tf=Counter(t for t in found if t in wanted)  # only the query's terms matter for the score
                total+=len(found); frequency.update(tf.keys()); stats.append((row.id,len(found),tf))
            if local_dense: dense.append((sum(a*b for a,b in zip(qv,row.embedding)),row.id))
        count=len(chunks); average=total/(count or 1) or 1
        for id,length,tf in stats:
            if not tf: continue
            score=0.
            for t in terms:
                n=tf[t]
                if n: score+=math.log(1+(count-frequency[t]+.5)/(frequency[t]+.5))*(n*2.2)/(n+1.2*(.25+.75*length/average))
            sparse.append((score,id))
    if vector_store and docs and (chunks or not use_sparse):
        from qdrant_client import models
        client=qdrant()
        if chunks or client.collection_exists(COLLECTION):
            allowed=models.Filter(must=[models.FieldCondition(key='tenant_id',match=models.MatchValue(value=tenant_id)),models.FieldCondition(key='document_id',match=models.MatchAny(any=list(docs)))])
            points=client.query_points(COLLECTION,query=qv,query_filter=allowed,limit=50).points
            missing=[str(p.id) for p in points if str(p.id) not in chunks]
            if missing:
                for row in db.execute(select(Chunk.id,Chunk.document_id,Chunk.page,Chunk.text,Chunk.kind).where(*scope,Chunk.id.in_(missing))):
                    if row.document_id in docs: chunks[row.id]=(row.document_id,row.page,row.text); kinds[row.id]=row.kind
            dense=[(p.score,str(p.id)) for p in points if str(p.id) in chunks]
    if use_dense and docs and multimodal.enabled() and has_pictures(db,tenant_id,docs):  # no picture indexed in scope: skip the extra embedding call
        try:
            pictures=picture_hits(db,tenant_id,query,docs)
            missing=[i for _,i in pictures if i not in chunks]
            if missing:
                for row in db.execute(select(Chunk.id,Chunk.document_id,Chunk.page,Chunk.text,Chunk.kind).where(Chunk.tenant_id==tenant_id,Chunk.id.in_(missing))):
                    if row.document_id in docs: chunks[row.id]=(row.document_id,row.page,row.text); kinds[row.id]=row.kind
            pictures=[(s,i) for s,i in pictures if i in chunks]
        except Exception:
            import logging; logging.getLogger('hub.multimodal').warning('picture search skipped',exc_info=True); pictures=[]  # text search still answers
    sparse.sort(key=lambda x:x[0],reverse=True); dense.sort(key=lambda x:x[0],reverse=True); pictures.sort(key=lambda x:x[0],reverse=True)
    ranks={}
    for source in ([sparse] if mode=='keyword' else [dense,pictures] if mode=='semantic' else [sparse,dense,pictures]):
        for rank,(score,id) in enumerate(source):
            if score < (multimodal.settings()['min_score'] if source is pictures else 0 if relaxed else 0.10 if source is sparse else 0 if cross else spec.get('min_score',0.16)) or (relaxed and source is sparse and score<=0): continue
            old=ranks.get(id,[0,id]); old[0]+=1/(60+rank+1); ranks[id]=old
    if user is not None and not kb_id and ranks:  # the user's own department's knowledge wins a close call (a gentle nudge, not a filter)
        from .policies import department_ids
        mine=department_ids(db,user)
        if mine:
            own=set(db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.tenant_id==tenant_id,KnowledgeBase.department_id.in_(mine))))
            for id,entry in ranks.items():
                if docs[chunks[id][0]].knowledge_base_id in own: entry[0]*=DEPARTMENT_BOOST
    results=[]; taken={}
    cap=pool or (max(limit,30) if relaxed else max(limit,CROSS_POOL) if cross else limit)  # how many candidates go to the reranker (a CPU model: the cost grows with this number)
    for score,id in sorted(ranks.values(),key=lambda x:x[0],reverse=True):
        if len(results)>=cap:break
        document_id,page,text=chunks[id]; d=docs[document_id]
        if per_doc and taken.get(document_id,0)>=per_doc:continue  # keep a few passages per document so the list covers more documents
        taken[document_id]=taken.get(document_id,0)+1
        results.append({'chunk_id':id,'document_id':document_id,'name':d.name,'name_en':d.name_en,'version':d.version,'page':page,'snippet':text,'score':round(score,5),'knowledge_base_id':d.knowledge_base_id,'kind':kinds.get(id,'text')})
    ranked=embeddings.rerank(query,results,floor=0 if relaxed else None)
    return ranked[:limit] if cross and not pool else ranked
