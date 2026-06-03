import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface TransactionRecord {
  id: string;
  ticker: string;
  action: 'buy' | 'sell';
  shares: number;
  price_per_share: number;
  currency: string;
  size_czk: number;
  realized_pnl_czk: number | null;
  recommendation_id: string | null;
  executed_at: string;
  notes: string | null;
}

export async function fetchTransactions(limit = 100): Promise<TransactionRecord[]> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/transactions/?limit=${limit}`, { headers });
  if (!response.ok) throw new Error('Nepodařilo se načíst transakce.');
  return response.json();
}

export interface ManualTradePayload {
  ticker: string;
  action: 'buy' | 'sell';
  shares: number;
  price_per_share: number;
  currency: string;
  executed_at: string;
  notes?: string | null;
  play_type: 'A' | 'B' | 'C';
}

export async function createManualTrade(payload: ManualTradePayload) {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/transactions/manual`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Nepodařilo se uložit manuální obchod.');
  }

  return response.json();
}
