import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
}

export function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-8 ring-soft">
      <div className="flex max-w-xl flex-col gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-white/6">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <h2 className="text-lg font-medium text-foreground">{title}</h2>
        <p className="text-sm leading-6 text-muted-foreground">{description}</p>
      </div>
    </div>
  );
}
