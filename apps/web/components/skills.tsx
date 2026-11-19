'use client';
import {useState,type FormEvent} from 'react';
import {useRouter} from 'next/navigation';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Plus,Pencil,Trash2,Copy,MessageSquare,Users,Lock,Sparkles} from 'lucide-react';
import {api,post} from './api';
import { tr } from '../lib/i18n';
import {Button} from './ui/button';
import {Badge} from './ui/badge';
import {Input} from './ui/input';
import {Label} from './ui/label';
import {Textarea} from './ui/textarea';
import {Checkbox} from './ui/checkbox';
import {Modal,DialogFooter} from './ui/dialog';
import {useConfirm} from './ui/confirm';
import {H1} from './page-title';
import {Popover,PopoverContent,PopoverTrigger} from './ui/popover';

const ICONS=['✨','📄','📑','📝','📋','📊','📈','📉','⚖️','🏛️','🤝','🔍','🔎','🛡️','🔒','💼','💡','🎯','🧠','🤖','📚','🗂️','✅','⚠️','📌','🧾','💰','🏢','👥','🌐','📧','🗓️','⏱️','🚀','🔧'];

export type Skill={id:string;name:string;description:string;instructions:string;icon:string;use_documents:boolean;shared:boolean;uses:number;mine:boolean;owner:string};
export type SkillList={can_share:boolean;skills:Skill[]};
type Draft=Pick<Skill,'name'|'description'|'instructions'|'icon'|'use_documents'|'shared'>;
const blank:Draft={name:'',description:'',instructions:'',icon:'✨',use_documents:true,shared:false};

// One-click starting points; the user edits them before saving.
const TEMPLATES:Draft[]=[
 {icon:'📄',name:'Document review',description:'Check a document for completeness and accuracy',use_documents:true,shared:false,instructions:'You are a careful document reviewer. Review the document provided for missing sections, internal contradictions, and inconsistent numbers, dates or names. Answer under these headings: 1) Short summary 2) Problems found (give the location/page) 3) What should be fixed. If you find no problems, say so plainly.'},
 {icon:'⚖️',name:'Legal',description:'Explain legal issues from the documents available',use_documents:true,shared:false,instructions:'You are the organisation\'s legal assistant. Explain legal issues in plain language, citing only text from the documents provided. Separate clearly the facts in the documents from your own observations. End by stating that this is not formal legal advice.'},
 {icon:'🤝',name:'Contract analysis',description:'Point out obligations, risks and key terms of a contract',use_documents:true,shared:false,instructions:'Analyse the contract provided. Answer under these headings: parties and term; each side\'s duties and obligations; payment terms; penalties and cancellation terms; risks or points to negotiate, in order of importance. Cite the clause number/page every time.'},
 {icon:'📊',name:'Report summary',description:'Summarise a report into key points and recommendations',use_documents:true,shared:false,instructions:'Summarise the report provided for an executive with little time. Start with a 3-line summary, then the key numbers or findings as bullets, the risks, and what needs a decision or action next. Never add information that is not in the report.'},
];

