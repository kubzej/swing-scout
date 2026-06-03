import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchRunDetail,
  fetchRuns,
  triggerRun,
  type RunDetail,
  type RunSummary,
} from '@/lib/api/runs';
import { GC_TIMES, queryKeys, STALE_TIMES } from '@/lib/query-client';

export function useLatestDailyRun(options?: { refetchInterval?: number | false }) {
  return useQuery({
    queryKey: queryKeys.latestRun(),
    queryFn: async () => {
      const runs = await fetchRuns({ limit: 1, runType: 'daily' });
      return runs[0] ?? null;
    },
    staleTime: STALE_TIMES.runs,
    gcTime: GC_TIMES.medium,
    refetchInterval: options?.refetchInterval,
  });
}

export function useRunDetail(
  runId: string | null,
  options?: { refetchInterval?: number | false },
) {
  return useQuery<RunDetail>({
    queryKey: runId ? queryKeys.runDetail(runId) : ['runs', 'none'],
    queryFn: () => fetchRunDetail(runId!),
    enabled: !!runId,
    staleTime: STALE_TIMES.runs,
    gcTime: GC_TIMES.medium,
    refetchInterval: options?.refetchInterval,
  });
}

export function useTriggerDailyRun() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => triggerRun('daily'),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.latestRun() });
      await queryClient.invalidateQueries({ queryKey: queryKeys.runs() });
    },
  });
}

export function isRunStillActive(run: RunSummary | null, watchStartedAt: number | null) {
  if (!run) {
    return !!watchStartedAt;
  }

  if (run.status === 'running') {
    return true;
  }

  if (!watchStartedAt) {
    return false;
  }

  return false;
}
