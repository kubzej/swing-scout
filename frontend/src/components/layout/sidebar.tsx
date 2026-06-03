import { LogOut } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { NavItem, NavId } from '@/lib/navigation';
import { cn } from '@/lib/utils';

interface SidebarProps {
  activeTab: NavId;
  items: NavItem[];
  onNavigate: (id: NavId) => void;
  onSignOut: () => Promise<void>;
  userEmail: string | null;
}

export function Sidebar({
  activeTab,
  items,
  onNavigate,
  onSignOut,
  userEmail,
}: SidebarProps) {
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-border bg-black/18 backdrop-blur md:flex md:flex-col">
      <div className="border-b border-border px-6 py-6">
        <div className="text-xs uppercase tracking-[0.28em] text-primary/80">SwingScout</div>
        <div className="mt-2 text-lg font-semibold text-foreground">Denní trading cockpit</div>
        {userEmail ? (
          <div className="mt-3 text-xs text-muted-foreground">{userEmail}</div>
        ) : null}
      </div>
      <nav className="flex-1 space-y-1 px-4 py-6">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              className={cn(
                'flex w-full items-center gap-3 rounded-xl px-4 py-3 text-left text-sm transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-white/6 hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>
      <div className="border-t border-border p-4">
        <Button
          className="w-full justify-start"
          onClick={() => {
            void onSignOut();
          }}
          variant="ghost"
        >
          <LogOut className="mr-2 h-4 w-4" />
          Odhlásit se
        </Button>
      </div>
    </aside>
  );
}
