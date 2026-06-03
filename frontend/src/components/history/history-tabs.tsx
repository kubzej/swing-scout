import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export type HistoryTab = 'reports' | 'recommendations' | 'transactions';

interface HistoryTabsProps {
  activeTab: HistoryTab;
  onChange: (tab: HistoryTab) => void;
}

export function HistoryTabs({ activeTab, onChange }: HistoryTabsProps) {
  return (
    <div className="inline-flex rounded-full border border-border bg-card/70 p-1 ring-soft">
      <TabButton active={activeTab === 'reports'} onClick={() => onChange('reports')}>
        Reporty
      </TabButton>
      <TabButton active={activeTab === 'recommendations'} onClick={() => onChange('recommendations')}>
        Doporučení
      </TabButton>
      <TabButton active={activeTab === 'transactions'} onClick={() => onChange('transactions')}>
        Transakce
      </TabButton>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-full px-4 py-2 text-sm transition',
        active
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-white/8 hover:text-foreground',
      )}
    >
      {children}
    </button>
  );
}
