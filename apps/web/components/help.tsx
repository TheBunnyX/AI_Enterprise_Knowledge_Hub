'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { MessagesSquare, Search, FolderOpen, Mic, ImageIcon, AudioLines, Settings, Boxes, Database, CircleHelp, ChevronDown, ArrowRight, type LucideIcon } from 'lucide-react';
import { useT } from '../lib/i18n';

/** Help center: quick start, one card per feature with basic steps and a shortcut, and a short FAQ. Static content translated with tr(). */
const ICONS: Record<string, LucideIcon> = { MessagesSquare, Search, FolderOpen, Mic, ImageIcon, AudioLines, Settings, Boxes, Database };

export function HelpPage({ role }: { role?: string }) {
 const tr = useT();
 const [query, setQuery] = useState('');
 const quick: [string, string][] = [
  [tr('อัปโหลดเอกสาร'),tr('ไปที่ "เอกสารของฉัน" แล้วลากไฟล์ PDF, Word, Excel หรือภาพมาวาง (ไม่เกิน 20 MB)')],
  [tr('รอสถานะ "พร้อมใช้งาน"'),tr('ระบบอ่าน แบ่งส่วน และทำดัชนีเอกสารให้อัตโนมัติ ใช้เวลาไม่กี่วินาทีถึงไม่กี่นาที')],
  [tr('ถามคำถามในแชท'),tr('พิมพ์คำถามที่ "แชทเอกสาร" คำตอบจะมีเลขหน้าอ้างอิงและเปิดต้นฉบับได้')]
 ];
 // eslint-disable-next-line react-hooks/exhaustive-deps
 const topics = useMemo(() => [
  {key:'chat',href:'/chat',icon:'MessagesSquare',title:tr('แชทเอกสาร'),desc:tr('ถามคำถามจากเอกสารที่คุณมีสิทธิ์ หรือคุยกับ AI ทั่วไป'),admin:false,steps:[tr('เลือก AI Model ที่ไอคอนสมองข้างช่องถาม'),tr('เลือกโหมดตอบจากเอกสาร หรือคุยทั่วไป'),tr('แนบไฟล์หรือวางภาพ (Ctrl+V) ได้สูงสุด 5 ไฟล์ ไฟล์ละไม่เกิน 20 MB')]},
  {key:'search',href:'/knowledge/search',icon:'Search',title:tr('ค้นหาความรู้'),desc:tr('ค้นเอกสารด้วยคีย์เวิร์ด เวกเตอร์ หรือแบบผสม'),admin:false,steps:[tr('พิมพ์คำค้นแล้วกด Enter'),tr('เลือกโหมด Keyword, Vector หรือ Hybrid'),tr('เปิดผลลัพธ์เพื่อดูหน้าที่ตรงกันในต้นฉบับ')]},
  {key:'docs',href:'/documents',icon:'FolderOpen',title:tr('เอกสารของฉัน'),desc:tr('อัปโหลดและจัดการเอกสารในคลังที่คุณมีสิทธิ์เขียน'),admin:false,steps:[tr('เลือกคลังความรู้ แล้วลากไฟล์มาวางหรือกดอัปโหลด'),tr('ดูสถานะ: กำลังประมวลผล พร้อมใช้งาน หรือล้มเหลว'),tr('ไฟล์ที่ลบกู้คืนได้จากถังขยะ และเก็บเวอร์ชันเก่าไว้')]},
  {key:'voice',href:'/voice',icon:'Mic',title:tr('คุยด้วยเสียง'),desc:tr('สนทนาแบบเสียงต่อเสียงกับ AI และพูดแทรกได้'),admin:false,steps:[tr('อนุญาตไมโครโฟนเมื่อเบราว์เซอร์ถาม (ต้องเปิดผ่าน localhost หรือ HTTPS)'),tr('เลือกเอนจินเสียงและโหมด แล้วกดเริ่มคุย'),tr('ดูข้อความของคุณและ AI แยกเป็นสองฝั่งด้านล่าง')]},
  {key:'image',href:'/studio/image',icon:'ImageIcon',title:tr('สร้างภาพ / วิดีโอ'),desc:tr('สร้างภาพและวิดีโอจากข้อความด้วยโมเดลที่ผู้ดูแลเปิดไว้'),admin:false,steps:[tr('เลือกโมเดล และขนาดหรือความยาว'),tr('พิมพ์คำอธิบายแล้วกดสร้าง งานจะทำงานเบื้องหลัง'),tr('โมเดลบางตัวสร้างวิดีโอจากภาพ ต้องแนบภาพเฟรมแรก')]},
  {key:'stt',href:'/studio/stt',icon:'AudioLines',title:tr('ถอดเสียง / อ่านออกเสียง'),desc:tr('แปลงไฟล์เสียงเป็นข้อความ หรือข้อความเป็นเสียงพูด'),admin:false,steps:[tr('ถอดเสียง: อัปโหลดไฟล์เสียงแล้วเลือกภาษา'),tr('อ่านออกเสียง: พิมพ์ข้อความ เลือกเสียง แล้วกดสร้าง'),tr('ดาวน์โหลดผลลัพธ์จากประวัติงาน')]},
  {key:'account',href:'/settings',icon:'Settings',title:tr('ตั้งค่าบัญชี'),desc:tr('ปรับภาษา ธีม และดูเซสชันที่เข้าสู่ระบบ'),admin:false,steps:[tr('สลับภาษา TH | EN และโหมดสว่างหรือมืดจากแถบด้านบน'),tr('ดูและยกเลิกเซสชันในหน้าตั้งค่าบัญชี'),tr('ออกจากระบบเพื่อยกเลิกเซสชันปัจจุบัน')]},
  {key:'models',href:'/super-admin/models',icon:'Boxes',title:tr('โมเดลและบริการ AI'),desc:tr('เปิดโมเดล ตั้ง API key และกำหนดนโยบายและงบประมาณ'),admin:true,steps:[tr('ใส่ API key ของผู้ให้บริการ (เก็บแบบเข้ารหัส)'),tr('เพิ่มและเปิดใช้งานโมเดล เช่น Google AI หรือ OpenRouter'),tr('กำหนดนโยบายโมเดลและงบประมาณการใช้งาน')]},
  {key:'ops',href:'/super-admin/operations',icon:'Database',title:tr('สำรองและกู้คืน'),desc:tr('ดูสถานะบริการและจัดการชุดสำรองข้อมูลแบบเข้ารหัส'),admin:true,steps:[tr('ระบบสำรองอัตโนมัติทุก 24 ชั่วโมง และเก็บ 7 ชุดล่าสุด'),tr('คัดลอกไฟล์สำรองและเก็บคีย์เข้ารหัสไว้นอกเครื่อง'),tr('การกู้คืนต้องพิมพ์ยืนยัน และระบบทำ snapshot ก่อนแทนที่ข้อมูล')]}
 ], [tr]);
 const faq: [string, string][] = [
  [tr('ทำไมอัปโหลดไฟล์ไม่ได้'),tr('ต้องมีสิทธิ์เขียนในคลังความรู้นั้น (ผู้ดูแลแผนกหรือผู้ดูแลระบบ) รองรับ PDF, Word, Excel, PowerPoint, TXT, MD, CSV, HTML, PNG, JPEG ไม่เกิน 20 MB')],
  [tr('เอกสารค้างที่ "กำลังประมวลผล" ทำอย่างไร'),tr('รอสักครู่ ไฟล์สแกนต้องผ่าน OCR จึงใช้เวลานานกว่า หากขึ้นว่าล้มเหลว ผู้ดูแลสั่งทำดัชนีใหม่ได้')],
  [tr('คำตอบไม่มีแหล่งอ้างอิงหรือบอกว่าไม่พบข้อมูล'),tr('ระบบตอบเฉพาะจากเอกสารที่คุณมีสิทธิ์เห็น ลองถามให้เจาะจงขึ้น เลือกคลังความรู้ หรือสลับเป็นโหมดคุยทั่วไป')],
  [tr('AI Model ไม่ปรากฏในรายการ'),tr('โมเดลต้องเปิดใช้งานและมี API key ผู้ดูแลระบบตั้งค่าได้ที่หน้าโมเดลและบริการ AI')],
  [tr('ข้อมูลของฉันถูกส่งออกนอกองค์กรหรือไม่'),tr('เมื่อใช้โมเดลภายนอก (เช่น Google AI, OpenRouter) คำถามและข้อความจากเอกสารที่เกี่ยวข้องจะถูกส่งไปยังผู้ให้บริการนั้น การค้นเว็บส่งคำค้นออกนอกองค์กร และโหมดเสียงสดส่งเสียงให้ Google หากต้องการให้ข้อมูลอยู่ในเครื่อง ให้เลือกโมเดล Local LLM')]
 ];
 const needle = query.trim().toLowerCase();
 const visible = topics.filter(x => (role === 'SUPER_ADMIN' || !x.admin) && (!needle || [x.title, x.desc, ...x.steps].join(' ').toLowerCase().includes(needle)));
 const user = visible.filter(x => !x.admin), admin = visible.filter(x => x.admin);
 const card = (x: (typeof topics)[number]) => {
  const Icon = ICONS[x.icon] || CircleHelp;
  return <article key={x.key} className="card padded flex flex-col gap-3" aria-label={x.title}>
   <div className="flex items-start gap-3"><span className="grid size-10 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><Icon className="size-5" /></span>
    <div><h3 className="m-0 text-base font-semibold">{x.title}</h3><p className="muted small m-0">{x.desc}</p></div></div>
   <ol className="m-0 grid list-none gap-2 p-0">{x.steps.map((s: string, i: number) => <li key={i} className="flex gap-2 text-sm"><span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-muted text-xs font-semibold" aria-label={tr('ขั้นตอนที่') + ' ' + (i + 1)}>{i + 1}</span><span>{s}</span></li>)}</ol>
   <Link href={x.href} className="mt-auto inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">{tr('เปิดหน้านี้')}<ArrowRight className="size-4" /></Link>
  </article>;
 };
 return <>
  <div className="page-heading"><div><h1>{tr('ศูนย์ช่วยเหลือ')}</h1><p>{tr('คู่มือการใช้งานเบื้องต้นของแต่ละหน้า พร้อมทางลัดไปยังฟังก์ชันที่ใช้บ่อย')}</p></div></div>
  <div className="relative mb-4 max-w-xl"><Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder={tr('ค้นหาหัวข้อวิธีใช้')} aria-label={tr('ค้นหาหัวข้อวิธีใช้')} className="h-10 w-full rounded-full border border-border bg-background pl-9 pr-4 text-sm" /></div>
  {!needle && <section aria-label={tr('เริ่มต้นใช้งานใน 3 ขั้นตอน')} className="mb-6"><h2 className="mb-3 text-lg font-semibold">{tr('เริ่มต้นใช้งานใน 3 ขั้นตอน')}</h2>
   <div className="grid gap-3 md:grid-cols-3">{quick.map(([title, text], i) => <div key={i} className="card padded flex gap-3"><span className="grid size-8 shrink-0 place-items-center rounded-full bg-primary text-sm font-bold text-primary-foreground">{i + 1}</span><div><strong>{title}</strong><p className="muted small m-0 mt-1">{text}</p></div></div>)}</div></section>}
  {user.length > 0 && <section className="mb-6"><h2 className="mb-3 text-lg font-semibold">{tr('ฟังก์ชันที่ใช้บ่อย')}</h2><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{user.map(card)}</div></section>}
  {admin.length > 0 && <section className="mb-6"><h2 className="mb-3 text-lg font-semibold">{tr('สำหรับผู้ดูแลระบบ')}</h2><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{admin.map(card)}</div></section>}
  {visible.length === 0 && <p className="muted">{tr('ไม่พบหัวข้อที่ตรงกับคำค้น')}</p>}
  {!needle && <section className="mb-6"><h2 className="mb-3 text-lg font-semibold">{tr('คำถามที่พบบ่อย')}</h2><div className="grid gap-2">{faq.map(([a, b], i) => <details key={i} className="card padded group"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-medium">{a}<ChevronDown className="size-4 shrink-0 transition-transform group-open:rotate-180" /></summary><p className="muted m-0 mt-2 text-sm">{b}</p></details>)}</div></section>}
  <p className="muted small">{tr('ต้องการความช่วยเหลือเพิ่มเติม ติดต่อผู้ดูแลระบบขององค์กร')}</p>
 </>;
}
