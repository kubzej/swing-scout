import type { NavItem, NavId } from '@/lib/navigation';
import { cn } from '@/lib/utils';

interface MobileNavProps {
  activeTab: NavId;
  items: NavItem[];
  onNavigate: (id: NavId) => void;
}

export function MobileNav({ activeTab, items, onNavigate }: MobileNavProps) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 px-2 pb-3 pt-2 backdrop-blur md:hidden">
      <div className="grid grid-cols-5 gap-1">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              className={cn(
                'flex flex-col items-center gap-1 rounded-xl px-2 py-2 text-[11px] transition-colors',
                isActive ? 'bg-primary text-primary-foreground' : 'text-muted-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
