"""Persistent asynchronous media adapters using LiteLLM/OpenAI-compatible APIs."""
import base64, json, os, time
from urllib.parse import quote
import httpx
from sqlalchemy import select
from .database import SessionLocal
from .models import AIModel, User, Usage, Audit, Organization, now
from .feature_models import GenerationJob
from . import storage, gateway

MAX_OUTPUT=80*1024*1024
def public_job(j):
    return {k:getattr(j,k) for k in ('id','kind','model_id','prompt','status','progress','error','output_type','output_text','created_at','updated_at')}|{'cost':j.cost if j.cost_known else None,'output_url':f'/api/media/{j.id}/content' if j.output_key and j.status=='completed' else None}

def update(id,**values):
    with SessionLocal() as db:
        j=db.get(GenerationJob,id)
        if not j or j.status=='cancelled':return False
        for k,v in values.items():setattr(j,k,v)
        j.updated_at=now();db.commit();return True

def remote_file(client,url,headers=None):
    with client.stream('GET',url,headers=headers) as r:
        r.raise_for_status();data=bytearray()
        for part in r.iter_bytes():
            data.extend(part)
            if len(data)>MAX_OUTPUT:raise ValueError('ผลลัพธ์มีขนาดใหญ่เกิน 80 MB')
        return bytes(data),r.headers.get('content-type','application/octet-stream')

def _nearest(value,choices):
    return min(choices,key=lambda c:abs(c-value)) if choices else value

