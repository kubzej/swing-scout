import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

interface BadgeProps {
  children: ReactNode;
  className?: string;
}

export function Badge({ children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border border-border bg-white/6 px-2.5 py-1 text-xs font-medium text-foreground',
        className,
      )}
    >
      {children}
    </span>
  );
}
