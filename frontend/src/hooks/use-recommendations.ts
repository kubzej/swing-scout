import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  confirmRecommendation,
  fetchRecommendationHistory,
  fetchRecommendations,
  rejectRecommendation,
} from '@/lib/api/recommendations';
import { GC_TIMES, queryKeys, STALE_TIMES } from '@/lib/query-client';

export function usePendingRecommendations() {
  return useQuery({
    queryKey: queryKeys.recommendations('pending,updated'),
    queryFn: () => fetchRecommendations({ status: 'pending,updated', limit: 50 }),
    staleTime: STALE_TIMES.recommendations,
    gcTime: GC_TIMES.medium,
  });
}

export function useRecommendationActions() {
  const queryClient = useQueryClient();

  const invalidateRecommendationQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.recommendations('pending,updated') });
    await queryClient.invalidateQueries({ queryKey: queryKeys.recommendations('pending') });
    await queryClient.invalidateQueries({ queryKey: queryKeys.latestRun() });
    await queryClient.invalidateQueries({ queryKey: queryKeys.portfolio() });
    await queryClient.invalidateQueries({ queryKey: queryKeys.recommendationHistory() });
    await queryClient.invalidateQueries({ queryKey: queryKeys.watchlist() });
  };

  const confirm = useMutation({
    mutationFn: ({ recId, actualPrice, actualShares }: { recId: string; actualPrice: number; actualShares?: number }) =>
      confirmRecommendation(recId, actualPrice, actualShares),
    onSuccess: async () => {
      await invalidateRecommendationQueries();
    },
  });

  const reject = useMutation({
    mutationFn: ({ recId, reason }: { recId: string; reason?: string }) =>
      rejectRecommendation(recId, reason),
    onSuccess: async () => {
      await invalidateRecommendationQueries();
    },
  });

  return { confirm, reject };
}

export function useRecommendationHistory() {
  return useQuery({
    queryKey: queryKeys.recommendationHistory(),
    queryFn: () => fetchRecommendationHistory(100),
    staleTime: STALE_TIMES.recommendationHistory,
    gcTime: GC_TIMES.medium,
  });
}
