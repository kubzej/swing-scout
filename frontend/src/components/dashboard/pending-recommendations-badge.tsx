import { Badge } from '@/components/ui/badge';

interface PendingRecommendationsBadgeProps {
  count: number;
}

export function PendingRecommendationsBadge({
  count,
}: PendingRecommendationsBadgeProps) {
  if (count <= 0) {
    return null;
  }

  return (
    <Badge className="border-primary/30 bg-primary/12 text-primary">
      {count} doporučení čeká
    </Badge>
  );
}
