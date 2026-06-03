import { Badge } from '@/components/ui/badge';

const STAGE_STYLES: Record<string, string> = {
  watching: 'border-sky-400/30 bg-sky-400/12 text-sky-100',
  candidate: 'border-primary/30 bg-primary/12 text-accent-foreground',
};

const STAGE_LABELS: Record<string, string> = {
  watching: 'Watching',
  candidate: 'Candidate',
};

interface StageBadgeProps {
  stage: string;
}

export function StageBadge({ stage }: StageBadgeProps) {
  const normalized = stage.toLowerCase();
  return (
    <Badge className={STAGE_STYLES[normalized] ?? 'border-border bg-white/6 text-foreground'}>
      {STAGE_LABELS[normalized] ?? stage}
    </Badge>
  );
}
