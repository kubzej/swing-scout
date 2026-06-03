import { StageBadge } from '@/components/watchlist/stage-badge';
import type { WatchlistItem } from '@/lib/api/watchlist';
import { formatDateTime } from '@/lib/format';

interface WatchlistTableProps {
  items: WatchlistItem[];
}

function WatchReason({ text }: { text: string | null }) {
  if (!text) {
    return <span>—</span>;
  }

  const normalized = text.trim();
  const needsExpand = normalized.length > 140;

  if (!needsExpand) {
    return <span className="text-sm leading-6">{normalized}</span>;
  }

  return (
    <details className="group">
      <summary className="cursor-pointer list-none text-sm leading-6 marker:hidden">
        <span className="group-open:hidden">
          <span className="line-clamp-2">{normalized}</span>
        </span>
        <span className="hidden whitespace-pre-wrap text-foreground/85 group-open:block">
          {normalized}
        </span>
        <span className="mt-1 inline-flex text-xs font-medium text-amber-200/90 group-open:hidden">
          Zobrazit celý důvod
        </span>
        <span className="mt-1 hidden text-xs font-medium text-amber-200/90 group-open:inline-flex">
          Skrýt
        </span>
      </summary>
    </details>
  );
}

export function WatchlistTable({ items }: WatchlistTableProps) {
  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 shadow-lg shadow-black/10 ring-soft">
      <div className="border-b border-border px-5 py-4">
        <h2 className="text-lg font-semibold text-foreground">Agent watchlist</h2>
        <p className="text-sm text-muted-foreground">
          Aktivní tickery, které agent drží v hledáčku nebo už povýšil na kandidáty.
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
            <tr>
              <th className="px-5 py-3 font-medium">Ticker</th>
              <th className="px-5 py-3 font-medium">Fáze</th>
              <th className="px-5 py-3 font-medium">Důvod</th>
              <th className="px-5 py-3 font-medium">Sektor</th>
              <th className="px-5 py-3 font-medium">Aktualizováno</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={`${item.ticker}-${item.last_updated_at}`} className="border-t border-border/80">
                <td className="px-5 py-4 text-base font-semibold text-foreground">{item.ticker}</td>
                <td className="px-5 py-4">
                  <StageBadge stage={item.stage} />
                </td>
                <td className="px-5 py-4 text-muted-foreground max-w-xs">
                  <WatchReason text={item.signal_reason} />
                </td>
                <td className="px-5 py-4 text-muted-foreground">{item.theme || '—'}</td>
                <td className="px-5 py-4 text-muted-foreground">
                  {formatDateTime(item.last_updated_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
