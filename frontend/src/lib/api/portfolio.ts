import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface PortfolioPosition {
  id: string;
  ticker: string;
  shares: number;
  avg_cost: number;
  currency: string;
  play_type: 'A' | 'B' | 'C';
  status: 'open' | 'closed';
  current_price: number | null;
  change_pct: number | null;
  current_value_czk: number;
  cost_czk: number;
  unrealized_pnl_czk: number;
  unrealized_pnl_pct: number | null;
  realized_pnl_czk: number | null;
  sector: string | null;
}

export interface PortfolioSnapshotResponse {
  total_value_czk: number;
  total_cost_czk: number;
  total_pnl_czk: number;
  total_pnl_pct: number | null;
  cash_czk: number;
  starting_cash_czk: number;
  total_return_pct: number | null;
  total_realized_pnl_czk: number;
  sector_exposure: Record<string, number>;
  positions: PortfolioPosition[];
}

export async function fetchPortfolioSnapshot(): Promise<PortfolioSnapshotResponse> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/portfolio/snapshot`, { headers });

  if (!response.ok) {
    throw new Error('Nepodařilo se načíst portfolio snapshot.');
  }

  return response.json();
}
