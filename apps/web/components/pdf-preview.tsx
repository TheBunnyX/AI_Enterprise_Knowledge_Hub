'use client';
import {useEffect,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import type {PDFDocumentProxy,RenderTask} from 'pdfjs-dist';
import {ArrowLeft,ArrowRight,Download,Search,ZoomIn,ZoomOut} from 'lucide-react';
import {api} from './api';
import { tr } from '../lib/i18n';
import {Modal} from './ui/dialog';
import {Button} from './ui/button';
import {Input} from './ui/input';

export type PreviewContext={page?:number;quote?:string};
type TextBox={text:string;left:number;top:number;width:number;height:number;hit:boolean};
const normalize=(s:string)=>s.replace(/\s+/g,'').toLocaleLowerCase();
export function matchingItems(items:string[],quote:string):Set<number>{
 const query=normalize(quote);if(!query)return new Set();
 let text='';const owners:number[]=[];
 items.forEach((item,i)=>{const value=normalize(item);text+=value;for(let j=0;j<value.length;j++)owners.push(i)});
 const result=new Set<number>();let at=text.indexOf(query);
 while(at>=0){for(let i=at;i<at+query.length;i++)result.add(owners[i]);at=text.indexOf(query,at+Math.max(query.length,1))}
 return result;
}

function PdfCanvas({url,initialPage=1,initialQuote=''}:{url:string;initialPage?:number;initialQuote?:string}){
 const [doc,setDoc]=useState<PDFDocumentProxy|null>(null);const [page,setPage]=useState(initialPage);const [quote,setQuote]=useState(initialQuote);const [zoom,setZoom]=useState(1);const [width,setWidth]=useState(650);const [height,setHeight]=useState(800);const [boxes,setBoxes]=useState<TextBox[]>([]);const [error,setError]=useState('');const [rendering,setRendering]=useState(true);const [scanned,setScanned]=useState(false);const canvas=useRef<HTMLCanvasElement>(null);const container=useRef<HTMLDivElement>(null);
 useEffect(()=>{setPage(initialPage);setQuote(initialQuote)},[initialPage,initialQuote]);
 useEffect(()=>{if(!container.current)return;const observer=new ResizeObserver(entries=>setWidth(Math.min(1600,Math.max(260,entries[0].contentRect.width-2))));observer.observe(container.current);return()=>observer.disconnect()},[]);
 useEffect(()=>{
  let active=true;let destroy:(()=>void)|undefined;setError('');
  import('pdfjs-dist').then(lib=>{if(!active)return;lib.GlobalWorkerOptions.workerSrc='/pdf.worker.min.mjs';const task=lib.getDocument({url,withCredentials:true,enableXfa:false});destroy=()=>{void task.destroy()};return task.promise.then(pdf=>{if(active){setDoc(pdf);setPage(p=>Math.max(1,Math.min(pdf.numPages,p)))}})}).catch(()=>{if(active)setError(tr('เปิด PDF ไม่สำเร็จ กรุณาตรวจสิทธิ์หรือดาวน์โหลดต้นฉบับ'))});
  return()=>{active=false;destroy?.()};
 },[url]);
 useEffect(()=>{
  if(!doc||!canvas.current)return;let active=true;let render:RenderTask|undefined;setRendering(true);setBoxes([]);
  (async()=>{const lib=await import('pdfjs-dist');const p=await doc.getPage(Math.max(1,Math.min(page,doc.numPages)));if(!active||!canvas.current)return;
   const base=p.getViewport({scale:1});const viewport=p.getViewport({scale:width/base.width*zoom});const ratio=Math.min(window.devicePixelRatio||1,2);const el=canvas.current;el.width=Math.ceil(viewport.width*ratio);el.height=Math.ceil(viewport.height*ratio);el.style.width=viewport.width+'px';el.style.height=viewport.height+'px';setHeight(viewport.height);
   render=p.render({canvas:el,canvasContext:el.getContext('2d')!,viewport,transform:ratio===1?undefined:[ratio,0,0,ratio,0,0]});await render.promise;
   const content=await p.getTextContent();const items=content.items.filter((x):x is Extract<typeof x,{str:string}>=>'str' in x);const hits=matchingItems(items.map(i=>i.str),quote);
   const result=items.map((item,i)=>{const transform=lib.Util.transform(viewport.transform,item.transform);const h=Math.hypot(transform[2],transform[3]);return {text:item.str,left:transform[4],top:transform[5]-h*.85,width:Math.max(1,item.width*viewport.scale),height:h*1.15,hit:hits.has(i)}});
   if(active){setBoxes(result);setScanned(!items.some(i=>i.str.trim()));setRendering(false)}
  })().catch(e=>{if(active&&e?.name!=='RenderingCancelledException'){setError(tr('แสดงหน้า PDF ไม่สำเร็จ'));setRendering(false)}});
  return()=>{active=false;render?.cancel()};
 },[doc,page,width,zoom,quote]);
 return <div className="pdf-reader flex min-h-0 flex-1 flex-col gap-2"><div className="pdf-controls flex shrink-0 flex-wrap items-center gap-2"><div className="flex items-center gap-1"><Button variant="outline" size="icon" aria-label={tr('หน้าก่อนหน้า')} disabled={page<=1} onClick={()=>setPage(page-1)}><ArrowLeft size={15}/></Button><span className="text-[13px]">{tr('หน้า')}</span><Input className="h-8 w-16 text-center" aria-label={tr('หน้า PDF')} type="number" min={1} max={doc?.numPages||1} value={page} onChange={e=>setPage(Math.max(1,Math.min(doc?.numPages||1,Number(e.target.value)||1)))}/><span className="text-[13px]">/ {doc?.numPages||'…'}</span><Button variant="outline" size="icon" aria-label={tr('หน้าถัดไป')} disabled={!doc||page>=doc.numPages} onClick={()=>setPage(page+1)}><ArrowRight size={15}/></Button></div><div className="flex items-center gap-1"><Button variant="ghost" size="icon" aria-label={tr('ย่อ PDF')} onClick={()=>setZoom(Math.max(.5,zoom-.15))}><ZoomOut size={17}/></Button><span className="w-11 text-center text-[13px]">{Math.round(zoom*100)}%</span><Button variant="ghost" size="icon" aria-label={tr('ขยาย PDF')} onClick={()=>setZoom(Math.min(2,zoom+.15))}><ZoomIn size={17}/></Button></div><div className="relative min-w-[200px] flex-1 sm:max-w-md sm:ml-auto"><Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"/><Input className="h-8" style={{paddingLeft:34}} aria-label={tr('ข้อความไฮไลต์ใน PDF')} value={quote} onChange={e=>setQuote(e.target.value)} placeholder={tr('ค้นหาและไฮไลต์ข้อความในหน้านี้')}/></div></div>{error&&<p className="error-box shrink-0">{error}</p>}{scanned&&<p className="info-box shrink-0">{tr('PDF สแกนหน้านี้ไม่มีชั้นข้อความ จะแสดงหน้าอ้างอิงต้นฉบับ และอ่านข้อความ OCR ได้ในแท็บ “ข้อความ”')}</p>}{quote&&!rendering&&!scanned&&<p className="small muted shrink-0">{boxes.some(b=>b.hit)?tr('ไฮไลต์ข้อความอ้างอิงในหน้าแล้ว'):tr('ยังไม่พบข้อความตรงกันในหน้านี้ ลองเปลี่ยนคำค้นหรือหน้า')}</p>}<div className="pdf-scroll" ref={container}><div className="pdf-page" style={{width:width*zoom,height}}><canvas ref={canvas}/><div className="pdf-text-layer">{boxes.map((b,i)=><span key={i} className={b.hit?'citation-highlight':''} style={{left:b.left,top:b.top,width:b.width,height:b.height,fontSize:b.height/1.15}}>{b.text}</span>)}</div>{rendering&&<div className="pdf-loading">{tr('กำลังแสดง PDF…')}</div>}</div></div></div>
}

export function SecureDocumentPreview({id,context,onClose}:{id:string;context?:PreviewContext;onClose:()=>void}){
 const [tab,setTab]=useState('pdf');const [docId,query='']=id.split('?');const version=new URLSearchParams(query).get('version');
 const q=useQuery({queryKey:['preview',id],queryFn:()=>api<{name:string;version:number;status:string;error:string;download_url:string;pages:{id:string;page:number;text:string}[]}>('/documents/'+id)});
 const isPdf=q.data?.name.toLowerCase().endsWith('.pdf');const url='/api/documents/'+docId+'/pdf'+(version?'?version='+encodeURIComponent(version):'');
 return <Modal title={q.data?.name||tr('ตัวอย่างเอกสาร')} onClose={onClose} full>{q.isLoading?<div className="skeleton tall"/>:q.error?<p className="error-box">{(q.error as Error).message}</p>:<div className="flex min-h-0 flex-1 flex-col gap-2"><div className="preview-toolbar flex shrink-0 flex-wrap items-center justify-between gap-2 !border-b-0 !pb-0">{isPdf?<div className="tabs"><button className={tab==='pdf'?'selected':''} onClick={()=>setTab('pdf')}>{tr('PDF ต้นฉบับ')}</button><button className={tab==='text'?'selected':''} onClick={()=>setTab('text')}>{tr('ข้อความ / OCR')}</button></div>:<span/>}<div className="flex items-center gap-3"><span className="small muted">{tr('เวอร์ชัน {version} · {v1}',{version:q.data?.version,v1:q.data?.status==='ready'?tr('พร้อมใช้งาน'):q.data?.status})}</span><Button asChild variant="outline" size="sm"><a href={q.data?.download_url}><Download size={16}/>{tr('ดาวน์โหลดต้นฉบับ')}</a></Button></div></div>{q.data?.error&&<p className="error-box shrink-0">{q.data.error}</p>}{isPdf&&tab==='pdf'?<PdfCanvas url={url} initialPage={context?.page||1} initialQuote={(context?.quote||'').slice(0,180)}/>:<div className="document-preview min-h-0 flex-1">{q.data?.pages.map(p=><article key={p.id}><small>{tr('หน้า {page}',{page:p.page})}</small><p>{p.text}</p></article>)}</div>}</div>}</Modal>
}
