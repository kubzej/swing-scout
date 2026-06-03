import { Skeleton } from '@/components/ui/skeleton';

export function PortfolioLoading() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-32 rounded-[1.5rem]" />
        ))}
      </div>
      <Skeleton className="h-52 rounded-[1.5rem]" />
      <Skeleton className="h-96 rounded-[1.5rem]" />
    </div>
  );
}
