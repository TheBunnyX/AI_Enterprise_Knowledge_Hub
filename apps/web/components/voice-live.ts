'use client';
import {useCallback,useEffect,useMemo,useRef} from 'react';
import { tr } from '../lib/i18n';

export type LiveOptions={modelId:string;mode:'docs'|'general';web:boolean;kb:string;voice:string;lang:string};
export type LivePhase='listening'|'hearing'|'thinking'|'speaking';
export type LiveHandlers={
  onPhase:(p:LivePhase)=>void;onLevel:(n:number)=>void;onTranscript:(role:'user'|'ai',text:string)=>void;
  onStatus:(text:string)=>void;onOutLevel?:(n:number)=>void;onSources:(items:{name:string;url?:string;page?:number}[])=>void;onError:(message:string)=>void;onClosed:()=>void;
};

// Mic worklet: resample the device rate to 16 kHz mono 16-bit PCM and post ~100 ms chunks plus a level meter.
const WORKLET=`
class Down extends AudioWorkletProcessor{
 constructor(){super();this.buf=[];this.pos=0;this.sum=0;this.n=0}
 process(inputs){
  const ch=inputs[0]&&inputs[0][0];if(!ch)return true;
  const step=sampleRate/16000;
  for(let i=0;i<ch.length;i++){this.sum+=ch[i]*ch[i];this.n++}
  for(;this.pos<ch.length;this.pos+=step){
   const i=Math.floor(this.pos),f=this.pos-i,a=ch[i],b=i+1<ch.length?ch[i+1]:a;
   this.buf.push(Math.max(-1,Math.min(1,a+(b-a)*f)))
  }
  this.pos-=ch.length;
  if(this.buf.length>=1600){
   const out=new Int16Array(this.buf.length);for(let i=0;i<out.length;i++)out[i]=this.buf[i]*32767;
   this.buf=[];this.port.postMessage({pcm:out.buffer,level:Math.sqrt(this.sum/Math.max(1,this.n))},[out.buffer]);this.sum=0;this.n=0
  }
  return true
 }
}
registerProcessor('down',Down);`;

