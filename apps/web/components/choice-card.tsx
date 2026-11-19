'use client';
import { useEffect, useRef, useState } from 'react';
import { ChevronRight, Pencil, X } from 'lucide-react';
import { tr } from '../lib/i18n';

/** A question with numbered options docked above the composer: arrow keys and Enter pick, a number key jumps, "something else" takes free text, Esc or Skip dismisses. */
export function ChoiceCard({ question, options, onPick, onSkip }: { question: string; options: string[]; onPick: (answer: string) => void; onSkip: () => void }) {
  const [index, setIndex] = useState(0);
  const [custom, setCustom] = useState('');
  const box = useRef<HTMLDivElement>(null);
  const text = useRef<HTMLInputElement>(null);
  const last = options.length; // the "something else" row
  useEffect(() => { box.current?.focus({ preventScroll: true }); box.current?.scrollIntoView?.({ block: 'nearest' }); }, []);
  const choose = (i: number) => { if (i < options.length) onPick(options[i]); else if (custom.trim()) onPick(custom.trim()); else text.current?.focus(); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); onSkip(); return; }
    if (e.target === text.current) {
      if (e.key === 'Enter' && custom.trim()) { e.preventDefault(); onPick(custom.trim()); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(last - 1); box.current?.focus(); }
      return;
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); setIndex(i => Math.min(last, i + 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => Math.max(0, i - 1)); }
    else if (e.key === 'Enter') { e.preventDefault(); choose(index); }
    else if (/^[1-9]$/.test(e.key) && Number(e.key) <= options.length) { e.preventDefault(); onPick(options[Number(e.key) - 1]); }
  };
  return (
    <div ref={box} tabIndex={0} onKeyDown={key} role="group" aria-label={tr('คำถามจาก AI')} className="ml-11 mt-2 max-w-2xl rounded-2xl border border-border bg-card p-4 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">
      <div className="mb-3 flex items-start justify-between gap-3">
        <p className="text-sm font-medium leading-6">{question}</p>
        <button type="button" onClick={onSkip} aria-label={tr('ข้าม')} className="text-muted-foreground hover:text-foreground"><X className="size-4" /></button>
      </div>
      <div className="divide-y divide-border">
        {options.map((o, i) => (
          <button key={o} type="button" onClick={() => onPick(o)} onMouseEnter={() => setIndex(i)} className={'flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left text-sm ' + (index === i ? 'bg-muted' : '')}>
            <span className="grid size-6 place-items-center rounded-md bg-muted text-xs text-muted-foreground">{i + 1}</span>
            <span className="flex-1">{o}</span>
            {index === i && <ChevronRight className="size-4 text-muted-foreground" />}
          </button>
        ))}
        <div className={'flex items-center gap-3 rounded-lg px-2 py-2 ' + (index === last ? 'bg-muted' : '')} onMouseEnter={() => setIndex(last)}>
          <span className="grid size-6 place-items-center rounded-md bg-muted text-muted-foreground"><Pencil className="size-3.5" /></span>
          <input ref={text} value={custom} onChange={e => setCustom(e.target.value)} onFocus={() => setIndex(last)} maxLength={500} aria-label={tr('คำตอบอื่น')} placeholder={tr('อย่างอื่น...')} className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
          <button type="button" onClick={onSkip} className="rounded-md border border-border px-3 py-1 text-xs hover:bg-muted">{tr('ข้าม')}</button>
        </div>
      </div>
      <p className="mt-3 text-center text-xs text-muted-foreground">{tr('↑↓ เลือก · Enter ยืนยัน · Esc ข้าม')}</p>
    </div>
  );
}
