"""Web search tool for chat. Runs on our server (DuckDuckGo, no API key), so it works with any model.
Queries leave the organisation; results are untrusted text."""
import asyncio,json
from starlette.concurrency import run_in_threadpool

TOOL={'type':'function','function':{'name':'web_search','description':'Search the web for current or external facts. Use only when the answer needs information that is recent or not already known. Returns titles, URLs and snippets.','parameters':{'type':'object','properties':{'query':{'type':'string','description':'Search query, in the language most likely to find the answer'}},'required':['query']}}}
MAX_SEARCHES=3

def _search(query,n=5):
    from ddgs import DDGS
    out=[]
    for r in (DDGS(timeout=10).text(query[:300],max_results=n,region='th-th') or [])[:n]:
        url=r.get('href') or ''
        if url.startswith(('http://','https://')):out.append({'title':(r.get('title') or url)[:200],'url':url,'snippet':(r.get('body') or '')[:400]})
    return out

async def search(query,n=5):
    try:return await asyncio.wait_for(run_in_threadpool(_search,query,n),timeout=20)
    except Exception:return []

def sources(found,start):
    """Search hits -> source cards numbered after the document citations."""
    return [{'chunk_id':f'web:{start+i+1}','document_id':'','url':r['url'],'name':r['title'],'page':0,'snippet':r['snippet'],'number':start+i+1} for i,r in enumerate(found)]

def as_text(cards):
    return chr(10).join(f'[{c["number"]}] {c["name"]} ({c["url"]}){chr(10)}{c["snippet"]}' for c in cards) or 'ไม่พบผลการค้นหา'
