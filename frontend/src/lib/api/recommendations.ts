import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface RecommendationSummary {
  id: string;
  status: string;
  ticker: string;
  action: string;
  play_type: 'A' | 'B' | 'C';
  confidence: number;
  recommended_price: number;
  recommended_size_czk: number | null;
  add_reserve_czk: number | null;
  thesis_text: string;
  exit_conditions: string | null;
  price_update_note: string | null;
  actual_price: number | null;
  rejection_reason: string | null;
  options_details: Record<string, unknown> | null;
  created_at: string;
  confirmed_at?: string | null;
  rejected_at?: string | null;
  run_id?: string | null;
  source_run_type?: 'daily' | 'intraday' | null;
}

export async function fetchRecommendations(params?: {
  status?: string;
  limit?: number;
}): Promise<RecommendationSummary[]> {
  const headers = await getAuthHeader();
  const url = new URL(`${API_URL}/api/recommendations/`);

  url.searchParams.set('status', params?.status ?? 'pending,updated');
  url.searchParams.set('limit', String(params?.limit ?? 50));

  const response = await fetch(url.toString(), { headers });
  if (!response.ok) {
    throw new Error('Nepodařilo se načíst doporučení.');
  }
  return response.json();
}

export async function confirmRecommendation(recId: string, actualPrice: number, actualShares?: number) {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/recommendations/${recId}/confirm`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify({
      actual_price: actualPrice,
      ...(actualShares != null ? { actual_shares: actualShares } : {}),
    }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Nepodařilo se potvrdit doporučení.');
  }

  return response.json() as Promise<{ status: string; rec_id: string }>;
}

export async function rejectRecommendation(recId: string, reason?: string) {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/recommendations/${recId}/reject`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
    body: JSON.stringify({ reason: reason || null }),
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Nepodařilo se odmítnout doporučení.');
  }

  return response.json() as Promise<{ status: string; rec_id: string }>;
}

export async function fetchFxRates(): Promise<{ USD_CZK: number; EUR_CZK: number | null }> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/recommendations/fx-rates`, { headers });
  if (!response.ok) throw new Error('Nepodařilo se načíst kurzy.');
  return response.json();
}

export async function fetchRecommendationHistory(limit = 50): Promise<RecommendationSummary[]> {
  const headers = await getAuthHeader();
  const url = new URL(`${API_URL}/api/recommendations/history`);
  url.searchParams.set('limit', String(limit));

  const response = await fetch(url.toString(), { headers });
  if (!response.ok) {
    throw new Error('Nepodařilo se načíst recommendation historii.');
  }

  return response.json();
}
