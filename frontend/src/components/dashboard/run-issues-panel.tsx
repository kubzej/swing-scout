import { AlertTriangle } from 'lucide-react';

import type { RunDiscoveryLog, RunSummary } from '@/lib/api/runs';

interface RunIssuesPanelProps {
  status: RunSummary['status'];
  errorMessage: string | null;
  discoveryLog: RunDiscoveryLog | null;
}

export function RunIssuesPanel({ status, errorMessage, discoveryLog }: RunIssuesPanelProps) {
  const warnings = discoveryLog?.warnings ?? [];
  const warningSources = discoveryLog?.warning_sources ?? [];
  const warningsCount = discoveryLog?.warnings_count ?? 0;
  const failureReason = discoveryLog?.failure_reason ?? errorMessage;
  const failedStep = discoveryLog?.failed_step;
  const hasFailure = status === 'failed' && Boolean(failureReason);
  const hasWarnings = !hasFailure && Boolean(discoveryLog?.degraded_mode || warningsCount > 0);

  if (!hasFailure && !hasWarnings) {
    return null;
  }

  return (
    <section
      className={
        hasFailure
          ? 'rounded-[1.5rem] border border-rose-400/25 bg-rose-400/10 p-5 text-rose-50 shadow-lg shadow-black/10'
          : 'rounded-[1.5rem] border border-amber-400/25 bg-amber-400/10 p-5 text-amber-50 shadow-lg shadow-black/10'
      }
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
        <div className="min-w-0 space-y-3">
          <div className="space-y-1">
            <div className="text-sm font-semibold">
              {hasFailure ? 'Run selhal, protože' : 'Run doběhl v degraded mode'}
            </div>
            <p className="text-sm leading-6 text-current/90">
              {hasFailure
                ? failureReason
                : 'Výstup vznikl, ale část providerů nebo kroků běžela s warningy nebo fallbackem.'}
            </p>
            {failedStep ? (
              <div className="text-xs uppercase tracking-[0.16em] text-current/75">
                Fáze: {failedStep}
              </div>
            ) : null}
          </div>

          {warningSources.length > 0 ? (
            <div className="text-xs uppercase tracking-[0.16em] text-current/75">
              Zasažené zdroje: {warningSources.join(', ')}
            </div>
          ) : null}

          {warnings.length > 0 ? (
            <div className="space-y-2">
              <div className="text-xs uppercase tracking-[0.16em] text-current/75">
                {warningsCount > 0 ? `${warningsCount} warningů` : 'Warningy'}
              </div>
              <div className="space-y-2 text-sm leading-6 text-current/90">
                {warnings.slice(0, 4).map((warning, index) => (
                  <div
                    className="rounded-2xl border border-current/15 bg-black/10 px-4 py-3"
                    key={`${warning.source}-${index}`}
                  >
                    <div className="text-xs uppercase tracking-[0.16em] text-current/70">
                      {warning.source}
                    </div>
                    <div>{warning.message}</div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
