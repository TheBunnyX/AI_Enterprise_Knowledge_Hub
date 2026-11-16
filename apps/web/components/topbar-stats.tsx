'use client';
import Link from 'next/link';
import { ArrowRight, Database, Gauge, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { fmt, money as money2 } from './api';
import { tr } from '../lib/i18n';

/** USD; amounts under one cent keep up to 4 decimals so tiny usage doesn't read as $0.00. */
const money = (n = 0) => (n > 0 && n < 0.01 ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 4 }).format(n) : money2(n));
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from './ui/popover';
import { cn } from '../lib/utils';

const formatBytes = (b = 0) => (b < 1024 * 1024 ? `${(b / 1024).toFixed(0)} KB` : b < 1024 ** 3 ? `${(b / 1024 / 1024).toFixed(2)} MB` : `${(b / 1024 ** 3).toFixed(2)} GB`);

/** Quota usage level → colour. */
const level = (pct: number) => (pct >= 90 ? { bar: 'bg-red-500', text: 'text-red-600', label: tr('ใกล้เต็มโควตา') } : pct >= 70 ? { bar: 'bg-amber-500', text: 'text-amber-600', label: tr('ใช้ไปมากแล้ว') } : { bar: 'bg-emerald-500', text: 'text-emerald-600', label: tr('ปกติ') });

function StatChip({ icon: Icon, tone, label, value, children, extra }: { icon: LucideIcon; tone: string; label: string; value: ReactNode; children: ReactNode; extra?: ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label={label} className="group flex h-11 min-w-[168px] shrink-0 cursor-pointer tabular-nums max-[1180px]:min-w-[120px] max-[760px]:min-w-0 items-center gap-2.5 rounded-lg border border-border bg-background px-2.5 text-left transition-colors hover:border-primary/40 hover:bg-accent/40 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none data-[state=open]:border-primary/50 data-[state=open]:bg-accent/50 max-[760px]:h-9 max-[760px]:px-2">
          <span className={cn('grid size-7 shrink-0 place-items-center rounded-md', tone)}><Icon className="size-4" /></span>
          <span className="flex min-w-0 flex-col leading-tight">
            <span className="text-[11px] text-muted-foreground max-[1180px]:hidden">{label}</span>
            <span className="flex items-center gap-1.5 text-[13px] font-semibold text-slate-800 dark:text-slate-200">{value}</span>
            {extra}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">{children}</PopoverContent>
    </Popover>
  );
}

/** Same footprint as a loaded chip, so the topbar doesn't jump while data arrives. */
function ChipSkeleton({ label }: { label: string }) {
  return (
    <div aria-label={label} aria-busy="true" className="flex h-11 w-[168px] shrink-0 items-center gap-2.5 rounded-lg border border-border bg-background px-2.5 max-[1180px]:w-[120px] max-[760px]:h-9 max-[760px]:w-[84px] max-[760px]:px-2">
      <span className="size-7 shrink-0 animate-pulse rounded-md bg-muted" />
      <span className="flex flex-1 flex-col gap-1.5">
        <span className="h-2 w-16 animate-pulse rounded bg-muted max-[1180px]:hidden" />
        <span className="h-2.5 w-full animate-pulse rounded bg-muted" />
      </span>
    </div>
  );
}

