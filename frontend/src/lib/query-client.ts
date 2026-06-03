import { QueryClient } from '@tanstack/react-query';

export const STALE_TIMES = {
  runs: 60 * 1000,
  recommendations: 60 * 1000,
  recommendationHistory: 5 * 60 * 1000,
  portfolio: 5 * 60 * 1000,
  thesis: 5 * 60 * 1000,
  watchlist: 5 * 60 * 1000,
  history: 5 * 60 * 1000,
  auth: 5 * 60 * 1000,
} as const;

export const GC_TIMES = {
  short: 5 * 60 * 1000,
  medium: 30 * 60 * 1000,
} as const;

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: STALE_TIMES.portfolio,
      gcTime: GC_TIMES.medium,
      refetchOnWindowFocus: false,
      retry: 1,
      placeholderData: (previousData: unknown) => previousData,
    },
  },
});

export const queryKeys = {
  authSession: () => ['auth', 'session'] as const,
  latestRun: () => ['runs', 'latest'] as const,
  runs: () => ['runs'] as const,
  runDetail: (runId: string) => ['runs', runId] as const,
  portfolio: () => ['portfolio'] as const,
  thesis: (positionId: string) => ['thesis', positionId] as const,
  recommendations: (status: string) => ['recommendations', status] as const,
  recommendationHistory: () => ['recommendations', 'history'] as const,
  watchlist: () => ['watchlist'] as const,
  history: () => ['history'] as const,
} as const;
