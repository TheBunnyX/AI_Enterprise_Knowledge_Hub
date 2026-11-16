import {expect,it} from 'vitest';
import {matchingItems} from '../components/pdf-preview';
it('matches citations across PDF text fragments and whitespace',()=>{
 expect([...matchingItems(['Annual ','leave policy: ','12 days per year.'],'leave policy: 12 days')]).toEqual([1,2]);
});
it('matches Thai citations without requiring word spaces',()=>{
 expect([...matchingItems(['นโยบาย','ลาพักร้อน ','10 วัน'],'ลาพักร้อน10 วัน')]).toEqual([1,2]);
});
it('does not highlight unrelated or empty queries',()=>{
 expect(matchingItems(['policy'],'unrelated').size).toBe(0);
 expect(matchingItems(['policy'],'').size).toBe(0);
});
