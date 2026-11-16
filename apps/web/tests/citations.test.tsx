import {describe,expect,it} from 'vitest';
import {linkCitations} from '@/components/markdown';

describe('linkCitations',()=>{
 it('numbers markers by first use and drops invalid ones',()=>{
  const r=linkCitations('สิทธิลา 10 วัน [2] ยื่นล่วงหน้า [1], [2] และอื่น ๆ [9]',3);
  expect(r.order).toEqual([2,1]);
  expect(r.text).toContain('[1](#cite-2)');
  expect(r.text).toContain('[2](#cite-1)');
  expect(r.text).not.toContain('#cite-9');
 });
});
