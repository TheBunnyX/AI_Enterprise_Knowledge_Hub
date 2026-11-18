"""OpenRouter model catalogue: browse models, add them, and keep prices in step with OpenRouter.

The catalogue (GET /models) is public. OpenRouter quotes USD per token as strings; the hub stores USD per 1M tokens.
Manual sync shows a preview before anything is written. Automatic sync (every 5 minutes, only when a Super Admin switched
it on) applies price changes for existing OpenRouter models without asking; it never adds, enables or disables models.
Models with variable pricing (negative / missing price) are skipped rather than set to a wrong number.
"""
import asyncio,time
from datetime import datetime,timezone
import httpx
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .database import db_session,SessionLocal
from .models import AIModel,Audit,now
from .feature_models import Setting
from .auth import admin
from . import alerts

PROVIDER='OpenRouter'
MEDIA_URLS={'image':'https://openrouter.ai/api/v1/images/models','video':'https://openrouter.ai/api/v1/videos/models'}
MEDIA_CATEGORY={'image':'Image','video':'Video'}
CATALOG_URL='https://openrouter.ai/api/v1/models'  # the one source of truth for prices; never redirected through a configured gateway URL
SYNC_KEY='openrouter_sync'
INTERVAL=300  # seconds between automatic syncs
CATALOG_TTL=60
_cache={'at':0.0,'data':[]}
_media_cache={}

def _per_million(value):
    """'0.0000005' (USD/token) -> 0.5 (USD/1M tokens); None when absent or variable (negative)."""
    try:v=float(value)
    except (TypeError,ValueError):return None
    return None if v<0 else round(v*1_000_000,6)

def normalize(item):
    p=item.get('pricing') or {}
    arch=item.get('architecture') or {}
    return {'id':item.get('id',''),'name':item.get('name') or item.get('id',''),'context_length':item.get('context_length') or 0,
            'input_price':_per_million(p.get('prompt')),'output_price':_per_million(p.get('completion')),
            'inputs':arch.get('input_modalities') or [],'outputs':arch.get('output_modalities') or [],
            'tools':'tools' in (item.get('supported_parameters') or [])}

async def fetch_catalog(force=False):
    if not force and _cache['data'] and time.time()-_cache['at']<CATALOG_TTL:return _cache['data']
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=10)) as client:
            r=await client.get(CATALOG_URL);r.raise_for_status();data=r.json().get('data') or []
    except (httpx.HTTPError,ValueError) as e:
        raise HTTPException(502,'ดึงรายการโมเดลจาก OpenRouter ไม่สำเร็จ (เซิร์ฟเวอร์ออกอินเทอร์เน็ตได้หรือไม่)') from e
    items=[normalize(x) for x in data if isinstance(x,dict) and x.get('id')]
    _cache.update(at=time.time(),data=items);return items

def _video_price(item):
    """USD per second of the cheapest tier. Skus are either USD ('duration_seconds_...') or US cents ('cents_per_video_output_second_...')."""
    out=[]
    for k,v in (item.get('pricing_skus') or {}).items():
        try:f=float(v)
        except (TypeError,ValueError):continue
        if f>0:out.append(f/100 if k.startswith('cents_') else f)
    return round(min(out),6) if out else None

async def fetch_media_catalog(kind,force=False):
    """Image/video models OpenRouter offers. Video prices come with the list; image prices need one call per model (image_price)."""
    hit=_media_cache.get(kind)
    if not force and hit and time.time()-hit[0]<CATALOG_TTL:return hit[1]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=10)) as client:
            r=await client.get(MEDIA_URLS[kind]);r.raise_for_status();data=r.json().get('data') or []
    except (httpx.HTTPError,ValueError) as e:
        raise HTTPException(502,'ดึงรายการโมเดลจาก OpenRouter ไม่สำเร็จ (เซิร์ฟเวอร์ออกอินเทอร์เน็ตได้หรือไม่)') from e
    items=[{'id':x['id'],'name':x.get('name') or x['id'],'context_length':0,'input_price':None,'output_price':_video_price(x) if kind=='video' else None,'inputs':[],'outputs':[kind],'tools':False,'kind':kind}
           for x in data if isinstance(x,dict) and x.get('id')]
    _media_cache[kind]=(time.time(),items);return items

