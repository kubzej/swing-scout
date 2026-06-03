import { BellRing, CircleAlert, Star } from 'lucide-react';

import { ActionBadge } from '@/components/recommendations/action-badge';
import { PlayTypeBadge } from '@/components/recommendations/play-type-badge';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { RecommendationSummary } from '@/lib/api/recommendations';
import { formatCurrency, formatCzk, formatDateTime } from '@/lib/format';

interface RecommendationCardProps {
  recommendation: RecommendationSummary;
  readOnly?: boolean;
  onConfirm?: (recommendation: RecommendationSummary) => void;
  onReject?: (recommendation: RecommendationSummary) => void;
}

const USD_CZK_APPROX = 23;

const CONFIDENCE_LABELS: Record<number, string> = {
  1: 'Spekulativní',
  2: 'Explorační',
  3: 'Střední',
  4: 'Silné',
};

const SOURCE_LABELS: Record<string, string> = {
  daily: 'Denní',
  intraday: 'Intraday',
};

const GENERIC_FIT_NOTES = ['fit ok', 'ok', 'fits', 'fits ok', 'žádný problém', 'bez omezení'];

function isGenericFitNote(text: string | null): boolean {
  if (!text) return true;
  return GENERIC_FIT_NOTES.some((g) => text.toLowerCase().trim().startsWith(g));
}

export function RecommendationCard({
  recommendation,
  readOnly = false,
  onConfirm,
  onReject,
}: RecommendationCardProps) {
  const opts = recommendation.options_details as Record<string, unknown> | null;
  const entryRationale = (opts?.entry_rationale as string) || null;
  const portfolioFitNote = (opts?.portfolio_fit_note as string) || null;
  const optionsNote = (opts?.note as string) || null;
  const sector = (opts?.sector as string) || null;
  const industry = (opts?.industry as string) || null;
  const exchange = (opts?.exchange as string) || null;
  const currency = (opts?.currency as string) || 'USD';
  const priceUsd = (opts?.current_price_usd as number) || null;
  const recommendedShares = (opts?.recommended_shares as number) || null;
  const sourceType =
    recommendation.source_run_type ??
    (recommendation.run_id ? 'daily' : 'intraday');
  const sourceLabel = sourceType
    ? SOURCE_LABELS[sourceType] ?? sourceType
    : null;

  const shares =
    recommendedShares ??
    (priceUsd && recommendation.recommended_size_czk
      ? Math.round(recommendation.recommended_size_czk / (priceUsd * USD_CZK_APPROX))
      : null);

  const showFitNote = portfolioFitNote && !isGenericFitNote(portfolioFitNote);

  return (
    <article className="rounded-[1.5rem] border border-border bg-card/80 px-5 py-4 shadow-lg shadow-black/10 ring-soft">
      <div className="flex flex-col gap-3">

        {/* Header row */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className="text-xl font-semibold text-foreground">{recommendation.ticker}</span>
          <ActionBadge action={recommendation.action} />
          <PlayTypeBadge playType={recommendation.play_type} />
          {sourceLabel ? (
            <Badge className="border-border/70 bg-background/55 text-muted-foreground">
              {sourceLabel}
            </Badge>
          ) : null}
          <Badge className="gap-1">
            {Array.from({ length: recommendation.confidence }).map((_, i) => (
              <Star key={i} className="h-2.5 w-2.5 fill-current" />
            ))}
            <span className="ml-0.5 text-[10px] opacity-70">
              {CONFIDENCE_LABELS[recommendation.confidence]}
            </span>
          </Badge>
          {recommendation.status === 'updated' ? (
            <Badge className="border-warning/30 bg-warning/12 text-yellow-100">Aktualizováno</Badge>
          ) : null}
          {recommendation.status === 'confirmed' ? (
            <span className="text-xs font-medium text-positive">
              Koupeno{recommendation.actual_price ? ` za ${formatCurrency(recommendation.actual_price, currency)}` : ''}
            </span>
          ) : null}
          {recommendation.status === 'rejected' ? (
            <span className="text-xs font-medium text-negative">
              Zamítnuto{recommendation.rejection_reason ? ` — ${recommendation.rejection_reason}` : ''}
            </span>
          ) : null}
          <span className="ml-auto text-xs text-muted-foreground/50">
            {formatDateTime(recommendation.created_at)}
          </span>
        </div>

        {/* Company info + stats */}
        <div className="flex flex-wrap items-center justify-between gap-y-2 border-b border-border/40 pb-3">
          <div className="space-y-0.5">
            {(industry || sector) ? (
              <div className="text-sm text-muted-foreground">
                {[industry, sector].filter(Boolean)[0]}
              </div>
            ) : null}
            {exchange ? (
              <div className="text-xs text-muted-foreground/50">{exchange}</div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            {priceUsd ? (
              <Stat label="Aktuální cena" value={formatCurrency(priceUsd, currency)} />
            ) : null}
            {shares ? (
              <Stat label="Počet akcií" value={`${recommendedShares != null ? '' : '~'}${shares} ks`} />
            ) : null}
            <Stat label="Nákup" value={formatCzk(recommendation.recommended_size_czk)} />
          </div>
        </div>

        {recommendation.price_update_note ? (
          <div className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-yellow-100">
            <BellRing className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{recommendation.price_update_note}</span>
          </div>
        ) : null}

        {/* Content sections — all same font/color */}
        <div className="space-y-3">
          {entryRationale ? (
            <Section label="Důvod vstupu" text={entryRationale} />
          ) : null}
          <Section label="Teze" text={recommendation.thesis_text} />
          {recommendation.exit_conditions ? (
            <Section label="Exit" text={recommendation.exit_conditions} />
          ) : null}
          {showFitNote ? (
            <Section label="Portfolio fit" text={portfolioFitNote!} />
          ) : null}
        </div>

        {optionsNote ? (
          <div className="flex items-start gap-2 rounded-xl border border-sky-400/25 bg-sky-400/10 px-3 py-2 text-xs text-sky-100">
            <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{optionsNote}</span>
          </div>
        ) : null}

        {!readOnly ? (
          <div className="flex justify-end gap-2 pt-0.5">
            <Button onClick={() => onReject?.(recommendation)} variant="ghost" size="sm">
              Odmítnout
            </Button>
            <Button onClick={() => onConfirm?.(recommendation)} variant="outline" size="sm">
              Potvrdit s cenou
            </Button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className="text-sm font-semibold text-foreground">{value}</div>
    </div>
  );
}

function Section({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <p className="text-sm leading-relaxed text-foreground/85">{text}</p>
    </div>
  );
}
