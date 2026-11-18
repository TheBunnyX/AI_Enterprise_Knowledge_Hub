'use client';
import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Boxes, ChartNoAxesCombined, Coins, Database, Download, FileText, HardDrive, Library, MessagesSquare, Search, Users, Zap, type LucideIcon } from 'lucide-react';
import { tr, useLang } from '../lib/i18n';
import { api, date, fmt, money, money4, type Analytics, type Audit } from './api';
import { BudgetNotice } from './features';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Sel } from './ui/sel';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { cn } from '../lib/utils';

export const COLORS = ['#2877ff', '#8b5cf6', '#2dd4bf', '#ffad47', '#f43f5e', '#64748b'];
export const SERIES = { requests: { get label() { return tr('คำถาม'); }, color: '#2877ff' }, cost: { get label() { return tr('ค่าใช้จ่าย (USD)'); }, color: '#ffad47' }, tokens: { get label() { return tr('โทเคน'); }, color: '#8b5cf6' } } as const;
export type Series = keyof typeof SERIES;
export const bytes = (n = 0) => (n >= 1 << 30 ? (n / (1 << 30)).toFixed(2) + ' GB' : n >= 1 << 20 ? (n / (1 << 20)).toFixed(1) + ' MB' : n >= 1024 ? (n / 1024).toFixed(0) + ' KB' : n + ' B');
export const price = (n = 0) => (n > 0 && n < 0.01 ? '<$0.01' : money(n));
export const STATUS: Record<string, string> = { ready: 'พร้อมใช้งาน', processing: 'กำลังประมวลผล', failed: 'ล้มเหลว', pending: 'รอดำเนินการ', quarantined: 'กักกัน' };

export function Stat({ icon: Icon, title, value, note, tone = 'text-primary bg-primary/10' }: { icon: LucideIcon; title: string; value: string; note?: string; tone?: string }) {
  return <Card className="gap-0 py-4"><CardContent className="flex items-center gap-3 px-4">
    <span className={cn('grid size-11 shrink-0 place-items-center rounded-2xl', tone)}><Icon className="size-5" /></span>
    <div className="min-w-0"><p className="text-sm text-muted-foreground">{title}</p><strong className="block truncate text-xl leading-tight">{value}</strong>{note && <small className="block truncate text-xs text-muted-foreground">{note}</small>}</div>
  </CardContent></Card>;
}

export function Blank({ icon: Icon, title, text }: { icon: LucideIcon; title: string; text: string }) {
  return <div className="flex flex-col items-center gap-1 py-10 text-center text-muted-foreground"><Icon className="size-9" strokeWidth={1.3} /><strong className="text-foreground">{title}</strong><p className="text-sm">{text}</p></div>;
}

