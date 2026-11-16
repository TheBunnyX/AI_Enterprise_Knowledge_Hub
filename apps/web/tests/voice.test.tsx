import {describe,expect,it} from 'vitest';
import {cleanSpoken,splitSpeech} from '../components/voice';

describe('voice helpers',()=>{
 it('removes citations and markdown before speaking',()=>{
  expect(cleanSpoken('**ทำงานที่บ้านได้ 2 วัน** [1] ตามนโยบาย [2]')).toBe('ทำงานที่บ้านได้ 2 วัน ตามนโยบาย');
 });
 it('emits complete sentences and keeps the unfinished rest',()=>{
  const a=splitSpeech('Hello there friend. This is not fini');
  expect(a.sentences).toEqual(['Hello there friend.']);expect(a.rest).toBe('This is not fini');
  const b=splitSpeech(a.rest+'shed.',true);
  expect(b.sentences).toEqual(['This is not finished.']);expect(b.rest).toBe('');
 });
 it('flushes nothing when empty',()=>{expect(splitSpeech('  ',true).sentences).toEqual([])});
});
