import { Skeleton } from '@/components/ui/skeleton';

export function WatchlistLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-64 rounded-[1.5rem]" />
      <Skeleton className="h-96 rounded-[1.5rem]" />
    </div>
  );
}
