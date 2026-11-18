'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ArrowRight, Boxes, Building2, ChartNoAxesCombined, CheckCircle2, Coins, Database, Download, FileText, Globe, HardDrive, KeyRound, Library, MessagesSquare, Search, ShieldCheck, Users, Zap } from 'lucide-react';
import { tr, useLang } from '../lib/i18n';
import { api, date, fmt, money, money4, type Analytics, type Audit, type Org } from './api';
import { Blank, COLORS, SERIES, STATUS, Stat, bytes, price, type Series } from './analytics';
import { BudgetNotice } from './features';
import { H1 } from './page-title';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Input } from './ui/input';
import { Sel } from './ui/sel';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';

const DAY_CHOICES = ['7', '30', '90', '365'];
const dayLabel = (d: string) => ({ '7': tr('7 วันที่ผ่านมา'), '30': tr('30 วันที่ผ่านมา'), '90': tr('90 วันที่ผ่านมา'), '365': tr('1 ปีที่ผ่านมา') } as Record<string, string>)[d];
const DaysSelect = ({ value, onChange }: { value: string; onChange: (v: string) => void }) => <Sel aria-label={tr('ช่วงเวลา')} value={value} onChange={(e) => onChange(e.target.value)} className="w-44">{DAY_CHOICES.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}</Sel>;

function useAnalytics(days: string, tenant = '') {
  return useQuery({ queryKey: ['admin-analytics', days, tenant], queryFn: () => api<Analytics>(`/analytics?days=${days}${tenant ? '&tenant_id=' + tenant : ''}`) });
}

function DailyChart({ daily, series, empty }: { daily: Record<string, number | string>[]; series: Series; empty: boolean }) {
  const s = SERIES[series];
  if (empty) return <Blank icon={ChartNoAxesCombined} title={tr('ยังไม่มีการใช้งานในช่วงเวลานี้')} text={tr('เริ่มสนทนากับเอกสาร แล้วข้อมูลจริงจะแสดงที่นี่')} />;
  return <div className="usage-chart" style={{ flex: "none", height: 280 }}><ResponsiveContainer width="100%" height="100%"><AreaChart data={daily} margin={{ top: 15, right: 20, left: -10, bottom: 5 }}>
    <defs><linearGradient id={'fill-' + series} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={s.color} stopOpacity={0.28} /><stop offset="100%" stopColor={s.color} stopOpacity={0.01} /></linearGradient></defs>
    <CartesianGrid stroke="var(--border)" vertical={false} />
    <XAxis dataKey="date" tickFormatter={(v) => String(v).slice(5)} axisLine={false} tickLine={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} minTickGap={24} />
    <YAxis allowDecimals={series === 'cost'} axisLine={false} tickLine={false} tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }} />
    <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid var(--border)' }} />
    <Area name={s.label} type="monotone" dataKey={series} stroke={s.color} fill={`url(#fill-${series})`} strokeWidth={2.5} dot={daily.length <= 31 ? { r: 3, fill: s.color } : false} />
  </AreaChart></ResponsiveContainer></div>;
}

