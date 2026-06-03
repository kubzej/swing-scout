import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchFxRates, type RecommendationSummary } from '@/lib/api/recommendations';
import { formatCurrency } from '@/lib/format';

interface RecommendationConfirmDialogProps {
  open: boolean;
  recommendation: RecommendationSummary | null;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: (actualPrice: number, actualShares: number) => Promise<void>;
}

const FX_FALLBACKS: Record<string, number> = {
  USD: 23, EUR: 25, GBP: 29, HKD: 3,
};

export function RecommendationConfirmDialog({
  open,
  recommendation,
  submitting,
  error,
  onClose,
  onConfirm,
}: RecommendationConfirmDialogProps) {
  const [actualPrice, setActualPrice] = useState('');
  const [actualShares, setActualShares] = useState('');
  const [fxRates, setFxRates] = useState<Record<string, number>>({});

  const opts = recommendation?.options_details as Record<string, unknown> | null;
  const currency = (opts?.currency as string) || 'USD';
  const fxKey = `${currency}_CZK`;
  const fxRate = fxRates[fxKey] ?? FX_FALLBACKS[currency] ?? 23;

  useEffect(() => {
    if (!recommendation) {
      setActualPrice('');
      setActualShares('');
      return;
    }
    setActualPrice(String(recommendation.recommended_price ?? ''));
    setActualShares(String((opts?.recommended_shares as number) ?? ''));
    fetchFxRates().then((fx) => setFxRates(fx as Record<string, number>)).catch(() => {});
  }, [recommendation]);

  if (!open || !recommendation) return null;

  const parsedPrice = Number(actualPrice);
  const parsedShares = Number(actualShares);
  const isValid =
    Number.isFinite(parsedPrice) && parsedPrice > 0 &&
    Number.isFinite(parsedShares) && parsedShares > 0;

  const totalCzk =
    parsedPrice > 0 && parsedShares > 0
      ? new Intl.NumberFormat('cs-CZ', { style: 'currency', currency: 'CZK', maximumFractionDigits: 0 })
          .format(parsedShares * parsedPrice * fxRate)
      : null;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-[1.75rem] border border-border bg-card p-6 shadow-2xl shadow-black/30">
        <div className="space-y-1 mb-5">
          <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Potvrdit nákup
          </div>
          <h2 className="text-xl font-semibold text-foreground">
            {recommendation.ticker}
          </h2>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground" htmlFor="actual-price">
              Cena za akcii ({currency})
            </label>
            <Input
              id="actual-price"
              inputMode="decimal"
              placeholder={formatCurrency(recommendation.recommended_price, currency) ?? '0.00'}
              step="0.01"
              type="number"
              value={actualPrice}
              onChange={(e) => setActualPrice(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-foreground" htmlFor="actual-shares">
              Počet akcií
            </label>
            <Input
              id="actual-shares"
              inputMode="numeric"
              placeholder="0"
              type="number"
              value={actualShares}
              onChange={(e) => setActualShares(e.target.value)}
            />
          </div>

          {totalCzk ? (
            <div className="rounded-xl border border-border bg-white/4 px-3 py-2 text-sm">
              <span className="text-muted-foreground">Celkem přibližně </span>
              <span className="font-medium text-foreground">{totalCzk}</span>
              <span className="text-muted-foreground"> ({fxRate.toFixed(2)} Kč/{currency})</span>
            </div>
          ) : null}
        </div>

        {error ? <p className="mt-3 text-sm text-negative">{error}</p> : null}

        <div className="mt-5 flex justify-end gap-3">
          <Button disabled={submitting} onClick={onClose} variant="ghost" size="sm">
            Zrušit
          </Button>
          <Button
            disabled={submitting || !isValid}
            size="sm"
            onClick={() => void onConfirm(parsedPrice, parsedShares)}
          >
            {submitting ? 'Potvrzuji…' : 'Potvrdit'}
          </Button>
        </div>
      </div>
    </div>
  );
}
