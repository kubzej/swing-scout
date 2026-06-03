import { Skeleton } from '@/components/ui/skeleton';

export function RecommendationsLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-10 w-80 max-w-full" />
        <Skeleton className="h-5 w-[32rem] max-w-full" />
      </div>
      <Skeleton className="h-72 w-full rounded-[1.5rem]" />
      <Skeleton className="h-72 w-full rounded-[1.5rem]" />
    </div>
  );
}
