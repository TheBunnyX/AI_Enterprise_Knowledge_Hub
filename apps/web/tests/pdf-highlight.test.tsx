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

import {layoutPages,pageAt,visibleRange} from '../components/pdf-preview';
const pages=[{w:600,h:800},{w:600,h:800},{w:300,h:400},{w:600,h:800}];  // the third page is a half-size page
it('lays pages out top to bottom with each page keeping its own proportions',()=>{
 const l=layoutPages(pages,600,1,10);
 expect(l.tops).toEqual([0,810,1620,2430]);
 expect(l.heights).toEqual([800,800,800,800]);  // the small page is scaled up to the same width
 expect(l.widths).toEqual([600,600,600,600]);
 expect(l.total).toBe(3230);
 expect(layoutPages(pages,600,.5,10).heights).toEqual([400,400,400,400]);  // zoom scales every page
});
it('finds the page under a scroll position, including gaps and both ends',()=>{
 const l=layoutPages(pages,600,1,10);
 expect([0,799,805,810,1700,3029,9999,-50].map(y=>pageAt(l,y))).toEqual([1,1,1,2,3,4,4,1]);
 expect(pageAt(layoutPages([],600,1),0)).toBe(1);
});
it('draws only the pages near the screen',()=>{
 const l=layoutPages(Array.from({length:100},()=>({w:600,h:800})),600,1,10);
 expect(visibleRange(l,0,700,0)).toEqual([0,0]);
 expect(visibleRange(l,0,700,1000)).toEqual([0,2]);  // the window reaches 1700, into the third page
 const [from,to]=visibleRange(l,40*810,700,1050);  // in the middle of a long document
 expect(from).toBeGreaterThanOrEqual(38);expect(to).toBeLessThanOrEqual(43);expect(to-from).toBeLessThanOrEqual(5);
 expect(visibleRange(l,10**7,700,1000)).toEqual([99,99]);  // far past the end: the last page
 expect(visibleRange(layoutPages([],600,1),0,700,1000)).toEqual([0,-1]);
});
