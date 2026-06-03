import { Skeleton } from '@/components/ui/skeleton';

export function DashboardLoading() {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-10 w-96 max-w-full" />
        <Skeleton className="h-5 w-[34rem] max-w-full" />
      </div>
      <Skeleton className="h-44 w-full rounded-[1.5rem]" />
      <Skeleton className="h-[28rem] w-full rounded-[1.5rem]" />
    </div>
  );
}
