import { AlertTriangle, CheckCircle2, LoaderCircle, type LucideIcon } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

type RunStatus = 'running' | 'completed' | 'failed';

const STATUS_META: Record<
  RunStatus,
  { label: string; icon: LucideIcon; className: string }
> = {
  running: {
    label: 'Běží',
    icon: LoaderCircle,
    className: 'border-sky-400/30 bg-sky-400/12 text-sky-200',
  },
  completed: {
    label: 'Dokončeno',
    icon: CheckCircle2,
    className: 'border-emerald-400/30 bg-emerald-400/12 text-emerald-200',
  },
  failed: {
    label: 'Selhalo',
    icon: AlertTriangle,
    className: 'border-rose-400/30 bg-rose-400/12 text-rose-200',
  },
};

interface RunStatusBadgeProps {
  status: RunStatus;
}

export function RunStatusBadge({ status }: RunStatusBadgeProps) {
  const meta = STATUS_META[status];
  const Icon = meta.icon;

  return (
    <Badge className={cn('gap-1.5', meta.className)}>
      <Icon className={cn('h-3.5 w-3.5', status === 'running' && 'animate-spin')} />
      {meta.label}
    </Badge>
  );
}