export function AnalyticsPage({ data, audit }: { data?: Analytics; audit: Audit[] }) {
  const { lang } = useLang();
  const [days, setDays] = useState('30'); const [series, setSeries] = useState<Series>('requests');
  const [find, setFind] = useState(''); const [rows, setRows] = useState(10);
  const q = useQuery({ queryKey: ['analytics-filtered', days], queryFn: () => api<Analytics>(`/analytics?days=${days}`) });
  const a = q.data || data;
  const daily = useMemo(() => (a?.daily || []).map((d) => ({ ...d, tokens: (d.input_tokens || 0) + (d.output_tokens || 0) })), [a]);
  const modelShare = useMemo(() => {
    const ms: { name: string; value: number; other?: boolean }[] = [...(a?.models || [])].sort((x, y) => y.value - x.value);
    if (ms.length <= 6) return ms;
    const rest = ms.slice(5);
    return [...ms.slice(0, 5), { name: tr('อื่น ๆ ({v1} โมเดล)',{v1:rest.length}), value: rest.reduce((n, m) => n + m.value, 0), other: true }];
  }, [a, lang]);
  const tokens = (a?.input_tokens || 0) + (a?.output_tokens || 0);
  const active = daily.filter((d) => d.requests).length;
  const events = useMemo(() => audit.filter((e) => !find.trim() || `${e.actor} ${e.action} ${e.detail} ${e.ip||''}`.toLowerCase().includes(find.trim().toLowerCase())), [audit, find]);
  const statuses = Object.entries(a?.document_status || {});
  const s = SERIES[series];

  return <>
    <div className="page-heading">
      <div><h1>{tr('รายงานและสถิติ')}</h1><p>{tr('ติดตามการใช้งาน AI และค่าใช้จ่ายที่บันทึกจากระบบจริง')}</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <Sel aria-label={tr('ช่วงเวลา')} value={days} onChange={(e) => setDays(e.target.value)} className="w-44"><option value="7">{tr('7 วันที่ผ่านมา')}</option><option value="30">{tr('30 วันที่ผ่านมา')}</option><option value="90">{tr('90 วันที่ผ่านมา')}</option><option value="365">{tr('1 ปีที่ผ่านมา')}</option></Sel>
        <Button asChild variant="outline"><a href={`/api/usage/export?days=${days}`}><Download className="size-4" />{tr('ส่งออก CSV')}</a></Button>
      </div>
    </div>
    <BudgetNotice />

    <div className="stats-grid" data-testid="stats">
      <Stat icon={Users} title={tr('ผู้ใช้งาน')} value={fmt(a?.users)} />
      <Stat icon={MessagesSquare} title={tr('จำนวนคำถาม')} value={fmt(a?.requests)} note={tr('ใช้งาน {active} จาก {v2} วัน',{active,v2:daily.length})} tone="text-teal-600 bg-teal-500/10" />
      <Stat icon={FileText} title={tr('เอกสารในระบบ')} value={fmt(a?.documents)} note={tr('พื้นที่ {v1}',{v1:bytes(a?.storage_bytes)})} tone="text-violet-600 bg-violet-500/10" />
      <Stat icon={Coins} title={tr('ค่าใช้จ่าย AI (USD)')} value={money(a?.cost)} note={a?.estimated ? tr('ประมาณการตามราคาที่กำหนด') : tr('ค่าใช้จ่ายที่บันทึกจริง')} tone="text-orange-600 bg-orange-500/10" />
    </div>
    <div className="stats-grid" data-testid="stats-more">
      <Stat icon={Zap} title={tr('โทเคนทั้งหมด')} value={fmt(tokens)} note={tr('เข้า {v1} · ออก {v2}',{v1:fmt(a?.input_tokens),v2:fmt(a?.output_tokens)})} />
      <Stat icon={Library} title={tr('คลังความรู้')} value={fmt(a?.knowledge_bases)} tone="text-teal-600 bg-teal-500/10" />
      <Stat icon={MessagesSquare} title={tr('บทสนทนา')} value={fmt(a?.conversations)} note={tr('{v1} ข้อความ',{v1:fmt(a?.messages)})} tone="text-violet-600 bg-violet-500/10" />
      <Stat icon={HardDrive} title={tr('ค่าเฉลี่ยต่อคำถาม')} value={a?.requests ? price(a.cost / a.requests) : '—'} note={a?.requests ? tr('{v1} โทเคน/คำถาม',{v1:fmt(Math.round(tokens / a.requests))}) : undefined} tone="text-orange-600 bg-orange-500/10" />
    </div>

    <div className="chart-columns">
      <Card className="h-full">
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <div><CardTitle>{tr('การใช้งานรายวัน')}</CardTitle><CardDescription>{tr('{label} ต่อวัน · {days} วันล่าสุด',{label:s.label,days})}</CardDescription></div>
          <div role="group" aria-label={tr('เลือกข้อมูลกราฟ')} className="flex flex-wrap gap-1">
            {(Object.keys(SERIES) as Series[]).map((k) => <Button key={k} type="button" size="sm" variant={series === k ? 'default' : 'outline'} aria-pressed={series === k} onClick={() => setSeries(k)}>{SERIES[k].label}</Button>)}
          </div>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col">
          {a?.requests ? <div className="usage-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={daily} margin={{ top: 15, right: 20, left: -10, bottom: 5 }}>
            <defs><linearGradient id="seriesFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={s.color} stopOpacity={0.28} /><stop offset="100%" stopColor={s.color} stopOpacity={0.01} /></linearGradient></defs>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(v) => String(v).slice(5)} axisLine={false} tickLine={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} minTickGap={24} />
            <YAxis allowDecimals={series === 'cost'} axisLine={false} tickLine={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
            <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid var(--border)' }} />
            <Area name={s.label} type="monotone" dataKey={series} stroke={s.color} fill="url(#seriesFill)" strokeWidth={2.5} dot={daily.length <= 31 ? { r: 3, fill: s.color } : false} />
          </AreaChart></ResponsiveContainer></div> : <Blank icon={ChartNoAxesCombined} title={tr('ยังไม่มีการใช้งานในช่วงเวลานี้')} text={tr('เริ่มสนทนากับเอกสาร แล้วข้อมูลจริงจะแสดงที่นี่')} />}
        </CardContent>
      </Card>
      <Card className="h-full">
        <CardHeader><CardTitle>{tr('สัดส่วนการใช้งานโมเดล AI')}</CardTitle><CardDescription>{tr('นับตามจำนวนคำถาม')}</CardDescription></CardHeader>
        <CardContent className="flex flex-1 flex-col justify-center">
          {a?.models.length ? <>
            <div className="donut-chart"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={modelShare} dataKey="value" innerRadius={65} outerRadius={88} paddingAngle={0} stroke="none">{modelShare.map((m, i) => <Cell key={m.name} fill={m.other ? COLORS[5] : COLORS[i % COLORS.length]} />)}</Pie><Tooltip /></PieChart></ResponsiveContainer>
              <div><small>{tr('ทั้งหมด')}</small><strong>{fmt(a.requests)}</strong><small>{tr('คำถาม')}</small></div></div>
            <div className="chart-legend w-full">{modelShare.map((m, i) => <div key={m.name}><i style={{ background: m.other ? COLORS[5] : COLORS[i % COLORS.length] }} /><span>{m.name}</span><strong>{fmt(m.value)}</strong></div>)}</div>
          </> : <Blank icon={Boxes} title={tr('ยังไม่มีการเรียกโมเดล')} text={tr('สถิติจะแสดงเมื่อเริ่มใช้งาน')} />}
        </CardContent>
      </Card>
    </div>

    <div className="chart-columns">
      <Card>
        <CardHeader><CardTitle>{tr('การใช้งานแยกตามโมเดล')}</CardTitle><CardDescription>{tr('คำถาม โทเคน และค่าใช้จ่ายของแต่ละโมเดล')}</CardDescription></CardHeader>
        <CardContent>
          {a?.model_rows?.length ? <Table><TableHeader><TableRow><TableHead>{tr('โมเดล')}</TableHead><TableHead className="text-right">{tr('คำถาม')}</TableHead><TableHead className="text-right">{tr('โทเคนเข้า')}</TableHead><TableHead className="text-right">{tr('โทเคนออก')}</TableHead><TableHead className="text-right">{tr('ค่าใช้จ่าย')}</TableHead></TableRow></TableHeader>
            <TableBody>{a.model_rows.map((m) => <TableRow key={m.name}><TableCell className="max-w-56 truncate font-medium">{m.name}</TableCell><TableCell className="text-right">{fmt(m.requests)}</TableCell><TableCell className="text-right">{fmt(m.input_tokens)}</TableCell><TableCell className="text-right">{fmt(m.output_tokens)}</TableCell><TableCell className="text-right tabular-nums">{money4(m.cost)}</TableCell></TableRow>)}</TableBody></Table>
            : <Blank icon={Boxes} title={tr('ยังไม่มีข้อมูลโมเดล')} text={tr('ตารางจะแสดงเมื่อมีการเรียกใช้')} />}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>{tr('ผู้ใช้งานสูงสุด')}</CardTitle><CardDescription>{tr('10 อันดับแรกตามจำนวนคำถาม')}</CardDescription></CardHeader>
        <CardContent>
          {a?.top_users?.length ? <Table><TableHeader><TableRow><TableHead>{tr('ผู้ใช้')}</TableHead><TableHead className="text-right">{tr('คำถาม')}</TableHead><TableHead className="text-right">{tr('โทเคน')}</TableHead><TableHead className="text-right">{tr('ค่าใช้จ่าย')}</TableHead></TableRow></TableHeader>
            <TableBody>{a.top_users.map((u, i) => <TableRow key={u.name + i}><TableCell className="max-w-48 truncate font-medium">{i + 1}. {u.name}</TableCell><TableCell className="text-right">{fmt(u.requests)}</TableCell><TableCell className="text-right">{fmt(u.input_tokens + u.output_tokens)}</TableCell><TableCell className="text-right">{price(u.cost)}</TableCell></TableRow>)}</TableBody></Table>
            : <Blank icon={Users} title={tr('ยังไม่มีข้อมูลผู้ใช้')} text={tr('จะแสดงเมื่อมีการใช้งาน')} />}
        </CardContent>
      </Card>
    </div>

    <Card>
      <CardHeader><CardTitle>{tr('สถานะเอกสาร')}</CardTitle><CardDescription>{tr('เอกสาร {v1} ไฟล์ · {v2}',{v1:fmt(a?.documents),v2:bytes(a?.storage_bytes)})}</CardDescription></CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {statuses.length ? statuses.map(([k, v]) => <Badge key={k} variant={k === 'failed' ? 'destructive' : 'secondary'} className="px-3 py-1 text-sm"><Database className="size-3.5" />{STATUS[k] ? tr(STATUS[k]) : k} · {fmt(v)}</Badge>) : <span className="text-sm text-muted-foreground">{tr('ยังไม่มีเอกสาร')}</span>}
      </CardContent>
    </Card>


    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div><CardTitle>{tr('กิจกรรมล่าสุดในระบบ')}</CardTitle><CardDescription>{tr('บันทึกตรวจสอบการทำงาน · {v1} จาก {v2} รายการ',{v1:fmt(events.length),v2:fmt(audit.length)})}</CardDescription></div>
        <div className="relative w-64 max-w-full"><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label={tr('ค้นหากิจกรรม')} placeholder={tr('ค้นหาผู้ใช้ กิจกรรม รายละเอียด')} className="pl-10!" value={find} onChange={(e) => { setFind(e.target.value); setRows(10); }} /></div>
      </CardHeader>
      <CardContent>
        {events.length ? <>
          <Table><TableHeader><TableRow><TableHead>{tr('เวลา')}</TableHead><TableHead>{tr('กิจกรรม')}</TableHead><TableHead>{tr('รายละเอียด')}</TableHead><TableHead>{tr('ผู้ดำเนินการ')}</TableHead><TableHead>IP</TableHead></TableRow></TableHeader>
            <TableBody>{events.slice(0, rows).map((e) => <TableRow key={e.id}><TableCell className="whitespace-nowrap text-muted-foreground">{date(e.created_at)}</TableCell><TableCell className="font-medium">{e.action}</TableCell><TableCell className="max-w-80 truncate" title={e.detail}>{e.detail || '—'}</TableCell><TableCell>{e.actor}</TableCell><TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{e.ip || '—'}</TableCell></TableRow>)}</TableBody></Table>
          {events.length > rows && <div className="mt-3 flex justify-center"><Button variant="outline" size="sm" onClick={() => setRows(rows + 20)}>{tr('แสดงเพิ่ม ({v1} รายการ)',{v1:fmt(events.length - rows)})}</Button></div>}
        </> : <Blank icon={Search} title={audit.length ? tr('ไม่พบกิจกรรมที่ค้นหา') : tr('ยังไม่มีกิจกรรม')} text={audit.length ? tr('ลองใช้คำค้นอื่น') : tr('กิจกรรมจะแสดงเมื่อมีการใช้งาน')} />}
      </CardContent>
    </Card>
  </>;
}
