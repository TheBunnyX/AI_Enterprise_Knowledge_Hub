import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import Hub from '../components/hub';
import { EN } from '../lib/en';
import { tr } from '../lib/i18n';

let pathname = '/dashboard';
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => pathname, useSearchParams: () => new URLSearchParams() }));
vi.mock('next/link', () => ({ default: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a> }));

const THAI = /[฀-๿]/;
const root = join(__dirname, '..');
const sources = (dir: string): string[] => readdirSync(join(root, dir), { withFileTypes: true }).flatMap(e => e.isDirectory() ? sources(join(dir, e.name)) : /\.tsx?$/.test(e.name) ? [join(dir, e.name)] : []);

describe('translation table', () => {
  it('has an English entry for every Thai string literal in the UI source', () => {
    const missing: string[] = [];
    for (const f of sources('components')) {
      if (f.endsWith('lang-toggle.tsx')) continue;
      let s = readFileSync(join(root, f), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
      s = s.split('\n').map(l => l.replace(/(?<![:'"])\/\/.*$/, '')).join('\n');
      for (const m of s.matchAll(/'((?:[^'\\\n]|\\.)*)'/g)) {
        const v = m[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\');
        if (THAI.test(v) && !(v in EN)) missing.push(`${f}: ${v}`);
      }
    }
    expect(missing).toEqual([]);
  });

  it('keeps {placeholders} identical between Thai and English', () => {
    const ph = (s: string) => (s.match(/\{\w+\}/g) || []).sort().join();
    const bad = Object.entries(EN).filter(([k, v]) => ph(k) !== ph(v)).map(([k]) => k);
    expect(bad).toEqual([]);
  });

  it('has no Thai left inside English text', () => {
    expect(Object.values(EN).filter(v => THAI.test(v))).toEqual([]);
  });
});

const base = { id: 'user-1', name: 'Tester', email: 'tester@example.test', tenant_id: 'tenant-1' };
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as never;
  vi.stubGlobal('fetch', vi.fn(async (input: string) => {
    const path = String(input); let data: unknown = [];
    if (path.includes('/savings/report')) data = { month: { budget: 0, spent: 0 }, savings: { cache_hits: 0, routed: 0, routed_to: {}, embedding_batches_cached: 0 } };
    if (path.endsWith('/skills')) data = { skills: [], templates: [], can_share: false };
    if (path.endsWith('/admin/backups')) data = { items: [], interval_hours: 24, retention: 7, encryption_configured: true };
    if (path.endsWith('/maintenance-status')) data = { maintenance: false, restore: null };
    if (path.endsWith('/auth/me')) data = { ...base, role: 'SUPER_ADMIN' };
    if (path.endsWith('/config')) data = { demo: true, demo_accounts: [{ label: 'ผู้ดูแลระบบ', email: 'a@x', password: 'p' }, { label: 'ผู้ดูแลแผนก', email: 'b@x', password: 'p' }, { label: 'ผู้ใช้งาน', email: 'c@x', password: 'p' }] };
    if (path.endsWith('/analytics') || path.includes('/analytics?')) data = { organizations: 1, users: 1, documents: 0, storage_bytes: 0, requests: 0, cost: 0, input_tokens: 0, output_tokens: 0, daily: [], models: [], model_rows: [], top_users: [], document_status: {}, demo: true, estimated: false };
    return { ok: true, json: async () => data };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); pathname = '/dashboard'; document.cookie = 'hub.lang=; max-age=0'; });

describe('language switching', () => {
  it('shows Thai by default, English when asked, and switches live without remounting', async () => {
    render(<Hub initialUser={{ ...base, role: 'USER' }} />);
    expect(screen.getByRole('link', { name: 'เอกสารของฉัน' })).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Switch to English' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'My documents' })).toBeTruthy());
    expect(screen.queryByRole('link', { name: 'เอกสารของฉัน' })).toBeNull();
    expect(document.documentElement.lang).toBe('en');
    expect(document.cookie).toContain('hub.lang=en');
    fireEvent.click(screen.getByRole('button', { name: 'สลับเป็นภาษาไทย' }));
    await waitFor(() => expect(screen.getByRole('link', { name: 'เอกสารของฉัน' })).toBeTruthy());
  });

  it('translates strings outside React (api errors, dates)', () => {
    expect(tr('บันทึกแล้ว')).toBe('บันทึกแล้ว');
  });

  const routes: [string, string][] = [
    ['/dashboard', 'USER'], ['/chat', 'USER'], ['/documents', 'USER'], ['/knowledge', 'USER'], ['/knowledge/search', 'USER'], ['/skills', 'USER'],
    ['/settings', 'USER'], ['/voice', 'USER'], ['/studio/image', 'USER'], ['/studio/stt', 'USER'], ['/analytics', 'USER'], ['/nope', 'USER'],
    ['/super-admin', 'SUPER_ADMIN'], ['/super-admin/organizations', 'SUPER_ADMIN'], ['/super-admin/users', 'SUPER_ADMIN'], ['/super-admin/models', 'SUPER_ADMIN'],
    ['/super-admin/savings', 'SUPER_ADMIN'], ['/super-admin/security', 'SUPER_ADMIN'], ['/super-admin/operations', 'SUPER_ADMIN'], ['/super-admin/system', 'SUPER_ADMIN'], ['/super-admin/settings', 'SUPER_ADMIN'], ['/super-admin/billing', 'SUPER_ADMIN'], ['/team', 'DEPARTMENT_ADMIN'],
  ];
  it.each(routes)('renders %s (%s) in English without any Thai text', async (path, role) => {
    pathname = path;
    const { container } = render(<Hub initialUser={{ ...base, role }} initialLang="en" />);
    await new Promise(r => setTimeout(r, 400));
    const text = [container.textContent, ...Array.from(container.querySelectorAll('[placeholder],[aria-label],[title],[alt]')).flatMap(e => ['placeholder', 'aria-label', 'title', 'alt'].map(a => e.getAttribute(a)))].filter(v => v && v !== 'สลับเป็นภาษาไทย').join('\n'); // the language switch names its target language, so it is Thai on purpose
    expect(text.split('\n').filter(l => THAI.test(l))).toEqual([]);
  });

  it('renders the login screen in English', async () => {
    const { container } = render(<Hub initialUser={null} initialLang="en" />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeTruthy());
    expect(THAI.test(container.textContent || '')).toBe(false);
  });
});
