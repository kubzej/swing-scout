import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import type { ManualTradePayload } from '@/lib/api/transactions';

interface ManualTradeDialogProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onSubmit: (payload: ManualTradePayload) => Promise<void>;
}

interface ManualTradeFormState {
  ticker: string;
  action: 'buy' | 'sell';
  shares: string;
  price_per_share: string;
  currency: string;
  executed_at: string;
  notes: string;
  play_type: 'A' | 'B' | 'C';
}

const DEFAULT_FORM: ManualTradeFormState = {
  ticker: '',
  action: 'buy',
  shares: '',
  price_per_share: '',
  currency: 'USD',
  executed_at: '',
  notes: '',
  play_type: 'A',
};

export function ManualTradeDialog({
  open,
  loading,
  onClose,
  onSubmit,
}: ManualTradeDialogProps) {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }

    const now = new Date();
    const localValue = new Date(now.getTime() - now.getTimezoneOffset() * 60 * 1000)
      .toISOString()
      .slice(0, 16);

    setForm({
      ...DEFAULT_FORM,
      executed_at: localValue,
    });
    setError(null);
  }, [open]);

  if (!open) {
    return null;
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const shares = Number(form.shares);
    const price = Number(form.price_per_share);

    if (!form.ticker.trim() || !shares || !price || !form.executed_at) {
      setError('Vyplň ticker, shares, price a datum exekuce.');
      return;
    }

    try {
      await onSubmit({
        ticker: form.ticker.trim().toUpperCase(),
        action: form.action,
        shares,
        price_per_share: price,
        currency: form.currency,
        executed_at: new Date(form.executed_at).toISOString(),
        notes: form.notes.trim() || null,
        play_type: form.play_type,
      });

      setForm(DEFAULT_FORM);
      onClose();
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Uložení selhalo.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/55 px-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-[1.75rem] border border-border bg-[#161b1e] p-6 shadow-2xl shadow-black/50">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Manuální trade</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Pro obchody mimo doporučení agenta. Backend se pak pokusí dopočítat
              retroaktivní thesis.
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
            aria-label="Close manual trade dialog"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Ticker">
              <Input
                value={form.ticker}
                onChange={(event) =>
                  setForm((current) => ({ ...current, ticker: event.target.value }))
                }
                placeholder="RTX"
              />
            </Field>
            <Field label="Akce">
              <Select
                value={form.action}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    action: event.target.value as 'buy' | 'sell',
                  }))
                }
              >
                <option value="buy">Koupit</option>
                <option value="sell">Prodat</option>
              </Select>
            </Field>
            <Field label="Počet akcií">
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.shares}
                onChange={(event) =>
                  setForm((current) => ({ ...current, shares: event.target.value }))
                }
                placeholder="25"
              />
            </Field>
            <Field label="Cena za akcii">
              <Input
                type="number"
                min="0"
                step="0.01"
                value={form.price_per_share}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    price_per_share: event.target.value,
                  }))
                }
                placeholder="138.40"
              />
            </Field>
            <Field label="Měna">
              <Select
                value={form.currency}
                onChange={(event) =>
                  setForm((current) => ({ ...current, currency: event.target.value }))
                }
              >
                <option value="USD">USD</option>
                <option value="CZK">CZK</option>
                <option value="EUR">EUR</option>
              </Select>
            </Field>
            <Field label="Typ příležitosti">
              <Select
                value={form.play_type}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    play_type: event.target.value as 'A' | 'B' | 'C',
                  }))
                }
              >
                <option value="A">A</option>
                <option value="B">B</option>
                <option value="C">C</option>
              </Select>
            </Field>
            <Field label="Datum a čas" className="md:col-span-2">
              <Input
                type="datetime-local"
                value={form.executed_at}
                onChange={(event) =>
                  setForm((current) => ({ ...current, executed_at: event.target.value }))
                }
              />
            </Field>
            <Field label="Poznámky" className="md:col-span-2">
              <Textarea
                value={form.notes}
                onChange={(event) =>
                  setForm((current) => ({ ...current, notes: event.target.value }))
                }
                placeholder="Krátký kontext, proč byl trade otevřený nebo zavřený."
              />
            </Field>
          </div>

          {error ? (
            <div className="rounded-2xl border border-rose-400/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100">
              {error}
            </div>
          ) : null}

          <div className="flex flex-wrap justify-end gap-3">
            <Button type="button" variant="ghost" onClick={onClose} disabled={loading}>
              Zrušit
            </Button>
            <Button type="submit" variant="outline" disabled={loading}>
              {loading ? 'Ukládám…' : 'Uložit trade'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={className}>
      <div className="mb-2 text-xs uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
      {children}
    </label>
  );
}
