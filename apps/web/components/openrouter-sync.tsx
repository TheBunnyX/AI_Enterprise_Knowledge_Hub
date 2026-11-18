'use client';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, Plus, Check, Search, Wrench } from 'lucide-react';
import { api, post, date } from './api';
import { Button } from './ui/button';
import { tr } from '../lib/i18n';
import { Modal } from './ui/dialog';
import { useConfirm } from './ui/confirm';

type Notify = (s: string) => void;
type SyncStatus = { auto: boolean; interval_seconds: number; last_at: string; last_status: string; last_changed: number; last_error: string };
type Change = { id: string; name: string; api_id: string; category?: string; unit?: string; status: 'changed' | 'same' | 'missing' | 'variable'; input_price: number; output_price: number; new_input: number | null; new_output: number | null };
type CatalogItem = { id: string; name: string; context_length: number; input_price: number | null; output_price: number | null; tools: boolean; outputs: string[]; added: boolean };
type Kind = 'llm' | 'image' | 'video';

const price = (v: number | null) => (v === null ? tr('ผันแปร') : v === 0 ? tr('ฟรี') : '$' + Number(v.toFixed(4)));
const mediaPrice = (v: number | null, unit?: string) => (v === null ? tr('ผันแปร') : v === 0 ? '—' : '$' + Number(v.toFixed(4)) + ' / ' + (unit === 'วินาที' ? tr('วินาที') : tr('ภาพ')));
const err = (e: unknown) => (e as Error).message;

