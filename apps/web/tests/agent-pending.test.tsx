import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import Hub from '../components/hub';

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => '/chat', useSearchParams: () => new URLSearchParams() }));
vi.mock('next/link', () => ({ default: ({ children, ...props }: React.ComponentProps<'a'>) => <a {...props}>{children}</a> }));

const user = { id: 'u1', name: 'สมชาย', email: 'member@test.example', role: 'USER', tenant_id: 't1' };
const model = { id: 'm1', name: 'Test LLM', display_name: 'Test LLM', provider: 'OpenRouter', api_id: 'x/y', category: 'LLM', enabled: true, configured: true, input_price: 0, output_price: 0, effort: '', rpm: 0, tpm: 0, rpd: 0, used_rpm: 0, used_tpm: 0, used_rpd: 0 };
const chats: Record<string, unknown>[] = [];
let replies: Record<string, unknown>[][] = [];
let waiting: unknown = null;
let webPolicy = 'ask';

function stream(events: Record<string, unknown>[]) {
  const bytes = new TextEncoder().encode(events.map(e => JSON.stringify(e)).join('\n') + '\n'); let sent = false;
  return { ok: true, body: { getReader: () => ({ read: async () => sent ? { done: true, value: undefined } : (sent = true, { done: false, value: bytes }) }) } };
}

beforeEach(() => {
  chats.length = 0; waiting = null; webPolicy = 'ask'; localStorage.setItem('hub.model', 'm1');
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input); let data: unknown = [];
    if (path.endsWith('/api/chat')) { chats.push(JSON.parse(String(init?.body))); return stream(replies.shift() || []); }
    if (path.endsWith('/agent-pending')) data = waiting;
    if (path.endsWith('/savings/status')) data = { auto_route: false, web_search: webPolicy };
    if (path.endsWith('/models')) data = [model];
    if (path.endsWith('/conversations')) data = [{ id: 'c1', title: 'ราคาทองวันนี้', created_at: '2026-11-10T00:00:00+00:00' }];
    if (path.endsWith('/conversations/c1')) data = [{ id: 'q', role: 'user', content: 'ราคาทองวันนี้', citations: [] }, { id: 'a', role: 'assistant', content: 'Agent ต้องการค้นเว็บ', citations: [] }];
    if (path.endsWith('/skills')) data = { skills: [], templates: [], can_share: false };
    if (path.endsWith('/maintenance-status')) data = { maintenance: false, restore: null };
    if (path.endsWith('/config')) data = { ai_gateway_configured: true };
    if (path.endsWith('/account/preferences')) data = { name: 'สมชาย', default_model: 'm1', notifications: true };
    if (path.includes('/analytics')) data = { organizations: 1, users: 1, documents: 0, storage_bytes: 0, requests: 0, cost: 0, input_tokens: 0, output_tokens: 0, daily: [], models: [], model_rows: [], top_users: [], document_status: {} };
    return { ok: true, json: async () => data };
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function ask(text: string) {
  const box = await waitFor(() => screen.getByRole('textbox', { name: /คำถาม|ข้อความ/ }));
  fireEvent.change(box, { target: { value: text } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'ส่งคำถาม' }).hasAttribute('disabled')).toBe(false));
  fireEvent.click(screen.getByRole('button', { name: 'ส่งคำถาม' }));
}

it('offers allow / deny when the agent asks to search the web, and sends the decision', async () => {
  replies = [
    [{ type: 'meta', conversation_id: 'c9', message_id: 'm9', citations: [] }, { type: 'pending', kind: 'approval', tool: 'web_search', queries: ['ราคาทองคำวันนี้'] }, { type: 'delta', text: 'Agent ต้องการค้นเว็บ' }, { type: 'done', message_id: 'm9' }],
    [{ type: 'meta', conversation_id: 'c9', message_id: 'm10', citations: [] }, { type: 'delta', text: 'ทองบาทละ 40,000' }, { type: 'done', message_id: 'm10' }],
  ];
  render(<Hub initialUser={user} />);
  await ask('ราคาทองวันนี้');
  await waitFor(() => expect(chats.length).toBe(1)).catch(() => { throw new Error('no chat request; alerts: ' + screen.queryAllByRole('alert').map(a => a.textContent).join(' / ')); });
  const allow = await waitFor(() => screen.getByRole('button', { name: 'อนุญาต' }));
  expect(screen.getByRole('button', { name: 'ไม่อนุญาต' })).toBeTruthy();
  fireEvent.click(allow);
  await waitFor(() => expect(chats.length).toBe(2));
  expect(chats[1]).toMatchObject({ agent: true, agent_decision: 'approve', conversation_id: 'c9' });
  await waitFor(() => expect(screen.queryByRole('button', { name: 'อนุญาต' })).toBeNull());
});

it('turns the options of a clarifying question into one-click replies', async () => {
  replies = [
    [{ type: 'meta', conversation_id: 'c9', message_id: 'm9', citations: [] }, { type: 'pending', kind: 'question', question: 'หมายถึงการลาประเภทไหน', options: ['ลาพักร้อน', 'ลาป่วย'] }, { type: 'delta', text: 'หมายถึงการลาประเภทไหน' }, { type: 'done', message_id: 'm9' }],
    [{ type: 'meta', conversation_id: 'c9', message_id: 'm10', citations: [] }, { type: 'delta', text: 'ลาป่วยได้ 30 วัน' }, { type: 'done', message_id: 'm10' }],
  ];
  render(<Hub initialUser={user} />);
  await ask('ลาได้กี่วัน');
  fireEvent.click(await waitFor(() => screen.getByRole('button', { name: 'ลาป่วย' })));
  await waitFor(() => expect(chats.length).toBe(2));
  expect(chats[1]).toMatchObject({ question: 'ลาป่วย', agent: true, conversation_id: 'c9' });
  expect(chats[1].agent_decision ?? null).toBeNull();
});

it('disables the web search switch when the organisation forbids web search', async () => {
  webPolicy = 'off';
  render(<Hub initialUser={user} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'ค้นเว็บ' }).getAttribute('title')).toBe('องค์กรปิดการค้นเว็บ'));
  expect(screen.getByRole('button', { name: 'ค้นเว็บ' }).hasAttribute('disabled')).toBe(true);
  await ask('ราคาทองวันนี้');
  await waitFor(() => expect(chats.length).toBe(1));
  expect(chats[0].web_search).toBe(false);
});