async def image_price(client,api_id):
    """USD per generated image (cheapest endpoint), or None when OpenRouter bills it another way."""
    try:
        r=await client.get(MEDIA_URLS['image']+'/'+api_id+'/endpoints');r.raise_for_status()
        costs=[p['cost_usd'] for e in r.json().get('endpoints',[]) for p in e.get('pricing',[]) if p.get('unit')=='image' and isinstance(p.get('cost_usd'),(int,float)) and p['cost_usd']>0]
    except (httpx.HTTPError,ValueError,KeyError,TypeError):return None
    return round(min(costs),6) if costs else None

async def media_prices(db):
    """{api_id: reference price} for the image/video models already in the hub (image = USD per image, video = USD per second)."""
    have=[(m.api_id,m.category) for m in db.scalars(select(AIModel).where(AIModel.provider==PROVIDER,AIModel.category.in_(['Image','Video'])))]
    out={}
    if any(c=='Video' for _,c in have):
        for v in await fetch_media_catalog('video',force=True):out[v['id']]=v['output_price']
    images=[a for a,c in have if c=='Image']
    if images:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=10)) as client:
            for a,price in zip(images,await asyncio.gather(*(image_price(client,a) for a in images))):out[a]=price
    return out

def get_setting(db):
    s=db.scalar(select(Setting).where(Setting.key==SYNC_KEY))
    return s,dict(s.value) if s else {}

def put_setting(db,**changes):
    s,value=get_setting(db);value.update(changes)
    if s:s.value=value
    else:db.add(Setting(key=SYNC_KEY,value=value))
    db.commit();return value

def diff(db,catalog,media=None):
    """Price changes for the OpenRouter models already in the hub (no writes). LLM prices are USD per 1M tokens; image/video
    (checked only when `media` is given) are a single reference price in output_price: USD per image or per second of video."""
    by_id={c['id']:c for c in catalog};out=[]
    for m in db.scalars(select(AIModel).where(AIModel.provider==PROVIDER,AIModel.category.in_(['LLM','Image','Video'])).order_by(AIModel.name)):
        base={'id':m.id,'name':m.name,'api_id':m.api_id,'category':m.category,'unit':{'Image':'ภาพ','Video':'วินาที'}.get(m.category,''),'input_price':m.input_price,'output_price':m.output_price,'new_input':None,'new_output':None}
        if m.category!='LLM':
            if media is None:continue
            if m.api_id not in media:out.append({**base,'status':'missing'});continue
            new=media[m.api_id]
            if new is None:out.append({**base,'status':'variable'});continue
            out.append({**base,'status':'changed' if abs(new-m.output_price)>1e-9 else 'same','new_input':m.input_price,'new_output':new});continue
        c=by_id.get(m.api_id)
        if not c:out.append({**base,'status':'missing'});continue
        if c['input_price'] is None or c['output_price'] is None:out.append({**base,'status':'variable'});continue
        changed=abs(c['input_price']-m.input_price)>1e-9 or abs(c['output_price']-m.output_price)>1e-9
        out.append({**base,'status':'changed' if changed else 'same','new_input':c['input_price'],'new_output':c['output_price']})
    return out

def apply_prices(db,catalog,ids=None,media=None):
    changes=[d for d in diff(db,catalog,media) if d['status']=='changed' and (ids is None or d['id'] in ids)]
    for d in changes:
        m=db.get(AIModel,d['id']);m.input_price,m.output_price=d['new_input'],d['new_output']
    db.commit();return changes

def run_auto_sync():
    """Called by the scheduler every minute; does work only when switched on and 5 minutes have passed."""
    with SessionLocal() as db:
        _,st=get_setting(db)
        if not st.get('auto') or time.time()-st.get('last_run',0)<INTERVAL:return
        put_setting(db,last_run=time.time())  # claim the slot first so a failing fetch is not retried every minute
    try:
        with SessionLocal() as db:media=asyncio.run(media_prices(db))
        catalog=asyncio.run(fetch_catalog(force=True))
        with SessionLocal() as db:
            changes=apply_prices(db,catalog,media=media)
            put_setting(db,last_status='ok',last_at=now(),last_changed=len(changes),last_error='')
        alerts.resolve('openrouter-sync')
    except Exception as e:
        with SessionLocal() as db:put_setting(db,last_status='error',last_at=now(),last_error=str(getattr(e,'detail',e))[:200])
        alerts.publish('openrouter-sync','ซิงก์ราคา OpenRouter ไม่สำเร็จ',str(getattr(e,'detail',e))[:200])

router=APIRouter(prefix='/api/admin/openrouter')

