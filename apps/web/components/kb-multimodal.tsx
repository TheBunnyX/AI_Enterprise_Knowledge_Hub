'use client';
import { useState } from 'react';
import { ImageIcon } from 'lucide-react';
import { api, type KB } from './api';
import { Button } from './ui/button';
import { Checkbox } from './ui/checkbox';
import { tr } from '../lib/i18n';

/** Multimodal RAG is opt-in per knowledge base: only libraries with charts, diagrams or scans send pictures to Google AI. */
export function KbMultimodal({ bases, notify, refresh }: { bases: KB[]; notify: (s: string) => void; refresh: () => void }) {
  const [busy, setBusy] = useState('');
  const mine = bases.filter(b => b.can_write);
  if (!mine.length) return null;
  const toggle = async (b: KB, on: boolean) => {
    setBusy(b.id);
    try {
      await api('/knowledge-bases/' + b.id, { method: 'PUT', body: JSON.stringify({ name: b.name, description: b.description || '', multimodal: on }) });
      refresh();
      notify(on ? tr('เปิดแล้ว กดอัปเดตเอกสารเพื่อประมวลผลภาพของเอกสารเดิม') : tr('ปิดแล้ว กดอัปเดตเอกสารเพื่อลบข้อมูลภาพออกจากดัชนี'));
    } catch (e) { notify((e as Error).message); }
    setBusy('');
  };
  const apply = async (b: KB) => {
    setBusy(b.id);
    try {
      const r = await api<{ reindexed: number }>('/knowledge-bases/' + b.id + '/multimodal/apply', { method: 'POST' });
      refresh();
      notify(tr('กำลังประมวลผลใหม่ {n} เอกสาร (เอกสารอื่นไม่ถูกแตะ)', { n: r.reindexed }));
    } catch (e) { notify((e as Error).message); }
    setBusy('');
  };
  return <section className="card padded mt-4" aria-label={tr('ภาพและแผนภาพในเอกสาร (Multimodal RAG)')}>
    <div className="section-heading"><h2 className="flex items-center gap-2"><ImageIcon size={18} />{tr('ภาพและแผนภาพในเอกสาร (Multimodal RAG)')}</h2></div>
    <p className="muted small">{tr('เปิดเฉพาะคลังที่มีกราฟ แผนภาพ หรือหน้าสแกน ภาพจะถูกส่งไปยัง Google AI เพื่ออธิบายและทำเวกเตอร์ ค่าใช้จ่ายเกิดเฉพาะคลังที่เปิด')}</p>
    <div className="grid gap-2">
      {mine.map(b => <div key={b.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
        <label className="flex items-center gap-2 text-sm font-medium"><Checkbox checked={!!b.multimodal} disabled={busy === b.id} onCheckedChange={v => toggle(b, v === true)} aria-label={tr('ประมวลผลภาพ') + ' ' + b.name} />{b.name}<span className="muted small font-normal">{tr('ประมวลผลภาพ')}</span></label>
        <Button type="button" variant="outline" size="sm" disabled={busy === b.id} onClick={() => apply(b)}>{tr('อัปเดตเอกสาร')}</Button>
      </div>)}
    </div>
  </section>;
}
