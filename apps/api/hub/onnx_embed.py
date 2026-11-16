"""Local multilingual-e5-small embeddings (ONNX Runtime, CPU). Model files are fetched once into DATA_DIR/models."""
import os
from functools import lru_cache
import numpy as np

REPO='intfloat/multilingual-e5-small'
DIMENSIONS=384
MAX_TOKENS=512  # model limit; longer text is truncated

@lru_cache(maxsize=1)
def _load():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    cache=os.path.join(os.getenv('DATA_DIR','/data'),'models')
    model=hf_hub_download(REPO,'onnx/model.onnx',cache_dir=cache)
    tokenizer=Tokenizer.from_file(hf_hub_download(REPO,'onnx/tokenizer.json',cache_dir=cache))
    tokenizer.enable_truncation(MAX_TOKENS)
    tokenizer.enable_padding(pad_id=1,pad_token='<pad>')
    options=ort.SessionOptions()
    options.intra_op_num_threads=int(os.getenv('ONNX_THREADS',str(min(4,os.cpu_count() or 1))))
    session=ort.InferenceSession(model,options,providers=['CPUExecutionProvider'])
    return tokenizer,session,{i.name for i in session.get_inputs()}

def embed(texts,kind='passage'):
    """L2-normalised vectors. E5 needs a 'query: ' / 'passage: ' prefix, so callers say which one they are embedding."""
    if kind not in('query','passage'):raise ValueError('kind must be query or passage')
    tokenizer,session,names=_load()
    size=max(1,int(os.getenv('ONNX_BATCH_SIZE','16')))
    out=[]
    for i in range(0,len(texts),size):
        encoded=tokenizer.encode_batch([f'{kind}: {t}' for t in texts[i:i+size]])
        ids=np.array([e.ids for e in encoded],dtype=np.int64)
        mask=np.array([e.attention_mask for e in encoded],dtype=np.int64)
        feeds={'input_ids':ids,'attention_mask':mask}
        if 'token_type_ids' in names:feeds['token_type_ids']=np.zeros_like(ids)
        hidden=session.run(None,feeds)[0]
        pooled=(hidden*mask[...,None]).sum(1)/mask.sum(1,keepdims=True)
        pooled/=np.linalg.norm(pooled,axis=1,keepdims=True)
        out+=pooled.astype(float).tolist()
    return out

def token_count(text):
    tokenizer,_,_=_load()
    return len(tokenizer.encode('passage: '+text).ids)
