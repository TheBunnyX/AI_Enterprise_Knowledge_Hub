'use client';
import { Bot, Brain, CircleHelp, Database, FileSearch, Globe, MessagesSquare, Paperclip, type LucideIcon } from 'lucide-react';
import { tr } from '../lib/i18n';
import { Button } from './ui/button';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';

type Option = { icon: LucideIcon; name: string; text: string };

/** What each control above the question box does, in words, so nobody has to hover over an icon to find out. */
const options = (): Option[] => [
  { icon: FileSearch, name: tr('ตอบจากเอกสาร'), text: tr('ค้นจากเอกสารที่คุณมีสิทธิ์อ่าน แล้วตอบพร้อมอ้างอิงชื่อเอกสารและหน้า กดอ้างอิงเพื่อเปิดต้นฉบับได้ ถ้าไม่พบหลักฐานจะบอกตรงๆ') },
  { icon: MessagesSquare, name: tr('คุยทั่วไป'), text: tr('คุยกับ AI ตรงๆ จากความรู้ทั่วไปของโมเดล ไม่ค้นเอกสารองค์กร จึงไม่มีการอ้างอิง และคำตอบอาจไม่ตรงกับข้อมูลขององค์กร') },
  { icon: Database, name: tr('ทุกคลังความรู้'), text: tr('เลือกขอบเขตการค้น: ทุกคลัง คลังเดียว หรือเฉพาะบางเอกสาร ถ้ารู้ว่าคำตอบอยู่ที่ไหน การจำกัดขอบเขตจะได้ผลตรงและเร็วขึ้น') },
  { icon: Brain, name: tr('Effort: ตามโมเดล'), text: tr('ระดับการคิดของโมเดล minimal/low เร็วและประหยัด medium สมดุล high คิดลึกแต่ช้าและแพงกว่า มีผลเฉพาะโมเดลที่รองรับ') },
  { icon: Paperclip, name: tr('แนบไฟล์'), text: tr('แนบ PDF, Word, Excel, PowerPoint, TXT หรือภาพ ได้สูงสุด 5 ไฟล์ ใช้กับคำถามนี้ครั้งเดียว ไม่ถูกเพิ่มเข้าคลังความรู้ ลากไฟล์มาวางได้') },
  { icon: Globe, name: tr('ค้นเว็บ'), text: tr('ให้ AI ค้นอินเทอร์เน็ตเมื่อจำเป็น เหมาะกับข้อมูลภายนอกที่เปลี่ยนเร็ว คำค้นจะถูกส่งออกนอกองค์กร (องค์กรอาจปิดฟีเจอร์นี้) และแสดงลิงก์แหล่งที่มา') },
  { icon: Bot, name: 'Agent', text: tr('AI วางแผนและใช้เครื่องมือเองหลายรอบ: ค้นและอ่านเอกสาร เปรียบเทียบหลายฉบับ คำนวณตัวเลข อ่านตาราง Excel สรุปเอกสารยาว ดูภาพกราฟ ค้นเว็บ สร้างไฟล์ (สไลด์ Excel Word PDF) และบันทึกไฟล์เข้าคลังเมื่อคุณอนุญาต อาจถามกลับเมื่อคำสั่งกำกวม ใช้โมเดลหลายรอบ ค่าใช้จ่ายสูงกว่าปกติ และใช้ไม่ได้กับโมเดลในเครื่อง') },
];

export function ChatOptionsHelp() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="h-8 gap-1.5 rounded-full px-2.5 text-xs text-muted-foreground" aria-label={tr('ตัวเลือกเหล่านี้ทำอะไรได้บ้าง')}><CircleHelp className="size-4" /><span className="max-sm:hidden">{tr('แต่ละตัวเลือกทำอะไร')}</span></Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(92vw,26rem)] p-0">
        <div className="border-b px-4 py-3"><strong className="text-sm">{tr('ตัวเลือกเหนือช่องคำถาม')}</strong><p className="text-xs text-muted-foreground">{tr('เปิดหลายอย่างพร้อมกันได้ ยกเว้นสองโหมดแรกที่เลือกได้อย่างใดอย่างหนึ่ง')}</p></div>
        <ul className="max-h-[60vh] divide-y overflow-y-auto" aria-label={tr('คำอธิบายตัวเลือก')}>
          {options().map(({ icon: Icon, name, text }) => <li key={name} className="flex gap-3 px-4 py-3"><Icon className="mt-0.5 size-4 shrink-0 text-primary" /><div className="min-w-0"><strong className="block text-sm">{name}</strong><p className="text-[13px] leading-5 text-muted-foreground">{text}</p></div></li>)}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
