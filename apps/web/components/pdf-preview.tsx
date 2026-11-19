'use client';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import type {PDFDocumentProxy,RenderTask} from 'pdfjs-dist';
import {Download,Search,ZoomIn,ZoomOut} from 'lucide-react';
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

// ---- continuous scroll: every page is laid out top to bottom; only pages near the screen are drawn ----
export type PageSize={w:number;h:number};
export type PageLayout={tops:number[];heights:number[];widths:number[];total:number};
const GAP=10;const PAD=6;
/** Where each page sits when its width is `width * zoom` points wide. Heights follow each page's own proportions. */
export function layoutPages(sizes:PageSize[],width:number,zoom:number,gap=GAP):PageLayout{
 const tops:number[]=[];const heights:number[]=[];const widths:number[]=[];let y=0;
 for(const s of sizes){const scale=width*zoom/s.w;tops.push(y);widths.push(s.w*scale);heights.push(s.h*scale);y+=s.h*scale+gap}
 return {tops,heights,widths,total:Math.max(0,y-gap)};
}
/** The 1-based page under the vertical position y (the nearest page when y falls in a gap or outside). */
export function pageAt(layout:PageLayout,y:number):number{
 const n=layout.tops.length;if(!n)return 1;
 let lo=0,hi=n-1;while(lo<hi){const mid=(lo+hi+1)>>1;if(layout.tops[mid]<=y)lo=mid;else hi=mid-1}
 return lo+1;
}
/** 0-based first and last pages that touch the window [scrollTop - buffer, scrollTop + viewport + buffer]. */
export function visibleRange(layout:PageLayout,scrollTop:number,viewport:number,buffer:number):[number,number]{
 const n=layout.tops.length;if(!n)return [0,-1];
 const from=Math.max(0,pageAt(layout,scrollTop-buffer)-1);
 let to=pageAt(layout,scrollTop+viewport+buffer)-1;to=Math.min(n-1,Math.max(from,to));
 return [from,to];
}

type PageReport={scanned:boolean;hit:boolean};

