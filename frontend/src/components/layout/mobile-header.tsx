import { LogOut } from 'lucide-react';

import { Button } from '@/components/ui/button';

interface MobileHeaderProps {
  onSignOut: () => Promise<void>;
}

export function MobileHeader({ onSignOut }: MobileHeaderProps) {
  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 px-4 py-4 backdrop-blur md:hidden">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] text-primary/80">SwingScout</div>
          <div className="text-sm font-medium text-foreground">Denní trading cockpit</div>
        </div>
        <Button
          className="h-9 w-9"
          onClick={() => {
            void onSignOut();
          }}
          size="icon"
          variant="ghost"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
