import type { TransactionRecord } from '@/lib/api/transactions';
import { formatCurrency, formatCzk, formatDateTime } from '@/lib/format';

interface TransactionHistoryProps {
  transactions: TransactionRecord[];
}

export function TransactionHistory({ transactions }: TransactionHistoryProps) {
  if (transactions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">Žádné transakce zatím.</p>
    );
  }

  return (
    <section className="rounded-[1.5rem] border border-border bg-card/80 shadow-lg shadow-black/10 ring-soft">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
            <tr>
              <th className="px-5 py-3 font-medium">Datum</th>
              <th className="px-5 py-3 font-medium">Ticker</th>
              <th className="px-5 py-3 font-medium">Akce</th>
              <th className="px-5 py-3 font-medium">Akcií</th>
              <th className="px-5 py-3 font-medium">Cena</th>
              <th className="px-5 py-3 font-medium">Celkem</th>
              <th className="px-5 py-3 font-medium">Realized P&L</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => {
              const isBuy = tx.action === 'buy';
              const pnlClass =
                tx.realized_pnl_czk == null
                  ? ''
                  : tx.realized_pnl_czk >= 0
                    ? 'text-positive'
                    : 'text-negative';

              return (
                <tr key={tx.id} className="border-t border-border/60 transition hover:bg-white/4">
                  <td className="px-5 py-3 text-muted-foreground">{formatDateTime(tx.executed_at)}</td>
                  <td className="px-5 py-3 font-semibold text-foreground">{tx.ticker}</td>
                  <td className="px-5 py-3">
                    <span className={`text-xs font-medium uppercase tracking-wide ${isBuy ? 'text-positive' : 'text-negative'}`}>
                      {isBuy ? 'Nákup' : 'Prodej'}
                    </span>
                  </td>
                  <td className="px-5 py-3 font-mono-price text-foreground">{tx.shares}</td>
                  <td className="px-5 py-3 font-mono-price text-foreground">
                    {formatCurrency(tx.price_per_share, tx.currency)}
                  </td>
                  <td className="px-5 py-3 font-mono-price text-foreground">
                    {formatCzk(tx.size_czk)}
                  </td>
                  <td className={`px-5 py-3 font-mono-price ${pnlClass}`}>
                    {tx.realized_pnl_czk != null ? formatCzk(tx.realized_pnl_czk) : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
