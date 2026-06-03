import { useEffect, useMemo, useState, type ComponentType } from 'react';

import { AppLayout } from '@/components/layout/app-layout';
import { LoginPage } from '@/pages/login-page';
import { DashboardPage } from '@/pages/dashboard-page';
import { RecommendationsPage } from '@/pages/recommendations-page';
import { PortfolioPage } from '@/pages/portfolio-page';
import { WatchlistPage } from '@/pages/watchlist-page';
import { HistoryPage } from '@/pages/history-page';
import { useAuth } from '@/contexts/auth-context';
import { usePathname } from '@/hooks/use-pathname';
import { NAV_ITEMS, type NavId } from '@/lib/navigation';
import { HOME_PATH, LOGIN_PATH } from '@/lib/routes';

const PAGE_MAP: Record<NavId, ComponentType> = {
  dashboard: DashboardPage,
  recommendations: RecommendationsPage,
  portfolio: PortfolioPage,
  watchlist: WatchlistPage,
  history: HistoryPage,
};

export default function App() {
  const { loading, user, signOut } = useAuth();
  const [activeTab, setActiveTab] = useState<NavId>('dashboard');
  const { pathname, navigate } = usePathname();

  const ActivePage = useMemo(() => PAGE_MAP[activeTab], [activeTab]);

  useEffect(() => {
    if (loading) {
      return;
    }

    if (!user && pathname !== LOGIN_PATH) {
      navigate(LOGIN_PATH, { replace: true });
      return;
    }

    if (user && pathname === LOGIN_PATH) {
      navigate(HOME_PATH, { replace: true });
    }
  }, [loading, navigate, pathname, user]);

  if (loading) {
    return <div className="grid min-h-screen place-items-center text-sm text-muted-foreground">Kontroluji přihlášení…</div>;
  }

  if (!user && pathname === LOGIN_PATH) {
    return <LoginPage />;
  }

  if (!user) {
    return null;
  }

  return (
    <AppLayout
      activeTab={activeTab}
      items={NAV_ITEMS}
      onNavigate={setActiveTab}
      onSignOut={signOut}
      userEmail={user.email ?? null}
    >
      <ActivePage />
    </AppLayout>
  );
}
