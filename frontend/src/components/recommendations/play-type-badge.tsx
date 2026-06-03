import { Badge } from '@/components/ui/badge';

const PLAY_META = {
  A: { label: 'Fundamental', className: 'border-amber-400/30 bg-amber-400/12 text-amber-100' },
  B: { label: 'Katalyzátor', className: 'border-cyan-400/30 bg-cyan-400/12 text-cyan-100' },
  C: { label: 'Momentum', className: 'border-fuchsia-400/30 bg-fuchsia-400/12 text-fuchsia-100' },
} as const;

interface PlayTypeBadgeProps {
  playType: 'A' | 'B' | 'C';
}

export function PlayTypeBadge({ playType }: PlayTypeBadgeProps) {
  const meta = PLAY_META[playType];
  return <Badge className={meta.className}>{meta.label}</Badge>;
}
