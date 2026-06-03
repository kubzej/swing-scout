import { RecommendationCard } from '@/components/recommendations/recommendation-card';
import type { RecommendationSummary } from '@/lib/api/recommendations';

interface RecommendationTimelineProps {
  recommendations: RecommendationSummary[];
}

function groupByDay(recs: RecommendationSummary[]): [string, RecommendationSummary[]][] {
  const map = new Map<string, RecommendationSummary[]>();
  for (const rec of recs) {
    const day = new Date(rec.created_at).toLocaleDateString('cs-CZ', {
      day: 'numeric', month: 'long', year: 'numeric',
    });
    if (!map.has(day)) map.set(day, []);
    map.get(day)!.push(rec);
  }
  return Array.from(map.entries());
}

export function RecommendationTimeline({ recommendations }: RecommendationTimelineProps) {
  if (!recommendations.length) {
    return (
      <div className="rounded-2xl border border-dashed border-border px-4 py-6 text-sm text-muted-foreground">
        Recommendation timeline je zatím prázdná.
      </div>
    );
  }

  const grouped = groupByDay(recommendations);

  return (
    <div className="space-y-8">
      {grouped.map(([day, recs]) => (
        <div key={day}>
          <div className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            {day}
          </div>
          <div className="space-y-3">
            {recs.map((rec) => (
              <RecommendationCard key={rec.id} recommendation={rec} readOnly />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
