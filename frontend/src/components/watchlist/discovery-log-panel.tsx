import { Badge } from '@/components/ui/badge';
import type { RunDetail, RunSummary } from '@/lib/api/runs';
import { formatDateTime } from '@/lib/format';

interface DiscoveryLogPanelProps {
  latestRun: RunSummary | null | undefined;
  runDetail: RunDetail | null | undefined;
  loading: boolean;
}

export function DiscoveryLogPanel({ latestRun, runDetail, loading }: DiscoveryLogPanelProps) {
  if (loading || !latestRun) return null;

  const log = runDetail?.discovery_log;
  const scanned = typeof log?.scanned_count === 'number' ? log.scanned_count : null;
  const candidates = typeof log?.candidates_found === 'number' ? log.candidates_found : null;

  return (
    <div className="flex items-center gap-3 text-xs text-muted-foreground">
      <Badge className="text-[10px]">{latestRun.status}</Badge>
      <span>
        Poslední run {formatDateTime(latestRun.started_at)}
        {scanned != null ? ` · ${scanned} tickerů` : ''}
        {candidates != null ? ` · ${candidates} kandidátů` : ''}
      </span>
    </div>
  );
}
