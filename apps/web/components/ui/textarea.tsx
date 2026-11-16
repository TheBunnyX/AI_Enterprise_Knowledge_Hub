import * as React from 'react';
import { cn } from '../../lib/utils';

/** shadcn Textarea without `field-sizing-content`/`min-h-16`, so callers can control height (e.g. JS autosize). */
export function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea data-slot="textarea" className={cn('flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive', className)} {...props} />;
}
