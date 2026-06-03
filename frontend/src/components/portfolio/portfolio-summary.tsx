import { formatCzk, formatPercent } from '@/lib/format';

interface PortfolioSummaryProps {
  totalValueCzk: number;
  totalCostCzk: number;
  totalPnlCzk: number;
  totalPnlPct: number | null;
  cashCzk: number;
  totalReturnPct: number | null;
  totalRealizedPnlCzk: number;
}

export function PortfolioSummary({
  totalValueCzk,
  totalCostCzk,
  totalPnlCzk,
  totalPnlPct,
  cashCzk,
  totalReturnPct,
  totalRealizedPnlCzk,
}: PortfolioSummaryProps) {
  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <SummaryCard
        label="Hodnota portfolia"
        value={formatCzk(totalValueCzk)}
        tone="neutral"
        detail={`Vstupní cena ${formatCzk(totalCostCzk)}`}
      />
      <SummaryCard
        label="Nerealizovaný P&L"
        value={formatCzk(totalPnlCzk)}
        tone={totalPnlCzk >= 0 ? 'positive' : 'negative'}
        detail={formatPercent(totalPnlPct)}
      />
      <SummaryCard
        label="Realizovaný P&L"
        value={formatCzk(totalRealizedPnlCzk)}
        tone={totalRealizedPnlCzk >= 0 ? 'positive' : 'negative'}
        detail="Z uzavřených pozic"
      />
      <SummaryCard
        label="Cash"
        value={formatCzk(cashCzk)}
        tone="neutral"
        detail={`${formatPercent(cashCzk / totalValueCzk * 100)} portfolia`}
      />
    </section>
  );
}

function SummaryCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: string;
  detail: string;
  tone: 'neutral' | 'positive' | 'negative';
}) {
  const valueClassName =
    tone === 'positive'
      ? 'text-positive'
      : tone === 'negative'
        ? 'text-negative'
        : 'text-foreground';

  return (
    <article className="rounded-[1.5rem] border border-border bg-card/80 p-5 shadow-lg shadow-black/10 ring-soft">
      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className={`mt-3 text-2xl font-semibold ${valueClassName}`}>{value}</div>
      <div className="mt-2 text-sm text-muted-foreground">{detail}</div>
    </article>
  );
}
