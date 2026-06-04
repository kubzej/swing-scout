import { formatDateTime } from '@/lib/format';
import type { RunSummary } from '@/lib/api/runs';

import { RunStatusBadge } from './run-status-badge';

interface RunSummaryCardProps {
  run: RunSummary;
}

export function RunSummaryCard({ run }: RunSummaryCardProps) {
  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 p-5 shadow-lg shadow-black/10 ring-soft">
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Poslední daily run
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <RunStatusBadge status={run.status} />
            <span className="text-sm text-muted-foreground">
              Start: {formatDateTime(run.started_at)}
            </span>
            {run.completed_at ? (
              <span className="text-sm text-muted-foreground">
                Konec: {formatDateTime(run.completed_at)}
              </span>
            ) : null}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm md:min-w-64">
          <div className="rounded-2xl border border-border bg-white/4 px-4 py-3">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              Režim trhu
            </div>
            <div className="mt-1 font-medium text-foreground">
              {run.market_regime ? run.market_regime.toUpperCase() : '—'}
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-white/4 px-4 py-3">
            <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              Sentiment
            </div>
            <div className="mt-1 font-medium text-foreground">
              {run.fng_score ?? '—'}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
