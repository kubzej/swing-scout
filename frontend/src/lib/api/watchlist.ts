import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface WatchlistItem {
  id?: string;
  ticker: string;
  stage: 'watching' | 'candidate' | string;
  signal_reason: string | null;
  theme: string | null;
  first_seen_at?: string | null;
  last_updated_at: string | null;
}

export async function fetchWatchlist(): Promise<WatchlistItem[]> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/watchlist/`, { headers });

  if (!response.ok) {
    throw new Error('Nepodařilo se načíst agent watchlist.');
  }

  return response.json();
}
