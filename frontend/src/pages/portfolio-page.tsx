import { useMemo, useState } from 'react';
import { BriefcaseBusiness, Plus } from 'lucide-react';

import {
  HoldingsTable,
  ManualTradeDialog,
  PortfolioLoading,
  PortfolioSummary,
  SectorExposurePanel,
} from '@/components/portfolio';
import { EmptyState } from '@/components/shared/empty-state';
import { PageHeader } from '@/components/shared/page-header';
import { PageShell } from '@/components/shared/page-shell';
import { Button } from '@/components/ui/button';
import {
  useManualTrade,
  usePortfolioSnapshot,
  usePortfolioThesisStatuses,
} from '@/hooks/use-portfolio';

export function PortfolioPage() {
  const [manualTradeOpen, setManualTradeOpen] = useState(false);

  const snapshotQuery = usePortfolioSnapshot();
  const positions = snapshotQuery.data?.positions ?? [];
  const thesisStatuses = usePortfolioThesisStatuses(positions);
  const manualTrade = useManualTrade();

  const portfolioMetrics = useMemo(() => {
    if (!snapshotQuery.data) return null;
    return {
      totalValueCzk: snapshotQuery.data.total_value_czk,
      totalCostCzk: snapshotQuery.data.total_cost_czk,
      totalPnlCzk: snapshotQuery.data.total_pnl_czk,
      totalPnlPct: snapshotQuery.data.total_pnl_pct,
      cashCzk: snapshotQuery.data.cash_czk,
      totalReturnPct: snapshotQuery.data.total_return_pct,
      totalRealizedPnlCzk: snapshotQuery.data.total_realized_pnl_czk ?? 0,
    };
  }, [snapshotQuery.data]);

  return (
    <PageShell>
      <PageHeader
        eyebrow="Portfolio"
        title="Pozice, cash a thesis stav"
        description="Portfolio snapshot, thesis stav pro každou pozici a rychlý manuální trade flow mimo doporučení agenta."
        actions={(
          <Button type="button" variant="outline" onClick={() => setManualTradeOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            Manuální trade
          </Button>
        )}
      />

      {snapshotQuery.isLoading ? <PortfolioLoading /> : null}

      {snapshotQuery.isError ? (
        <EmptyState
          icon={BriefcaseBusiness}
          title="Portfolio se nepodařilo načíst"
          description="API snapshot momentálně nevrátilo data. Zkus to prosím znovu za chvíli."
        />
      ) : null}

      {snapshotQuery.data && portfolioMetrics ? (
        <div className="space-y-6">
          <PortfolioSummary {...portfolioMetrics} />
          <SectorExposurePanel exposure={snapshotQuery.data.sector_exposure} />

          {positions.length ? (
            <HoldingsTable
              positions={positions}
              thesisStatuses={thesisStatuses.byPositionId}
            />
          ) : (
            <EmptyState
              icon={BriefcaseBusiness}
              title="Portfolio je zatím prázdné"
              description="Až potvrdíš doporučení nebo zaloguješ manuální trade, objeví se tady holdings a thesis tracking."
            />
          )}

          {thesisStatuses.hasError ? (
            <div className="rounded-2xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-yellow-100">
              Některé thesis detaily se nepodařilo načíst. Holdings ale zůstávají použitelné.
            </div>
          ) : null}
        </div>
      ) : null}

      <ManualTradeDialog
        open={manualTradeOpen}
        loading={manualTrade.isPending}
        onClose={() => setManualTradeOpen(false)}
        onSubmit={async (payload) => {
          await manualTrade.mutateAsync(payload);
        }}
      />
    </PageShell>
  );
}
