'use client';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import { cn } from '../lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip';
import { tr } from '../lib/i18n';

type Service = { key: string; label: string; up: boolean | null };
const PLACEHOLDER = ['API', 'ฐานข้อมูล', 'จัดเก็บเอกสาร', 'ค้นหาเวกเตอร์', 'คิวประมวลผล', 'Antivirus'];

/** Six live dots for the infrastructure services: green = up, red = down. */
export function InfraStatus({ isAdmin }: { isAdmin: boolean }) {
  const q = useQuery({ queryKey: ['system-health'], queryFn: () => api<{ services: Service[] }>('/system/health'), refetchInterval: 30000 });
  const services = q.data?.services;
  const used = services?.filter(s => s.up !== null) || [];
  const down = used.filter(s => !s.up).length;
  const summary = !services ? (q.isError ? tr('ตรวจสอบไม่ได้') : tr('กำลังตรวจสอบ...')) : down ? tr('ขัดข้อง {down} บริการ',{down}) : tr('ปกติทั้งหมด');
  const body = (
    <>
      <div className="flex items-center justify-between gap-2 text-xs">
        <span className="text-slate-500 dark:text-slate-400">{tr('ระบบและโครงสร้างพื้นฐาน')}</span>
        <span className={cn('font-medium', !services ? 'text-muted-foreground' : down ? 'text-red-600' : 'text-emerald-600')}>{services ? `${used.length - down}/${used.length}` : ''}</span>
      </div>
      <div className="mt-2 flex items-center justify-between gap-1" aria-label={tr('ระบบและโครงสร้างพื้นฐาน: {summary}',{summary})}>
        {(services || PLACEHOLDER.map(label => ({ key: label, label, up: undefined }))).map(s => (
          <Tooltip key={s.key}>
            <TooltipTrigger asChild>
              <span
                role="img"
                aria-label={`${tr(s.label)}: ${s.up === undefined ? tr('กำลังตรวจสอบ') : s.up === null ? tr('ไม่ได้ใช้งาน') : s.up ? tr('ทำงานปกติ') : tr('ขัดข้อง')}`}
                className={cn('size-3.5 rounded-full ring-2 ring-white dark:ring-card', s.up === undefined ? (q.isError ? 'bg-red-500' : 'animate-pulse bg-slate-200') : s.up === null ? 'bg-slate-300' : s.up ? 'bg-emerald-500' : 'bg-red-500 animate-pulse')}
              />
            </TooltipTrigger>
            <TooltipContent side="top">{tr(s.label)} · {s.up === undefined ? (q.isError ? tr('ตรวจสอบไม่ได้') : tr('กำลังตรวจสอบ')) : s.up === null ? tr('ไม่ได้ใช้งาน') : s.up ? tr('ทำงานปกติ') : tr('ขัดข้อง')}</TooltipContent>
          </Tooltip>
        ))}
      </div>
    </>
  );
  const box = 'mx-1 mb-2 block rounded-lg border border-border bg-white dark:bg-card px-3 py-2.5';
  return (
    <TooltipProvider delayDuration={150}>
      {isAdmin ? <Link href="/super-admin/system" className={cn(box, 'transition-colors hover:border-primary/40 hover:bg-accent/40')}>{body}</Link> : <div className={box}>{body}</div>}
    </TooltipProvider>
  );
}
