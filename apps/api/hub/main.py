import os, time,asyncio
from .clientip import client_ip, current_ip
from contextlib import asynccontextmanager
from collections import defaultdict, deque
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .database import Base, engine
from .routes import router
from .seed import seed
from .feature_routes import router as feature_router
from .ops_routes import router as ops_router
from .team_routes import router as team_router
from .savings import router as savings_router
from .voice_routes import router as voice_router
from .live import router as live_router
from .skills import router as skills_router
from .generated import router as files_router
from .openrouter_sync import router as openrouter_router
from .sync_routes import router as sync_router
from . import agent_store, sync_models  # register the tables of paused agent runs and sync sources  # registers the tables of paused agent runs

@asynccontextmanager
async def lifespan(app):
    if os.getenv('APP_ENV')!='production': Base.metadata.create_all(engine)
    seed()
    try:
        from .cleanup import run as cleanup
        await asyncio.to_thread(cleanup)  # expired sessions, stale chat attachments, expired generated files
    except Exception:pass  # housekeeping must never keep the API from starting
    monitor=None
    if os.getenv('CELERY_BROKER_URL'):
        async def monitor_services():
            from .monitoring import probe
            from .jobs import maintenance
            while True:
                try:
                    try:paused=await asyncio.to_thread(maintenance)
                    except Exception:paused=False
                    if not paused:await asyncio.to_thread(probe)
                except Exception:pass
                await asyncio.sleep(60)
        monitor=asyncio.create_task(monitor_services())
    try:yield
    finally:
        if monitor:
            monitor.cancel()
            try:await monitor
            except asyncio.CancelledError:pass

app=FastAPI(title='AI Knowledge Hub',version='0.1.0',lifespan=lifespan)
windows=defaultdict(deque)
@app.middleware('http')
async def security(request:Request,call_next):
    ip=client_ip(request.headers,request.client.host if request.client else '');current_ip.set(ip)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        if os.getenv('CELERY_BROKER_URL'):
            try:
                from .jobs import maintenance
                if maintenance():return JSONResponse({'detail':'ระบบกำลังกู้คืนข้อมูล กรุณารอจนเสร็จแล้วเข้าสู่ระบบใหม่'},503)
            except Exception:return JSONResponse({'detail':'บริการคิวไม่พร้อมใช้งาน ยังไม่รับคำขอแก้ไขข้อมูล'},503)
        origin=request.headers.get('origin')
        allowed=os.getenv('WEB_ORIGIN','http://localhost:3009').split(',')+['http://127.0.0.1:3009']
        if origin and origin not in allowed: return JSONResponse({'detail':'Origin not allowed'},403)
        if request.headers.get('sec-fetch-site')=='cross-site': return JSONResponse({'detail':'Cross-site request denied'},403)
        if request.url.path in ('/api/auth/login',):
            key=ip or 'unknown'; q=windows[key]; now=time.monotonic()
            while q and q[0]<now-60: q.popleft()
            if len(q)>=20: return JSONResponse({'detail':'กรุณารอ 1 นาทีก่อนลองอีกครั้ง'},429)
            q.append(now)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='same-origin'
    return response

app.include_router(router)

app.include_router(feature_router)

app.include_router(ops_router)

app.include_router(team_router)
app.include_router(savings_router)
app.include_router(voice_router)
app.include_router(live_router)
app.include_router(skills_router)
app.include_router(files_router)
app.include_router(openrouter_router)
app.include_router(sync_router)
