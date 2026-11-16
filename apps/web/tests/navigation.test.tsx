import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Hub from '../components/hub';
import { api } from '../components/api';
const replace=vi.fn();
vi.mock('next/navigation',()=>({useRouter:()=>({push:vi.fn(),replace}),usePathname:()=>'/dashboard',useSearchParams:()=>new URLSearchParams()}));
vi.mock('next/link',()=>({default:({children,...props}:React.ComponentProps<'a'>)=><a {...props}>{children}</a>}));
const base={id:'user-1',name:'ผู้ทดสอบ',email:'tester@example.test',tenant_id:'tenant-1'};
beforeEach(()=>{
 vi.stubGlobal('fetch',vi.fn(async(input:string)=>{
  const path=String(input);let data:unknown=[];
  if(path.endsWith('/auth/me'))data={...base,role:'USER'};
  if(path.endsWith('/config'))data={demo_accounts:[{label:'ผู้ใช้งาน',email:'member@local.test',password:'demo-password'}]};
  if(path.endsWith('/analytics'))data={organizations:1,users:1,documents:0,storage_bytes:0,requests:0,cost:0,input_tokens:0,output_tokens:0,daily:[],models:[],demo:true,estimated:false};
  return {ok:true,json:async()=>data};
 }));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
describe('role-aware navigation',()=>{
 it('offers the demo accounts the backend lists and fills the labelled sign-in fields with one',async()=>{
  render(<Hub initialUser={null}/>);
  fireEvent.click(await waitFor(()=>screen.getByRole('button',{name:'ผู้ใช้ทั่วไป'})));
  await waitFor(()=>expect((screen.getByLabelText('อีเมล') as HTMLInputElement).value).toBe('member@local.test'));
  expect((screen.getByLabelText('รหัสผ่าน') as HTMLInputElement).value).toBe('demo-password');
 });
 it('keeps admin console out of member navigation',async()=>{
  render(<Hub initialUser={{...base,role:'USER'}}/>);
  expect(screen.queryByRole('link',{name:'Super Admin Console'})).toBeNull();
  expect(screen.getByRole('link',{name:'เอกสารของฉัน'}).getAttribute('href')).toBe('/documents');
  await waitFor(()=>expect(screen.getByText('เริ่มต้นด้วยเอกสารแรก')).toBeTruthy());
 });
 it('shows no console switch link, even to super admins',()=>{
  render(<Hub initialUser={{...base,role:'SUPER_ADMIN'}}/>);
  expect(screen.queryByRole('link',{name:'Super Admin Console'})).toBeNull();
  expect(screen.queryByRole('link',{name:'กลับหน้าผู้ใช้งาน'})).toBeNull();
  expect(replace).toHaveBeenCalledWith('/super-admin');
 });
 it('surfaces backend errors with readable Thai messages',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,status:403,json:async()=>({detail:'ไม่มีสิทธิ์เข้าถึง'})})));
  await expect(api('/documents')).rejects.toThrow('ไม่มีสิทธิ์เข้าถึง');
 });
});
