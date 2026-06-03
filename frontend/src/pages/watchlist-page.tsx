import { Radar } from 'lucide-react';

import {
  DiscoveryLogPanel,
  WatchlistLoading,
  WatchlistTable,
} from '@/components/watchlist';
import { EmptyState } from '@/components/shared/empty-state';
import { PageHeader } from '@/components/shared/page-header';
import { PageShell } from '@/components/shared/page-shell';
import { useLatestDailyRun, useRunDetail } from '@/hooks/use-runs';
import { useWatchlist } from '@/hooks/use-watchlist';

export function WatchlistPage() {
  const watchlistQuery = useWatchlist();
  const latestRunQuery = useLatestDailyRun();
  const runDetailQuery = useRunDetail(latestRunQuery.data?.id ?? null);
  const items = watchlistQuery.data ?? [];

  return (
    <PageShell>
      <PageHeader
        eyebrow="Agent watchlist"
        title="Co agent sleduje"
        description="Aktivní ticker shortlist a rychlý vhled do toho, co poslední discovery run opravdu prošel."
      />

      {watchlistQuery.isLoading ? <WatchlistLoading /> : null}

      {watchlistQuery.isError ? (
        <EmptyState
          icon={Radar}
          title="Watchlist se nepodařilo načíst"
          description="API momentálně nevrátilo aktivní watchlist tickery."
        />
      ) : null}

      {!watchlistQuery.isLoading && !watchlistQuery.isError ? (
        <div className="space-y-6">
          <DiscoveryLogPanel
            latestRun={latestRunQuery.data}
            runDetail={runDetailQuery.data}
            loading={latestRunQuery.isLoading || runDetailQuery.isLoading}
          />

          {items.length ? (
            <WatchlistTable items={items} />
          ) : (
            <EmptyState
              icon={Radar}
              title="Watchlist je zatím prázdný"
              description="Až discovery pipeline začne ukládat watching a candidate tickery, objeví se tady celý shortlist."
            />
          )}
        </div>
      ) : null}
    </PageShell>
  );
}
