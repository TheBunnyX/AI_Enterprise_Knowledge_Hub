import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,waitFor,fireEvent} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {AccountWorkspace,GatewayPanel,StudioWorkspace} from '../components/features';
import type {ReactNode} from 'react';
const calls: {path:string;init?:RequestInit}[]=[];
function show(children:ReactNode){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>)}
beforeEach(()=>{
 calls.length=0;
 vi.stubGlobal('fetch',vi.fn(async(path:string,init?:RequestInit)=>{
  calls.push({path:String(path),init});let data:unknown=[];
  if(String(path).endsWith('/config'))data={ai_gateway_configured:false};
  if(String(path).endsWith('/preferences'))data=init?{id:'me',name:'ชื่อใหม่',role:'USER'}:{name:'สมาชิก',default_model:'',notifications:true};
  if(String(path).endsWith('/gateway'))data={url:'https://gateway.test/v1',key_configured:true,encryption_configured:true};
  return {ok:true,json:async()=>data};
 }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
it('disables media submission until a configured authorized model exists',async()=>{
 show(<StudioWorkspace path="/studio/image" notify={vi.fn()}/>);
 await waitFor(()=>expect(screen.getByRole('button',{name:'ส่งงานให้ AI'}).hasAttribute('disabled')).toBe(true));
 expect(screen.getByText('ต้องตั้งค่า Gateway / โมเดล')).toBeTruthy();
 expect(calls.some(c=>c.path.endsWith('/media/jobs?kind=image'))).toBe(true);
});
it('saves editable account preferences through the backend',async()=>{
 show(<AccountWorkspace user={{id:'me',name:'สมาชิก',email:'member@test.example',role:'USER',tenant_id:'tenant'}} onLogout={vi.fn()} notify={vi.fn()}/>);
 await waitFor(()=>expect(screen.getByLabelText('ชื่อที่แสดง').getAttribute('value')).toBe('สมาชิก'));
 fireEvent.change(screen.getByLabelText('ชื่อที่แสดง'),{target:{value:'ชื่อใหม่'}});
 fireEvent.click(screen.getByRole('button',{name:'บันทึกการตั้งค่า'}));
 await waitFor(()=>expect(calls.some(c=>c.path.endsWith('/preferences')&&c.init?.method==='PUT')).toBe(true));
 const request=calls.find(c=>c.path.endsWith('/preferences')&&c.init?.method==='PUT');
 expect(JSON.parse(String(request?.init?.body)).name).toBe('ชื่อใหม่');
});
it('shows key configuration without fetching or populating a plaintext API key',async()=>{
 show(<GatewayPanel notify={vi.fn()}/>);
 await waitFor(()=>expect(screen.getByLabelText('API Base URL').getAttribute('value')).toBe('https://gateway.test/v1'));
 const field=screen.getByLabelText('API key ใหม่ (เว้นว่างเพื่อใช้ค่าเดิม)') as HTMLInputElement;
 expect(field.type).toBe('password');expect(field.value).toBe('');
});
