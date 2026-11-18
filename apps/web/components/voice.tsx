'use client';
import { Sel } from './ui/sel';
import {useCallback,useEffect,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Mic,PhoneOff,Volume2,Loader2,Hand,Globe,FileSearch,MessagesSquare,Languages} from 'lucide-react';
import {cn} from '@/lib/utils';
import { tr } from '../lib/i18n';
import {api,type KB,type Model} from './api';
import {Button} from './ui/button';
import {H1} from './page-title';
import {VoicePicker,DEFAULT_VOICE} from './voice-picker';
import {useLiveVoice} from './voice-live';
import {VoiceOrb} from './voice-orb';

type Notify=(s:string)=>void;
type Phase='idle'|'listening'|'hearing'|'thinking'|'speaking';
type Turn={role:'user'|'assistant';text:string};
const liveKind=(apiId=''):'translate'|'transcribe'|'agent'=>apiId.includes('translate')?'translate':apiId.includes('transcribe')?'transcribe':'agent';

/** Remove citation markers and markdown so the text reads naturally when spoken. */
export function cleanSpoken(text:string){return text.replace(/\[\d+\]/g,'').replace(/[*_`#>|]/g,'').replace(/\s+/g,' ').trim()}
/** Cut streaming text into sentences that can be sent to text-to-speech as soon as they are complete. */
export function splitSpeech(buffer:string,flush=false){
 const out:string[]=[];let rest=buffer;
 for(;;){
  const m=/^([\s\S]{8,}?[.!?。]\s|[\s\S]{8,}?\n|[\s\S]{40,}?\s)/.exec(rest);
  if(!m)break;
  const s=cleanSpoken(m[1]);if(s)out.push(s.slice(0,590));
  rest=rest.slice(m[1].length);
 }
 if(flush){const s=cleanSpoken(rest);if(s)out.push(s.slice(0,590));rest=''}
 return {sentences:out,rest};
}

const THRESHOLD=0.04,SILENCE_MS=900,MIN_SPEECH_MS=350,BARGE_MS=250,START_MS=120;

type Engine={on:boolean;phase:Phase;conv:string|null;kb:string;docs:boolean;web:boolean;stream:MediaStream|null;ctx:AudioContext|null;an:AnalyserNode|null;raf:number;rec:MediaRecorder|null;chunks:Blob[];speechStart:number;lastVoice:number;loud:number;abort:AbortController|null;audio:HTMLAudioElement|null;queue:Promise<string|null>[];playing:boolean;gen:number};

export function VoicePage({kbs,notify}:{kbs:KB[];notify:Notify}){
 const models=useQuery({queryKey:['models'],queryFn:()=>api<Model[]>('/models')});
 const [kb,setKb]=useState('');const [docs,setDocs]=useState(true);const [web,setWeb]=useState(false);const [status,setStatus]=useState('');const [phase,setPhase]=useState<Phase>('idle');const [turns,setTurns]=useState<Turn[]>([]);const [level,setLevel]=useState(0);const [on,setOn]=useState(false);
 const [voice,setVoice]=useState(DEFAULT_VOICE);const voiceRef=useRef('alloy');
 useEffect(()=>{try{const v=localStorage.getItem('hub.voice');if(v)setVoice(v)}catch{}},[]);
 const pickVoice=(v:string)=>{setVoice(v);try{localStorage.setItem('hub.voice',v)}catch{}};
 const googleTts=!!models.data?.some(m=>m.enabled&&m.category==='TTS'&&m.provider==='Google AI'&&m.configured);
 voiceRef.current=googleTts?voice:'alloy';
 const ready=(c:string)=>!!models.data?.some(m=>m.enabled&&m.category===c);
 const webOk=!!models.data?.some(m=>m.enabled&&m.category==='LLM'&&m.configured);const savingsStatus=useQuery({queryKey:['savings-status'],queryFn:()=>api<{web_search?:'off'|'ask'|'always'}>('/savings/status')});const webAllowed=savingsStatus.data?.web_search!=='off';
 const liveModels=(models.data||[]).filter(m=>m.category==='Live'&&m.enabled&&m.configured);
 const langs=useQuery({queryKey:['voice-languages'],queryFn:()=>api<{code:string;name:string}[]>('/voice/languages'),staleTime:Infinity});
 const LANGS:[string,string][]=(langs.data||[{code:'th',name:tr('ไทย')},{code:'en',name:tr('อังกฤษ')}]).map(l=>[l.code,l.name]);
 const [engine,setEngine]=useState('');const [lang,setLang]=useState('en');
 useEffect(()=>{if(LANGS.length&&!LANGS.some(([c])=>c===lang))setLang(LANGS[0][0])},[langs.data]); // eslint-disable-line react-hooks/exhaustive-deps

 useEffect(()=>{try{const v=localStorage.getItem('hub.voice.engine');if(v)setEngine(v);const l=localStorage.getItem('hub.voice.lang');if(l)setLang(l)}catch{}},[]);
 useEffect(()=>{ // always a live model: keep the stored choice if still available, else prefer the standard live agent
  if(!liveModels.length||liveModels.some(m=>m.id===engine))return;
  const agents=liveModels.filter(x=>liveKind(x.api_id)==='agent');const m=agents.find(x=>x.api_id==='gemini-3.8-live')||agents.find(x=>!x.api_id.includes('thinking'))||agents[0]||liveModels[0];setEngine(m.id)
 },[liveModels.length,engine]); // eslint-disable-line react-hooks/exhaustive-deps
 const liveModel=liveModels.find(m=>m.id===engine);const live=!!liveModel;const kind=liveKind(liveModel?.api_id);const streamKind=useRef(kind);streamKind.current=kind;
 const pickEngine=(v:string)=>{setEngine(v);try{localStorage.setItem('hub.voice.engine',v)}catch{}};
 const pickLang=(v:string)=>{setLang(v);try{localStorage.setItem('hub.voice.lang',v)}catch{}};
 const missing=!!models.data&&!liveModels.length;
 const box=useRef<Engine>({on:false,phase:'idle',conv:null,kb:'',docs:true,web:false,stream:null,ctx:null,an:null,raf:0,rec:null,chunks:[],speechStart:0,lastVoice:0,loud:0,abort:null,audio:null,queue:[],playing:false,gen:0});
 box.current.kb=kb;box.current.docs=docs;box.current.web=web&&webOk;
 const setP=useCallback((p:Phase)=>{box.current.phase=p;setPhase(p)},[]);

 const outLevel=useRef(0);
 const sess=useLiveVoice({
  onPhase:p=>{if(p!=='thinking')setStatus('');setP(p)},onLevel:setLevel,onOutLevel:v=>{outLevel.current=v},onStatus:setStatus,onSources:()=>{},onError:m=>notify(m),
  onClosed:()=>{setOn(false);setP('idle');setLevel(0)},
  onTranscript:(role,text)=>setTurns(t=>{
   const r=role==='user'?'user':'assistant';
   if(streamKind.current!=='agent'){ // translation / transcription: one running column per side
    const i=t.findIndex(x=>x.role===r);return i<0?[...t,{role:r,text}]:t.map((x,k)=>k===i?{...x,text:x.text+text}:x)}
   const last=t[t.length-1];return last&&last.role===r?[...t.slice(0,-1),{...last,text:last.text+text}]:[...t,{role:r,text}]}),
 });
 const stopSpeaking=useCallback(()=>{const e=box.current;e.gen++;e.abort?.abort();e.abort=null;e.queue=[];e.playing=false;if(e.audio){e.audio.pause();e.audio=null}},[]);

 const playQueue=useCallback(async(gen:number)=>{
  const e=box.current;if(e.playing)return;e.playing=true;
  while(e.queue.length&&gen===e.gen){
   const url=await e.queue.shift()!;
   if(gen!==e.gen){if(url)URL.revokeObjectURL(url);break}
   if(!url)continue;
   await new Promise<void>(done=>{const a=new Audio(url);e.audio=a;const end=()=>{URL.revokeObjectURL(url);done()};a.onended=end;a.onerror=end;a.play().catch(end)});
  }
  if(gen===e.gen){e.playing=false;e.audio=null}
 },[]);

 const speak=useCallback((text:string,gen:number)=>{
  const e=box.current;
  const p=fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,voice:voiceRef.current})})
   .then(async x=>{if(!x.ok)throw new Error((await x.json().catch(()=>({}))).detail||tr('สร้างเสียงไม่สำเร็จ'));return URL.createObjectURL(await x.blob())})
   .catch(err=>{if(gen===box.current.gen)notify((err as Error).message);return null});
  e.queue.push(p);void playQueue(gen);
 },[notify,playQueue]);

 const answer=useCallback(async(question:string)=>{
  const e=box.current;stopSpeaking();const gen=e.gen;const controller=new AbortController();e.abort=controller;setP('thinking');setStatus('');
  setTurns(t=>[...t,{role:'user',text:question},{role:'assistant',text:''}]);
  try{
   const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question,conversation_id:e.conv,knowledge_base_id:e.kb||null,document_ids:[],model_id:null,spoken:true,use_documents:e.docs,web_search:e.web}),signal:controller.signal});
   if(!res.ok||!res.body)throw new Error((await res.json().catch(()=>({}))).detail||tr('ส่งคำถามไม่สำเร็จ'));
   const reader=res.body.getReader();const dec=new TextDecoder();let buf='',pending='',started=false;
   const emit=(flush:boolean)=>{
    const s=splitSpeech(pending,flush);pending=s.rest;
    for(const x of s.sentences){if(gen!==e.gen)return;if(!started){started=true;setP('speaking');setStatus('')}speak(x,gen)}
   };
   for(;;){
    const {value,done}=await reader.read();if(done)break;
    buf+=dec.decode(value,{stream:true});const lines=buf.split('\n');buf=lines.pop()||'';
    for(const line of lines){
     if(!line.trim())continue;const ev=JSON.parse(line);
     if(ev.type==='meta')e.conv=ev.conversation_id;
     if(ev.type==='error')throw new Error(ev.message);
     if(ev.type==='status')setStatus(ev.text);
     if(ev.type==='delta'){pending+=ev.text;setTurns(t=>t.map((m,i)=>i===t.length-1?{...m,text:m.text+ev.text}:m));emit(false)}
    }
   }
   emit(true);
  }catch(err){if((err as Error).name!=='AbortError')notify((err as Error).message)}
  finally{
   if(gen===e.gen){
    const wait=async()=>{
     while(gen===e.gen&&(e.playing||e.queue.length))await new Promise(x=>setTimeout(x,150));
     if(gen===e.gen&&e.on)setP('listening');
    };
    void wait();
   }
  }
 },[speak,stopSpeaking,notify,setP]);

 const finishUtterance=useCallback(async(blob:Blob)=>{
  const e=box.current;setP('thinking');
  try{
   const f=new FormData();f.append('file',blob,'speech.webm');f.append('language','th');
   const x=await fetch('/api/voice/transcribe',{method:'POST',body:f});
   if(!x.ok)throw new Error((await x.json().catch(()=>({}))).detail||tr('ถอดเสียงไม่สำเร็จ'));
   const {text}=await x.json();
   if(!String(text).trim()){if(e.on)setP('listening');return}
   await answer(String(text).trim());
  }catch(err){notify((err as Error).message);if(e.on)setP('listening')}
 },[answer,notify,setP]);

 const startRecording=useCallback(()=>{
  const e=box.current;if(!e.stream||e.rec)return;
  const rec=new MediaRecorder(e.stream);e.chunks=[];
  rec.ondataavailable=ev=>{if(ev.data.size)e.chunks.push(ev.data)};
  rec.onstop=()=>{
   const long=Date.now()-e.speechStart>=MIN_SPEECH_MS;
   const blob=new Blob(e.chunks,{type:rec.mimeType||'audio/webm'});e.rec=null;
   if(long&&e.on)void finishUtterance(blob);else if(e.on&&e.phase==='hearing')setP('listening');
  };
  rec.start();e.rec=rec;e.speechStart=Date.now();
 },[finishUtterance,setP]);

 const tick=useRef<() => void>(() => {});
 useEffect(()=>{
  tick.current=()=>{
   const e=box.current;if(!e.an||!e.on)return;
   const data=new Uint8Array(e.an.fftSize);e.an.getByteTimeDomainData(data);
   let sum=0;for(const v of data){const d=(v-128)/128;sum+=d*d}
   const rms=Math.sqrt(sum/data.length);setLevel(Math.min(1,rms*8));
   const now=performance.now();
   if(rms>THRESHOLD){e.lastVoice=now;e.loud+=16}else e.loud=Math.max(0,e.loud-32);
   if(e.phase==='speaking'){
    // barge-in: sustained voice while the assistant talks stops it and starts a new utterance
    if(e.loud>=BARGE_MS){stopSpeaking();setP('hearing');startRecording()}
   }else if(e.phase==='listening'){
    if(e.loud>=START_MS){setP('hearing');startRecording()}
   }else if(e.phase==='hearing'&&now-e.lastVoice>SILENCE_MS){
    if(e.rec?.state==='recording')e.rec.stop();
   }
   e.raf=requestAnimationFrame(()=>tick.current());
  };
 },[stopSpeaking,startRecording,setP]);

 const startLive=async()=>{
  if(!liveModel)return;setTurns([]);setStatus('');setOn(true);setP('thinking');setStatus(tr('กำลังเชื่อมต่อ'));
  const ok=await sess.start({modelId:liveModel.id,mode:docs?'docs':'general',web:web&&webOk&&webAllowed&&kind==='agent',kb:kb,voice,lang});
  if(!ok){setOn(false);setP('idle');setStatus('')}
 };
 const start=async()=>{
  if(live){await startLive();return}
  if(!navigator.mediaDevices?.getUserMedia||typeof MediaRecorder==='undefined'){notify(tr('เบราว์เซอร์นี้ไม่รองรับการอัดเสียง'));return}
  try{
   const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
   const ctx=new AudioContext();const src=ctx.createMediaStreamSource(stream);const an=ctx.createAnalyser();an.fftSize=1024;src.connect(an);
   const e=box.current;Object.assign(e,{stream,ctx,an,on:true,loud:0,conv:null});
   setOn(true);setTurns([]);setP('listening');e.raf=requestAnimationFrame(()=>tick.current());
  }catch{notify(tr('ไม่สามารถใช้ไมโครโฟนได้ กรุณาอนุญาตการเข้าถึงไมโครโฟนในเบราว์เซอร์'))}
 };
 const stop=useCallback(()=>{
  const e=box.current;e.on=false;setOn(false);cancelAnimationFrame(e.raf);stopSpeaking();sess.stop();
  if(e.rec&&e.rec.state==='recording'){e.rec.onstop=null;e.rec.stop()}e.rec=null;
  e.stream?.getTracks().forEach(t=>t.stop());e.stream=null;void e.ctx?.close();e.ctx=null;e.an=null;setP('idle');setLevel(0);
 },[stopSpeaking,setP,sess]);
 useEffect(()=>stop,[stop]);

 const label={idle:tr('พร้อมเริ่มสนทนา'),listening:tr('กำลังฟัง… พูดได้เลย'),hearing:tr('ได้ยินเสียงคุณ…'),thinking:(status||tr('กำลังคิดคำตอบ'))+'…',speaking:tr('กำลังตอบ — พูดแทรกได้ทุกเมื่อ')}[phase];
 return <>
  <div className="page-heading"><div><H1>{tr('คุยด้วยเสียง')}</H1><p>{tr('สนทนาแบบเสียงต่อเสียงกับผู้ช่วย AI เลือกให้ตอบจากเอกสาร คุยทั่วไป หรือค้นเว็บได้ พูดแทรกระหว่างที่ AI ตอบได้')}</p></div></div>
  {missing&&<p className="error-box">{tr('ต้องเปิดใช้โมเดลหมวด Live (Google AI) และตั้งค่า API key ก่อน ผู้ดูแลตั้งค่าได้ที่หน้าโมเดล AI')}</p>}
  <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
  <section className="card padded voice-panel order-1 lg:col-start-1 lg:row-span-3 lg:row-start-1">
   <div className="voice-orb-stage"><VoiceOrb phase={phase} mic={level} out={outLevel}/></div><p className="voice-legend" aria-hidden="true"><span className="who-user">{tr('คุณพูด')}</span><span className="who-ai">{tr('AI พูด')}</span></p>
   <p className="voice-status">{label}</p>
   {on?<Button variant="outline" onClick={stop}><PhoneOff size={17}/>{tr('จบการสนทนา')}</Button>:<Button disabled={missing} onClick={start}><Mic size={17}/>{tr('เริ่มคุย')}</Button>}
   {live?<p className="muted small max-w-md">{tr('{v1} · เซสชันสูงสุด 15 นาที',{v1:kind==='translate'?tr('แปลเสียงพูดแบบเรียลไทม์ พูดต่อเนื่องได้เลย'):kind==='transcribe'?tr('ถอดเสียงพูดเป็นข้อความแบบเรียลไทม์'):tr('สตรีมเสียงสดผ่านเซิร์ฟเวอร์ของระบบ เสียงของคุณถูกส่งให้ Google (Gemini Live) พูดแทรกได้ทุกเมื่อ ค่าใช้จ่ายนับตามโควตา')})}</p>:<p className="muted small max-w-md">{tr('เสียงของคุณถูกส่งไปถอดเป็นข้อความ แล้วให้ AI ตอบตามโหมดที่เลือก (โหมดเอกสารใช้เฉพาะเอกสารที่คุณมีสิทธิ์เห็น) ค่าใช้จ่ายนับรวมในโควตารายเดือนของคุณ')}</p>}
  </section>
  <section className="card padded order-2 grid gap-3 lg:col-start-2" aria-label={tr('ตั้งค่าการสนทนา')}><h2 className="text-sm font-semibold">{tr('ตั้งค่า')}</h2>
   <div className="grid gap-2.5 [&_select]:w-full">
    {liveModels.length>0&&<Sel aria-label={tr('เลือกเอนจินเสียง')} value={engine} disabled={on} onChange={ev=>pickEngine(ev.target.value)} className="w-full">{liveModels.map(m=><option key={m.id} value={m.id}>{tr('{name} · สด',{name:m.name})}</option>)}</Sel>}
    {kind==='translate'&&live&&<Sel aria-label={tr('แปลเป็นภาษา')} value={lang} disabled={on} onChange={ev=>pickLang(ev.target.value)} className="w-full">{LANGS.map(([c,n])=><option key={c} value={c}>{tr('แปลเป็น{n}',{n})}</option>)}</Sel>}
    {(!live||kind==='agent')&&<>
    <div role="group" aria-label={tr('โหมดการตอบ')} className="grid w-full grid-cols-2 rounded-full border border-border bg-muted/40 p-0.5 text-xs">
     {([[true,tr('ตอบจากเอกสาร'),FileSearch],[false,tr('คุยทั่วไป'),MessagesSquare]] as const).map(([v,l,Icon])=><button key={l} type="button" aria-pressed={docs===v} disabled={on&&live} onClick={()=>setDocs(v)} className={cn('inline-flex items-center justify-center gap-1.5 rounded-full px-3 py-2 font-medium transition-colors',docs===v?'bg-background text-primary shadow-xs':'text-muted-foreground hover:text-foreground')}><Icon className="size-4"/>{l}</button>)}
    </div>
    <Button type="button" variant={web&&webOk?'default':'outline'} size="sm" className="h-9 w-full justify-center gap-1.5 rounded-full px-3 text-xs" aria-label={tr('ค้นเว็บ')} aria-pressed={web&&webOk&&webAllowed} disabled={!webOk||!webAllowed||(on&&live)} onClick={()=>setWeb(!web)} title={!webAllowed?tr('องค์กรปิดการค้นเว็บ'):webOk?tr('ให้ AI ค้นเว็บเองเมื่อจำเป็น (คำค้นจะถูกส่งออกนอกองค์กร)'):tr('ต้องมีโมเดล LLM ที่ไม่ใช่โหมดสาธิต')}><Globe className="size-4"/>{tr('ค้นเว็บ')}</Button>
    {docs&&<Sel aria-label={tr('เลือกคลังความรู้')} value={kb} disabled={on} onChange={ev=>setKb(ev.target.value)} className="w-full"><option value="">{tr('ทุกคลังความรู้')}</option>{kbs.map(k=><option key={k.id} value={k.id}>{k.name}</option>)}</Sel>}
    </>}
   </div>
  </section>
  {((googleTts&&!live)||(live&&kind==='agent'))&&<details className="card padded order-3 lg:col-start-2"><summary className="cursor-pointer text-sm font-medium">{tr('เสียงที่ใช้ตอบ: {voice}{v1}',{voice,v1:live&&liveModel?` · ${liveModel.name}`:''})}</summary><div className="mt-3"><VoicePicker key={live?liveModel?.id:'tts'} value={voice} onChange={pickVoice} modelId={live?liveModel?.id:undefined} live={live} notify={notify}/></div></details>}
  {turns.length>0&&<div className="card padded voice-log order-4 max-h-[40vh] overflow-y-auto lg:col-span-2 lg:col-start-1" role="log" aria-label={tr('ข้อความถอดเสียง')}>
   <p className="voice-side user" aria-hidden="true">{kind==='agent'||!live?tr('คุณ'):tr('ต้นฉบับ')}</p><p className="voice-side assistant" aria-hidden="true">{kind==='agent'||!live?'AI':tr('คำแปล')}</p>
   {turns.map((t,i)=><p key={i} className={'voice-turn '+t.role}><span className="sr-only">{kind==='agent'||!live?(t.role==='user'?tr('คุณ'):'AI'):(t.role==='user'?tr('ต้นฉบับ'):tr('คำแปล'))} </span>{t.text||'…'}</p>)}
  </div>}
  </div>
 </>
}
