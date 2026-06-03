import { useMemo } from 'react';
import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';

import { fetchPortfolioSnapshot, type PortfolioPosition } from '@/lib/api/portfolio';
import { fetchThesis, type ThesisResponse } from '@/lib/api/theses';
import {
  createManualTrade,
  type ManualTradePayload,
} from '@/lib/api/transactions';
import { GC_TIMES, queryKeys, STALE_TIMES } from '@/lib/query-client';

export interface ThesisStatusSummary {
  positionId: string;
  status: string;
  thesis: ThesisResponse | null;
  isLoading: boolean;
  isError: boolean;
}

export function usePortfolioSnapshot() {
  return useQuery({
    queryKey: queryKeys.portfolio(),
    queryFn: fetchPortfolioSnapshot,
    staleTime: STALE_TIMES.portfolio,
    gcTime: GC_TIMES.medium,
  });
}

export function usePositionThesis(positionId: string | null) {
  return useQuery({
    queryKey: queryKeys.thesis(positionId ?? 'unknown'),
    queryFn: () => fetchThesis(positionId ?? ''),
    enabled: Boolean(positionId),
    staleTime: STALE_TIMES.thesis,
    gcTime: GC_TIMES.medium,
    placeholderData: undefined,
  });
}

export function usePortfolioThesisStatuses(positions: PortfolioPosition[]) {
  const thesisQueries = useQueries({
    queries: positions.map((position) => ({
      queryKey: queryKeys.thesis(position.id),
      queryFn: () => fetchThesis(position.id),
      staleTime: STALE_TIMES.thesis,
      gcTime: GC_TIMES.medium,
    })),
  }) as UseQueryResult<ThesisResponse | null>[];

  return useMemo(() => {
    const byPositionId: Record<string, ThesisStatusSummary> = {};

    positions.forEach((position, index) => {
      const query = thesisQueries[index];
      const thesis = query?.data ?? null;

      byPositionId[position.id] = {
        positionId: position.id,
        status: thesis?.status ?? 'missing',
        thesis,
        isLoading: query?.isLoading ?? false,
        isError: query?.isError ?? false,
      };
    });

    return {
      byPositionId,
      isLoading: thesisQueries.some((query) => query.isLoading),
      hasError: thesisQueries.some((query) => query.isError),
    };
  }, [positions, thesisQueries]);
}

export function useManualTrade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ManualTradePayload) => createManualTrade(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.portfolio() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.latestRun() });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.recommendations('pending,updated'),
      });
      await queryClient.invalidateQueries({
        queryKey: queryKeys.recommendationHistory(),
      });
    },
  });
}
