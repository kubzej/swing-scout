import type { SelectHTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

export function Select({
  className,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'h-11 w-full rounded-xl border border-input bg-transparent px-3 text-sm outline-none transition focus:ring-2 focus:ring-ring',
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}
