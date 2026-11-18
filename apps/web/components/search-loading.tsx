'use client';
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { tr } from '../lib/i18n';

/** Shown while the search page waits for results: a spinner with what is happening, and skeleton cards where the results will appear.
 *  The first search after the server starts loads the search models, so after a few seconds it explains the wait. */
export function SearchLoading({ slowAfterMs = 6000 }: { slowAfterMs?: number }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => { const t = setTimeout(() => setSlow(true), slowAfterMs); return () => clearTimeout(t); }, [slowAfterMs]);
  return <div role="status" aria-live="polite" aria-busy="true" className="search-loading" data-testid="search-loading">
    <div className="search-loading-head">
      <Loader2 className="size-6 animate-spin text-primary" aria-hidden />
      <div>
        <strong>{tr('กำลังค้นหาในเอกสาร…')}</strong>
        <p className="muted small m-0">{slow ? tr('การค้นหาครั้งแรกอาจใช้เวลาสักครู่ เพราะต้องโหลดโมเดลค้นหา') : tr('ค้นข้อความและเวกเตอร์ แล้วให้โมเดลจัดอันดับผลลัพธ์')}</p>
      </div>
    </div>
    <div className="search-loading-list" aria-hidden>
      {[0, 1, 2].map(i => <div key={i} className="card search-skeleton"><span className="sk sk-icon" /><div><span className="sk sk-title" /><span className="sk sk-line" /><span className="sk sk-line short" /></div><span className="sk sk-thumb" /></div>)}
    </div>
  </div>;
}
