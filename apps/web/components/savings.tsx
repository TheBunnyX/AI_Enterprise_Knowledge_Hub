'use client';
import { Sel } from './ui/sel';
import {useEffect,useState,type FormEvent} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {Check,Gauge,Globe,PiggyBank,Zap} from 'lucide-react';
import {api,post,fmt,money,date} from './api';
import { tr } from '../lib/i18n';
import {Button} from './ui/button';
import {useConfirm} from './ui/confirm';
import { H1 } from './page-title';

type Notify=(s:string)=>void;
type Policy={cache:boolean;cache_days:number;auto_route:boolean;router_model:string;history_messages:number;history_chars:number;max_output_tokens:number;rate_per_minute:number;daily_requests:number;alert_percent:number;media_daily_limit:number;media_approval_usd:number;media_daily_usd:number;web_search?:'off'|'ask'|'always'};
type Report={days:number;by_model:{model:string;requests:number;cost:number}[];top_users:{name:string;email:string;requests:number;cost:number}[];by_department:{name:string;requests:number;cost:number}[];month:{month:string;spent:number;budget:number};savings:{cache_hits:number;cache_saved:number;embedding_batches_cached:number;routed:number;routed_to:Record<string,number>;cached_answers:number}};
type Approval={id:string;kind:string;prompt:string;user:string;email:string;estimate:number|null;created_at:string};
const kinds=():Record<string,string>=>({image:tr('ภาพ'),video:tr('วิดีโอ'),stt:tr('ถอดเสียง'),tts:tr('อ่านออกเสียง')});

function Rows({rows,empty}:{rows:{label:string;sub?:string;requests:number;cost:number}[];empty:string}){
 if(!rows.length)return <p className="muted small" style={{padding:'6px 0'}}>{empty}</p>;
 return <div className="table-scroll"><table><thead><tr><th>{tr('ชื่อ')}</th><th>{tr('คำขอ')}</th><th>{tr('ค่าใช้จ่าย')}</th></tr></thead><tbody>{rows.map(r=><tr key={r.label+(r.sub||'')}><td><strong>{r.label}</strong>{r.sub&&<small>{r.sub}</small>}</td><td>{fmt(r.requests)}</td><td>{money(r.cost)}</td></tr>)}</tbody></table></div>
}