/** Super Admin home: how big the platform is and whether it is healthy. No money and no audit trail here. */
export function AdminOverview() {
  const { lang } = useLang();
  const [days, setDays] = useState('30');
  const q = useAnalytics(days);
  const a = q.data;
  const orgs = useQuery({ queryKey: ['orgs'], queryFn: () => api<Org[]>('/admin/organizations') });
  const health = useQuery({ queryKey: ['system-health'], queryFn: () => api<{ services: { key: string; label: string; up: boolean | null }[] }>('/system/health'), refetchInterval: 30000 });
  const daily = a?.daily || [];
  const active = daily.filter((d) => d.requests).length;
  const used = (health.data?.services || []).filter((x) => x.up !== null);
  const down = used.filter((x) => !x.up).length;
  const statuses = Object.entries(a?.document_status || {});
  const modelShare = useMemo(() => {
    const ms: { name: string; value: number; other?: boolean }[] = [...(a?.models || [])].sort((x, y) => y.value - x.value);
    if (ms.length <= 6) return ms;
    const rest = ms.slice(5);
    return [...ms.slice(0, 5), { name: tr('อื่น ๆ ({v1} โมเดล)', { v1: rest.length }), value: rest.reduce((n, m) => n + m.value, 0), other: true }];
  }, [a, lang]);

  return <>
    <div className="page-heading">
      <div><h1>{tr('สวัสดีครับ, Super Admin 👋')}</h1><p>{tr('ภาพรวม AI Knowledge Hub และการใช้งานของทุกองค์กร')}</p></div>
      <DaysSelect value={days} onChange={setDays} />
    </div>

    <div className="stats-grid" data-testid="overview-stats">
      <Stat icon={Building2} title={tr('องค์กรทั้งหมด')} value={fmt(a?.organizations)} note={tr('{v1} ผู้ใช้งาน', { v1: fmt(a?.users) })} />
      <Stat icon={FileText} title={tr('เอกสารในระบบ')} value={fmt(a?.documents)} note={tr('พื้นที่ {v1}', { v1: bytes(a?.storage_bytes) })} tone="text-violet-600 bg-violet-500/10" />
      <Stat icon={Library} title={tr('คลังความรู้')} value={fmt(a?.knowledge_bases)} note={tr('{v1} บทสนทนา · {v2} ข้อความ', { v1: fmt(a?.conversations), v2: fmt(a?.messages) })} tone="text-teal-600 bg-teal-500/10" />
      <Stat icon={ShieldCheck} title={tr('บริการที่ทำงานปกติ')} value={health.data ? `${used.length - down}/${used.length}` : '—'} note={health.isError ? tr('ตรวจสอบไม่ได้') : down ? tr('ขัดข้อง {down} บริการ', { down }) : tr('ปกติทั้งหมด')} tone={down ? 'text-red-600 bg-red-500/10' : 'text-emerald-600 bg-emerald-500/10'} />
    </div>

    <div className="chart-columns">
      <Card className="h-full">
        <CardHeader><CardTitle>{tr('การใช้งานรายวัน')}</CardTitle><CardDescription>{tr('{v1} · ใช้งาน {active} จาก {v2} วัน', { v1: tr('จำนวนคำถาม'), active, v2: daily.length })}</CardDescription></CardHeader>
        <CardContent className="flex flex-1 flex-col"><DailyChart daily={daily} series="requests" empty={!a?.requests} /></CardContent>
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

    <Card>
      <CardHeader><CardTitle>{tr('สถานะเอกสาร')}</CardTitle><CardDescription>{tr('เอกสาร {v1} ไฟล์ · {v2}', { v1: fmt(a?.documents), v2: bytes(a?.storage_bytes) })}</CardDescription></CardHeader>
      <CardContent className="flex flex-wrap gap-2">
        {statuses.length ? statuses.map(([k, v]) => <Badge key={k} variant={k === 'failed' ? 'destructive' : 'secondary'} className="px-3 py-1 text-sm"><Database className="size-3.5" />{STATUS[k] ? tr(STATUS[k]) : k} · {fmt(v)}</Badge>) : <span className="text-sm text-muted-foreground">{tr('ยังไม่มีเอกสาร')}</span>}
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="flex-row items-center justify-between"><div><CardTitle>{tr('องค์กรในระบบ')}</CardTitle><CardDescription>{tr('{v1} องค์กร', { v1: fmt(orgs.data?.length) })}</CardDescription></div><Button asChild variant="ghost" size="sm"><Link href="/super-admin/organizations">{tr('จัดการองค์กร')}<ArrowRight className="size-4" /></Link></Button></CardHeader>
      <CardContent>
        <Table><TableHeader><TableRow><TableHead>{tr('องค์กร')}</TableHead><TableHead className="text-right">{tr('ผู้ใช้')}</TableHead><TableHead className="text-right">{tr('เอกสาร')}</TableHead><TableHead>{tr('สถานะ')}</TableHead></TableRow></TableHeader>
          <TableBody>{orgs.data?.slice(0, 8).map((o) => <TableRow key={o.id}><TableCell className="font-medium">{o.name}</TableCell><TableCell className="text-right">{fmt(o.users)}</TableCell><TableCell className="text-right">{fmt(o.documents)}</TableCell><TableCell><Badge variant={o.status === 'active' ? 'secondary' : 'outline'}>{o.status === 'active' ? tr('ใช้งาน') : o.status}</Badge></TableCell></TableRow>)}</TableBody></Table>
      </CardContent>
    </Card>
  </>;
}

