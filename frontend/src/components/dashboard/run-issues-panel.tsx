import { AlertTriangle, ChevronDown } from 'lucide-react';

import type { RunDiscoveryLog, RunSummary } from '@/lib/api/runs';

interface RunIssuesPanelProps {
  status: RunSummary['status'];
  errorMessage: string | null;
  discoveryLog: RunDiscoveryLog | null;
}

const REASON_LABELS: Record<string, string> = {
  already_held: 'Už držené v portfoliu',
  invalid_stock: 'Neplatný ticker nebo instrument',
  llm_skip: 'LLM označil jako nepoužitelné',
  bear_regime: 'Bear režim vyžadoval vyšší confidence',
  bear_regime_low_confidence: 'Bear režim vyřadil příliš slabou confidence',
  bear_regime_momentum: 'Bear režim vyřadil slabý momentum setup',
  exception: 'Selhání během deep filteru',
  recently_rejected: 'Nedávno zamítnuté',
  portfolio_full: 'Portfolio plné bez rotace',
  insufficient_cash: 'Nedostatek hotovosti',
};

function renderReasonLabel(reason: string) {
  return REASON_LABELS[reason] ?? reason;
}

export function RunIssuesPanel({ status, errorMessage, discoveryLog }: RunIssuesPanelProps) {
  const warnings = discoveryLog?.warnings ?? [];
  const warningSources = discoveryLog?.warning_sources ?? [];
  const warningsCount = discoveryLog?.warnings_count ?? 0;
  const failureReason = discoveryLog?.failure_reason ?? errorMessage ?? 'Run selhal, ale backend neposlal podrobnější důvod.';
  const failedStep = discoveryLog?.failed_step;
  const stage2 = discoveryLog?.stage2_diagnostics ?? null;
  const recommendation = discoveryLog?.recommendation_diagnostics ?? null;
  const hasFailure = status === 'failed';
  const hasWarnings = !hasFailure && Boolean(discoveryLog?.degraded_mode || warningsCount > 0);
  const hasWarningList = warnings.length > 0;
  const noRecommendations = recommendation?.recommendations_out === 0;
  const hasHoldDiagnostics = Boolean(stage2 || recommendation) && noRecommendations;

  if (!hasFailure && !hasWarnings && !hasHoldDiagnostics) {
    return null;
  }

  return (
    <section
      className={
        hasFailure
          ? 'rounded-[1.5rem] border border-rose-400/25 bg-rose-400/8 p-5 text-rose-50 shadow-lg shadow-black/10'
          : 'rounded-[1.5rem] border border-amber-300/20 bg-card/70 p-5 text-foreground shadow-lg shadow-black/10 ring-soft'
      }
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className={hasFailure ? 'mt-0.5 h-5 w-5 shrink-0 text-rose-200' : 'mt-0.5 h-5 w-5 shrink-0 text-amber-300'}
        />
        <div className="min-w-0 space-y-3">
          <div className="space-y-1">
            <div className="text-sm font-semibold text-foreground">
              {hasFailure ? 'Run selhal, protože' : hasHoldDiagnostics ? 'Run doběhl, ale skončil jako HOLD' : 'Run doběhl s warningy'}
            </div>
            <p className={hasFailure ? 'text-sm leading-6 text-rose-50/90' : 'text-sm leading-6 text-muted-foreground'}>
              {hasFailure
                ? failureReason
                : hasHoldDiagnostics
                  ? 'Po doběhu nevzniklo žádné doporučení. Níže je diagnostika, kde se kandidáti ztratili.'
                  : 'Výstup vznikl, ale část providerů nebo kroků běžela s warningy nebo fallbackem.'}
            </p>
            {failedStep ? (
              <div className={hasFailure ? 'text-xs uppercase tracking-[0.16em] text-rose-100/75' : 'text-xs uppercase tracking-[0.16em] text-muted-foreground'}>
                Fáze: {failedStep}
              </div>
            ) : null}
          </div>

          {hasHoldDiagnostics ? (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl border border-border/70 bg-background/35 px-4 py-3">
                <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Stage 2</div>
                <div className="mt-1 text-sm text-foreground">
                  {stage2?.candidates_found ?? discoveryLog?.candidates_found ?? 0} kandidátů z {stage2?.top_signals_count ?? 0} top signálů
                </div>
              </div>
              <div className="rounded-2xl border border-border/70 bg-background/35 px-4 py-3">
                <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Doporučovací vrstva</div>
                <div className="mt-1 text-sm text-foreground">
                  {recommendation?.recommendations_out ?? 0} doporučení z {recommendation?.candidates_in ?? 0} kandidátů
                </div>
              </div>
            </div>
          ) : null}

          {warningSources.length > 0 || warningsCount > 0 ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {warningSources.length > 0 ? <span>Zdroje: {warningSources.join(', ')}</span> : null}
              {warningsCount > 0 ? <span>{warningsCount} warningů celkem</span> : null}
            </div>
          ) : null}

          {hasHoldDiagnostics ? (
            <details className="group rounded-2xl border border-border/70 bg-black/10 px-4 py-3">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground marker:hidden">
                <span>Proč vznikl HOLD</span>
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>

              <div className="mt-3 space-y-4 border-t border-border/60 pt-3 text-sm leading-6 text-muted-foreground">
                {stage2?.rejection_counts && Object.keys(stage2.rejection_counts).length > 0 ? (
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Důvody vyřazení ve Stage 2</div>
                    <div className="space-y-1">
                      {Object.entries(stage2.rejection_counts).map(([reason, count]) => (
                        <div className="flex items-center justify-between gap-3" key={reason}>
                          <span>{renderReasonLabel(reason)}</span>
                          <span className="text-foreground">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}

                {recommendation ? (
                  <div className="space-y-2">
                    <div className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Důvody bez doporučení</div>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between gap-3">
                        <span>Nedávno zamítnuté</span>
                        <span className="text-foreground">{recommendation.recently_rejected_skipped ?? 0}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span>Portfolio plné bez rotace</span>
                        <span className="text-foreground">{recommendation.portfolio_full_skipped ?? 0}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span>Nedostatek hotovosti</span>
                        <span className="text-foreground">{recommendation.insufficient_cash_skipped ?? 0}</span>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}

          {hasWarningList ? (
            <details className="group rounded-2xl border border-border/70 bg-black/10 px-4 py-3">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground marker:hidden">
                <span>Zobrazit všechny warningy</span>
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>

              <div className="mt-3 space-y-2 border-t border-border/60 pt-3 text-sm leading-6 text-muted-foreground">
                {warnings.map((warning, index) => (
                  <div
                    className="rounded-xl border border-border/60 bg-background/40 px-3 py-2"
                    key={`${warning.source}-${index}`}
                  >
                    <div className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground/80">
                      {warning.source}
                    </div>
                    <div>{warning.message}</div>
                  </div>
                ))}
              </div>
            </details>
          ) : null}
        </div>
      </div>
    </section>
  );
}