@router.get('/catalog')
async def catalog(q:str=Query('',max_length=100),free:bool=False,kind:str=Query('llm',pattern='^(llm|image|video)$'),limit:int=Query(60,ge=1,le=200),u=Depends(admin),db:Session=Depends(db_session)):
    items=await fetch_catalog() if kind=='llm' else await fetch_media_catalog(kind)
    have={m.api_id for m in db.scalars(select(AIModel).where(AIModel.provider==PROVIDER))}
    q=q.strip().lower()
    rows=[c for c in items if (not q or q in c['id'].lower() or q in c['name'].lower()) and (not free or kind=='llm' and c['input_price']==0 and c['output_price']==0)]
    return {'total':len(rows),'kind':kind,'items':[{**c,'added':c['id'] in have} for c in rows[:limit]]}

@router.get('/sync')
async def sync_status(u=Depends(admin),db:Session=Depends(db_session)):
    _,st=get_setting(db)
    return {'auto':bool(st.get('auto')),'interval_seconds':INTERVAL,'last_at':st.get('last_at',''),'last_status':st.get('last_status',''),'last_changed':st.get('last_changed',0),'last_error':st.get('last_error','')}

class AutoInput(BaseModel):
    auto:bool

@router.put('/sync')
def set_auto(body:AutoInput,u=Depends(admin),db:Session=Depends(db_session)):
    put_setting(db,auto=body.auto,last_run=0)
    db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action='ซิงก์ราคา OpenRouter อัตโนมัติ',detail='เปิด' if body.auto else 'ปิด'));db.commit()
    return {'auto':body.auto}

@router.get('/sync/preview')
async def preview(u=Depends(admin),db:Session=Depends(db_session)):
    media=await media_prices(db);items=diff(db,await fetch_catalog(force=True),media)
    return {'items':items,'changed':sum(1 for i in items if i['status']=='changed')}

class ApplyInput(BaseModel):
    ids:list[str]|None=Field(default=None,max_length=500)  # None = every changed model

@router.post('/sync/apply')
async def apply(body:ApplyInput,u=Depends(admin),db:Session=Depends(db_session)):
    media=await media_prices(db)
    changes=apply_prices(db,await fetch_catalog(force=True),set(body.ids) if body.ids is not None else None,media)
    put_setting(db,last_status='ok',last_at=now(),last_changed=len(changes),last_error='')
    if changes:db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action='ซิงก์ราคาโมเดลจาก OpenRouter',detail=f'{len(changes)} โมเดล: '+', '.join(c['name'] for c in changes)[:200]));db.commit()
    return {'updated':len(changes),'items':changes}

class AddInput(BaseModel):
    api_id:str=Field(min_length=1,max_length=200)
    name:str|None=Field(default=None,max_length=100)
    enabled:bool=False
    kind:str=Field(default='llm',pattern='^(llm|image|video)$')

@router.post('/models',status_code=201)
async def add_from_catalog(body:AddInput,u=Depends(admin),db:Session=Depends(db_session)):
    media=body.kind!='llm'
    c=next((x for x in (await fetch_media_catalog(body.kind) if media else await fetch_catalog()) if x['id']==body.api_id),None)
    if not c:raise HTTPException(404,'ไม่พบโมเดลนี้ในรายการของ OpenRouter')
    if db.scalar(select(AIModel).where(AIModel.provider==PROVIDER,AIModel.api_id==c['id'])):raise HTTPException(409,'มีโมเดลนี้ในระบบแล้ว')
    if media:
        price=c['output_price']
        if body.kind=='image':
            async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=10)) as client:price=await image_price(client,c['id'])
        m=AIModel(name=(body.name or c['name'])[:100],provider=PROVIDER,api_id=c['id'],category=MEDIA_CATEGORY[body.kind],enabled=body.enabled,input_price=0,output_price=price or 0)
        variable=price is None
    else:
        if 'text' not in c['outputs'] and c['outputs']:raise HTTPException(422,'เพิ่มได้เฉพาะโมเดลที่ตอบเป็นข้อความ (LLM)')
        m=AIModel(name=(body.name or c['name'])[:100],provider=PROVIDER,api_id=c['id'],category='LLM',enabled=body.enabled,input_price=c['input_price'] or 0,output_price=c['output_price'] or 0)
        variable=c['input_price'] is None or c['output_price'] is None
    db.add(m);db.add(Audit(tenant_id=u.tenant_id,user_id=u.id,actor=u.name,action='เพิ่มโมเดลจาก OpenRouter',detail=m.name));db.commit()
    from .policies import allow_new_model
    allow_new_model(db,m)
    return {'id':m.id,'name':m.name,'variable_price':variable}
