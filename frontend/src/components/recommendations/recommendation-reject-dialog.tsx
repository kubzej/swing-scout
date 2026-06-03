import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { RecommendationSummary } from '@/lib/api/recommendations';

interface RecommendationRejectDialogProps {
  open: boolean;
  recommendation: RecommendationSummary | null;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onReject: (reason: string) => Promise<void>;
}

export function RecommendationRejectDialog({
  open,
  recommendation,
  submitting,
  error,
  onClose,
  onReject,
}: RecommendationRejectDialogProps) {
  const [reason, setReason] = useState('');

  useEffect(() => {
    setReason('');
  }, [recommendation?.id]);

  if (!open || !recommendation) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-[1.75rem] border border-border bg-card p-6 shadow-2xl shadow-black/30">
        <div className="space-y-2">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Odmítnout doporučení
          </div>
          <h2 className="text-xl font-semibold text-foreground">
            {recommendation.ticker} {recommendation.action.toUpperCase()}
          </h2>
          <p className="text-sm leading-6 text-muted-foreground">
            Důvod je volitelný, ale hodí se pro budoucí kalibraci agenta.
          </p>
        </div>

        <div className="mt-5 space-y-2">
          <label className="text-sm font-medium text-foreground" htmlFor="reject-reason">
            Důvod odmítnutí
          </label>
          <Textarea
            id="reject-reason"
            placeholder="Např. chci počkat na pullback, thesis mi nesedí, sektor už mám plný…"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </div>

        {error ? <p className="mt-4 text-sm text-negative">{error}</p> : null}

        <div className="mt-6 flex justify-end gap-3">
          <Button disabled={submitting} onClick={onClose} variant="ghost">
            Zrušit
          </Button>
          <Button
            disabled={submitting}
            onClick={() => {
              void onReject(reason.trim());
            }}
            variant="outline"
          >
            {submitting ? 'Ukládám…' : 'Odmítnout'}
          </Button>
        </div>
      </div>
    </div>
  );
}
