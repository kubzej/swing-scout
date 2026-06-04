import type { ThesisStrategySnapshot } from '@/lib/api/theses';

interface ThesisStrategySectionProps {
  strategy: ThesisStrategySnapshot;
  compact?: boolean;
}

export function ThesisStrategySection({ strategy, compact = false }: ThesisStrategySectionProps) {
  const sourceLabel =
    strategy.source_run_type === 'intraday'
      ? 'Intraday'
      : strategy.source_run_type === 'daily'
        ? 'Denní'
        : null;

  const sections = [
    { label: 'Kdy brát zisky', value: strategy.profit_taking_plan },
    { label: 'Kdy je teze špatně', value: strategy.invalidation_conditions },
    { label: 'Horizont', value: strategy.holding_horizon },
    { label: 'Co dál hlídat', value: strategy.monitoring_focus },
  ].filter((section) => section.value);

  if (sections.length === 0 && !sourceLabel) {
    return null;
  }

  if (compact) {
    return (
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
          Strategie při otevření
        </div>
        {sections.map((section) => (
          <div key={section.label}>
            <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
              {section.label} -{' '}
            </span>
            <span className="text-xs leading-relaxed text-foreground/90">{section.value}</span>
          </div>
        ))}
        {sourceLabel ? (
          <div>
            <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
              Zdroj -{' '}
            </span>
            <span className="text-xs leading-relaxed text-foreground/90">{sourceLabel}</span>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-2xl border border-border/70 bg-white/[0.03] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Strategie při otevření
        </div>
        {sourceLabel ? (
          <span className="rounded-full border border-border/80 bg-white/[0.03] px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {sourceLabel}
          </span>
        ) : null}
      </div>

      <div className="space-y-3">
        {sections.map((section) => (
          <div key={section.label}>
            <div className="mb-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {section.label}
            </div>
            <p className="text-sm leading-relaxed text-foreground/90">{section.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
