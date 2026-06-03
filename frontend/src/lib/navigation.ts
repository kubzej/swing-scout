import type { LucideIcon } from 'lucide-react';
import {
  ActivitySquare,
  BriefcaseBusiness,
  History,
  Radar,
  ScrollText,
} from 'lucide-react';

export type NavId = 'dashboard' | 'recommendations' | 'portfolio' | 'watchlist' | 'history';

export interface NavItem {
  id: NavId;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Report', icon: ScrollText },
  { id: 'recommendations', label: 'Doporučení', icon: ActivitySquare },
  { id: 'portfolio', label: 'Portfolio', icon: BriefcaseBusiness },
  { id: 'watchlist', label: 'Watchlist', icon: Radar },
  { id: 'history', label: 'Historie', icon: History },
];
