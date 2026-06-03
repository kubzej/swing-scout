import { Badge } from '@/components/ui/badge';

const STATUS_STYLES: Record<string, string> = {
  intact: 'border-emerald-400/30 bg-emerald-400/12 text-emerald-100',
  weakening: 'border-amber-400/30 bg-amber-400/12 text-amber-100',
  broken: 'border-rose-400/30 bg-rose-400/12 text-rose-100',
  exited: 'border-slate-400/30 bg-slate-400/12 text-slate-100',
  missing: 'border-border bg-white/6 text-muted-foreground',
  loading: 'border-sky-400/30 bg-sky-400/12 text-sky-100',
  error: 'border-rose-400/30 bg-rose-400/12 text-rose-100',
};

const STATUS_LABELS: Record<string, string> = {
  intact: 'Intaktní',
  weakening: 'Slábne',
  broken: 'Porušena',
  exited: 'Uzavřena',
  missing: 'Bez teze',
  loading: 'Načítám',
  error: 'Chyba',
};

interface ThesisStatusBadgeProps {
  status: string;
}

export function ThesisStatusBadge({ status }: ThesisStatusBadgeProps) {
  const normalized = status.toLowerCase();
  const label = STATUS_LABELS[normalized] ?? status;
  const className = STATUS_STYLES[normalized] ?? STATUS_STYLES.missing;

  return <Badge className={className}>{label}</Badge>;
}
