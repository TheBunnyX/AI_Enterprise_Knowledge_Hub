import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Hub from '../components/hub';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => '/chat', useSearchParams: () => new URLSearchParams() }));
vi.mock('next/link', () => ({ default: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a> }));

const user = { id: 'u1', name: 'สมชาย', email: 'member@test.example', role: 'USER', tenant_id: 't1' };
const base = { category: 'LLM', enabled: true, configured: true, input_price: 0, output_price: 0, effort: '', rpm: 0, tpm: 0, rpd: 0, used_rpm: 0, used_tpm: 0, used_rpd: 0 };
const studio = { ...base, id: 'g-studio', name: 'Gemini 3.5 Flash Lite', display_name: 'Gemini 3.5 Flash Lite', provider: 'Google AI', api_id: 'gemini-3.5-flash-lite' };
const viaRouter = { ...base, id: 'g-router', name: 'Google: Gemini 3.5 Flash Lite', display_name: 'Google: Gemini 3.5 Flash Lite', provider: 'OpenRouter', api_id: 'google/gemini-3.5-flash-lite' };
const other = { ...base, id: 'other', name: 'Other LLM', display_name: 'Other LLM', provider: 'OpenRouter', api_id: 'x/other' };
let models: Record<string, unknown>[] = [];
const chats: Record<string, unknown>[] = [];

function stream() {
  const bytes = new TextEncoder().encode([{ type: 'meta', conversation_id: 'c1', message_id: 'm1', citations: [] }, { type: 'delta', text: 'ok' }, { type: 'done', message_id: 'm1' }].map(e => JSON.stringify(e)).join('\n') + '\n'); let sent = false;
  return { ok: true, body: { getReader: () => ({ read: async () => sent ? { done: true, value: undefined } : (sent = true, { done: false, value: bytes }) }) } };
}

beforeEach(() => {
  chats.length = 0; localStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input); let data: unknown = [];
    if (path.endsWith('/api/chat')) { chats.push(JSON.parse(String(init?.body))); return stream(); }
    if (path.endsWith('/agent-pending')) data = null;
    if (path.endsWith('/savings/status')) data = { auto_route: false, web_search: 'ask' };
    if (path.endsWith('/models')) data = models;
    if (path.endsWith('/skills')) data = { skills: [], templates: [], can_share: false };
    if (path.endsWith('/maintenance-status')) data = { maintenance: false, restore: null };
    if (path.endsWith('/config')) data = { ai_gateway_configured: true };
    if (path.endsWith('/account/preferences')) data = { name: 'สมชาย', default_model: '', notifications: true };
    if (path.includes('/analytics')) data = { organizations: 1, users: 1, documents: 0, storage_bytes: 0, requests: 0, cost: 0, input_tokens: 0, output_tokens: 0, daily: [], models: [], model_rows: [], top_users: [], document_status: {} };
    return { ok: true, json: async () => data };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function askAndGetModel() {
  const box = await waitFor(() => screen.getByRole('textbox', { name: /คำถาม|ข้อความ/ }));
  fireEvent.change(box, { target: { value: 'ลาพักร้อนกี่วัน' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'ส่งคำถาม' }).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'ส่งคำถาม' }));
  await waitFor(() => expect(chats.length).toBe(1));
  return chats[0].model_id;
}

it('opens on Gemini 3.5 Flash Lite from Google AI Studio, not the OpenRouter copy of it', async () => {
  models = [other, viaRouter, studio];
  render(<Hub initialUser={user} />);
  expect(await askAndGetModel()).toBe('g-studio');
});

it('starts on it again on every visit even when another model was chosen last time', async () => {
  localStorage.setItem('hub.model', 'other');
  models = [other, studio];
  render(<Hub initialUser={user} />);
  expect(await askAndGetModel()).toBe('g-studio');
});

it('falls back to the last choice when that model is not available', async () => {
  localStorage.setItem('hub.model', 'other');
  models = [other, viaRouter];
  render(<Hub initialUser={user} />);
  expect(await askAndGetModel()).toBe('other');
});