export function TopbarStats({ storageBytes, documents = 0, quota, quotaLoading, isAdmin }: { storageBytes?: number; documents?: number; quota?: { monthly_budget: number; month_spend: number }; quotaLoading?: boolean; isAdmin: boolean }) {
  if (storageBytes === undefined || (quotaLoading && !quota))
    return (
      <div className="flex items-center gap-2" aria-label={tr('สรุปการใช้งาน')}>
        <ChipSkeleton label={tr('พื้นที่จัดเก็บเอกสาร')} />
        {(quotaLoading || quota) && <ChipSkeleton label={tr('โควตาเดือนนี้')} />}
      </div>
    );
  const budget = quota?.monthly_budget || 0;
  const spend = quota?.month_spend || 0;
  const pct = budget ? Math.min(100, Math.round((spend / budget) * 100)) : 0;
  const lv = level(pct);
  const remain = Math.max(0, budget - spend);
  const docsHref = isAdmin ? '/super-admin/documents' : '/documents';
  const usageHref = isAdmin ? '/super-admin/billing' : '/analytics';

  return (
    <div className="flex items-center gap-2 max-[430px]:hidden" aria-label={tr('สรุปการใช้งาน')}>
      <StatChip icon={Database} tone="bg-blue-50 text-blue-600" label={tr('พื้นที่จัดเก็บเอกสาร')} value={<>{formatBytes(storageBytes)}<span className="font-normal text-muted-foreground max-[760px]:hidden">{tr('· {v1} ไฟล์',{v1:fmt(documents)})}</span></>}>
        <div className="flex items-center gap-2 text-sm font-semibold"><Database className="size-4 text-blue-600" />{tr('พื้นที่จัดเก็บเอกสาร')}</div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-md bg-muted p-2.5"><div className="text-xs text-muted-foreground">{tr('ใช้พื้นที่')}</div><div className="text-lg font-semibold">{formatBytes(storageBytes)}</div></div>
          <div className="rounded-md bg-muted p-2.5"><div className="text-xs text-muted-foreground">{tr('เอกสารในระบบ')}</div><div className="text-lg font-semibold">{tr('{v1} ไฟล์',{v1:fmt(documents)})}</div></div>
        </div>
        <p className="mt-3 text-xs leading-5 text-muted-foreground">{tr('ขนาดรวมของไฟล์เอกสารที่อัปโหลดในองค์กรของคุณ')}</p>
        <PopoverClose asChild><Button asChild variant="outline" size="sm" className="mt-3 w-full"><Link href={docsHref}>{tr('จัดการเอกสาร')}<ArrowRight className="size-3.5" /></Link></Button></PopoverClose>
      </StatChip>

      {quota && (
        <StatChip icon={Gauge} tone={budget ? (pct >= 90 ? 'bg-red-50 text-red-600' : pct >= 70 ? 'bg-amber-50 text-amber-600' : 'bg-emerald-50 text-emerald-600') : 'bg-violet-50 text-violet-600'} label={tr('โควตาเดือนนี้')}
          value={budget ? <><span className={lv.text}>{pct}%</span><span className="font-normal text-muted-foreground max-[760px]:hidden">· {money(spend)} / {money(budget)}</span></> : <><Badge variant="secondary" className="h-5 px-1.5">{tr('ไม่จำกัด')}</Badge><span className="font-normal text-muted-foreground max-[760px]:hidden">{tr('ใช้ไป {v1}',{v1:money(spend)})}</span></>}
          extra={budget ? <span className="mt-1 block h-1 w-full overflow-hidden rounded-full bg-muted max-[760px]:hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={tr('สัดส่วนโควตาที่ใช้')}><span className={cn('block h-full rounded-full', lv.bar)} style={{ width: `${pct}%` }} /></span> : undefined}>
          <div className="flex items-center gap-2 text-sm font-semibold"><Gauge className="size-4" />{tr('โควตาค่าใช้จ่าย AI เดือนนี้')}</div>
          {budget ? (
            <>
              <div className="mt-3 flex items-end justify-between"><span className={cn('text-2xl font-semibold', lv.text)}>{pct}%</span><Badge variant="outline" className={lv.text}>{lv.label}</Badge></div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-muted"><div className={cn('h-full rounded-full', lv.bar)} style={{ width: `${pct}%` }} /></div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div className="rounded-md bg-muted p-2"><div className="text-[11px] text-muted-foreground">{tr('ใช้ไป')}</div><div className="text-sm font-semibold">{money(spend)}</div></div>
                <div className="rounded-md bg-muted p-2"><div className="text-[11px] text-muted-foreground">{tr('คงเหลือ')}</div><div className="text-sm font-semibold">{money(remain)}</div></div>
                <div className="rounded-md bg-muted p-2"><div className="text-[11px] text-muted-foreground">{tr('โควตา')}</div><div className="text-sm font-semibold">{money(budget)}</div></div>
              </div>
            </>
          ) : (
            <div className="mt-3 rounded-md bg-muted p-3"><div className="text-xs text-muted-foreground">{tr('ใช้ไปเดือนนี้')}</div><div className="text-2xl font-semibold">{money(spend)}</div><div className="mt-1 text-xs text-muted-foreground">{tr('บัญชีนี้ไม่มีเพดานค่าใช้จ่ายรายเดือน')}</div></div>
          )}
          <p className="mt-3 text-xs leading-5 text-muted-foreground">{tr('คิดจากค่าใช้โมเดล AI ของคุณในเดือนปฏิทินนี้ (เวลา UTC) และเริ่มนับใหม่ทุกต้นเดือน')}</p>
          <PopoverClose asChild><Button asChild variant="outline" size="sm" className="mt-3 w-full"><Link href={usageHref}>{tr('ดูรายงานการใช้งาน')}<ArrowRight className="size-3.5" /></Link></Button></PopoverClose>
        </StatChip>
      )}
    </div>
  );
}
