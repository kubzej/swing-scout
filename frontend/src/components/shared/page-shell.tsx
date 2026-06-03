import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

type ShellWidth = 'default' | 'wide' | 'full';

const WIDTH_CLASSES: Record<ShellWidth, string> = {
  default: 'mx-auto w-full max-w-5xl',
  wide: 'mx-auto w-full max-w-7xl',
  full: 'w-full',
};

interface PageShellProps {
  children: ReactNode;
  width?: ShellWidth;
  className?: string;
}

export function PageShell({
  children,
  width = 'wide',
  className,
}: PageShellProps) {
  return (
    <div className={cn('space-y-6 pb-12', WIDTH_CLASSES[width], className)}>
      {children}
    </div>
  );
}