/** Money only: what was spent, on which models, by which organisations and people. */
export function AdminBilling() {
  const [days, setDays] = useState('30');
  const [tenant, setTenant] = useState('');
  const [series, setSeries] = useState<Series>('cost');
  const [modelRows, setModelRows] = useState(10);
  const q = useAnalytics(days, tenant);
  const a = q.data;
  const orgs = useQuery({ queryKey: ['orgs'], queryFn: () => api<Org[]>('/admin/organizations') });
  const daily = useMemo(() => (a?.daily || []).map((d) => ({ ...d, tokens: (d.input_tokens || 0) + (d.output_tokens || 0) })), [a]);
  const tokens = (a?.input_tokens || 0) + (a?.output_tokens || 0);
  const choices = ['cost', 'tokens', 'requests'] as Series[];

  return <>
    <div className="page-heading">
      <div><h1>{tr('การใช้งานและค่าใช้จ่าย')}</h1><p>{tr('ค่าใช้จ่าย AI แยกตามช่วงเวลา โมเดล องค์กร และผู้ใช้ ตามที่บันทึกจากระบบจริง')}</p></div>
      <div className="flex flex-wrap items-center gap-2">
        <Sel aria-label={tr('เลือกองค์กร')} value={tenant} onChange={(e) => setTenant(e.target.value)} className="w-52"><option value="">{tr('ทุกองค์กร')}</option>{orgs.data?.map((o) => <option value={o.id} key={o.id}>{o.name}</option>)}</Sel>
        <DaysSelect value={days} onChange={setDays} />
        <Button asChild variant="outline"><a href={`/api/usage/export?days=${days}${tenant ? '&tenant_id=' + tenant : ''}`}><Download className="size-4" />{tr('ส่งออก CSV')}</a></Button>
      </div>
    </div>
    <BudgetNotice />

    <div className="stats-grid" data-testid="billing-stats">
      <Stat icon={Coins} title={tr('ค่าใช้จ่าย AI (USD)')} value={money(a?.cost)} note={a?.estimated ? tr('ประมาณการตามราคาที่กำหนด') : tr('ค่าใช้จ่ายที่บันทึกจริง')} tone="text-orange-600 bg-orange-500/10" />
      <Stat icon={MessagesSquare} title={tr('จำนวนคำถาม')} value={fmt(a?.requests)} tone="text-teal-600 bg-teal-500/10" />
      <Stat icon={Zap} title={tr('โทเคนทั้งหมด')} value={fmt(tokens)} note={tr('เข้า {v1} · ออก {v2}', { v1: fmt(a?.input_tokens), v2: fmt(a?.output_tokens) })} />
      <Stat icon={HardDrive} title={tr('ค่าเฉลี่ยต่อคำถาม')} value={a?.requests ? price(a.cost / a.requests) : '—'} note={a?.requests ? tr('{v1} โทเคน/คำถาม', { v1: fmt(Math.round(tokens / a.requests)) }) : undefined} tone="text-orange-600 bg-orange-500/10" />
    </div>

    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div><CardTitle>{tr('แนวโน้มรายวัน')}</CardTitle><CardDescription>{tr('{label} ต่อวัน · {days} วันล่าสุด', { label: SERIES[series].label, days })}</CardDescription></div>
        <div role="group" aria-label={tr('เลือกข้อมูลกราฟ')} className="flex flex-wrap gap-1">
          {choices.map((k) => <Button key={k} type="button" size="sm" variant={series === k ? 'default' : 'outline'} aria-pressed={series === k} onClick={() => setSeries(k)}>{SERIES[k].label}</Button>)}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col"><DailyChart daily={daily} series={series} empty={!a?.requests} /></CardContent>
    </Card>

    <div className="chart-columns">
      <Card>
        <CardHeader><CardTitle>{tr('การใช้งานแยกตามโมเดล')}</CardTitle><CardDescription>{tr('คำถาม โทเคน และค่าใช้จ่ายของแต่ละโมเดล')}</CardDescription></CardHeader>
        <CardContent>
          {a?.model_rows?.length ? <><Table><TableHeader><TableRow><TableHead>{tr('โมเดล')}</TableHead><TableHead className="text-right">{tr('คำถาม')}</TableHead><TableHead className="text-right">{tr('โทเคนเข้า')}</TableHead><TableHead className="text-right">{tr('โทเคนออก')}</TableHead><TableHead className="text-right">{tr('ค่าใช้จ่าย')}</TableHead></TableRow></TableHeader>
            <TableBody>{[...a.model_rows].sort((x, y) => y.cost - x.cost).slice(0, modelRows).map((m) => <TableRow key={m.name}><TableCell className="max-w-56 truncate font-medium">{m.name}</TableCell><TableCell className="text-right">{fmt(m.requests)}</TableCell><TableCell className="text-right">{fmt(m.input_tokens)}</TableCell><TableCell className="text-right">{fmt(m.output_tokens)}</TableCell><TableCell className="text-right tabular-nums">{money4(m.cost)}</TableCell></TableRow>)}</TableBody></Table>
            {a.model_rows.length > modelRows && <div className="mt-3 flex justify-center"><Button variant="outline" size="sm" onClick={() => setModelRows(modelRows + 20)}>{tr('แสดงเพิ่ม ({v1} รายการ)', { v1: fmt(a.model_rows.length - modelRows) })}</Button></div>}</>
            : <Blank icon={Boxes} title={tr('ยังไม่มีข้อมูลโมเดล')} text={tr('ตารางจะแสดงเมื่อมีการเรียกใช้')} />}
        </CardContent>
      </Card>
      <Card className="self-start">
        <CardHeader><CardTitle>{tr('ค่าใช้จ่ายสะสมแยกตามองค์กร')}</CardTitle><CardDescription>{tr('ตลอดช่วงที่ใช้งาน ไม่ขึ้นกับตัวกรองช่วงเวลา')}</CardDescription></CardHeader>
        <CardContent>
          {orgs.data?.length ? <Table><TableHeader><TableRow><TableHead>{tr('องค์กร')}</TableHead><TableHead className="text-right">{tr('ผู้ใช้')}</TableHead><TableHead className="text-right">{tr('ค่าใช้จ่าย')}</TableHead></TableRow></TableHeader>
            <TableBody>{[...orgs.data].sort((x, y) => y.cost - x.cost).map((o) => <TableRow key={o.id}><TableCell className="max-w-56 truncate font-medium">{o.name}</TableCell><TableCell className="text-right">{fmt(o.users)}</TableCell><TableCell className="text-right tabular-nums">{money4(o.cost)}</TableCell></TableRow>)}</TableBody></Table>
            : <Blank icon={Building2} title={tr('ยังไม่มีองค์กร')} text={tr('ข้อมูลจะแสดงเมื่อมีการใช้งาน')} />}
        </CardContent>
      </Card>
    </div>

    <Card>
      <CardHeader><CardTitle>{tr('ผู้ใช้งานสูงสุด')}</CardTitle><CardDescription>{tr('10 อันดับแรกตามจำนวนคำถาม')}</CardDescription></CardHeader>
      <CardContent>
        {a?.top_users?.length ? <Table><TableHeader><TableRow><TableHead>{tr('ผู้ใช้')}</TableHead><TableHead className="text-right">{tr('คำถาม')}</TableHead><TableHead className="text-right">{tr('โทเคน')}</TableHead><TableHead className="text-right">{tr('ค่าใช้จ่าย')}</TableHead></TableRow></TableHeader>
          <TableBody>{a.top_users.map((u, i) => <TableRow key={u.name + i}><TableCell className="max-w-48 truncate font-medium">{i + 1}. {u.name}</TableCell><TableCell className="text-right">{fmt(u.requests)}</TableCell><TableCell className="text-right">{fmt(u.input_tokens + u.output_tokens)}</TableCell><TableCell className="text-right">{price(u.cost)}</TableCell></TableRow>)}</TableBody></Table>
          : <Blank icon={Users} title={tr('ยังไม่มีข้อมูลผู้ใช้')} text={tr('จะแสดงเมื่อมีการใช้งาน')} />}
      </CardContent>
    </Card>
  </>;
}

