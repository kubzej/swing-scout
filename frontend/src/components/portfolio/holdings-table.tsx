import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

import { ThesisStrategySection } from '@/components/portfolio/thesis-strategy-section';
import { PlayTypeBadge } from '@/components/recommendations/play-type-badge';
import { ThesisStatusBadge } from '@/components/portfolio/thesis-status-badge';
import type { PortfolioPosition } from '@/lib/api/portfolio';
import type { ThesisStatusSummary } from '@/hooks/use-portfolio';
import { getDisplayNotes, getLatestStrategySnapshot } from '@/lib/api/theses';
import { formatCurrency, formatCzk, formatPercent } from '@/lib/format';

interface HoldingsTableProps {
  positions: PortfolioPosition[];
  thesisStatuses: Record<string, ThesisStatusSummary>;
}

export function HoldingsTable({ positions, thesisStatuses }: HoldingsTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 shadow-lg shadow-black/10 ring-soft">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-lg font-semibold text-foreground">Pozice</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
            <tr>
              <th className="px-5 py-3 font-medium">Ticker</th>
              <th className="px-5 py-3 font-medium">Ks</th>
              <th className="px-5 py-3 font-medium">Cena</th>
              <th className="px-5 py-3 font-medium">Hodnota</th>
              <th className="px-5 py-3 font-medium">P&L</th>
              <th className="px-5 py-3 font-medium">Teze</th>
              <th className="px-5 py-3 font-medium">Sektor</th>
              <th className="px-5 py-3" />
            </tr>
          </thead>
          <tbody>
            {positions.map((position) => {
              const ts = thesisStatuses[position.id];
              const thesis = ts?.thesis ?? null;
              const isExpanded = expandedId === position.id;
              const pnlClass = (position.unrealized_pnl_czk ?? 0) >= 0 ? 'text-positive' : 'text-negative';
              const displayNotes = thesis ? getDisplayNotes(thesis.notes_log) : [];
              const strategy = thesis ? getLatestStrategySnapshot(thesis.notes_log) : null;

              return (
                <>
                  <tr
                    key={position.id}
                    className="border-t border-border/80 transition hover:bg-white/4 cursor-pointer"
                    onClick={() => setExpandedId(isExpanded ? null : position.id)}
                  >
                    <td className="px-5 py-4">
                      <div className="flex flex-col gap-1">
                        <span className="text-base font-semibold text-foreground">{position.ticker}</span>
                        <PlayTypeBadge playType={position.play_type} />
                      </div>
                    </td>
                    <td className="px-5 py-4 font-mono-price text-foreground">
                      {position.shares.toFixed(0)}
                    </td>
                    <td className="px-5 py-4">
                      <div className="font-mono-price text-foreground">
                        {formatCurrency(position.current_price, position.currency)}
                      </div>
                      <div className={`mt-0.5 text-xs ${(position.change_pct ?? 0) >= 0 ? 'text-positive' : 'text-negative'}`}>
                        {formatPercent(position.change_pct)}
                      </div>
                    </td>
                    <td className="px-5 py-4 font-mono-price text-foreground">
                      {formatCzk(position.current_value_czk)}
                    </td>
                    <td className="px-5 py-4">
                      <div className={`font-mono-price ${pnlClass}`}>
                        {formatCzk(position.unrealized_pnl_czk)}
                      </div>
                      <div className={`mt-0.5 text-xs ${pnlClass}`}>
                        {formatPercent(position.unrealized_pnl_pct)}
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <ThesisStatusBadge
                        status={
                          ts?.isError ? 'error' : ts?.isLoading ? 'loading' : ts?.status ?? 'missing'
                        }
                      />
                    </td>
                    <td className="px-5 py-4 text-muted-foreground">{position.sector || '—'}</td>
                    <td className="px-5 py-4 text-right text-muted-foreground">
                      {isExpanded
                        ? <ChevronDown className="h-4 w-4" />
                        : <ChevronRight className="h-4 w-4" />
                      }
                    </td>
                  </tr>

                  {isExpanded ? (
                    <tr key={`${position.id}-detail`} className="border-t border-border/40 bg-white/[0.02]">
                      <td colSpan={8} className="px-5 py-4">
                        {ts?.isLoading ? (
                          <p className="text-xs text-muted-foreground">Načítám…</p>
                        ) : thesis ? (
                          <div className="space-y-3 max-w-2xl">
                            <InlineSection label="Teze" text={thesis.entry_thesis} />
                            {strategy ? <ThesisStrategySection strategy={strategy} compact /> : null}
                            {!strategy && thesis.exit_conditions ? (
                              <InlineSection label="Exit" text={thesis.exit_conditions} />
                            ) : null}
                            {displayNotes.length > 0 ? (
                              <div>
                                <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
                                  Poznámky —{' '}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {displayNotes[displayNotes.length - 1].text}
                                </span>
                              </div>
                            ) : null}
                          </div>
                        ) : (
                          <p className="text-xs text-muted-foreground">Thesis zatím chybí.</p>
                        )}
                      </td>
                    </tr>
                  ) : null}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function InlineSection({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">{label} — </span>
      <span className="text-xs leading-relaxed text-foreground/90">{text}</span>
    </div>
  );
}
