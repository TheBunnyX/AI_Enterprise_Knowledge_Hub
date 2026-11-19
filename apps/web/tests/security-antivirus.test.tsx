import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Hub from '../components/hub';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => '/super-admin/security', useSearchParams: () => new URLSearchParams() }));
vi.mock('next/link', () => ({ default: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a> }));

const admin = { id: 'a1', name: 'ผู้ดูแลระบบ', email: 'admin@test.example', role: 'SUPER_ADMIN', tenant_id: 't1' };
let scanner = { enabled: true, configured: true, required: true };
let health: Record<string, string> = { antivirus: 'healthy' };
const puts: unknown[] = [];

beforeEach(() => {
  puts.length = 0; scanner = { enabled: true, configured: true, required: true }; health = { antivirus: 'healthy' };
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input); let data: unknown = [];
    if (path.endsWith('/admin/antivirus')) {
      if (init?.method === 'PUT') { const body = JSON.parse(String(init.body)); puts.push(body); scanner = { ...scanner, enabled: body.enabled }; if (!body.enabled) delete health.antivirus; data = scanner; } else data = scanner;
    }
    if (path.endsWith('/admin/operations/health')) data = { checks: health, checked_at: '' };
    if (path.endsWith('/admin/backups')) data = { items: [], encryption_configured: true, interval_hours: 24, retention: 7 };
    if (path.endsWith('/savings/policy')) data = { web_search: 'ask' };
    if (path.endsWith('/maintenance-status')) data = { maintenance: false, restore: null };
    if (path.endsWith('/config')) data = { ai_gateway_configured: true };
    if (path.endsWith('/account/preferences')) data = { name: 'x', default_model: '', notifications: true };
    if (path.includes('/system/health')) data = { services: [] };
    return { ok: true, json: async () => data };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const toggle = () => waitFor(() => screen.getByRole('checkbox', { name: 'เปิดการสแกนไวรัส' }) as HTMLInputElement);

it('shows scanning as running, and turning it off asks first and then tells the server', async () => {
  render(<Hub initialUser={admin} />);
  const box = await toggle();
  expect(box.checked).toBe(true);
  await waitFor(() => expect(screen.getByText('ทำงานปกติ')).toBeTruthy());
  fireEvent.click(box);
  expect(puts.length).toBe(0);  // nothing is sent before the person confirms
  fireEvent.click(await waitFor(() => screen.getByRole('button', { name: 'ปิดการสแกน' })));
  await waitFor(() => expect(puts).toEqual([{ enabled: false }]));
  await waitFor(() => expect(screen.getByText('ปิดอยู่ (ไม่สแกนไฟล์)')).toBeTruthy());
  expect(((await toggle()) as HTMLInputElement).checked).toBe(false);
});

it('cancelling the confirmation leaves scanning on', async () => {
  render(<Hub initialUser={admin} />);
  fireEvent.click(await toggle());
  fireEvent.click(await waitFor(() => screen.getByRole('button', { name: 'ยกเลิก' })));
  await new Promise(r => setTimeout(r, 100));
  expect(puts.length).toBe(0);
  expect(((await toggle()) as HTMLInputElement).checked).toBe(true);
});

it('turning it back on needs no confirmation', async () => {
  scanner = { enabled: false, configured: false, required: false }; health = {};
  render(<Hub initialUser={admin} />);
  const box = await toggle();
  expect(box.checked).toBe(false);
  await waitFor(() => expect(screen.getByText('ปิดอยู่ (ไม่สแกนไฟล์)')).toBeTruthy());
  fireEvent.click(box);
  await waitFor(() => expect(puts).toEqual([{ enabled: true }]));
});

it('says when ClamAV is not installed here', async () => {
  scanner = { enabled: true, configured: false, required: false }; health = {};
  render(<Hub initialUser={admin} />);
  await waitFor(() => expect(screen.getByText(/ไม่ได้ตั้งค่า ClamAV/)).toBeTruthy());
});
