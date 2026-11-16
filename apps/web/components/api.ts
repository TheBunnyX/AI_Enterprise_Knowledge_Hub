import {tr,getLang,LOCALE} from '../lib/i18n';
export const ROLES=['SUPER_ADMIN','DEPARTMENT_ADMIN','USER'] as const;
export const roleLabel=(role:string)=>({SUPER_ADMIN:'Super Admin',DEPARTMENT_ADMIN:tr('ผู้ดูแลแผนก'),USER:tr('ผู้ใช้')} as Record<string,string>)[role]||role;
export type User={id:string;name:string;email:string;role:string;tenant_id:string;active?:boolean;online?:boolean};
export type Doc={id:string;can_write?:boolean;name:string;knowledge_base_id:string;size:number;status:string;error:string;version:number;created_at:string};
export type KB={id:string;name:string;description:string;documents:number;department_id?:string;department?:string;can_write?:boolean};
export type Source={id:string;url:string;interval_minutes:number;enabled:boolean;document_id:string;last_checked:string;last_status:string;last_error:string};
export type Citation={number?:number;version?:number;document_id:string;chunk_id:string;name:string;page:number;snippet:string;score?:number;url?:string};
export type Message={id?:string;role:string;content:string;citations:Citation[]};
/** What a paused agent run waits for: a clarifying question (with optional quick replies) or approval to search the web. */
export type AgentPending={kind:'question'|'approval';question?:string;options?:string[];queries?:string[]};
export type Model={id:string;name:string;display_name?:string;provider:string;api_id:string;category:string;enabled:boolean;configured:boolean;input_price:number;output_price:number;effort?:string;media_limits?:Record<string,string[]>;rpm?:number;tpm?:number;rpd?:number;used_rpm?:number;used_tpm?:number;used_rpd?:number};
const compact=(n:number)=>n>=1e6?(n/1e6).toFixed(n%1e6?1:0)+'M':n>=1000?(n/1000).toFixed(n%1000?1:0)+'K':String(n);
export type LimitRow={label:string;used:number;limit:number;level:'ok'|'warn'|'full'};
/** Usage against the provider limits that are set (0 = unknown, skipped). Counted from requests made through this system only. */
export function limitRows(m:Pick<Model,'rpm'|'tpm'|'rpd'|'used_rpm'|'used_tpm'|'used_rpd'>):LimitRow[]{
 const row=(label:string,limit?:number,used?:number):LimitRow[]=>limit?[{label,used:used||0,limit,level:(used||0)>=limit?'full':(used||0)>=limit*.8?'warn':'ok'}]:[];
 return [...row('RPM',m.rpm,m.used_rpm),...row('TPM',m.tpm,m.used_tpm),...row('RPD',m.rpd,m.used_rpd)]}
export const levelClass={ok:'text-muted-foreground',warn:'text-amber-600 font-medium',full:'text-red-600 font-semibold'};
export const limitSummary=(m:Parameters<typeof limitRows>[0])=>limitRows(m).map(r=>`${r.label} ${compact(r.used)}/${compact(r.limit)}`).join(' · ');
export type Org={id:string;name:string;status:string;quota:number;users:number;documents:number;cost:number};
export type Audit={id:string;actor:string;action:string;detail:string;ip?:string;created_at:string};
export type Analytics={scope?:'organization'|'department'|'self';organizations:number;users:number;documents:number;storage_bytes:number;requests:number;cost:number;input_tokens:number;output_tokens:number;daily:{date:string;requests:number;cost:number;input_tokens:number;output_tokens:number}[];models:{name:string;value:number}[];model_rows:{name:string;requests:number;input_tokens:number;output_tokens:number;cost:number}[];top_users:{name:string;requests:number;input_tokens:number;output_tokens:number;cost:number}[];knowledge_bases:number;conversations:number;messages:number;document_status:Record<string,number>;days:number;estimated:boolean};
export type Conversation={id:string;title:string;created_at:string};
export async function api<T>(path:string,init?:RequestInit):Promise<T>{
 const r=await fetch('/api'+path,{...init,headers:{...(!(init?.body instanceof FormData)?{'Content-Type':'application/json'}:{}),...init?.headers}});
 if(!r.ok){let message=tr('เกิดข้อผิดพลาด ({n})',{n:r.status});try{const j=await r.json();message=typeof j.detail==='string'?j.detail:tr('กรุณาตรวจสอบข้อมูลที่กรอก')}catch{};throw new Error(message)}
 return r.json();
}
export const post=<T,>(path:string,body:unknown)=>api<T>(path,{method:'POST',body:JSON.stringify(body)});
export const date=(s:string)=>new Date(s).toLocaleString(LOCALE[getLang()],{dateStyle:'medium',timeStyle:'short'});
export const fmt=(n:number=0)=>n.toLocaleString(LOCALE[getLang()]);
export const money=(n:number=0)=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(n);
