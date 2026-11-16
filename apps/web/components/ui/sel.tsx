'use client';
import * as React from 'react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './select';
import { cn } from '../../lib/utils';

// Radix forbids value="" on items, so an empty option maps to a sentinel.
const EMPTY = '__empty__';
type Opt = { value: string; label: React.ReactNode; disabled?: boolean };

function collect(children: React.ReactNode, out: Opt[] = []): Opt[] {
  React.Children.forEach(children, (c) => {
    if (!React.isValidElement(c)) return;
    const p = c.props as { value?: string | number; children?: React.ReactNode; disabled?: boolean };
    if (c.type === React.Fragment) return void collect(p.children, out);
    if (c.type === 'option') {
      const label = p.children;
      const text = React.Children.toArray(label).join('');
      out.push({ value: String(p.value ?? text), label, disabled: p.disabled });
    }
  });
  return out;
}

type Props = {
  value?: string | number; defaultValue?: string; // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onChange?: (e: any) => unknown; onBlur?: (e: any) => unknown;
  name?: string; disabled?: boolean; required?: boolean; className?: string; children?: React.ReactNode; 'aria-label'?: string; id?: string;
};

/** Drop-in replacement for `<select>` built on shadcn's Select; also works with react-hook-form's `register()`. */
export const Sel = React.forwardRef<unknown, Props>(function Sel({ value, defaultValue, onChange, onBlur, name, disabled, className, children, ...rest }, ref) {
  const opts = collect(children);
  const [inner, setInner] = React.useState(String(defaultValue ?? ''));
  const controlled = value !== undefined;
  const current = controlled ? String(value) : inner;
  const innerRef = React.useRef(inner); innerRef.current = current;
  React.useImperativeHandle(ref, () => ({
    name, focus() {}, get value() { return innerRef.current; }, set value(v: string) { innerRef.current = String(v ?? ''); setInner(String(v ?? '')); },
  }), [name]);
  const known = opts.some((o) => o.value === current);
  const items = known || !current ? opts : [{ value: current, label: current }, ...opts];
  return (
    <Select value={current === '' ? EMPTY : current} onValueChange={(v) => { const next = v === EMPTY ? '' : v; if (!controlled) setInner(next); onChange?.({ target: { value: next, name } }); }} disabled={disabled} name={name}>
      <SelectTrigger aria-label={rest['aria-label']} id={rest.id} onBlur={() => onBlur?.({ target: { value: innerRef.current, name }, type: 'blur' })} className={cn('w-full min-w-0', className)}>
        <span className="min-w-0 truncate"><SelectValue /></span>
      </SelectTrigger>
      <SelectContent>
        {items.map((o) => <SelectItem key={o.value} value={o.value === '' ? EMPTY : o.value} disabled={o.disabled}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  );
});