const MEASURES = (): [string, string][] => [
  [tr('เซสชัน HttpOnly'), tr('คุกกี้เซสชันมีอายุ 8 ชั่วโมง และยกเลิกได้เมื่อออกจากระบบ')],
  [tr('การแยกข้อมูลระหว่างองค์กร'), tr('ตรวจสอบ tenant_id ทุกครั้งก่อนเข้าถึงเอกสาร คลังความรู้ และบทสนทนา')],
  [tr('บทบาทและสิทธิ์การใช้งาน'), tr('API ผู้ดูแลต้องมีบทบาท SUPER_ADMIN และผู้ชมไม่สามารถแก้ไขเอกสาร')],
  [tr('ป้องกันการส่งคำขอข้ามเว็บไซต์'), tr('ตรวจสอบ Origin สำหรับคำขอแก้ไขข้อมูล และปฏิเสธคำขอ cross-site')],
  [tr('ตรวจสอบไฟล์และจำกัดขนาด'), tr('รองรับชนิดไฟล์ที่กำหนด จำกัด 20 MB และตรวจขนาดข้อมูล Office เมื่อแตกไฟล์')],
];

/** Who may do what, which protections are live right now, and the audit trail. No spending here. */
export function SecurityPage({ audit }: { audit: Audit[] }) {
  const [find, setFind] = useState('');
  const [rows, setRows] = useState(10);
  const [exportDays, setExportDays] = useState('30');
  const health = useQuery({ queryKey: ['ops-health'], queryFn: () => api<{ checks: Record<string, string> }>('/admin/operations/health'), refetchInterval: 15000 });
  const backups = useQuery({ queryKey: ['backups'], queryFn: () => api<{ encryption_configured: boolean }>('/admin/backups') });
  const policy = useQuery({ queryKey: ['savings-policy'], queryFn: () => api<{ web_search?: 'off' | 'ask' | 'always' }>('/savings/policy') });
  const events = useMemo(() => audit.filter((e) => !find.trim() || `${e.actor} ${e.action} ${e.detail} ${e.ip || ''}`.toLowerCase().includes(find.trim().toLowerCase())), [audit, find]);
  const virus = health.data?.checks?.antivirus;
  const web = policy.data?.web_search || 'ask';
  const controls: { icon: typeof ShieldCheck; title: string; ok: boolean | null; label: string; note: string }[] = [
    { icon: ShieldCheck, title: tr('สแกนไวรัส (ClamAV)'), ok: virus === undefined ? null : virus === 'healthy', label: virus === undefined ? tr('กำลังตรวจสอบ') : virus === 'healthy' ? tr('ทำงานปกติ') : tr('ไม่พร้อมใช้งาน'), note: tr('ไฟล์ที่อัปโหลดถูกสแกนก่อนอ่านหรือเก็บ ถ้าตัวสแกนล่ม ระบบจะไม่รับไฟล์') },
    { icon: KeyRound, title: tr('เข้ารหัสชุดสำรอง'), ok: backups.data ? backups.data.encryption_configured : null, label: !backups.data ? tr('กำลังตรวจสอบ') : backups.data.encryption_configured ? tr('เข้ารหัสพร้อมใช้งาน') : tr('ยังไม่มีคีย์เข้ารหัส'), note: tr('ชุดสำรองและคีย์ผู้ให้บริการถูกเข้ารหัสก่อนเก็บ') },
    { icon: Globe, title: tr('การค้นเว็บ'), ok: policy.data ? web !== 'always' : null, label: !policy.data ? tr('กำลังตรวจสอบ') : web === 'off' ? tr('ห้ามค้นเว็บ') : web === 'ask' ? tr('ต้องขออนุญาต') : tr('ค้นได้โดยไม่ถาม'), note: tr('คำค้นถูกส่งออกนอกองค์กร ตั้งค่าได้ที่หน้าประหยัดค่าใช้จ่าย') },
  ];

  return <>
    <div className="page-heading">
      <div><H1>{tr('ความปลอดภัย')}</H1><p>{tr('มาตรการป้องกันที่ทำงานอยู่ และบันทึกตรวจสอบย้อนหลังว่าใครทำอะไร')}</p></div>
    </div>

    <div className="grid gap-4 md:grid-cols-3" data-testid="security-controls">
      {controls.map((c) => <Card key={c.title} className="gap-0 py-4"><CardContent className="flex items-start gap-3 px-4">
        <span className={`grid size-11 shrink-0 place-items-center rounded-2xl ${c.ok === null ? 'bg-slate-500/10 text-slate-500' : c.ok ? 'bg-emerald-500/10 text-emerald-600' : 'bg-red-500/10 text-red-600'}`}><c.icon className="size-5" /></span>
        <div className="min-w-0"><p className="text-sm text-muted-foreground">{c.title}</p><strong className="block text-base leading-tight">{c.label}</strong><small className="block text-xs text-muted-foreground">{c.note}</small></div>
      </CardContent></Card>)}
    </div>

    <Card>
      <CardHeader><CardTitle>{tr('มาตรการที่ทำงานอยู่')}</CardTitle><CardDescription>{tr('ป้องกันในระดับโค้ดและฐานข้อมูล ไม่ต้องตั้งค่าเพิ่ม')}</CardDescription></CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        {MEASURES().map(([name, desc]) => <div key={name} className="flex items-start gap-3 rounded-lg border border-border p-3"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" /><span className="min-w-0"><strong className="block text-sm">{name}</strong><p className="text-sm text-muted-foreground">{desc}</p></span></div>)}
      </CardContent>
    </Card>

    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div><CardTitle>{tr('บันทึกการใช้งาน')}</CardTitle><CardDescription>{tr('บันทึกตรวจสอบการทำงาน · {v1} จาก {v2} รายการ', { v1: fmt(events.length), v2: fmt(audit.length) })}</CardDescription></div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-64 max-w-full"><Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" /><Input aria-label={tr('ค้นหากิจกรรม')} placeholder={tr('ค้นหาผู้ใช้ กิจกรรม รายละเอียด')} className="pl-10!" value={find} onChange={(e) => { setFind(e.target.value); setRows(10); }} /></div>
          <DaysSelect value={exportDays} onChange={setExportDays} />
          <Button asChild variant="outline"><a href={`/api/audit/export?days=${exportDays}&format=csv`}><Download className="size-4" />{tr('ส่งออก CSV')}</a></Button>
          <Button asChild variant="outline"><a href={`/api/audit/export?days=${exportDays}&format=json`}><Download className="size-4" />{tr('ส่งออก JSON')}</a></Button>
        </div>
      </CardHeader>
      <CardContent>
        {events.length ? <>
          <Table><TableHeader><TableRow><TableHead>{tr('เวลา')}</TableHead><TableHead>{tr('กิจกรรม')}</TableHead><TableHead>{tr('รายละเอียด')}</TableHead><TableHead>{tr('ผู้ดำเนินการ')}</TableHead><TableHead>IP</TableHead></TableRow></TableHeader>
            <TableBody>{events.slice(0, rows).map((e) => <TableRow key={e.id}><TableCell className="whitespace-nowrap text-muted-foreground">{date(e.created_at)}</TableCell><TableCell className="font-medium">{e.action}</TableCell><TableCell className="max-w-80 truncate" title={e.detail}>{e.detail || '—'}</TableCell><TableCell>{e.actor}</TableCell><TableCell className="whitespace-nowrap font-mono text-xs text-muted-foreground">{e.ip || '—'}</TableCell></TableRow>)}</TableBody></Table>
          {events.length > rows && <div className="mt-3 flex justify-center"><Button variant="outline" size="sm" onClick={() => setRows(rows + 20)}>{tr('แสดงเพิ่ม ({v1} รายการ)', { v1: fmt(events.length - rows) })}</Button></div>}
        </> : <Blank icon={Search} title={audit.length ? tr('ไม่พบกิจกรรมที่ค้นหา') : tr('ยังไม่มีกิจกรรม')} text={audit.length ? tr('ลองใช้คำค้นอื่น') : tr('กิจกรรมจะแสดงเมื่อมีการใช้งาน')} />}
      </CardContent>
    </Card>
  </>;
}
