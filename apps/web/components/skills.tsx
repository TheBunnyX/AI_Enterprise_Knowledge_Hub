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
 {icon:'📄',name:'ตรวจเอกสาร',description:'ตรวจความครบถ้วนและความถูกต้องของเอกสาร',use_documents:true,shared:false,instructions:'คุณคือผู้ตรวจเอกสารที่ละเอียดรอบคอบ ตรวจเอกสารที่ให้มาโดยดูความครบถ้วนของหัวข้อ ความขัดแย้งภายในเอกสาร ตัวเลข วันที่ และชื่อที่ไม่สอดคล้องกัน ตอบเป็นหัวข้อ: 1) สรุปสั้น 2) ปัญหาที่พบ (ระบุตำแหน่ง/หน้า) 3) สิ่งที่ควรแก้ไข ถ้าไม่พบปัญหาให้บอกตามตรง'},
 {icon:'⚖️',name:'กฎหมาย',description:'อธิบายประเด็นกฎหมายจากเอกสารที่มี',use_documents:true,shared:false,instructions:'คุณคือผู้ช่วยด้านกฎหมายขององค์กร อธิบายประเด็นทางกฎหมายด้วยภาษาที่คนทั่วไปเข้าใจ อ้างอิงข้อความจากเอกสารที่ให้มาเท่านั้น แยกให้ชัดระหว่างข้อเท็จจริงในเอกสารกับข้อสังเกตของคุณ ปิดท้ายด้วยข้อความว่านี่ไม่ใช่คำปรึกษาทางกฎหมายอย่างเป็นทางการ'},
 {icon:'🤝',name:'วิเคราะห์สัญญา',description:'ชี้ภาระ ความเสี่ยง และเงื่อนไขสำคัญของสัญญา',use_documents:true,shared:false,instructions:'วิเคราะห์สัญญาที่ให้มา ตอบเป็นหัวข้อ: คู่สัญญาและระยะเวลา, หน้าที่และภาระของแต่ละฝ่าย, เงื่อนไขการชำระเงิน, ค่าปรับและเงื่อนไขการยกเลิก, ความเสี่ยงหรือข้อที่ควรเจรจา เรียงตามความสำคัญ ระบุเลขข้อ/หน้าที่อ้างอิงทุกครั้ง'},
 {icon:'📊',name:'สรุปรายงาน',description:'สรุปรายงานเป็นประเด็นสำคัญและข้อเสนอแนะ',use_documents:true,shared:false,instructions:'สรุปรายงานที่ให้มาสำหรับผู้บริหารที่มีเวลาน้อย เริ่มด้วยสรุป 3 บรรทัด ตามด้วยตัวเลขหรือข้อค้นพบสำคัญเป็นข้อ ๆ ความเสี่ยง และสิ่งที่ควรตัดสินใจหรือทำต่อ ห้ามใส่ข้อมูลที่ไม่มีในรายงาน'},
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
 const [form,setForm]=useState<{id?:string;draft:Draft}|null>(null);
 const list=q.data?.skills||[];const refresh=()=>qc.invalidateQueries({queryKey:['skills']});
 const save=async(d:Draft)=>{
  if(form?.id)await api('/skills/'+form.id,{method:'PUT',body:JSON.stringify(d)});else await post('/skills',d);
  setForm(null);await refresh();notify(tr('บันทึกทักษะแล้ว'));
 };
 const remove=async(s:Skill)=>{if(!await confirm({title:tr('ลบทักษะ'),text:tr('ลบ "{v1}" ถาวรใช่หรือไม่',{v1:s.name}),danger:true,confirmLabel:tr('ลบ')}))return;try{await api('/skills/'+s.id,{method:'DELETE'});await refresh();notify(tr('ลบทักษะแล้ว'))}catch(e){notify((e as Error).message)}};
 const copy=async(s:Skill)=>{try{await post(`/skills/${s.id}/copy`,{});await refresh();notify(tr('สร้างสำเนาแล้ว แก้ไขได้ในรายการของคุณ'))}catch(e){notify((e as Error).message)}};
 const names=new Set(list.filter(s=>s.mine).map(s=>s.name));const localize=(t:Draft):Draft=>({...t,name:tr(t.name),description:tr(t.description),instructions:tr(t.instructions)});
 return <div className="grid gap-5">
  <div className="flex flex-wrap items-start justify-between gap-3"><div><H1>{tr('ทักษะ AI')}</H1><p className="text-sm text-muted-foreground">{tr('สร้างคำสั่งที่ใช้บ่อยไว้ครั้งเดียว แล้วเลือกใช้ในแชทได้ทันที')}</p></div><Button onClick={()=>setForm({draft:blank})}><Plus className="size-4"/>{tr('สร้างทักษะ')}</Button></div>
  {q.isLoading?<p className="text-sm text-muted-foreground">{tr('กำลังโหลด…')}</p>:list.length===0&&<div className="rounded-xl border border-dashed p-8 text-center"><Sparkles className="mx-auto mb-2 size-8 text-primary"/><p className="font-medium">{tr('ยังไม่มีทักษะ')}</p><p className="text-sm text-muted-foreground">{tr('เริ่มจากแม่แบบด้านล่าง หรือกด “สร้างทักษะ”')}</p></div>}
  <div className="grid grid-cols-[repeat(auto-fill,minmax(280px,1fr))] gap-3">
   {list.map(s=><article key={s.id} className="flex flex-col gap-2 rounded-xl border bg-card p-4">
    <div className="flex items-start gap-3"><span className="text-2xl leading-none" aria-hidden>{s.icon}</span><div className="min-w-0 flex-1"><h3 className="truncate font-semibold">{s.name}</h3><p className="line-clamp-2 text-sm text-muted-foreground">{s.description||s.instructions}</p></div></div>
    <div className="flex flex-wrap items-center gap-1.5 text-xs"><Badge variant={s.shared?'default':'secondary'} className="gap-1 font-normal">{s.shared?<Users className="size-3"/>:<Lock className="size-3"/>}{s.shared?tr('ทั้งองค์กร'):tr('ส่วนตัว')}</Badge><Badge variant="outline" className="font-normal">{s.use_documents?tr('ตอบจากเอกสาร'):tr('คุยทั่วไป')}</Badge>{!s.mine&&<span className="text-muted-foreground">{tr('โดย {owner}',{owner:s.owner})}</span>}<span className="ml-auto text-muted-foreground">{tr('ใช้ {uses} ครั้ง',{uses:s.uses})}</span></div>
    <div className="mt-auto flex flex-wrap gap-1.5 pt-1">
     <Button size="sm" onClick={()=>router.push('/chat?skill='+s.id)}><MessageSquare className="size-4"/>{tr('ใช้ในแชท')}</Button>
     {s.mine?<><Button size="sm" variant="outline" aria-label={tr('แก้ไข {v1}',{v1:s.name})} onClick={()=>setForm({id:s.id,draft:s})}><Pencil className="size-4"/></Button><Button size="sm" variant="outline" aria-label={tr('ลบ {v1}',{v1:s.name})} onClick={()=>remove(s)}><Trash2 className="size-4"/></Button></>:<Button size="sm" variant="outline" onClick={()=>copy(s)}><Copy className="size-4"/>{tr('ทำสำเนา')}</Button>}
    </div>
   </article>)}
  </div>
  <section aria-label={tr('แม่แบบ')}><h2 className="mb-2 text-sm font-medium text-muted-foreground">{tr('เริ่มจากแม่แบบ')}</h2><div className="flex flex-wrap gap-2">{TEMPLATES.filter(t=>!names.has(t.name)&&!names.has(tr(t.name))).map(t=><Button key={t.name} variant="outline" className="rounded-full" onClick={()=>setForm({draft:localize(t)})}><span aria-hidden>{t.icon}</span>{tr(t.name)}</Button>)}</div></section>
  {form&&<SkillForm initial={form.draft} canShare={!!q.data?.can_share} onClose={()=>setForm(null)} onSave={save}/>}
 </div>;
}
