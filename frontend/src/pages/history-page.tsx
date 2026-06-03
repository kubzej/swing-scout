import { useEffect, useState } from 'react';
import { History } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { ReportPanel } from '@/components/dashboard/report-panel';
import {
  HistoryLoading,
  HistoryTabs,
  RecommendationTimeline,
  ReportArchiveList,
  TransactionHistory,
} from '@/components/history';
import type { HistoryTab } from '@/components/history';
import { EmptyState } from '@/components/shared/empty-state';
import { PageHeader } from '@/components/shared/page-header';
import { PageShell } from '@/components/shared/page-shell';
import { useRecommendationHistory } from '@/hooks/use-recommendations';
import { useRunDetail } from '@/hooks/use-runs';
import { fetchRuns } from '@/lib/api/runs';
import { fetchTransactions } from '@/lib/api/transactions';
import { GC_TIMES, queryKeys, STALE_TIMES } from '@/lib/query-client';

export function HistoryPage() {
  const [activeTab, setActiveTab] = useState<HistoryTab>('reports');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const runsQuery = useQuery({
    queryKey: queryKeys.history(),
    queryFn: () => fetchRuns({ limit: 20, runType: 'daily' }),
    staleTime: STALE_TIMES.history,
    gcTime: GC_TIMES.medium,
  });
  const selectedRunQuery = useRunDetail(selectedRunId);
  const recommendationHistoryQuery = useRecommendationHistory();
  const transactionsQuery = useQuery({
    queryKey: ['transactions'],
    queryFn: () => fetchTransactions(200),
    staleTime: STALE_TIMES.recommendations,
    gcTime: GC_TIMES.medium,
    enabled: activeTab === 'transactions',
  });

  useEffect(() => {
    if (!selectedRunId && runsQuery.data?.length) {
      setSelectedRunId(runsQuery.data[0].id);
    }
  }, [runsQuery.data, selectedRunId]);

  return (
    <PageShell>
      <PageHeader
        eyebrow="Historie"
        title="Archiv runů a doporučení"
        description="Staré reporty, recommendation timeline a kompletní přehled transakcí."
      />

      {runsQuery.isLoading && activeTab === 'reports' ? <HistoryLoading /> : null}

      {activeTab === 'reports' && runsQuery.isError ? (
        <EmptyState
          icon={History}
          title="Historii runů se nepodařilo načíst"
          description="Archiv daily runů momentálně není dostupný."
        />
      ) : null}

      <div className="space-y-6">
        <HistoryTabs activeTab={activeTab} onChange={setActiveTab} />

        {activeTab === 'reports' ? (
          <div className="grid gap-6 xl:grid-cols-[24rem_minmax(0,1fr)]">
            <ReportArchiveList
              runs={runsQuery.data ?? []}
              selectedRunId={selectedRunId}
              onSelect={setSelectedRunId}
            />
            <ReportPanel reportContent={selectedRunQuery.data?.report_content ?? null} />
          </div>
        ) : null}

        {activeTab === 'recommendations' ? (
          recommendationHistoryQuery.isError ? (
            <EmptyState
              icon={History}
              title="Recommendation historie se nepodařilo načíst"
              description="Backend momentálně nevrátil timeline zpracovaných doporučení."
            />
          ) : recommendationHistoryQuery.isLoading ? (
            <HistoryLoading />
          ) : (
            <RecommendationTimeline recommendations={recommendationHistoryQuery.data ?? []} />
          )
        ) : null}

        {activeTab === 'transactions' ? (
          transactionsQuery.isLoading ? (
            <HistoryLoading />
          ) : transactionsQuery.isError ? (
            <EmptyState
              icon={History}
              title="Transakce se nepodařilo načíst"
              description="Backend momentálně nevrátil historii transakcí."
            />
          ) : (
            <TransactionHistory transactions={transactionsQuery.data ?? []} />
          )
        ) : null}
      </div>
    </PageShell>
  );
}