def openrouter_video_body(client,url,api_id,prompt,options,input_key='',input_name=''):
    """OpenRouter takes `duration` (int) and `size` and rejects values the model does not list, so snap both to /videos/models."""
    body={'model':api_id,'prompt':prompt}
    try:
        info=next((m for m in client.get(url+'/videos/models').json().get('data',[]) if m.get('id')==api_id),{})
    except (httpx.HTTPError,ValueError):info={}
    body['duration']=int(_nearest(int(options.get('seconds',8)),info.get('supported_durations') or []))
    sizes=info.get('supported_sizes') or []
    size=options.get('size','1280x720')
    if options.get('aspect_ratio') in (info.get('supported_aspect_ratios') or []) and options.get('resolution') in (info.get('supported_resolutions') or []):
        body['aspect_ratio']=options['aspect_ratio'];body['resolution']=options['resolution']
    elif sizes:
        w=lambda s:int(s.split('x')[0])
        body['size']=size if size in sizes else min(sizes,key=lambda s:abs(w(s)-w(size)))
    else:body['size']=size
    if input_key:
        mime={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp'}.get(input_name.rsplit('.',1)[-1].lower(),'image/png')
        body['frame_images']=[{'type':'image_url','image_url':{'url':f'data:{mime};base64,'+base64.b64encode(storage.get(input_key)).decode()},'frame_type':'first_frame'}]
    return body

_options_cache={}

def model_options(client,url,provider,kind,api_id):
    """What the model accepts, read from OpenRouter's discovery API (cached 5 min). Empty dict = unknown, so the UI offers generic choices."""
    if provider!='OpenRouter' or kind not in ('image','video'):return {}
    hit=_options_cache.get((kind,api_id))
    if hit and time.time()-hit[0]<300:return hit[1]
    try:
        data=client.get(url+('/images/models' if kind=='image' else '/videos/models')).json().get('data',[])
    except (httpx.HTTPError,ValueError):return {}
    for m in data:
        p=m.get('supported_parameters') or {}
        _options_cache[(kind,m.get('id'))]=(time.time(),{
            'aspect_ratios':list((p.get('aspect_ratio') or {}).get('values') or m.get('supported_aspect_ratios') or []),
            'resolutions':list((p.get('resolution') or {}).get('values') or m.get('supported_resolutions') or []),
            'durations':list(m.get('supported_durations') or []),
            'accepts_image':bool((p.get('input_references') or {}).get('max')) if kind=='image' else bool(m.get('supported_frame_images')),
            'max_images':(p.get('input_references') or {}).get('max') if kind=='image' else len(m.get('supported_frame_images') or []),
            'requires_image':kind=='video' and image_only(m)})
    return _options_cache.get((kind,api_id),(0,{}))[1]

def image_only(m):
    """Image-to-video models (e.g. TBC mischief 1) reject a request without a first frame. OpenRouter has no flag for it, so read the description."""
    d=(m.get('description') or '').lower().replace('-',' ')
    return bool(m.get('supported_frame_images')) and 'image to video' in d and 'text to video' not in d

LIMIT_KEYS={'aspect_ratios':'aspect_ratios','resolutions':'resolutions','durations':'durations'}

def apply_limits(options,limits):
    """Narrow what a model offers to what the administrator allows. An empty or missing list means no restriction, and a restriction that
    matches nothing the model offers (the catalogue changed) is ignored rather than leaving users with no choice at all."""
    out=dict(options)
    for key in LIMIT_KEYS:
        allowed=[str(v) for v in (limits or {}).get(key) or []]
        if allowed and out.get(key):
            kept=[v for v in out[key] if str(v) in allowed]
            if kept:out[key]=kept
    return out

def check_limits(options,limits):
    """Server-side check of a job request: raises ValueError for a value the administrator did not allow."""
    for opt,key in (('resolution','resolutions'),('aspect_ratio','aspect_ratios'),('seconds','durations')):
        allowed=[str(v) for v in (limits or {}).get(key) or []]
        if allowed and opt in options and str(options[opt]) not in allowed:raise ValueError(opt)

def _ratio_value(text):
    try:
        a,b=text.replace('x',':').split(':');return int(a)/int(b)
    except (ValueError,ZeroDivisionError):return None

def openrouter_image_body(client,url,api_id,prompt,options,input_key='',input_name=''):
    """OpenRouter rejects parameters a model does not list, so send only what /images/models says this model accepts."""
    body={'model':api_id,'prompt':prompt,'n':1}
    try:
        params=next((m for m in client.get(url+'/images/models').json().get('data',[]) if m.get('id')==api_id),{}).get('supported_parameters') or {}
    except (httpx.HTTPError,ValueError):params={}
    wanted=_ratio_value(options.get('size','1024x1024'));ratios=[v for v in (params.get('aspect_ratio') or {}).get('values',[]) if _ratio_value(v)]
    if options.get('aspect_ratio') in (params.get('aspect_ratio') or {}).get('values',[]):body['aspect_ratio']=options['aspect_ratio']
    elif wanted and ratios:body['aspect_ratio']=min(ratios,key=lambda v:abs(_ratio_value(v)-wanted))
    if options.get('resolution') in (params.get('resolution') or {}).get('values',[]):body['resolution']=options['resolution']
    if input_key:
        if params and not (params.get('input_references') or {}).get('max'):raise ValueError('โมเดลนี้ไม่รองรับภาพต้นฉบับ')
        mime={'png':'image/png','jpg':'image/jpeg','jpeg':'image/jpeg','webp':'image/webp'}.get(input_name.rsplit('.',1)[-1].lower(),'image/png')
        body['input_references']=[{'type':'image_url','image_url':{'url':f'data:{mime};base64,'+base64.b64encode(storage.get(input_key)).decode()}}]
    return body

def run_job(id):
    with SessionLocal() as db:
        j=db.scalar(select(GenerationJob).where(GenerationJob.id==id).with_for_update())
        if not j or j.status not in ('queued','retrying'):return
        user=db.get(User,j.user_id);model=db.get(AIModel,j.model_id)
        from .policies import choose_model
        try:
            if not user or not user.active or not model or db.get(Organization,j.tenant_id).status!='active':raise ValueError('Account unavailable')
            choose_model(db,user,model.category,model.id)
            check_limits(j.options or {},model.media_limits)  # a retry must obey limits the administrator tightened after the job was created
        except Exception:
            j.status='failed';j.error='สิทธิ์ใช้งานโมเดลเปลี่ยนไป';db.commit();return
        j.status='processing';j.progress=10;j.error='';j.updated_at=now();db.commit()
        kind,prompt,options,input_key,input_name,tenant,user_id,api_id,model_name,provider_id,provider=j.kind,j.prompt,j.options,j.input_key,j.input_name,j.tenant_id,j.user_id,model.api_id,model.name,j.provider_job_id,model.provider
    try:
        url,key=gateway.configuration(provider=provider);r=None
        if not url:raise ValueError('ยังไม่ได้ตั้งค่า Gateway')
        headers=gateway.headers(key);output=b'';output_type='';text='';cost=None
        with httpx.Client(timeout=httpx.Timeout(180,connect=15),headers=headers,follow_redirects=False) as client:
            if kind=='image' and provider=='OpenRouter':
                # OpenRouter's own Image API (not /images/generations): aspect_ratio instead of size, input_references for edits.
                body=openrouter_image_body(client,url,api_id,prompt,options,input_key,input_name)
                r=client.post(url+'/images',json=body);r.raise_for_status();payload=r.json();item=(payload.get('data') or [{}])[0]
                if not item.get('b64_json'):raise ValueError('ไม่พบข้อมูลรูปภาพในผลลัพธ์')
                output=base64.b64decode(item['b64_json'],validate=True);output_type=item.get('media_type') or 'image/png'
                if output_type not in ('image/png','image/jpeg','image/webp'):raise ValueError('รูปแบบภาพจากผู้ให้บริการไม่รองรับ')
                c=(payload.get('usage') or {}).get('cost')
                if isinstance(c,(int,float)) and c>=0:cost=float(c)
            elif kind=='image':
                r=client.post(url+'/images/generations',json={'model':api_id,'prompt':prompt,'n':1,'size':options.get('size','1024x1024')})
                r.raise_for_status();item=r.json()['data'][0]
                if item.get('b64_json'):
                    output=base64.b64decode(item['b64_json'],validate=True);output_type='image/png'
                elif item.get('url'):
                    # URL hosts must be explicitly approved; never follow redirects or send the gateway key.
                    from urllib.parse import urlparse
                    target=urlparse(item['url'])
                    allowed={h.strip() for h in os.getenv('MEDIA_DOWNLOAD_HOSTS','').split(',') if h.strip()}
                    if target.scheme!='https' or target.hostname not in allowed or target.username:raise ValueError('ผู้ให้บริการส่ง URL รูปภาพ กรุณาอนุญาต host ผ่าน MEDIA_DOWNLOAD_HOSTS หรือใช้โมเดลที่ส่ง base64')
                    with httpx.Client(timeout=60,follow_redirects=False) as download:output,output_type=remote_file(download,item['url'])
                    if output_type.split(';')[0] not in ('image/png','image/jpeg','image/webp','image/gif'):raise ValueError('รูปแบบภาพจากผู้ให้บริการไม่รองรับ')
                else:raise ValueError('ไม่พบข้อมูลรูปภาพในผลลัพธ์')
            elif kind=='tts' and provider=='Google AI':
                from . import google_audio
                output,output_type=google_audio.speak(google_audio.base_url(url),key,api_id,prompt,options.get('voice',''))
            elif kind=='stt' and provider=='Google AI':
                from . import google_audio
                text=google_audio.transcribe(google_audio.base_url(url),key,api_id,storage.get(input_key),google_audio.audio_mime(input_name),options.get('language','th'));output=text.encode();output_type='text/plain; charset=utf-8'
            elif kind=='tts':
                r=client.post(url+'/audio/speech',json={'model':api_id,'input':prompt,'voice':options.get('voice','alloy'),'speed':options.get('speed',1),'response_format':'mp3'})
                r.raise_for_status();output=r.content;output_type='audio/mpeg'
            elif kind=='stt':
                r=client.post(url+'/audio/transcriptions',data={'model':api_id},files={'file':(input_name,storage.get(input_key),'application/octet-stream')})
                r.raise_for_status();text=r.json()['text'];output=text.encode();output_type='text/plain; charset=utf-8'
            elif kind=='video':
                if not provider_id:
                    if provider=='OpenRouter':body=openrouter_video_body(client,url,api_id,prompt,options,input_key,input_name)
                    else:body={'model':api_id,'prompt':prompt,'seconds':str(options.get('seconds',8)),'size':options.get('size','1280x720')}
                    r=client.post(url+'/videos',json=body);r.raise_for_status();provider_id=r.json()['id']
                    if not update(id,provider_job_id=provider_id,progress=15):return
                for _ in range(180):
                    with SessionLocal() as db:
                        if db.get(GenerationJob,id).status=='cancelled':return
                    r=client.get(url+'/videos/'+quote(provider_id,safe=''));r.raise_for_status();payload=r.json()
                    if payload['status']=='completed':
                        c=(payload.get('usage') or {}).get('cost')
                        if isinstance(c,(int,float)) and c>=0:cost=float(c)
                        break
                    if payload['status'] in ('failed','cancelled'):raise ValueError('ผู้ให้บริการไม่สามารถสร้างวิดีโอได้')
                    update(id,progress=min(90,max(15,int(payload.get('progress',15)))));time.sleep(5)
                else:raise ValueError('รอวิดีโอนานเกิน 15 นาที สามารถตรวจสถานะต่อด้วยปุ่มลองใหม่')
                output,output_type=remote_file(client,url+'/videos/'+quote(provider_id,safe='')+'/content')
                output_type='video/mp4'
            else:raise ValueError('ชนิดงานไม่ถูกต้อง')
            raw_cost=r.headers.get('x-litellm-response-cost') if r is not None else None
            if raw_cost is not None:
                try:cost=max(0,float(raw_cost))
                except ValueError:pass
        if len(output)>MAX_OUTPUT or not output:raise ValueError('ผลลัพธ์ว่างหรือมีขนาดเกินกำหนด')
        key=f'{tenant}/media/{id}'
        with SessionLocal() as db:
            j=db.get(GenerationJob,id)
            if not j or j.status=='cancelled':return
            storage.put(key,output)
            j.output_key=key;j.output_type=output_type;j.output_text=text;j.status='completed';j.progress=100;j.updated_at=now();j.cost=cost or 0;j.cost_known=cost is not None
            db.add(Usage(tenant_id=tenant,user_id=user_id,model=f'{kind} · {model_name}',cost=cost or 0,estimated=cost is None))
            db.add(Audit(tenant_id=tenant,user_id=user_id,actor=user.name,action='สร้างสื่อสำเร็จ',detail=kind));db.commit()
    except Exception:
        # Do not return provider response bodies: they can contain secrets or upstream request context.
        import logging
        logging.getLogger(__name__).warning('Media job %s failed',id)
        update(id,status='failed',error='สร้างสื่อไม่สำเร็จ ตรวจโมเดล API key รูปแบบไฟล์ และความพร้อมของ Gateway แล้วลองใหม่')
