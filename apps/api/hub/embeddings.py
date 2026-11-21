"""Versioned embedding and reranking adapters; hash baseline remains CPU-only."""
import hashlib,math,os,time
from concurrent.futures import ThreadPoolExecutor
import httpx
from . import gateway

LOCAL_RERANKER='local:bge-reranker-v2-m3'  # RERANK_MODEL value: INT8 ONNX cross-encoder in-process
LOCAL_E5='local:multilingual-e5-small'  # EMBEDDING_MODEL value: runs in-process via ONNX Runtime, no gateway needed

def specification():
    model=os.getenv('EMBEDDING_MODEL','')
    if not model:return {'model':'','dimensions':256,'version':'hash-ngram-v1-256','collection':'hub_hash_ngram_v1_256'}
    if model==LOCAL_E5:return {'model':model,'dimensions':384,'version':'onnx-e5-small-v1','collection':'hub_onnx_e5_small_v1','min_score':float(os.getenv('EMBEDDING_MIN_SCORE','0.80'))}
    dimensions=int(os.getenv('EMBEDDING_DIMENSIONS','1536'))
    if not 1<=dimensions<=65536:raise ValueError('Embedding dimensions out of range')
    fingerprint=hashlib.sha256((model+':'+str(dimensions)+':'+os.getenv('EMBEDDING_VERSION','1')).encode()).hexdigest()[:20]
    return {'model':model,'dimensions':dimensions,'version':'gateway-'+fingerprint,'collection':'hub_embedding_'+fingerprint}

QUERY_CACHE_SECONDS=int(os.getenv('QUERY_EMBED_CACHE_SECONDS','86400'))  # 0 = do not cache question embeddings

def _cached_queries(texts,spec,onnx_embed):
    """Question embeddings of the local model are kept in Redis (keyed by a hash of the text), so a repeated question skips the model. Best effort."""
    import json
    keys=['qemb:'+spec['version']+':'+hashlib.sha256(t.encode()).hexdigest() for t in texts]
    found={}
    try:
        from .jobs import redis_client
        r=redis_client()
        found={i:json.loads(v) for i,v in enumerate(r.mget(keys)) if v}
    except Exception:r=None
    missing=[i for i in range(len(texts)) if i not in found]
    if missing:
        fresh=onnx_embed.embed([texts[i] for i in missing],'query')
        for i,v in zip(missing,fresh):found[i]=v
        if r is not None:
            try:
                pipe=r.pipeline()
                for i,v in zip(missing,fresh):pipe.set(keys[i],json.dumps(v),ex=QUERY_CACHE_SECONDS)
                pipe.execute()
            except Exception:pass
    return [found[i] for i in range(len(texts))]

def batch(texts,tenant='',kind='passage'):
    """kind='query' for search questions, 'passage' for document chunks (only the local E5 model cares)."""
    spec=specification()
    if not spec['model']:
        from .retrieval import embed
        return [embed(t) for t in texts]
    if spec['model']==LOCAL_E5:
        from . import onnx_embed
        if kind=='query' and QUERY_CACHE_SECONDS>0 and os.getenv('CELERY_BROKER_URL'):return _cached_queries(texts,spec,onnx_embed)
        return onnx_embed.embed(texts,kind)
    from . import savings
    keys=[savings.embedding_key(spec['version'],tenant,t) for t in texts]
    known=savings.cached_vectors(list(set(keys)),spec['dimensions'])
    missing=[i for i,k in enumerate(keys) if k not in known]
    if not missing:
        if tenant:savings.record_event(tenant,'','embedding_hit',0,str(len(texts)))
        return [known[k] for k in keys]
    url,key=gateway.configuration()
    if not url:raise ValueError('Embedding model requires Gateway')
    fresh=_fetch([texts[i] for i in missing],spec,url,key)
    savings.store_vectors([(keys[i],v) for i,v in zip(missing,fresh)])
    if tenant and len(missing)<len(texts):savings.record_event(tenant,'','embedding_hit',0,str(len(texts)-len(missing)))
    new=dict(zip(missing,fresh))
    return [known[k] if i not in new else new[i] for i,k in enumerate(keys)]

def _fetch(texts,spec,url,key):
    size=max(1,int(os.getenv('EMBEDDING_BATCH_SIZE','32')))
    batches=[texts[i:i+size] for i in range(0,len(texts),size)]
    def run(client,inputs):
        for attempt in range(4):
            r=client.post(url+'/embeddings',headers=gateway.headers(key),json={'model':spec['model'],'input':inputs})
            if r.status_code in (429,500,502,503,504) and attempt<3:time.sleep(1.5*(attempt+1));continue
            r.raise_for_status();break
        data=sorted(r.json()['data'],key=lambda d:d['index'])
        if len(data)!=len(inputs):raise ValueError('Embedding batch size mismatch')
        for item in data:
            v=item['embedding']
            if len(v)!=spec['dimensions'] or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in v):raise ValueError('Embedding dimensions mismatch')
        return [d['embedding'] for d in data]
    with httpx.Client(timeout=90) as client,ThreadPoolExecutor(max_workers=min(4,len(batches)) or 1) as pool:
        return [v for part in pool.map(lambda b:run(client,b),batches) for v in part]

def rerank(query,results,floor=None):
    model=os.getenv('RERANK_MODEL','')
    if not model or not results:return results
    if model==LOCAL_RERANKER:
        from . import onnx_rerank
        scores=onnx_rerank.score(query,[x['snippet'] for x in results])
        ranked=[r|{'rerank_score':round(s,5)} for r,s in sorted(zip(results,scores),key=lambda p:p[1],reverse=True)]
        if floor is None:floor=float(os.getenv('RERANK_MIN_SCORE','0'))
        ranked=[r for r in ranked if r['rerank_score']>=floor] if floor>0 else ranked
        if floor>0:  # a question whose best passage is still weak gets no evidence at all (RERANK_TOP_MIN, 0 = off)
            top=float(os.getenv('RERANK_TOP_MIN','0'))
            if top>0 and ranked and ranked[0]['rerank_score']<top:return []
        return ranked
    url,key=gateway.configuration()
    with httpx.Client(timeout=30) as client:
        r=client.post(url+'/rerank',headers=gateway.headers(key),json={'model':model,'query':query,'documents':[x['snippet'] for x in results],'top_n':len(results)});r.raise_for_status()
        ranked=[];seen=set()
        for item in r.json()['results']:
            index=item['index']
            if not isinstance(index,int) or not 0<=index<len(results) or index in seen:raise ValueError('Invalid reranker index')
            seen.add(index);ranked.append(results[index]|{'rerank_score':item.get('relevance_score')})
        return ranked