function SkillForm({initial,canShare,onClose,onSave}:{initial:Draft;canShare:boolean;onClose:()=>void;onSave:(d:Draft)=>Promise<void>}){
 const [d,setD]=useState<Draft>(initial);const [busy,setBusy]=useState(false);const [err,setErr]=useState('');const [pick,setPick]=useState(false);
 const set=<K extends keyof Draft>(k:K,v:Draft[K])=>setD(p=>({...p,[k]:v}));
 const submit=async(e:FormEvent)=>{e.preventDefault();setBusy(true);setErr('');try{await onSave(d)}catch(x){setErr((x as Error).message)}finally{setBusy(false)}};
 return <Modal title={initial.name?tr('แก้ไขทักษะ'):tr('สร้างทักษะใหม่')} onClose={onClose} wide>
  <form onSubmit={submit} className="grid gap-4">
   <div className="grid grid-cols-[5rem_1fr] gap-3">
    <div className="grid gap-1.5"><Label htmlFor="sk-icon">{tr('ไอคอน')}</Label><Popover open={pick} onOpenChange={setPick}><PopoverTrigger asChild><Button id="sk-icon" type="button" variant="outline" aria-label={tr('เลือกไอคอน')} className="h-9 w-full justify-center rounded-full text-xl">{d.icon}</Button></PopoverTrigger><PopoverContent align="start" className="z-[200] w-72 p-2"><div role="listbox" aria-label={tr('ไอคอน')} className="grid grid-cols-7 gap-1">{ICONS.map(i=><button key={i} type="button" role="option" aria-selected={i===d.icon} aria-label={i} onClick={()=>{set('icon',i);setPick(false)}} className={'flex size-9 items-center justify-center rounded-md text-xl hover:bg-accent '+(i===d.icon?'bg-accent ring-2 ring-primary':'')}>{i}</button>)}</div></PopoverContent></Popover></div>
    <div className="grid gap-1.5"><Label htmlFor="sk-name">{tr('ชื่อทักษะ')}</Label><Input id="sk-name" value={d.name} maxLength={60} required placeholder={tr('เช่น ตรวจเอกสาร')} onChange={e=>set('name',e.target.value)}/></div>
   </div>
   <div className="grid gap-1.5"><Label htmlFor="sk-desc">{tr('คำอธิบายสั้น ๆ')}</Label><Input id="sk-desc" value={d.description} maxLength={200} placeholder={tr('ใช้ทำอะไร')} onChange={e=>set('description',e.target.value)}/></div>
   <div className="grid gap-1.5"><Label htmlFor="sk-ins">{tr('คำสั่งให้ AI')}</Label><Textarea id="sk-ins" value={d.instructions} rows={9} maxLength={4000} required minLength={10} placeholder={tr('บอก AI ว่าเป็นใคร ต้องทำอะไร ตอบในรูปแบบไหน')} onChange={e=>set('instructions',e.target.value)}/><small className="text-muted-foreground">{tr('{length}/4000 · กฎความปลอดภัยและการอ้างอิงเอกสารของระบบยังใช้เสมอ',{length:d.instructions.length})}</small></div>
   <Label className="source-option cursor-pointer justify-start border-0 py-1 items-center gap-2.5 text-left text-sm font-normal"><Checkbox checked={d.use_documents} onCheckedChange={v=>set('use_documents',v===true)}/>{tr('ตอบจากเอกสารขององค์กร (ปิด = คุยทั่วไป)')}</Label>
   {canShare&&<Label className="source-option cursor-pointer justify-start border-0 py-1 items-center gap-2.5 text-left text-sm font-normal"><Checkbox checked={d.shared} onCheckedChange={v=>set('shared',v===true)}/>{tr('แชร์ให้ทุกคนในองค์กรใช้')}</Label>}
   {err&&<p role="alert" className="text-sm text-destructive">{err}</p>}
   <DialogFooter><Button type="button" variant="outline" onClick={onClose}>{tr('ยกเลิก')}</Button><Button type="submit" disabled={busy||!d.name.trim()||d.instructions.trim().length<10}>{busy?tr('กำลังบันทึก…'):tr('บันทึก')}</Button></DialogFooter>
  </form>
 </Modal>;
}