export function SavingsPage({notify}:{notify:Notify}){
 const confirm=useConfirm();const qc=useQueryClient();const [days,setDays]=useState('30');const [busy,setBusy]=useState(false);
 const stored=useQuery({queryKey:['savings-policy'],queryFn:()=>api<Policy>('/savings/policy')});
 const report=useQuery({queryKey:['savings-report',days],queryFn:()=>api<Report>('/savings/report?days='+days)});
 const approvals=useQuery({queryKey:['media-approvals'],queryFn:()=>api<Approval[]>('/media/approvals'),refetchInterval:15000});
 const [form,setForm]=useState<Policy|null>(null);useEffect(()=>{if(stored.data)setForm(stored.data)},[stored.data]);
 const set=<K extends keyof Policy>(k:K,v:Policy[K])=>setForm(f=>f?{...f,[k]:v}:f);
 const num=(k:keyof Policy,min:number,max:number,step='1')=><input type="number" min={min} max={max} step={step} required value={form?.[k] as number} onChange={e=>set(k,(e.target.value===''?0:Number(e.target.value)) as never)}/>;
 const save=async(e:FormEvent)=>{e.preventDefault();if(!form)return;
  if(!await confirm({title:tr('บันทึกการตั้งค่าการประหยัดค่าใช้จ่าย'),text:tr('มีผลกับทุกคนในองค์กรทันที ทั้งการแชท การสร้างสื่อ และขีดจำกัดการใช้งาน')}))return;
  setBusy(true);try{await api('/savings/policy',{method:'PUT',body:JSON.stringify(form)});qc.invalidateQueries({queryKey:['savings-policy']});qc.invalidateQueries({queryKey:['savings-status']});notify(tr('บันทึกการตั้งค่าแล้ว'))}catch(err){notify((err as Error).message)}finally{setBusy(false)}};
 const decide=async(a:Approval,verb:'approve'|'reject')=>{
  if(!await confirm({title:verb==='approve'?tr('อนุมัติงานสร้างสื่อ'):tr('ไม่อนุมัติงานสร้างสื่อ'),text:tr('{v1} ของ {v2}{v3}',{v1:kinds()[a.kind]||a.kind,v2:a.user,v3:a.estimate!=null?tr(' · ค่าใช้จ่ายโดยประมาณ {v1}',{v1:money(a.estimate)}):''}),danger:verb==='reject',confirmLabel:verb==='approve'?tr('อนุมัติ'):tr('ไม่อนุมัติ')}))return;
  try{await post('/media/jobs/'+a.id+'/'+verb,{});qc.invalidateQueries({queryKey:['media-approvals']});notify(verb==='approve'?tr('อนุมัติแล้ว งานเริ่มประมวลผล'):tr('ไม่อนุมัติงานนี้แล้ว'))}catch(err){notify((err as Error).message)}};
 const r=report.data;const used=r&&r.month.budget?r.month.spent/r.month.budget*100:null;
 return <>
  <div className="page-heading"><div><H1>{tr('ประหยัดค่าใช้จ่าย')}</H1><p>{tr('ลดค่า API ด้วยแคช การเลือกโมเดลอัตโนมัติ ขีดจำกัดการใช้งาน และการอนุมัติงานสื่อ')}</p></div><Sel aria-label={tr('ช่วงเวลา')} value={days} onChange={e=>setDays(e.target.value)}><option value="7">{tr('7 วันที่ผ่านมา')}</option><option value="30">{tr('30 วันที่ผ่านมา')}</option><option value="90">{tr('90 วันที่ผ่านมา')}</option></Sel></div>
  {report.error&&<p className="error-box">{(report.error as Error).message}</p>}
  <div className="stats-grid">
   <div className="card metric"><div><p>{tr('ใช้ไปเดือนนี้')}</p><strong>{money(r?.month.spent)}</strong><small>{tr('{v1}',{v1:r?.month.budget?tr('{v1}% ของงบ {v2}',{v1:used!.toFixed(0),v2:money(r.month.budget)}):tr('ไม่ได้ตั้งงบองค์กร')})}</small></div></div>
   <div className="card metric"><div><p>{tr('ตอบจากแคช')}</p><strong>{tr('{v1} ครั้ง',{v1:fmt(r?.savings.cache_hits)})}</strong><small>{tr('ประหยัดได้ {v1} · มีคำตอบในแคช {v2}',{v1:money(r?.savings.cache_saved),v2:fmt(r?.savings.cached_answers)})}</small></div></div>
   <div className="card metric"><div><p>{tr('เลือกโมเดลอัตโนมัติ')}</p><strong>{tr('{v1} ครั้ง',{v1:fmt(r?.savings.routed)})}</strong><small>{Object.entries(r?.savings.routed_to||{}).map(([k,v])=>`${k} ${v}`).join(' · ')||tr('ยังไม่มีการเลือก')}</small></div></div>
   <div className="card metric"><div><p>{tr('Embedding ที่ใช้ซ้ำ')}</p><strong>{tr('{v1} ชุด',{v1:fmt(r?.savings.embedding_batches_cached)})}</strong><small>{tr('ไม่ต้องจ่ายซ้ำเมื่อข้อความเดิมถูกประมวลผลอีก')}</small></div></div>
  </div>
  <div className="chart-columns" style={{marginBottom:20}}>
   <div className="card padded"><div className="section-heading"><h2>{tr('ค่าใช้จ่ายแยกตามโมเดล')}</h2></div><Rows empty={tr('ยังไม่มีการใช้งาน')} rows={(r?.by_model||[]).map(m=>({label:m.model,requests:m.requests,cost:m.cost}))}/></div>
   <div className="card padded"><div className="section-heading"><h2>{tr('แยกตามฝ่าย')}</h2></div><Rows empty={tr('ยังไม่มีการใช้งาน')} rows={(r?.by_department||[]).map(m=>({label:m.name,requests:m.requests,cost:m.cost}))}/></div>
  </div>
  <div className="card padded" style={{marginBottom:20}}><div className="section-heading"><h2>{tr('ผู้ใช้ที่ใช้มากที่สุด')}</h2></div><Rows empty={tr('ยังไม่มีการใช้งาน')} rows={(r?.top_users||[]).map(m=>({label:m.name,sub:m.email,requests:m.requests,cost:m.cost}))}/></div>
  <div className="card padded" style={{marginBottom:20}}><div className="section-heading"><h2>{tr('งานสื่อที่รออนุมัติ')} <em>{approvals.data?.length||0}</em></h2></div>
   {!approvals.data?.length?<p className="muted small">{tr('ไม่มีงานรออนุมัติ งานที่ค่าประมาณสูงกว่าเกณฑ์จะมาแสดงที่นี่')}</p>:<div className="table-scroll"><table><thead><tr><th>{tr('ผู้ขอ')}</th><th>{tr('ชนิด')}</th><th>{tr('คำสั่ง')}</th><th>{tr('ประมาณ')}</th><th>{tr('เมื่อ')}</th><th>{tr('จัดการ')}</th></tr></thead><tbody>{approvals.data.map(a=><tr key={a.id}><td><strong>{a.user}</strong><small>{a.email}</small></td><td>{kinds()[a.kind]||a.kind}</td><td style={{maxWidth:280}}>{a.prompt||'-'}</td><td>{a.estimate!=null?money(a.estimate):'-'}</td><td>{date(a.created_at)}</td><td><div className="inline-actions"><Button onClick={()=>decide(a,'approve')}><Check size={16}/>{tr('อนุมัติ')}</Button><Button variant="outline" onClick={()=>decide(a,'reject')}>{tr('ไม่อนุมัติ')}</Button></div></td></tr>)}</tbody></table></div>}</div>
  {form&&<form className="card padded stack" onSubmit={save}>
   <div className="section-heading"><h2><PiggyBank size={18}/>{tr('ตั้งค่าการประหยัด')}</h2></div>
   <h3><Zap size={16}/> {tr('แคชและการเลือกโมเดล')}</h3>
   <label className="check-label"><input type="checkbox" checked={form.cache} onChange={e=>set('cache',e.target.checked)}/>{tr('ตอบคำถามซ้ำจากแคช (คำถามเดียวกัน หลักฐานเดียวกัน เฉพาะสิทธิ์ที่ผู้ถามเห็นได้)')}</label>
   <label>{tr('เก็บคำตอบในแคช (วัน)')}{num('cache_days',1,90)}</label>
   <label className="check-label"><input type="checkbox" checked={form.auto_route} onChange={e=>set('auto_route',e.target.checked)}/>{tr('เลือกโมเดลอัตโนมัติ ผู้ใช้ที่ไม่ได้เลือกโมเดลเองจะได้โมเดลที่เหมาะกับความยากของคำถาม')}</label>
   <label>{tr('โมเดลที่ใช้เลือก (Router)')}<input required maxLength={200} value={form.router_model} onChange={e=>set('router_model',e.target.value)}/></label>
   <h3><Globe size={16}/> {tr('การค้นเว็บ')}</h3>
   <label>{tr('คำค้นจะถูกส่งออกนอกองค์กร เลือกว่าใครตัดสินใจ')}<select value={form.web_search||'ask'} onChange={e=>set('web_search',e.target.value as 'off'|'ask'|'always')}><option value="off">{tr('ห้ามค้นเว็บ')}</option><option value="ask">{tr('ผู้ใช้เปิดเอง หรืออนุญาตทีละครั้งเมื่อ Agent ขอ')}</option><option value="always">{tr('Agent ค้นเว็บได้โดยไม่ต้องถาม')}</option></select></label>
   <h3><Gauge size={16}/> {tr('ขนาดคำขอ')}</h3>
   <div className="form-grid"><label>{tr('ข้อความย้อนหลังที่ส่ง (0 = ไม่ส่ง)')}{num('history_messages',0,20)}</label><label>{tr('ตัดแต่ละข้อความย้อนหลังที่ (ตัวอักษร)')}{num('history_chars',200,8000)}</label></div>
   <label>{tr('คำตอบยาวสุด (โทเคน)')}{num('max_output_tokens',128,8192)}</label>
   <h3>{tr('ขีดจำกัดและการแจ้งเตือน')}</h3>
   <div className="form-grid"><label>{tr('คำขอต่อนาทีต่อคน (0 = ไม่จำกัด)')}{num('rate_per_minute',0,1000)}</label><label>{tr('คำขอต่อวันต่อคน (0 = ไม่จำกัด)')}{num('daily_requests',0,100000)}</label></div>
   <label>{tr('แจ้งเตือนผู้ดูแลเมื่อใช้งบถึง (%)')}{num('alert_percent',1,100)}</label>
   <h3>{tr('การสร้างสื่อ (ภาพ / วิดีโอ / เสียง)')}</h3>
   <div className="form-grid"><label>{tr('งานต่อวันต่อคน (0 = ไม่จำกัด)')}{num('media_daily_limit',0,1000)}</label><label>{tr('ต้องอนุมัติเมื่อค่าประมาณตั้งแต่ (USD, 0 = ปิด)')}{num('media_approval_usd',0,100000,'0.01')}</label><label>{tr('งบสร้างภาพ/วิดีโอต่อวันต่อคน (USD, 0 = ไม่จำกัด)')}{num('media_daily_usd',0,100000,'0.01')}</label></div>
   <Button disabled={busy} type="submit"><Check size={17}/>{tr('บันทึกการตั้งค่า')}</Button>
  </form>}
 </>
}
