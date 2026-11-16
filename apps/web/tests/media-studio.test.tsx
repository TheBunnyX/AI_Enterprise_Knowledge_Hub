import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,fireEvent} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {StudioWorkspace} from '../components/features';
import type {ReactNode} from 'react';

const calls: string[]=[];
let options:Record<string,unknown>={};
function show(children:ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)}
beforeEach(()=>{
 calls.length=0;
 vi.stubGlobal('fetch',vi.fn(async(path:string)=>{
  const p=String(path);calls.push(p);let data:unknown=[];
  if(p.endsWith('/config'))data={ai_gateway_configured:true};
  if(p.endsWith('/models'))data=[{id:'m1',name:'Clip',display_name:'Clip',provider:'OpenRouter',api_id:'x/clip',category:'Video',enabled:true,configured:true,input_price:0,output_price:0}];
  if(p.includes('/media/model-options'))data=options;
  if(p.includes('/media/estimate'))data={cost:null,remaining_today:5,needs_approval:false,approval_usd:0};
  return {ok:true,json:async()=>data};
 }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});

it('marks the first-frame image as required for image-to-video models and blocks submitting without it',async()=>{
 options={aspect_ratios:['16:9'],resolutions:['480p','720p'],durations:[3,5],accepts_image:true,max_images:1,requires_image:true};
 const notify=vi.fn();const {container}=show(<StudioWorkspace path="/studio/video" notify={notify}/>);
 await waitFor(()=>expect(screen.getByText('ภาพเฟรมแรกของวิดีโอ (จำเป็น)')).toBeTruthy());
 fireEvent.change(container.querySelector('textarea') as HTMLTextAreaElement,{target:{value:'แมวเดิน'}});
 fireEvent.click(screen.getByRole('button',{name:/ส่งงานให้ AI|สร้าง/}));
 await waitFor(()=>expect(notify).toHaveBeenCalledWith('โมเดลนี้สร้างวิดีโอจากภาพ กรุณาแนบภาพเฟรมแรก'));
 expect(calls.some(c=>c.includes('/media/estimate'))).toBe(false); // stopped before asking for an estimate or sending a job
});

it('keeps the first-frame image optional when the model also takes text',async()=>{
 options={aspect_ratios:['16:9'],resolutions:['720p'],durations:[5],accepts_image:true,max_images:2,requires_image:false};
 show(<StudioWorkspace path="/studio/video" notify={vi.fn()}/>);
 await waitFor(()=>expect(screen.getByText('ภาพเฟรมแรกของวิดีโอ (ไม่บังคับ)')).toBeTruthy());
});

it('offers only the resolutions the backend allows and no automatic chip',async()=>{
 options={aspect_ratios:['16:9'],resolutions:['480p','720p'],durations:[3,5],accepts_image:true,requires_image:false};
 show(<StudioWorkspace path="/studio/video" notify={vi.fn()}/>);
 await waitFor(()=>expect(screen.getByRole('radio',{name:'480p'})).toBeTruthy());
 expect(screen.getByRole('radio',{name:'720p'})).toBeTruthy();
 expect(screen.queryByRole('radio',{name:'อัตโนมัติ'})).toBeNull();
 expect(screen.queryByRole('radio',{name:'4K'})).toBeNull();
});