export function SkillsPage({notify}:{notify:(s:string)=>void}){
 const qc=useQueryClient();const router=useRouter();const confirm=useConfirm();
 const q=useQuery({queryKey:['skills'],queryFn:()=>api<SkillList>('/skills')});
 const [form,setForm]=useState<{id?:string;draft:Draft}|null>(null);const [view,setView]=useState<'all'|'mine'|'shared'>('all');
 const list=q.data?.skills||[];const refresh=()=>qc.invalidateQueries({queryKey:['skills']});
 const save=async(d:Draft)=>{
  if(form?.id)await api('/skills/'+form.id,{method:'PUT',body:JSON.stringify(d)});else await post('/skills',d);
  setForm(null);await refresh();notify(tr('บันทึกทักษะแล้ว'));
 };
 const remove=async(s:Skill)=>{if(!await confirm({title:tr('ลบทักษะ'),text:tr('ลบ "{v1}" ถาวรใช่หรือไม่',{v1:s.name}),danger:true,confirmLabel:tr('ลบ')}))return;try{await api('/skills/'+s.id,{method:'DELETE'});await refresh();notify(tr('ลบทักษะแล้ว'))}catch(e){notify((e as Error).message)}};
 const copy=async(s:Skill)=>{try{await post(`/skills/${s.id}/copy`,{});await refresh();notify(tr('สร้างสำเนาแล้ว แก้ไขได้ในรายการของคุณ'))}catch(e){notify((e as Error).message)}};
 const shown=list.filter(s=>view==='all'||(view==='mine')===s.mine);
 const names=new Set(list.filter(s=>s.mine).map(s=>s.name));const localize=(t:Draft):Draft=>t;
 return <div className="grid gap-5">
  <div className="flex flex-wrap items-start justify-between gap-3"><div><H1>AI skills</H1><p className="text-sm text-muted-foreground">{tr('สร้างคำสั่งที่ใช้บ่อยไว้ครั้งเดียว แล้วเลือกใช้ในแชทได้ทันที')}</p></div><Button onClick={()=>setForm({draft:blank})}><Plus className="size-4"/>{tr('สร้างทักษะ')}</Button></div>
  {q.isLoading?<p className="text-sm text-muted-foreground">{tr('กำลังโหลด…')}</p>:list.length===0&&<div className="rounded-xl border border-dashed p-8 text-center"><Sparkles className="mx-auto mb-2 size-8 text-primary"/><p className="font-medium">{tr('ยังไม่มีทักษะ')}</p><p className="text-sm text-muted-foreground">{tr('เริ่มจากแม่แบบด้านล่าง หรือกด “สร้างทักษะ”')}</p></div>}
  {list.length>0&&<div role="tablist" aria-label={tr('กรองทักษะ')} className="flex flex-wrap gap-2">{(['all','mine','shared'] as const).map(k=>{const n=k==='all'?list.length:list.filter(s=>k==='mine'?s.mine:!s.mine).length;return <Button key={k} role="tab" aria-selected={view===k} size="sm" variant={view===k?'default':'outline'} className="rounded-full" onClick={()=>setView(k)}>{k==='all'?tr('ทั้งหมด'):k==='mine'?tr('ของฉัน'):tr('ที่แชร์ให้ฉัน')}<span className="ml-1 opacity-70">{n}</span></Button>})}</div>}
  {list.length>0&&shown.length===0&&<p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">{tr('ไม่มีทักษะในหมวดนี้')}</p>}
  <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
   {shown.map(s=><article key={s.id} className="flex min-h-[11.5rem] flex-col gap-3 rounded-xl border bg-card p-4">
    <div className="flex items-start gap-3"><span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-2xl leading-none" aria-hidden>{s.icon}</span><div className="min-w-0 flex-1"><h3 className="line-clamp-2 font-semibold leading-snug">{s.name}</h3><p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-muted-foreground">{s.description||s.instructions}</p></div></div>
    <div className="flex flex-wrap items-center gap-1.5 text-xs"><Badge variant={s.shared?'default':'secondary'} className="gap-1 font-normal">{s.shared?<Users className="size-3"/>:<Lock className="size-3"/>}{s.shared?tr('ทั้งองค์กร'):tr('ส่วนตัว')}</Badge><Badge variant="outline" className="font-normal">{s.use_documents?tr('ตอบจากเอกสาร'):tr('คุยทั่วไป')}</Badge></div>
    <div className="mt-auto flex items-center gap-1.5 border-t pt-3">
     <Button size="sm" onClick={()=>router.push('/chat?skill='+s.id)}><MessageSquare className="size-4"/>{tr('ใช้ในแชท')}</Button>
     {s.mine?<><Button size="sm" variant="outline" aria-label={tr('แก้ไข {v1}',{v1:s.name})} onClick={()=>setForm({id:s.id,draft:s})}><Pencil className="size-4"/></Button><Button size="sm" variant="outline" aria-label={tr('ลบ {v1}',{v1:s.name})} onClick={()=>remove(s)}><Trash2 className="size-4"/></Button></>:<Button size="sm" variant="outline" onClick={()=>copy(s)}><Copy className="size-4"/>{tr('ทำสำเนา')}</Button>}
     <span className="ml-auto truncate text-xs text-muted-foreground">{s.mine?'':tr('โดย {owner}',{owner:s.owner})+' · '}{tr('ใช้ {uses} ครั้ง',{uses:s.uses})}</span>
    </div>
   </article>)}
  </div>
  <section aria-label={tr('แม่แบบ')}><h2 className="mb-2 text-sm font-medium text-muted-foreground">{tr('เริ่มจากแม่แบบ')}</h2><div className="flex flex-wrap gap-2">{TEMPLATES.filter(t=>!names.has(t.name)).map(t=><Button key={t.name} variant="outline" className="rounded-full" onClick={()=>setForm({draft:localize(t)})}><span aria-hidden>{t.icon}</span>{t.name}</Button>)}</div></section>
  {form&&<SkillForm initial={form.draft} canShare={!!q.data?.can_share} onClose={()=>setForm(null)} onSave={save}/>}
 </div>;
}
