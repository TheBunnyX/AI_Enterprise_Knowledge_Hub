import {describe,expect,it} from 'vitest';
import {render} from '@testing-library/react';
import {LangProvider} from '../lib/i18n';
import {trStatus} from '../components/api';

const Line=({text}:{text:string})=><p data-testid="out">{trStatus(text)}</p>;  // translated while rendering, inside the provider
const show=(lang:'en'|'th',text:string)=>{const view=render(<LangProvider initialLang={lang}><Line text={text}/></LangProvider>);const out=view.getByTestId('out').textContent;view.unmount();return out};

describe('chat status lines from the API', () => {
  it('are translated in English', () => {
    expect(show('en','กำลังเรียบเรียงคำตอบ')).toBe('Writing the answer');
    expect(show('en','พบ 3 แหล่งในเอกสาร กำลังส่งให้โมเดล')).toBe('Found 3 source(s) in the documents · Sending to the model');
    expect(show('en','กำลังค้นเว็บ: ราคาน้ำมัน')).toBe('Searching the web: ราคาน้ำมัน');
  });
  it('translate every agent step', () => {
    expect(show('en','Agent กำลังพิจารณาผลลัพธ์')).toBe('Agent is reviewing the results');
    expect(show('en','Agent กำลังวางแผน')).toBe('Agent is planning');
    expect(show('en','กำลังค้นเอกสาร: ลาพักร้อน')).toBe('Searching documents: ลาพักร้อน');
    expect(show('en','กำลังสร้างไฟล์')).toBe('Creating the file');
  });
  it('stay Thai in Thai', () => {
    expect(show('th','กำลังเรียบเรียงคำตอบ')).toBe('กำลังเรียบเรียงคำตอบ');
  });
});
