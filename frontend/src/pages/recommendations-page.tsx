import { useMemo, useState } from 'react';
import { ActivitySquare, AlertTriangle } from 'lucide-react';

import {
  RecommendationCard,
  RecommendationConfirmDialog,
  RecommendationRejectDialog,
  RecommendationsLoading,
} from '@/components/recommendations';
import { EmptyState } from '@/components/shared/empty-state';
import { PageHeader } from '@/components/shared/page-header';
import { PageShell } from '@/components/shared/page-shell';
import { useRecommendationActions, usePendingRecommendations } from '@/hooks/use-recommendations';
import type { RecommendationSummary } from '@/lib/api/recommendations';

export function RecommendationsPage() {
  const recommendationsQuery = usePendingRecommendations();
  const { confirm, reject } = useRecommendationActions();
  const [confirmTarget, setConfirmTarget] = useState<RecommendationSummary | null>(null);
  const [rejectTarget, setRejectTarget] = useState<RecommendationSummary | null>(null);
  const [dialogError, setDialogError] = useState<string | null>(null);

  const recommendations = useMemo(
    () => recommendationsQuery.data ?? [],
    [recommendationsQuery.data],
  );

  const handleConfirm = async (actualPrice: number, actualShares: number) => {
    if (!confirmTarget) return;
    setDialogError(null);
    try {
      await confirm.mutateAsync({ recId: confirmTarget.id, actualPrice, actualShares });
      setConfirmTarget(null);
    } catch (error) {
      setDialogError(error instanceof Error ? error.message : 'Nepodařilo se potvrdit doporučení.');
    }
  };

  const handleReject = async (reason: string) => {
    if (!rejectTarget) {
      return;
    }
    setDialogError(null);
    try {
      await reject.mutateAsync({ recId: rejectTarget.id, reason });
      setRejectTarget(null);
    } catch (error) {
      setDialogError(error instanceof Error ? error.message : 'Nepodařilo se odmítnout doporučení.');
    }
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="Doporučení"
        title="Pending a updated recommendations"
        description="Aktivní doporučení od agenta. Po potvrzení nebo odmítnutí karta zmizí — v historii ji najdeš v záložce Historie."
      />

      {recommendationsQuery.isLoading ? <RecommendationsLoading /> : null}

      {!recommendationsQuery.isLoading && recommendationsQuery.error ? (
        <EmptyState
          icon={AlertTriangle}
          title="Nepodařilo se načíst doporučení"
          description={
            recommendationsQuery.error instanceof Error
              ? recommendationsQuery.error.message
              : 'Backend teď nevrátil response pro recommendations.'
          }
        />
      ) : null}

      {!recommendationsQuery.isLoading &&
      !recommendationsQuery.error &&
      recommendations.length === 0 ? (
        <EmptyState
          icon={ActivitySquare}
          title="Žádná doporučení"
          description="Agent teď nic neposlal nebo už je všechno vyřešené. Jakmile přibude pending nebo updated recommendation, ukáže se tady."
        />
      ) : null}

      {!recommendationsQuery.isLoading && !recommendationsQuery.error && recommendations.length > 0 ? (
        <div className="space-y-5">
          {recommendations.map((recommendation) => (
            <RecommendationCard
              key={recommendation.id}
              recommendation={recommendation}
              onConfirm={(target) => {
                setDialogError(null);
                setConfirmTarget(target);
              }}
              onReject={(target) => {
                setDialogError(null);
                setRejectTarget(target);
              }}
            />
          ))}
        </div>
      ) : null}

      <RecommendationConfirmDialog
        error={confirmTarget ? dialogError : null}
        onClose={() => {
          setDialogError(null);
          setConfirmTarget(null);
        }}
        onConfirm={handleConfirm}
        open={!!confirmTarget}
        recommendation={confirmTarget}
        submitting={confirm.isPending}
      />

      <RecommendationRejectDialog
        error={rejectTarget ? dialogError : null}
        onClose={() => {
          setDialogError(null);
          setRejectTarget(null);
        }}
        onReject={handleReject}
        open={!!rejectTarget}
        recommendation={rejectTarget}
        submitting={reject.isPending}
      />
    </PageShell>
  );
}
