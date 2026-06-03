import { useQuery } from '@tanstack/react-query';

import { fetchWatchlist } from '@/lib/api/watchlist';
import { GC_TIMES, queryKeys, STALE_TIMES } from '@/lib/query-client';

export function useWatchlist() {
  return useQuery({
    queryKey: queryKeys.watchlist(),
    queryFn: fetchWatchlist,
    staleTime: STALE_TIMES.watchlist,
    gcTime: GC_TIMES.medium,
  });
}
