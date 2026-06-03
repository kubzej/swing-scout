import { Activity, ArrowDownRight, ArrowUpRight, DoorOpen, ShieldEllipsis } from 'lucide-react';

import { Badge } from '@/components/ui/badge';

const ACTION_META = {
  buy: { label: 'Koupit', icon: ArrowUpRight, className: 'border-emerald-400/30 bg-emerald-400/12 text-emerald-200' },
  add: { label: 'Přikoupit', icon: ArrowUpRight, className: 'border-lime-400/30 bg-lime-400/12 text-lime-200' },
  sell: { label: 'Prodat', icon: ArrowDownRight, className: 'border-rose-400/30 bg-rose-400/12 text-rose-200' },
  exit: { label: 'Exit', icon: DoorOpen, className: 'border-rose-400/30 bg-rose-400/12 text-rose-200' },
  csp: { label: 'CSP', icon: ShieldEllipsis, className: 'border-sky-400/30 bg-sky-400/12 text-sky-200' },
  long_call: { label: 'Long Call', icon: Activity, className: 'border-violet-400/30 bg-violet-400/12 text-violet-200' },
} as const;

interface ActionBadgeProps {
  action: keyof typeof ACTION_META | string;
}

export function ActionBadge({ action }: ActionBadgeProps) {
  const meta = ACTION_META[action as keyof typeof ACTION_META];
  if (!meta) {
    return <Badge>{action}</Badge>;
  }

  const Icon = meta.icon;
  return (
    <Badge className={`gap-1.5 ${meta.className}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </Badge>
  );
}
