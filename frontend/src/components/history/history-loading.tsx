import { Skeleton } from '@/components/ui/skeleton';

export function HistoryLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-12 w-72 rounded-full" />
      <div className="grid gap-6 xl:grid-cols-[24rem_minmax(0,1fr)]">
        <Skeleton className="h-96 rounded-[1.5rem]" />
        <Skeleton className="h-96 rounded-[1.5rem]" />
      </div>
    </div>
  );
}