/** Streaming voice session against the server's Gemini Live relay (/api/voice/live). */
export function useLiveVoice(handlers:LiveHandlers){
 const h=useRef(handlers);h.current=handlers;
 const s=useRef<{ws:WebSocket|null;stream:MediaStream|null;ctx:AudioContext|null;node:AudioWorkletNode|null;out:AnalyserNode|null;raf:number;sources:Set<AudioBufferSourceNode>;next:number;turnDone:boolean;speaking:boolean}>({ws:null,stream:null,ctx:null,node:null,out:null,raf:0,sources:new Set(),next:0,turnDone:false,speaking:false});

 const halt=useCallback(()=>{ // drop queued model audio (user interrupted, or session ended)
  const e=s.current;e.sources.forEach(x=>{x.onended=null;try{x.stop()}catch{}});e.sources.clear();e.next=0;e.speaking=false;
 },[]);

 const stop=useCallback(()=>{
  const e=s.current;halt();
  const ws=e.ws;e.ws=null;
  if(ws&&ws.readyState===WebSocket.OPEN){try{ws.send(JSON.stringify({type:'stop'}))}catch{}}
  ws?.close();
  cancelAnimationFrame(e.raf);e.out=null;h.current.onOutLevel?.(0);
  e.node?.port.close();e.node?.disconnect();e.node=null;
  e.stream?.getTracks().forEach(t=>t.stop());e.stream=null;
  void e.ctx?.close();e.ctx=null;
  h.current.onLevel(0);
 },[halt]);

 useEffect(()=>stop,[stop]);

 const play=useCallback((buf:ArrayBuffer)=>{
  const e=s.current;const ctx=e.ctx;if(!ctx)return;
  const pcm=new Int16Array(buf.slice(0,buf.byteLength-(buf.byteLength%2)));if(!pcm.length)return;
  const audio=ctx.createBuffer(1,pcm.length,24000);const ch=audio.getChannelData(0);
  for(let i=0;i<pcm.length;i++)ch[i]=pcm[i]/32768;
  const src=ctx.createBufferSource();src.buffer=audio;
  if(!e.out){ // measure the AI's voice so the orb can move with it
   const an=ctx.createAnalyser();an.fftSize=512;an.connect(ctx.destination);e.out=an;
   const data=new Uint8Array(an.fftSize);
   const tick=()=>{if(e.out!==an)return;an.getByteTimeDomainData(data);let sum=0;for(let i=0;i<data.length;i++){const v=(data[i]-128)/128;sum+=v*v}
    h.current.onOutLevel?.(Math.min(1,Math.sqrt(sum/data.length)*5));e.raf=requestAnimationFrame(tick)};
   e.raf=requestAnimationFrame(tick)
  }
  src.connect(e.out);
  e.next=Math.max(e.next,ctx.currentTime+0.04);src.start(e.next);e.next+=audio.duration;
  e.sources.add(src);
  src.onended=()=>{e.sources.delete(src);if(!e.sources.size&&e.turnDone){e.speaking=false;e.turnDone=false;h.current.onPhase('listening')}};
  if(!e.speaking){e.speaking=true;e.turnDone=false;h.current.onPhase('speaking')}
 },[]);

 /** Resolves true once the session is ready (microphone open, server and Google connected). */
 const start=useCallback(async(o:LiveOptions):Promise<boolean>=>{
  if(!navigator.mediaDevices?.getUserMedia||typeof AudioWorkletNode==='undefined'){h.current.onError(tr('เบราว์เซอร์นี้ไม่รองรับการสตรีมเสียง'));return false}
  const e=s.current;stop();
  try{
   e.stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
  }catch{h.current.onError(tr('ไม่สามารถใช้ไมโครโฟนได้ กรุณาอนุญาตการเข้าถึงไมโครโฟนในเบราว์เซอร์'));return false}
  const ctx=new AudioContext();e.ctx=ctx;
  const url=URL.createObjectURL(new Blob([WORKLET],{type:'application/javascript'}));
  try{await ctx.audioWorklet.addModule(url)}finally{URL.revokeObjectURL(url)}
  const q=new URLSearchParams({model_id:o.modelId,mode:o.mode,web:o.web?'1':'0',kb:o.kb,voice:o.voice,lang:o.lang});
  const ws=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/voice/live?${q}`);ws.binaryType='arraybuffer';e.ws=ws;
  return await new Promise<boolean>(resolve=>{
   let ready=false;
   ws.onmessage=ev=>{
    if(typeof ev.data!=='string'){play(ev.data as ArrayBuffer);return}
    const d=JSON.parse(ev.data);
    if(d.type==='ready'){
     ready=true;
     const node=new AudioWorkletNode(ctx,'down');e.node=node;
     ctx.createMediaStreamSource(e.stream!).connect(node);
     node.port.onmessage=m=>{
      h.current.onLevel(Math.min(1,m.data.level*6));
      if(ws.readyState===WebSocket.OPEN)ws.send(m.data.pcm);
     };
     h.current.onPhase('listening');resolve(true);
    }
    else if(d.type==='transcript'){
     if(d.role==='user'&&!e.speaking)h.current.onPhase('hearing');
     h.current.onTranscript(d.role,d.text);
    }
    else if(d.type==='tool'){h.current.onPhase('thinking');h.current.onStatus(d.text)}
    else if(d.type==='sources')h.current.onSources(d.items||[]);
    else if(d.type==='interrupted'){halt();h.current.onPhase('listening')}
    else if(d.type==='turn'){e.turnDone=true;if(!e.sources.size){e.speaking=false;h.current.onPhase('listening')}}
    else if(d.type==='status')h.current.onStatus(d.text);
    else if(d.type==='error'){h.current.onError(d.message);if(!ready)resolve(false)}
   };
   ws.onclose=()=>{if(s.current.ws===ws){s.current.ws=null;stop();h.current.onClosed()}if(!ready)resolve(false)};
   ws.onerror=()=>{if(!ready)h.current.onError(tr('เชื่อมต่อเสียงสดไม่สำเร็จ'))};
  });
 },[halt,play,stop]);

 return useMemo(()=>({start,stop}),[start,stop]);
}
