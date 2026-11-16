"""Local bge-reranker-v2-m3 cross-encoder (ONNX, INT8-quantized, CPU). Files are fetched once into DATA_DIR/models."""
import math,os
from functools import lru_cache
import numpy as np

REPO='onnx-community/bge-reranker-v2-m3-ONNX'
MODEL_FILE='onnx/model_int8.onnx'  # 571 MB
MAX_TOKENS=512  # query + passage; chunks are ~250 tokens

@lru_cache(maxsize=1)
def _load():
    import onnxruntime as ort
    from huggingface_hub import hf_hub_download
    from tokenizers import Tokenizer
    cache=os.path.join(os.getenv('DATA_DIR','/data'),'models')
    model=hf_hub_download(REPO,MODEL_FILE,cache_dir=cache)
    tokenizer=Tokenizer.from_file(hf_hub_download(REPO,'tokenizer.json',cache_dir=cache))
    tokenizer.enable_truncation(MAX_TOKENS,strategy='only_second')
    tokenizer.enable_padding(pad_id=1,pad_token='<pad>')
    options=ort.SessionOptions()
    options.intra_op_num_threads=int(os.getenv('ONNX_THREADS',str(min(4,os.cpu_count() or 1))))
    session=ort.InferenceSession(model,options,providers=['CPUExecutionProvider'])
    return tokenizer,session,{i.name for i in session.get_inputs()}

def score(query,passages):
    """Relevance in 0..1 (sigmoid of the model logit) for each passage, in input order."""
    if not passages:return []
    tokenizer,session,names=_load()
    size=max(1,int(os.getenv('ONNX_RERANK_BATCH_SIZE','8')))
    out=[]
    for i in range(0,len(passages),size):
        encoded=tokenizer.encode_batch([(query,p) for p in passages[i:i+size]])
        ids=np.array([e.ids for e in encoded],dtype=np.int64)
        mask=np.array([e.attention_mask for e in encoded],dtype=np.int64)
        feeds={'input_ids':ids,'attention_mask':mask}
        if 'token_type_ids' in names:feeds['token_type_ids']=np.zeros_like(ids)
        logits=session.run(None,feeds)[0].reshape(len(encoded),-1)[:,0]
        out+=[1/(1+math.exp(-max(-60.,min(60.,float(x))))) for x in logits]
    return out
