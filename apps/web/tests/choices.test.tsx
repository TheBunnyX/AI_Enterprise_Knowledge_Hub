import { describe, it, expect } from 'vitest';
import { choiceOptions } from '../lib/choices';

describe('choiceOptions', () => {
  it('turns the options of a clarifying question into buttons and keeps the "other" one apart', () => {
    const r = choiceOptions('คุณต้องการให้ใส่ข้อมูลใดลงในไฟล์ Excel (xlsx)? • ข้อมูลการลาและสิทธิ์การหยุดงาน • ข้อมูลการประเมินผลการปฏิบัติงาน • ข้อมูลอื่น ๆ (โปรดระบุ)');
    expect(r.options).toEqual(['ข้อมูลการลาและสิทธิ์การหยุดงาน', 'ข้อมูลการประเมินผลการปฏิบัติงาน']);
    expect(r.question).toContain('ต้องการให้ใส่ข้อมูลใด')
    expect(r.other).toBe('ข้อมูลอื่น ๆ (โปรดระบุ)');
  });
  it('reads bullets and numbered lines on separate lines', () => {
    expect(choiceOptions('Which one?\n- Leave\n- Salary').options).toEqual(['Leave', 'Salary']);
    expect(choiceOptions('ต้องการแบบไหน\n1. สรุป\n2. ตาราง').options).toEqual(['สรุป', 'ตาราง']);
  });
  it('shows nothing for an ordinary answer or a long list', () => {
    expect(choiceOptions('ลาพักร้อนได้ 10 วัน').options).toEqual([]);
    expect(choiceOptions('Steps?\n- a\n- b\n- c\n- d\n- e\n- f\n- g').options).toEqual([]);
    expect(choiceOptions('Rules:\n- one thing only').options).toEqual([]);
  });
  it('handles a sample-table question with an example in brackets', () => {
    const r = choiceOptions('คุณต้องการให้สร้างตารางข้อมูลตัวอย่างประเภทใด หรือมีหัวข้อเฉพาะที่ต้องการใส่ในไฟล์ Excel ไหมครับ? • สร้างตารางข้อมูลตัวอย่าง (เช่น รายรับ-รายจ่าย หรือ รายชื่อพนักงาน) • ระบุหัวข้อหรือข้อมูลเฉพาะที่คุณต้องการเอง');
    expect(r.options).toEqual(['สร้างตารางข้อมูลตัวอย่าง (เช่น รายรับ-รายจ่าย หรือ รายชื่อพนักงาน)']);
    expect(r.other).toBe('ระบุหัวข้อหรือข้อมูลเฉพาะที่คุณต้องการเอง');
  });
});

import { splitFiles, listOptions } from '../lib/choices';
describe('splitFiles and listOptions', () => {
  it('moves the generated-file line out of the text into file cards', () => {
    const r = splitFiles('สร้างไฟล์ **a.xlsx** เรียบร้อยแล้วครับ\n\n📎 ไฟล์ที่สร้างให้: [Monthly_Budget.xlsx](/api/files/abc-123) · [b.csv](/api/files/def)');
    expect(r.text).toBe('สร้างไฟล์ **a.xlsx** เรียบร้อยแล้วครับ');
    expect(r.files).toEqual([{ name: 'Monthly_Budget.xlsx', href: '/api/files/abc-123' }, { name: 'b.csv', href: '/api/files/def' }]);
    expect(splitFiles('ไม่มีไฟล์').files).toEqual([]);
  });
  it('writes inline options as a list', () => {
    expect(listOptions('ต้องการอะไรครับ? • งบการเงิน • แผนงาน • อื่นๆ (โปรดระบุ)')).toBe('ต้องการอะไรครับ?\n\n- งบการเงิน\n- แผนงาน\n- อื่นๆ (โปรดระบุ)');
  });
});
