import { useEffect, useState } from 'react';
import { AlertTriangle, RefreshCw, ScrollText } from 'lucide-react';

import {
  DashboardLoading,
  PendingRecommendationsBadge,
  ReportPanel,
  RunIssuesPanel,
  RunSummaryCard,
} from '@/components/dashboard';
import { EmptyState } from '@/components/shared/empty-state';
import { PageHeader } from '@/components/shared/page-header';
import { PageShell } from '@/components/shared/page-shell';
import { Button } from '@/components/ui/button';
import { usePendingRecommendations } from '@/hooks/use-recommendations';
import {
  isRunStillActive,
  useLatestDailyRun,
  useRunDetail,
  useTriggerDailyRun,
} from '@/hooks/use-runs';

export function DashboardPage() {
  const [watchStartedAt, setWatchStartedAt] = useState<number | null>(null);
  const triggerMutation = useTriggerDailyRun();
  const latestRunQuery = useLatestDailyRun({
    refetchInterval:
      triggerMutation.isPending || watchStartedAt
        ? 3_000
        : false,
  });
  const pendingRecommendationsQuery = usePendingRecommendations();

  const latestRun = latestRunQuery.data;
  const activePolling = isRunStillActive(latestRun ?? null, watchStartedAt);
  const runDetailQuery = useRunDetail(latestRun?.id ?? null, {
    refetchInterval: activePolling ? 3_000 : false,
  });

  useEffect(() => {
    if (!watchStartedAt || !latestRun) {
      return;
    }

    const runStartedAt = new Date(latestRun.started_at).getTime();
    if (runStartedAt < watchStartedAt) {
      return;
    }

    if (latestRun.status !== 'running') {
      void runDetailQuery.refetch();
      setWatchStartedAt(null);
    }
  }, [latestRun, runDetailQuery, watchStartedAt]);

  const pendingCount = pendingRecommendationsQuery.data?.length ?? 0;
  const isLoading =
    latestRunQuery.isLoading || (latestRun?.id ? runDetailQuery.isLoading : false);
  const reportContent = runDetailQuery.data?.report_content ?? null;

  const handleTriggerRun = async () => {
    setWatchStartedAt(Date.now());
    try {
      await triggerMutation.mutateAsync();
    } catch {
      setWatchStartedAt(null);
    }
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="Denní report"
        title="Ranní briefing a stav běhu"
        description="Tady žije poslední daily run, markdown report, rerun flow a přehled čekajících doporučení."
        actions={
          <>
            <PendingRecommendationsBadge count={pendingCount} />
            <Button
              disabled={triggerMutation.isPending || activePolling}
              onClick={() => {
                void handleTriggerRun();
              }}
              variant="outline"
            >
              <RefreshCw
                className={`mr-2 h-4 w-4 ${
                  triggerMutation.isPending || activePolling ? 'animate-spin' : ''
                }`}
              />
              {triggerMutation.isPending || activePolling ? 'Spouštím…' : 'Spustit rerun'}
            </Button>
          </>
        }
      />

      {isLoading ? <DashboardLoading /> : null}

      {!isLoading && latestRunQuery.error ? (
        <EmptyState
          icon={AlertTriangle}
          title="Nepodařilo se načíst dashboard"
          description={
            latestRunQuery.error instanceof Error
              ? latestRunQuery.error.message
              : 'Backend pro runs teď nevrátil odpověď.'
          }
        />
      ) : null}

      {!isLoading && !latestRunQuery.error && !latestRun ? (
        <EmptyState
          icon={ScrollText}
          title="Zatím tu není žádný daily run"
          description="Jakmile agent proběhne poprvé, objeví se tady poslední report, stav běhu a rerun flow."
        />
      ) : null}

      {!isLoading && !latestRunQuery.error && latestRun ? (
        <>
          <RunSummaryCard run={latestRun} />
          <RunIssuesPanel
            status={latestRun.status}
            errorMessage={latestRun.error_message}
            discoveryLog={runDetailQuery.data?.discovery_log ?? null}
          />
          <ReportPanel reportContent={reportContent} />
        </>
      ) : null}
    </PageShell>
  );
}
