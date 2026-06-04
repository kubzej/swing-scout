import { X } from 'lucide-react';

import { PlayTypeBadge } from '@/components/recommendations/play-type-badge';
import { ThesisStrategySection } from '@/components/portfolio/thesis-strategy-section';
import { ThesisStatusBadge } from '@/components/portfolio/thesis-status-badge';
import { Button } from '@/components/ui/button';
import type { PortfolioPosition } from '@/lib/api/portfolio';
import type { ThesisResponse } from '@/lib/api/theses';
import { formatCurrency, formatCzk, formatDateTime, formatPercent } from '@/lib/format';

interface ThesisSheetProps {
  open: boolean;
  position: PortfolioPosition | null;
  thesis: ThesisResponse | null | undefined;
  loading: boolean;
  onClose: () => void;
}

export function ThesisSheet({ open, position, thesis, loading, onClose }: ThesisSheetProps) {
  if (!open || !position) return null;

  const pnlPositive = (position.unrealized_pnl_czk ?? 0) >= 0;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/55 backdrop-blur-sm">
      <div className="h-full w-full max-w-lg overflow-y-auto border-l border-border bg-[#161b1e] shadow-2xl shadow-black/50">

        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-border/40">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <PlayTypeBadge playType={position.play_type} />
              <ThesisStatusBadge status={thesis?.status ?? (loading ? 'loading' : 'missing')} />
            </div>
            <h2 className="text-2xl font-semibold text-foreground">{position.ticker}</h2>
            <p className="text-xs text-muted-foreground">
              {position.sector || '—'} · {position.currency}
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-2 gap-px bg-border/40 border-b border-border/40">
          <Stat label="Aktuální cena" value={formatCurrency(position.current_price, position.currency)} />
          <Stat label="Průměrná cena" value={formatCurrency(position.avg_cost, position.currency)} />
          <Stat label="Hodnota" value={formatCzk(position.current_value_czk)} />
          <Stat
            label="Nerealizovaný P&L"
            value={`${formatCzk(position.unrealized_pnl_czk)} ${formatPercent(position.unrealized_pnl_pct)}`}
            tone={pnlPositive ? 'positive' : 'negative'}
          />
        </div>

        {/* Content */}
        <div className="px-6 py-5 space-y-5">
          {loading ? (
            <p className="text-sm text-muted-foreground">Načítám…</p>
          ) : thesis ? (
            <>
              <Section label="Teze" text={thesis.entry_thesis} />

              <ThesisStrategySection thesis={thesis} />

              {thesis.last_thesis_check_summary ? (
                <div className="rounded-xl border border-border/50 bg-white/[0.02] px-4 py-3 space-y-1">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    Poslední denní check
                  </div>
                  <p className="text-sm leading-relaxed text-foreground/90">
                    {thesis.last_thesis_check_summary}
                  </p>
                  {thesis.last_thesis_check_at ? (
                    <p className="text-xs text-muted-foreground/60">
                      {formatDateTime(thesis.last_thesis_check_at)}
                      {thesis.last_thesis_check_action_bias
                        ? ` · ${thesis.last_thesis_check_action_bias}`
                        : null}
                    </p>
                  ) : null}
                </div>
              ) : null}

              {thesis.events.length > 0 ? (
                <div>
                  <div className="mb-2 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    Historie
                  </div>
                  <div className="space-y-2">
                    {thesis.events.map((event) => (
                      <div key={event.id} className="border-l-2 border-border pl-3">
                        <div className="flex items-center gap-2">
                          <EventKindBadge kind={event.kind} />
                          {event.status_before !== event.status_after && event.status_after ? (
                            <span className="text-[10px] text-muted-foreground/60">
                              → {event.status_after}
                            </span>
                          ) : null}
                        </div>
                        {event.text ? (
                          <p className="mt-0.5 text-sm text-foreground/80">{event.text}</p>
                        ) : null}
                        <p className="mt-0.5 text-xs text-muted-foreground/60">
                          {formatDateTime(event.created_at)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Thesis zatím chybí.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  return (
    <div className="bg-[#161b1e] px-5 py-3">
      <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</div>
      <div className={`mt-0.5 text-sm font-medium ${
        tone === 'positive' ? 'text-positive' : tone === 'negative' ? 'text-negative' : 'text-foreground'
      }`}>{value}</div>
    </div>
  );
}

function Section({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="mb-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</div>
      <p className="text-sm leading-relaxed text-foreground/90">{text}</p>
    </div>
  );
}

const KIND_LABELS: Record<string, string> = {
  opened: 'Otevřeno',
  scaled: 'Přikoupeno',
  manual_scaled: 'Ruční přikoupení',
  partial_exit: 'Částečný výstup',
  manual_partial_exit: 'Ruční část. výstup',
  closed: 'Uzavřeno',
  daily_check: 'Denní check',
  manual_update: 'Ruční aktualizace',
  status_change: 'Změna statusu',
};

function EventKindBadge({ kind }: { kind: string }) {
  return (
    <span className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground font-medium">
      {KIND_LABELS[kind] ?? kind}
    </span>
  );
}
