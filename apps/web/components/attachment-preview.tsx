'use client';
import { useEffect, useState } from 'react';
import { FileText, FileSpreadsheet, Presentation, Download } from 'lucide-react';
import { Modal } from './ui/dialog';
import { tr } from '../lib/i18n';

/** A file attached to a chat question; `url` is a browser-local object URL, nothing is uploaded for the preview. */
export type AttachedView = { name: string; size: number; type: string; url: string };
export type Kind = 'image' | 'pdf' | 'text' | 'sheet' | 'slides' | 'doc';

const ext = (n: string) => (n.split('.').pop() || '').toLowerCase();

export function kindOf(name: string, type = ''): Kind {
  const e = ext(name);
  if (type.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(e)) return 'image';
  if (type === 'application/pdf' || e === 'pdf') return 'pdf';
  if (type.startsWith('text/') || ['txt', 'md', 'csv', 'html'].includes(e)) return 'text';
  if (['xls', 'xlsx'].includes(e)) return 'sheet';
  if (['ppt', 'pptx'].includes(e)) return 'slides';
  return 'doc';
}

export function sizeLabel(n: number) {
  return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
}

function Icon({ kind, className }: { kind: Kind; className?: string }) {
  const I = kind === 'sheet' ? FileSpreadsheet : kind === 'slides' ? Presentation : FileText;
  return <I className={className} />;
}

/** Small card: thumbnail for pictures, a type icon for everything else. Click to open the preview. */
export function AttachCard({ a, onOpen, onRemove }: { a: AttachedView; onOpen: () => void; onRemove?: () => void }) {
  const k = kindOf(a.name, a.type);
  return (
    <div className="group relative flex max-w-60 items-center gap-2 rounded-lg border bg-card p-1.5 pr-2.5 text-left shadow-xs">
      <button type="button" onClick={onOpen} aria-label={tr('ดูตัวอย่าง {v1}', { v1: a.name })} title={a.name} className="flex min-w-0 items-center gap-2 text-left">
        {k === 'image'
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={a.url} alt={a.name} className="size-10 shrink-0 rounded-md object-cover" />
          : <span className="grid size-10 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground"><Icon kind={k} className="size-5" /></span>}
        <span className="min-w-0"><span className="block truncate text-xs font-medium">{a.name}</span><span className="block text-[11px] text-muted-foreground">{ext(a.name).toUpperCase()} · {sizeLabel(a.size)}</span></span>
      </button>
      {onRemove && <button type="button" aria-label={tr('ลบ {v1}', { v1: a.name })} onClick={onRemove} className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border bg-background text-xs leading-none shadow-xs hover:bg-accent">×</button>}
    </div>
  );
}

function TextBody({ url }: { url: string }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => { let live = true; fetch(url).then(r => r.text()).then(t => { if (live) setText(t.slice(0, 20000) + (t.length > 20000 ? '\n…' : '')); }).catch(() => { if (live) setText(''); }); return () => { live = false; }; }, [url]);
  return <pre className="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-xs [overflow-wrap:anywhere]">{text === null ? tr('กำลังโหลด…') : text}</pre>;
}

/** Preview dialog. Pictures, PDF and plain text render in place; Office files show their details and a download link. */
export function AttachPreview({ a, onClose }: { a: AttachedView; onClose: () => void }) {
  const k = kindOf(a.name, a.type);
  return (
    <Modal title={a.name} onClose={onClose} wide>
      {k === 'image' && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={a.url} alt={a.name} className="mx-auto max-h-[70vh] max-w-full rounded-md object-contain" />
      )}
      {k === 'pdf' && <iframe src={a.url} title={a.name} className="h-[70vh] w-full rounded-md border" />}
      {k === 'text' && <TextBody url={a.url} />}
      {(k === 'sheet' || k === 'slides' || k === 'doc') && (
        <div className="grid place-items-center gap-3 py-8 text-center text-sm text-muted-foreground">
          <Icon kind={k} className="size-12" />
          <p>{tr('ไฟล์ชนิดนี้ดูตัวอย่างในหน้านี้ไม่ได้ แต่ AI อ่านเนื้อหาได้ตามปกติ')}</p>
          <p className="text-xs">{ext(a.name).toUpperCase()} · {sizeLabel(a.size)}</p>
          <a href={a.url} download={a.name} className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-foreground hover:bg-accent"><Download className="size-4" />{tr('ดาวน์โหลด')}</a>
        </div>
      )}
    </Modal>
  );
}
