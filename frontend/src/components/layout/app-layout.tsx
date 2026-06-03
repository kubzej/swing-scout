import type { ReactNode } from 'react';

import { MobileHeader } from '@/components/layout/mobile-header';
import { MobileNav } from '@/components/layout/mobile-nav';
import { Sidebar } from '@/components/layout/sidebar';
import type { NavItem, NavId } from '@/lib/navigation';

interface AppLayoutProps {
  activeTab: NavId;
  items: NavItem[];
  onNavigate: (id: NavId) => void;
  onSignOut: () => Promise<void>;
  userEmail: string | null;
  children: ReactNode;
}

export function AppLayout({
  activeTab,
  items,
  onNavigate,
  onSignOut,
  userEmail,
  children,
}: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar
        activeTab={activeTab}
        items={items}
        onNavigate={onNavigate}
        onSignOut={onSignOut}
        userEmail={userEmail}
      />
      <MobileHeader onSignOut={onSignOut} />

      <main className="min-h-screen px-4 pb-28 pt-6 md:ml-64 md:px-6 md:pb-8 lg:px-8 xl:px-10">
        {children}
      </main>

      <MobileNav activeTab={activeTab} items={items} onNavigate={onNavigate} />
    </div>
  );
}