export function OpenRouterPanel({ notify }: { notify: Notify }) {
  const confirm = useConfirm();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['or-sync'], queryFn: () => api<SyncStatus>('/admin/openrouter/sync'), refetchInterval: 30000 });
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<{ items: Change[]; changed: number } | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [browse, setBrowse] = useState(false);
  const s = status.data;

  const toggleAuto = async () => {
    if (!s) return;
    const next = !s.auto;
    if (next && !(await confirm({ title: tr('เปิดซิงก์ราคาอัตโนมัติ'), text: tr('ระบบจะดึงราคาจาก OpenRouter ทุก 5 นาที และอัปเดตราคาของโมเดล OpenRouter ที่มีอยู่ทันทีโดยไม่ถามซ้ำ ซึ่งมีผลกับการคิดค่าใช้จ่ายและงบประมาณ (ไม่เพิ่มหรือเปิด/ปิดโมเดล)') }))) return;
    setBusy(true);
    try {
      await api('/admin/openrouter/sync', { method: 'PUT', body: JSON.stringify({ auto: next }) });
      qc.invalidateQueries({ queryKey: ['or-sync'] });
      notify(next ? tr('เปิดซิงก์ราคาอัตโนมัติแล้ว') : tr('ปิดซิงก์ราคาอัตโนมัติแล้ว'));
    } catch (e) { notify(err(e)); } finally { setBusy(false); }
  };

  const check = async () => {
    setBusy(true);
    try {
      const r = await api<{ items: Change[]; changed: number }>('/admin/openrouter/sync/preview');
      setPreview(r);
      setPicked(new Set(r.items.filter(i => i.status === 'changed').map(i => i.id)));
      if (!r.changed) notify(tr('ราคาตรงกับ OpenRouter แล้ว ไม่มีรายการที่ต้องอัปเดต'));
    } catch (e) { notify(err(e)); } finally { setBusy(false); }
  };

  const apply = async () => {
    if (!picked.size) return;
    if (!(await confirm({ title: tr('อัปเดตราคาโมเดล'), text: tr('ปรับราคา {v1} โมเดลตาม OpenRouter มีผลกับการคิดค่าใช้จ่ายทันที',{v1:picked.size}) }))) return;
    setBusy(true);
    try {
      const r = await post<{ updated: number }>('/admin/openrouter/sync/apply', { ids: [...picked] });
      notify(tr('อัปเดตราคาแล้ว {v1} โมเดล',{v1:r.updated}));
      setPreview(null);
      qc.invalidateQueries({ queryKey: ['models'] });
      qc.invalidateQueries({ queryKey: ['or-sync'] });
    } catch (e) { notify(err(e)); } finally { setBusy(false); }
  };

  return (
    <section className="card padded feature-section">
      <div className="section-heading price-sync-heading">
        <h2><RefreshCw size={18} />{tr('ราคาโมเดลจาก OpenRouter')}</h2>
        <span className="small muted">{tr('โมเดลข้อความ: ราคาต่อ 1 ล้านโทเคน (USD) · โมเดลภาพ/วิดีโอ: ราคาอ้างอิงต่อภาพหรือต่อวินาที ตามที่ OpenRouter ประกาศ ยอดจริงอาจต่างเล็กน้อยตามผู้ให้บริการปลายทาง')}</span>
      </div>
      <div className="stack">
        <label className="check-label price-sync-toggle">
          <input type="checkbox" checked={!!s?.auto} disabled={busy || !s} onChange={toggleAuto} aria-label={tr('ซิงก์ราคาอัตโนมัติทุก 5 นาที')} />
          <span>{tr('ซิงก์ราคาอัตโนมัติทุก 5 นาที')}</span>
        </label>
        {s && (
          <p className="small muted" role="status">
            {s.last_status === 'error' ? tr('ซิงก์ล่าสุดไม่สำเร็จ: {v1}',{v1:s.last_error}) : s.last_at ? tr('ซิงก์ล่าสุด {v1} · อัปเดต {v2} โมเดล',{v1:date(s.last_at),v2:s.last_changed}) : s.auto ? tr('รอรอบซิงก์แรก (ภายใน 5 นาที)') : tr('ยังไม่เคยซิงก์')}
            {s.auto && tr(' · ต้องมี scheduler (Celery) ทำงานอยู่')}
          </p>
        )}
        <div className="inline-actions">
          <Button type="button" variant="outline" disabled={busy} onClick={check}><RefreshCw size={16} />{tr('ตรวจสอบราคา')}</Button>
          <Button type="button" variant="outline" onClick={() => setBrowse(true)}><Plus size={16} />{tr('เพิ่มโมเดลจาก OpenRouter')}</Button>
        </div>
        {preview && (
          <div className="stack">
            <div className="table-scroll">
              <table>
                <thead><tr><th /><th>{tr('โมเดล')}</th><th>{tr('ราคาเดิม (เข้า/ออก)')}</th><th>{tr('ราคาใหม่ (เข้า/ออก)')}</th><th>{tr('สถานะ')}</th></tr></thead>
                <tbody>
                  {preview.items.filter(i => i.status !== 'same').map(i => (
                    <tr key={i.id}>
                      <td>{i.status === 'changed' && <input type="checkbox" aria-label={tr('เลือก {name}',{name:i.name})} checked={picked.has(i.id)} onChange={e => { const n = new Set(picked); if (e.target.checked) n.add(i.id); else n.delete(i.id); setPicked(n); }} />}</td>
                      <td><strong>{i.name}</strong><div className="small muted">{i.api_id}</div></td>
                      <td>{i.unit ? mediaPrice(i.output_price, i.unit) : `${price(i.input_price)} / ${price(i.output_price)}`}</td>
                      <td>{i.status === 'changed' ? (i.unit ? mediaPrice(i.new_output, i.unit) : `${price(i.new_input)} / ${price(i.new_output)}`) : '—'}</td>
                      <td className="small">{i.status === 'changed' ? tr('ราคาเปลี่ยน') : i.status === 'variable' ? tr('OpenRouter ไม่ระบุราคาตายตัว (ไม่อัปเดต)') : tr('ไม่พบใน OpenRouter แล้ว')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!preview.items.some(i => i.status !== 'same') && <p className="small muted">{tr('ราคาทุกโมเดลตรงกับ OpenRouter')}</p>}
            </div>
            {preview.changed > 0 && <div className="inline-actions"><Button type="button" disabled={busy || !picked.size} onClick={apply}><Check size={16} />{tr('อัปเดตที่เลือก ({size})',{size:picked.size})}</Button><Button type="button" variant="outline" onClick={() => setPreview(null)}>{tr('ปิด')}</Button></div>}
          </div>
        )}
      </div>
      {browse && <Browse notify={notify} onClose={() => setBrowse(false)} />}
    </section>
  );
}

function Browse({ notify, onClose }: { notify: Notify; onClose: () => void }) {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [free, setFree] = useState(false);
  const [kind, setKind] = useState<Kind>('llm');
  const [adding, setAdding] = useState('');
  const list = useQuery({ queryKey: ['or-catalog', q, free, kind], queryFn: () => api<{ total: number; items: CatalogItem[] }>('/admin/openrouter/catalog?limit=60&kind=' + kind + '&free=' + free + '&q=' + encodeURIComponent(q)), staleTime: 30000 });
  const add = async (c: CatalogItem) => {
    setAdding(c.id);
    try {
      const r = await post<{ variable_price: boolean }>('/admin/openrouter/models', { api_id: c.id, kind });
      notify(tr('เพิ่ม {v1} แล้ว (ยังปิดใช้งานอยู่ เปิดได้ที่รายการโมเดล)',{v1:c.name}) + (r.variable_price ? tr(' · ราคาผันแปร ตั้งราคาเองที่รายการโมเดล') : ''));
      qc.invalidateQueries({ queryKey: ['models'] });
      qc.invalidateQueries({ queryKey: ['or-catalog'] });
    } catch (e) { notify(err(e)); } finally { setAdding(''); }
  };
  return (
    <Modal title={tr('เพิ่มโมเดลจาก OpenRouter')} onClose={onClose} wide>
      <div className="stack">
        <div className="table-toolbar">
          <div className="input-icon"><Search size={17} /><input placeholder={tr('ค้นหาชื่อหรือรหัสโมเดล...')} value={q} onChange={e => setQ(e.target.value)} aria-label={tr('ค้นหาโมเดล OpenRouter')} /></div>
          <div className="tabs" role="tablist">{([['llm', tr('ข้อความ')], ['image', tr('ภาพ')], ['video', tr('วิดีโอ')]] as [Kind, string][]).map(([k, label]) => <button key={k} type="button" role="tab" aria-selected={kind === k} className={kind === k ? 'selected' : ''} onClick={() => setKind(k)}>{label}</button>)}</div>
          {kind === 'llm' && <label className="inline-actions" style={{ alignItems: 'center', gap: 6 }}><input type="checkbox" checked={free} onChange={e => setFree(e.target.checked)} />{tr('เฉพาะโมเดลฟรี')}</label>}
        </div>
        {list.isLoading && <p className="muted">{tr('กำลังโหลดรายการจาก OpenRouter...')}</p>}
        {list.isError && <p role="alert">{(list.error as Error).message}</p>}
        {list.data && <p className="small muted">{tr('พบ {total} โมเดล',{total:list.data.total})}{list.data.total > list.data.items.length ? tr(' (แสดง {v1} รายการแรก ใช้ช่องค้นหาเพื่อกรอง)',{v1:list.data.items.length}) : ''}</p>}
        <div className="table-scroll" style={{ maxHeight: '55vh', overflow: 'auto' }}>
          <table>
            <thead><tr><th>{tr('โมเดล')}</th><th>{kind === 'llm' ? 'Context' : ''}</th><th>{kind === 'llm' ? tr('ราคา เข้า / ออก') : tr('ราคาอ้างอิง')}</th><th /></tr></thead>
            <tbody>
              {list.data?.items.map(c => (
                <tr key={c.id}>
                  <td><strong>{c.name}</strong>{c.tools && <span title={tr('รองรับ tool calling (ใช้กับโหมด Agent ได้)')} style={{ marginLeft: 6 }}><Wrench size={13} style={{ display: 'inline' }} /></span>}<div className="small muted">{c.id}</div></td>
                  <td className="small">{c.context_length ? Math.round(c.context_length / 1000) + 'K' : '—'}</td>
                  <td className="small nowrap">{kind === 'llm' ? `${price(c.input_price)} / ${price(c.output_price)}` : c.output_price ? mediaPrice(c.output_price, kind === 'video' ? 'วินาที' : 'ภาพ') : '—'}</td>
                  <td>{c.added ? <span className="small muted">{tr('เพิ่มแล้ว')}</span> : c.outputs.length && !c.outputs.includes('text') ? <span className="small muted">{tr('ไม่ใช่โมเดลข้อความ')}</span> : <Button type="button" size="sm" variant="outline" disabled={adding === c.id} onClick={() => add(c)}><Plus size={14} />{tr('เพิ่ม')}</Button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Modal>
  );
}
