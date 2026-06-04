import type { ThesisResponse } from '@/lib/api/theses';

interface ThesisStrategySectionProps {
  thesis: ThesisResponse;
  compact?: boolean;
}

export function ThesisStrategySection({ thesis, compact = false }: ThesisStrategySectionProps) {
  const sections = [
    { label: 'Proč jsme vstoupili', value: thesis.entry_rationale },
    { label: 'Kdy je teze špatně', value: thesis.invalidation_conditions },
    { label: 'Kdy brát zisky', value: thesis.profit_taking_plan },
    { label: 'Co dál hlídat', value: thesis.monitoring_focus },
    { label: 'Horizont', value: thesis.holding_horizon },
    { label: 'Add plán', value: thesis.add_plan },
    { label: 'Exit plán', value: thesis.exit_plan },
  ].filter((section) => section.value);

  if (sections.length === 0) {
    return null;
  }

  if (compact) {
    return (
      <div className="space-y-1.5">
        <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
          Strategie
        </div>
        {sections.map((section) => (
          <div key={section.label}>
            <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground/70">
              {section.label} -{' '}
            </span>
            <span className="text-xs leading-relaxed text-foreground/90">{section.value}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-2xl border border-border/70 bg-white/[0.03] p-4">
      <div className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        Strategie
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
