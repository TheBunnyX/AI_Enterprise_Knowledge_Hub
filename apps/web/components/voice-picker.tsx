'use client';
import {useEffect,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {Loader2,Play,Square} from 'lucide-react';
import {api} from './api';
import {cn} from '@/lib/utils';
import { tr } from '../lib/i18n';

export type Voice={name:string;style:string;gender?:'male'|'female'};
export const DEFAULT_VOICE='Kore';

// Gemini TTS prebuilt voices: pick one, or press play to hear a short sample of each.
export function VoicePicker({value,onChange,modelId,live,notify}:{value:string;onChange:(v:string)=>void;modelId?:string;live?:boolean;notify:(s:string)=>void}){
 const voices=useQuery({queryKey:['voices'],queryFn:()=>api<Voice[]>('/voice/voices'),staleTime:Infinity});
 const [loading,setLoading]=useState('');const [playing,setPlaying]=useState('');
 const audio=useRef<HTMLAudioElement|null>(null);
 useEffect(()=>()=>{audio.current?.pause()},[]);
 const current=voices.data?.some(v=>v.name===value)?value:DEFAULT_VOICE;
 const stop=()=>{audio.current?.pause();audio.current=null;setPlaying('')};
 const play=async(name:string)=>{
  if(playing===name){stop();return}
  stop();setLoading(name);
  try{
   const r=await fetch('/api/voice/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({voice:name,model_id:modelId||'',live:!!live})});
   if(!r.ok)throw new Error((await r.json().catch(()=>({}))).detail||tr('เล่นตัวอย่างเสียงไม่สำเร็จ'));
   const url=URL.createObjectURL(await r.blob());const a=new Audio(url);audio.current=a;
   const end=()=>{URL.revokeObjectURL(url);if(audio.current===a){audio.current=null;setPlaying('')}};
   a.onended=end;a.onerror=end;setPlaying(name);await a.play();
  }catch(e){setPlaying('');notify((e as Error).message)}finally{setLoading('')}
 };
 return <div role="radiogroup" aria-label={tr('เลือกเสียง')} className="grid grid-cols-[repeat(auto-fill,minmax(190px,1fr))] gap-2">
  {voices.data?.map(v=>{const on=v.name===current;
   return <div key={v.name} role="radio" aria-checked={on} tabIndex={0} onClick={()=>onChange(v.name)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onChange(v.name)}}}
    className={cn('flex cursor-pointer items-center gap-2 rounded-full border bg-background py-1 pl-4 pr-1 text-sm transition-colors hover:bg-accent',on?'border-primary bg-accent text-primary':'border-input')}>
    <span className="min-w-0 flex-1 truncate"><strong className="font-medium">{v.name}</strong> <small className="text-muted-foreground">{v.gender==='female'?tr('หญิง'):tr('ชาย')} · {v.style}</small></span>
    <button type="button" aria-label={tr('ฟังตัวอย่างเสียง {v1}',{v1:v.name})} onClick={e=>{e.stopPropagation();play(v.name)}} className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90">
     {loading===v.name?<Loader2 className="size-4 animate-spin"/>:playing===v.name?<Square className="size-3.5 fill-current"/>:<Play className="size-3.5 fill-current"/>}
    </button>
   </div>})}
 </div>;
}