function PdfPage({doc,number,size,width,zoom,quote,show,report}:{doc:PDFDocumentProxy;number:number;size:PageSize;width:number;zoom:number;quote:string;show:boolean;report:(page:number,r:PageReport|null)=>void}){
 const canvas=useRef<HTMLCanvasElement>(null);const [boxes,setBoxes]=useState<TextBox[]>([]);const [state,setState]=useState<'idle'|'drawing'|'done'|'error'>('idle');
 const scale=width*zoom/size.w;
 useEffect(()=>{
  const el=canvas.current;if(!el)return;
  if(!show){el.width=0;el.height=0;setBoxes([]);setState('idle');report(number,null);return}  // far from the screen: give the memory back, keep the place
  let active=true;let render:RenderTask|undefined;setState('drawing');
  (async()=>{const lib=await import('pdfjs-dist/legacy/build/pdf.mjs');const p=await doc.getPage(number);if(!active)return;
   const viewport=p.getViewport({scale});const ratio=Math.min(window.devicePixelRatio||1,2);
   el.width=Math.ceil(viewport.width*ratio);el.height=Math.ceil(viewport.height*ratio);el.style.width=viewport.width+'px';el.style.height=viewport.height+'px';
   render=p.render({canvas:el,canvasContext:el.getContext('2d')!,viewport,transform:ratio===1?undefined:[ratio,0,0,ratio,0,0]});await render.promise;
   const content=await p.getTextContent();const items=content.items.filter((x):x is Extract<typeof x,{str:string}>=>'str' in x);const hits=matchingItems(items.map(i=>i.str),quote);
   const result=items.map((item,i)=>{const transform=lib.Util.transform(viewport.transform,item.transform);const h=Math.hypot(transform[2],transform[3]);return {text:item.str,left:transform[4],top:transform[5]-h*.85,width:Math.max(1,item.width*viewport.scale),height:h*1.15,hit:hits.has(i)}});
   if(active){setBoxes(result);setState('done');report(number,{scanned:!items.some(i=>i.str.trim()),hit:result.some(b=>b.hit)})}
  })().catch(e=>{if(active&&e?.name!=='RenderingCancelledException'){console.error('pdf page failed',number,e?.name,e?.message);setState('error')}});
  return()=>{active=false;render?.cancel()};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[doc,number,scale,quote,show]);
 return <div className="pdf-page" data-page={number} data-state={state} role="group" aria-label={tr('หน้า {page}',{page:number})} style={{width:size.w*scale,height:size.h*scale,marginBottom:GAP}}><canvas ref={canvas}/><div className="pdf-text-layer">{boxes.map((b,i)=><span key={i} className={b.hit?'citation-highlight':''} style={{left:b.left,top:b.top,width:b.width,height:b.height,fontSize:b.height/1.15}}>{b.text}</span>)}</div>{state==='drawing'&&<div className="pdf-loading">{tr('กำลังแสดง PDF…')}</div>}{state==='error'&&<div className="pdf-loading">{tr('แสดงหน้า PDF ไม่สำเร็จ')}</div>}</div>;
}

function PdfCanvas({url,initialPage=1,initialQuote=''}:{url:string;initialPage?:number;initialQuote?:string}){
 const [doc,setDoc]=useState<PDFDocumentProxy|null>(null);const [sizes,setSizes]=useState<PageSize[]|null>(null);const [current,setCurrent]=useState(initialPage);const [range,setRange]=useState<[number,number]>([0,2]);
 const [typed,setTyped]=useState(initialQuote);const [quote,setQuote]=useState(initialQuote);const [zoom,setZoom]=useState(1);const [width,setWidth]=useState(650);const [error,setError]=useState('');const [reports,setReports]=useState<Record<number,PageReport>>({});
 const container=useRef<HTMLDivElement>(null);const anchor=useRef({page:initialPage,frac:0});const arrived=useRef(false);
 useEffect(()=>{setTyped(initialQuote);setQuote(initialQuote);arrived.current=false},[initialPage,initialQuote]);
 useEffect(()=>{const t=setTimeout(()=>setQuote(typed),250);return()=>clearTimeout(t)},[typed]);  // not a redraw per keystroke
 useEffect(()=>{if(!container.current)return;const observer=new ResizeObserver(entries=>setWidth(Math.min(1600,Math.max(260,entries[0].contentRect.width-2*PAD-2))));observer.observe(container.current);return()=>observer.disconnect()},[]);
 useEffect(()=>{
  let active=true;let destroy:(()=>void)|undefined;setError('');setSizes(null);arrived.current=false;
  import('pdfjs-dist/legacy/build/pdf.mjs').then(lib=>{if(!active)return;lib.GlobalWorkerOptions.workerSrc='/pdf.worker.min.mjs';const task=lib.getDocument({url,withCredentials:true,enableXfa:false});destroy=()=>{void task.destroy()};return task.promise.then(async pdf=>{
   const out:PageSize[]=[];for(let i=1;i<=pdf.numPages;i+=20){const group=await Promise.all(Array.from({length:Math.min(20,pdf.numPages-i+1)},async(_,k)=>{const v=(await pdf.getPage(i+k)).getViewport({scale:1});return {w:v.width,h:v.height}}));if(!active)return;out.push(...group)}  // every page's proportions, so the scroll bar is right from the start
   if(active){setDoc(pdf);setSizes(out);setCurrent(c=>Math.max(1,Math.min(pdf.numPages,c)))}})}).catch(e=>{console.error('pdf open failed',e?.name,e?.message);if(active)setError(tr('เปิด PDF ไม่สำเร็จ กรุณาตรวจสิทธิ์หรือดาวน์โหลดต้นฉบับ'))});
  return()=>{active=false;destroy?.()};
 },[url]);
 const layout=useMemo(()=>sizes?layoutPages(sizes,width,zoom):null,[sizes,width,zoom]);
 const update=useCallback(()=>{
  const el=container.current;if(!el||!layout||!layout.tops.length)return;
  const y=Math.max(0,el.scrollTop-PAD);const vh=el.clientHeight;
  setRange(r=>{const next=visibleRange(layout,y,vh,vh*1.5);return r[0]===next[0]&&r[1]===next[1]?r:next});
  const page=pageAt(layout,y+vh*.3);setCurrent(page);anchor.current={page,frac:layout.heights[page-1]?Math.max(0,Math.min(1,(y-layout.tops[page-1])/layout.heights[page-1])):0};
 },[layout]);
 const jump=useCallback((page:number)=>{const el=container.current;if(!el||!layout)return;const n=Math.max(1,Math.min(layout.tops.length,page));el.scrollTop=PAD+layout.tops[n-1];update()},[layout,update]);
 useEffect(()=>{  // first layout: go to the cited page; later layout changes (zoom, window width) keep the reader where they were
  const el=container.current;if(!el||!layout)return;
  if(!arrived.current){arrived.current=true;const n=Math.max(1,Math.min(layout.tops.length,initialPage));el.scrollTop=PAD+layout.tops[n-1];anchor.current={page:n,frac:0}}
  else{const {page,frac}=anchor.current;el.scrollTop=PAD+layout.tops[page-1]+frac*layout.heights[page-1]}
  update();
 // eslint-disable-next-line react-hooks/exhaustive-deps
 },[layout]);
 const report=useCallback((page:number,r:PageReport|null)=>setReports(prev=>{if(!r){if(!(page in prev))return prev;const{[page]:_,...rest}=prev;return rest}const old=prev[page];return old&&old.hit===r.hit&&old.scanned===r.scanned?prev:{...prev,[page]:r}}),[]);
 const drawn=Object.values(reports);const anyHit=drawn.some(r=>r.hit);const here=reports[current];
 const count=doc?.numPages||0;
 return <div className="pdf-reader flex min-h-0 flex-1 flex-col gap-2"><div className="pdf-controls flex shrink-0 flex-wrap items-center gap-2"><div className="flex items-center gap-1"><span className="text-[13px]">{tr('หน้า')}</span><Input className="h-8 w-16 text-center" aria-label={tr('หน้า PDF')} type="number" min={1} max={count||1} value={current} disabled={!layout} onChange={e=>jump(Number(e.target.value)||1)}/><span className="text-[13px]">/ {count||'…'}</span></div><div className="flex items-center gap-1"><Button variant="ghost" size="icon" aria-label={tr('ย่อ PDF')} onClick={()=>setZoom(Math.max(.5,zoom-.15))}><ZoomOut size={17}/></Button><span className="w-11 text-center text-[13px]">{Math.round(zoom*100)}%</span><Button variant="ghost" size="icon" aria-label={tr('ขยาย PDF')} onClick={()=>setZoom(Math.min(2,zoom+.15))}><ZoomIn size={17}/></Button></div><div className="relative min-w-[200px] flex-1 sm:max-w-md sm:ml-auto"><Search size={16} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"/><Input className="h-8" style={{paddingLeft:34}} aria-label={tr('ข้อความไฮไลต์ใน PDF')} value={typed} onChange={e=>setTyped(e.target.value)} placeholder={tr('ค้นหาและไฮไลต์ข้อความในเอกสาร')}/></div></div>{error&&<p className="error-box shrink-0">{error}</p>}{here?.scanned&&<p className="info-box shrink-0">{tr('PDF สแกนหน้านี้ไม่มีชั้นข้อความ จะแสดงหน้าอ้างอิงต้นฉบับ และอ่านข้อความ OCR ได้ในแท็บ “ข้อความ”')}</p>}{quote&&drawn.length>0&&!here?.scanned&&<p className="small muted shrink-0">{anyHit?tr('ไฮไลต์ข้อความที่ตรงกันแล้ว เลื่อนขึ้นลงเพื่อดูหน้าอื่น'):tr('ยังไม่พบข้อความตรงกันในหน้าที่แสดงอยู่ เลื่อนขึ้นลงเพื่อดูหน้าอื่น หรือเปลี่ยนคำค้นหา')}</p>}<div className="pdf-scroll pdf-scroll-continuous" ref={container} onScroll={update} tabIndex={0} aria-label={tr('เนื้อหา PDF เลื่อนขึ้นลงเพื่อดูทุกหน้า')}>{doc&&sizes&&layout?<div style={{width:Math.max(...layout.widths),margin:'0 auto'}}>{sizes.map((size,i)=><PdfPage key={i} doc={doc} number={i+1} size={size} width={width} zoom={zoom} quote={quote} show={i>=range[0]&&i<=range[1]} report={report}/>)}</div>:!error&&<div className="pdf-loading" style={{position:'static',margin:12}}>{tr('กำลังแสดง PDF…')}</div>}</div></div>
}

export function SecureDocumentPreview({id,context,onClose}:{id:string;context?:PreviewContext;onClose:()=>void}){
 const [tab,setTab]=useState('pdf');const [docId,query='']=id.split('?');const version=new URLSearchParams(query).get('version');
 const q=useQuery({queryKey:['preview',id],queryFn:()=>api<{name:string;version:number;status:string;error:string;download_url:string;pages:{id:string;page:number;text:string}[]}>('/documents/'+id)});
 const isPdf=q.data?.name.toLowerCase().endsWith('.pdf');const url='/api/documents/'+docId+'/pdf'+(version?'?version='+encodeURIComponent(version):'');
 return <Modal title={q.data?.name||tr('ตัวอย่างเอกสาร')} onClose={onClose} full>{q.isLoading?<div className="skeleton tall"/>:q.error?<p className="error-box">{(q.error as Error).message}</p>:<div className="flex min-h-0 flex-1 flex-col gap-2"><div className="preview-toolbar flex shrink-0 flex-wrap items-center justify-between gap-2 !border-b-0 !pb-0">{isPdf?<div className="tabs"><button className={tab==='pdf'?'selected':''} onClick={()=>setTab('pdf')}>{tr('PDF ต้นฉบับ')}</button><button className={tab==='text'?'selected':''} onClick={()=>setTab('text')}>{tr('ข้อความ / OCR')}</button></div>:<span/>}<div className="flex items-center gap-3"><span className="small muted">{tr('เวอร์ชัน {version} · {v1}',{version:q.data?.version,v1:q.data?.status==='ready'?tr('พร้อมใช้งาน'):q.data?.status})}</span><Button asChild variant="outline" size="sm"><a href={q.data?.download_url}><Download size={16}/>{tr('ดาวน์โหลดต้นฉบับ')}</a></Button></div></div>{q.data?.error&&<p className="error-box shrink-0">{q.data.error}</p>}{isPdf&&tab==='pdf'?<PdfCanvas url={url} initialPage={context?.page||1} initialQuote={(context?.quote||'').slice(0,180)}/>:<div className="document-preview min-h-0 flex-1">{q.data?.pages.map(p=><article key={p.id}><small>{tr('หน้า {page}',{page:p.page})}</small><p>{p.text}</p></article>)}</div>}</div>}</Modal>
}
