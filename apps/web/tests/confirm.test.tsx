import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConfirmProvider, useConfirm } from '../components/ui/confirm';

function Probe({action}:{action:()=>void}){
 const confirm=useConfirm();
 return <button onClick={async()=>{if(await confirm({title:'ยืนยันการทำรายการ',text:'แน่ใจหรือไม่',danger:true}))action()}}>run</button>;
}
afterEach(cleanup);
describe('confirm dialog',()=>{
 it('does not run the action when cancelled',async()=>{
  const action=vi.fn();render(<ConfirmProvider><Probe action={action}/></ConfirmProvider>);
  fireEvent.click(screen.getByText('run'));
  fireEvent.click(await screen.findByText('ยกเลิก'));
  await waitFor(()=>expect(screen.queryByText('ยืนยัน')).toBeNull());
  expect(action).not.toHaveBeenCalled();
 });
 it('runs the action only after confirming',async()=>{
  const action=vi.fn();render(<ConfirmProvider><Probe action={action}/></ConfirmProvider>);
  fireEvent.click(screen.getByText('run'));
  expect(action).not.toHaveBeenCalled();
  fireEvent.click(await screen.findByText('ยืนยัน'));
  await waitFor(()=>expect(action).toHaveBeenCalledTimes(1));
 });
});
