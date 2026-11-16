'use client';
import {useMemo,useState} from 'react';
import {MessagesSquare,Search,Trash2} from 'lucide-react';
import {Button} from './ui/button';
import {Input} from './ui/input';
import {Checkbox} from './ui/checkbox';
import { tr, useLang, getLang, LOCALE } from '../lib/i18n';
import type {Conversation} from './api';

const DAY=86400000;
const startOfDay=(t:number)=>{const d=new Date(t);d.setHours(0,0,0,0);return d.getTime()};
function groupOf(iso:string,today:number){
 const t=startOfDay(new Date(iso).getTime());
 if(t>=today)return tr('วันนี้');if(t>=today-DAY)return tr('เมื่อวาน');if(t>=today-7*DAY)return tr('7 วันที่ผ่านมา');if(t>=today-30*DAY)return tr('30 วันที่ผ่านมา');return tr('เก่ากว่านั้น');
}
const time=(iso:string)=>new Date(iso).toLocaleString(LOCALE[getLang()],{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'});

/** Conversation history: searchable, grouped by recency, one line per chat. */
export function ChatHistory({items,onOpen,onDelete,onDeleteAll,onDeleteMany}:{items:Conversation[]|undefined;onOpen:(c:Conversation)=>void;onDelete:(c:Conversation)=>void;onDeleteAll:()=>void;onDeleteMany:(ids:string[])=>Promise<boolean>}){
 const {lang}=useLang();
 const [q,setQ]=useState('');const [picked,setPicked]=useState<string[]>([]);
 const groups=useMemo(()=>{
  const today=startOfDay(Date.now());const needle=q.trim().toLowerCase();const out=new Map<string,Conversation[]>();
  for(const c of items||[]){if(needle&&!c.title.toLowerCase().includes(needle))continue;const g=groupOf(c.created_at,today);out.set(g,[...(out.get(g)||[]),c])}
  return [...out.entries()];
 },[items,q,lang]);
 const shown=groups.flatMap(([,l])=>l.map(c=>c.id));
 const chosen=picked.filter(id=>items?.some(c=>c.id===id));const all=shown.length>0&&shown.every(id=>chosen.includes(id));
 const toggle=(id:string)=>setPicked(p=>p.includes(id)?p.filter(x=>x!==id):[...p,id]);
 const toggleAll=()=>setPicked(p=>all?p.filter(id=>!shown.includes(id)):[...new Set([...p,...shown])]);
 const removePicked=async()=>{if(await onDeleteMany(chosen))setPicked([])};
 if(!items?.length)return <div className="py-10 text-center"><p className="font-medium">{tr('ยังไม่มีการสนทนา')}</p><p className="text-sm text-muted-foreground">{tr('เริ่มถามคำถามแรกจากเอกสารของคุณ')}</p></div>;
 return <div className="grid gap-3">
  <div className="flex items-center gap-2">
   <div className="relative flex-1"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"/><Input value={q} onChange={e=>setQ(e.target.value)} placeholder={tr('ค้นหาบทสนทนา')} aria-label={tr('ค้นหาบทสนทนา')} className="h-9" style={{paddingLeft:40}}/></div>
   <Button type="button" variant="outline" size="sm" className="shrink-0 text-destructive hover:text-destructive" onClick={onDeleteAll}><Trash2 className="size-4"/>{tr('ลบทั้งหมด')}</Button>
  </div>
  <div className="flex min-h-9 items-center gap-3 rounded-lg bg-muted/50 px-2 text-sm">
   <label className="source-option flex cursor-pointer flex-row items-center gap-2 !border-0 !py-0"><Checkbox checked={all?true:chosen.length>0?'indeterminate':false} onCheckedChange={toggleAll} aria-label={tr('เลือกทั้งหมดที่แสดง')}/><span>{chosen.length>0?tr('เลือกแล้ว {v1}',{v1:chosen.length}):tr('เลือกทั้งหมด')}</span></label>
   {chosen.length>0&&<span className="ml-auto flex gap-2"><Button type="button" variant="ghost" size="sm" onClick={()=>setPicked([])}>{tr('ล้างที่เลือก')}</Button><Button type="button" variant="destructive" size="sm" onClick={removePicked}><Trash2 className="size-4"/>{tr('ลบที่เลือก ({length})',{length:chosen.length})}</Button></span>}
  </div>
  <div className="max-h-[60vh] overflow-y-auto pr-1">
   {groups.length===0&&<p className="py-8 text-center text-sm text-muted-foreground">{tr('ไม่พบบทสนทนาที่ตรงกับ “{q}”',{q})}</p>}
   {groups.map(([name,list])=><section key={name} className="mb-3"><h3 className="sticky top-0 z-10 bg-background/95 px-2 py-1 text-xs font-medium text-muted-foreground">{name} · {list.length}</h3>
    <ul>{list.map(c=><li key={c.id} className={'group flex items-center gap-1 rounded-lg pl-2 hover:bg-accent '+(chosen.includes(c.id)?'bg-accent':'')}>
     <Checkbox checked={chosen.includes(c.id)} onCheckedChange={()=>toggle(c.id)} aria-label={tr('เลือก {v1}',{v1:c.title})}/>
     <button type="button" onClick={()=>onOpen(c)} className="flex min-w-0 flex-1 items-center gap-3 rounded-lg px-2 py-2 text-left !border-0 !bg-transparent !shadow-none">
      <MessagesSquare className="size-4 shrink-0 text-muted-foreground"/><span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{c.title}</span><span className="shrink-0 text-xs text-muted-foreground">{time(c.created_at)}</span>
     </button>
     <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 text-muted-foreground opacity-60 hover:text-destructive group-hover:opacity-100" aria-label={tr('ลบ {v1}',{v1:c.title})} title={tr('ลบบทสนทนานี้')} onClick={()=>onDelete(c)}><Trash2 className="size-4"/></Button>
    </li>)}</ul></section>)}
  </div>
 </div>;
}
