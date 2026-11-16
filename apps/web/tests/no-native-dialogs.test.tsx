import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { blockNativeDialogs } from '../components/ui/confirm';

const ROOT = path.resolve(__dirname, '..');
const files = ['components', 'app', 'lib']
  .flatMap(dir => {
    const walk = (d: string): string[] => (fs.existsSync(d) ? fs.readdirSync(d, { withFileTypes: true }).flatMap(e => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)])) : []);
    return walk(path.join(ROOT, dir));
  })
  .filter(f => /\.(tsx?|jsx?)$/.test(f) && !f.endsWith(path.join('ui', 'confirm.tsx')));

describe('native browser dialogs are banned', () => {
  it('no alert(), prompt() or window./globalThis. dialog calls in source', () => {
    const hits = files.flatMap(f => {
      const s = fs.readFileSync(f, 'utf8');
      return [...s.matchAll(/(?<![\w.])(alert|prompt)\s*\(|\b(window|globalThis|self)\s*\.\s*(alert|confirm|prompt)\b/g)].map(m => `${path.relative(ROOT, f)}: ${m[0]}`);
    });
    expect(hits).toEqual([]);
  });

  it('every bare confirm() call is the useConfirm() hook, not window.confirm', () => {
    const unbound = files.flatMap(f => {
      const s = fs.readFileSync(f, 'utf8');
      return [...s.matchAll(/(?<![\w.])confirm\s*\(/g)].flatMap(m => {
        const before = s.slice(0, m.index);
        const fnStart = Math.max(before.lastIndexOf('\nfunction '), before.lastIndexOf('\nexport function '), 0);
        return s.slice(fnStart, m.index).includes('useConfirm()') ? [] : [`${path.relative(ROOT, f)} @${m.index}`];
      });
    });
    expect(unbound).toEqual([]);
  });

  it('runtime guard makes window.alert/confirm/prompt throw', () => {
    const restore = blockNativeDialogs();
    expect(() => window.alert('x')).toThrow(/disabled/);
    expect(() => window.confirm('x')).toThrow(/disabled/);
    expect(() => window.prompt('x')).toThrow(/disabled/);
    restore();
  });
});
