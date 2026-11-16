import { Brain } from 'lucide-react';
import type { ReactNode } from 'react';
import { tr } from '../lib/i18n';

// Logos from the lobe-icons set (public/brands). `color` ones keep their own colours; the others are single-colour and follow the text colour (works in dark mode).
type Brand = { file: string; mono?: boolean; label: string };
const BRANDS: Record<string, Brand> = {
  anthropic: { file: 'claude-color', label: 'Claude' },
  openai: { file: 'openai', mono: true, label: 'OpenAI' },
  google: { file: 'gemini-color', label: 'Gemini' },
  deepseek: { file: 'deepseek-color', label: 'DeepSeek' },
  'z-ai': { file: 'zai', mono: true, label: 'Z.ai' },
  xiaomi: { file: 'xiaomi-color', label: 'Xiaomi' },
  moonshotai: { file: 'kimi-color', label: 'Kimi' },
  qwen: { file: 'qwen-color', label: 'Qwen' },
  'meta-llama': { file: 'meta-color', label: 'Meta' },
  meta: { file: 'meta-color', label: 'Meta' },
  minimax: { file: 'minimax-color', label: 'MiniMax' },
  'black-forest-labs': { file: 'flux', mono: true, label: 'FLUX' },
  recraft: { file: 'recraft', mono: true, label: 'Recraft' },
  mistralai: { file: 'mistral-color', label: 'Mistral' },
  'x-ai': { file: 'xai', mono: true, label: 'xAI' },
  tbc: { file: '', label: 'TBC' },
  openrouter: { file: 'openrouter-color', label: 'OpenRouter' },
};

/** Vendor of a model: the part before "/" in its api_id (OpenRouter style), else guessed from the display name. */
export function brandOf(m: { api_id?: string; name?: string; provider?: string }): Brand | null {
  const vendor = (m.api_id || '').includes('/') ? (m.api_id || '').split('/')[0].toLowerCase().replace(/^~/, '') : '';
  if (BRANDS[vendor]) return BRANDS[vendor];
  const text = `${m.name || ''} ${m.api_id || ''}`.toLowerCase();
  if (/claude/.test(text)) return BRANDS.anthropic;
  if (/gpt|chatgpt|openai|\bo[134]\b/.test(text)) return BRANDS.openai;
  if (/gemini|gemma/.test(text)) return BRANDS.google;
  if (/qwen/.test(text)) return BRANDS.qwen;
  if (/deepseek/.test(text)) return BRANDS.deepseek;
  if (/glm|z\.ai/.test(text)) return BRANDS['z-ai'];
  if (/mimo|xiaomi/.test(text)) return BRANDS.xiaomi;
  if (/kimi|moonshot/.test(text)) return BRANDS.moonshotai;
  if (/llama|muse/.test(text)) return BRANDS['meta-llama'];
  if (/minimax/.test(text)) return BRANDS.minimax;
  if (/flux/.test(text)) return BRANDS['black-forest-labs'];
  if (/recraft/.test(text)) return BRANDS.recraft;
  if (/mistral/.test(text)) return BRANDS.mistralai;
  if (/\btbc\b|mischief/.test(text)) return BRANDS.tbc;
  return null;
}

export function ModelIcon({ m, size = 16 }: { m: { api_id?: string; name?: string; provider?: string }; size?: number }) {
  const b = brandOf(m);
  if (b && !b.file) return <span aria-hidden className="inline-flex shrink-0 items-center justify-center rounded-[3px] border border-current font-bold leading-none" style={{ width: size, height: size, fontSize: Math.max(6, size * 0.42) }}>{b.label}</span>;
  if (!b) return <Brain className="shrink-0" style={{ width: size, height: size }} aria-hidden />;
  const url = `/brands/${b.file}.svg`;
  return b.mono
    ? <span aria-hidden className="inline-block shrink-0 bg-current" style={{ width: size, height: size, WebkitMask: `url(${url}) center/contain no-repeat`, mask: `url(${url}) center/contain no-repeat` }} />
    // eslint-disable-next-line @next/next/no-img-element
    : <img src={url} alt="" aria-hidden width={size} height={size} className="shrink-0" style={{ width: size, height: size }} />;
}

/** Icon + name, used inside select items (Radix also shows it in the closed trigger). */
export function ModelLabel({ m, children }: { m: { api_id?: string; name?: string; provider?: string }; children: ReactNode }) {
  return <span className="inline-flex min-w-0 items-center gap-2"><ModelIcon m={m} /><span className="truncate">{children}</span></span>;
}

const ORDER = ['OpenAI', 'Claude', 'Gemini', 'DeepSeek', 'Z.ai', 'Xiaomi', 'Kimi', 'MiniMax', 'Qwen', 'Meta', 'Mistral', 'xAI', 'FLUX', 'Recraft', 'TBC', 'OpenRouter'];

/** Models grouped by company (fixed order); inside a group most expensive (top tier) first, cheapest (entry level) last. Price is OpenRouter's, kept in sync. */
export function groupModels<T extends { api_id?: string; name?: string; display_name?: string; provider?: string; input_price?: number; output_price?: number }>(models: T[]) {
  const groups = new Map<string, T[]>();
  for (const m of models) {
    const label = brandOf(m)?.label ?? tr('อื่น ๆ');
    groups.set(label, [...(groups.get(label) ?? []), m]);
  }
  const rank = (l: string) => { const i = ORDER.indexOf(l); return i < 0 ? ORDER.length : i; };
  return [...groups.entries()]
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
    .map(([label, items]) => ({ label, items: [...items].sort((x, y) => (y.output_price ?? 0) - (x.output_price ?? 0) || (y.input_price ?? 0) - (x.input_price ?? 0) || (x.display_name || x.name || '').localeCompare(y.display_name || y.name || '', 'th', { numeric: true, sensitivity: 'base' })) }));
}
