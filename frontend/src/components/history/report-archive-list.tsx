import { RunStatusBadge } from '@/components/dashboard/run-status-badge';
import { Button } from '@/components/ui/button';
import type { RunSummary } from '@/lib/api/runs';
import { formatDateTime } from '@/lib/format';
import { cn } from '@/lib/utils';

interface ReportArchiveListProps {
  runs: RunSummary[];
  selectedRunId: string | null;
  onSelect: (runId: string) => void;
}

export function ReportArchiveList({
  runs,
  selectedRunId,
  onSelect,
}: ReportArchiveListProps) {
  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 p-5 shadow-lg shadow-black/10 ring-soft">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-foreground">Archiv runů</h2>
        <p className="text-sm text-muted-foreground">
          Vyber report, který chceš znovu otevřít.
        </p>
      </div>

      <div className="space-y-3">
        {runs.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onSelect(run.id)}
            className={cn(
              'w-full rounded-2xl border border-border px-4 py-4 text-left transition',
              selectedRunId === run.id ? 'bg-white/8' : 'bg-white/4 hover:bg-white/6',
            )}
          >
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="text-sm font-medium text-foreground">
                  Daily run · {formatDateTime(run.started_at)}
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  Regime {run.market_regime || '—'} · Fear & Greed {run.fng_score ?? '—'}
                </div>
              </div>
              <RunStatusBadge status={run.status} />
            </div>
          </button>
        ))}
      </div>

      {!runs.length ? (
        <div className="mt-4 rounded-2xl border border-dashed border-border px-4 py-5 text-sm text-muted-foreground">
          Zatím tu nejsou žádné uložené daily runy.
        </div>
      ) : null}

      {runs.length > 0 && !selectedRunId ? (
        <div className="mt-4">
          <Button type="button" variant="ghost" onClick={() => onSelect(runs[0].id)}>
            Otevřít nejnovější report
          </Button>
        </div>
      ) : null}
    </section>
  );
}
