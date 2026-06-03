const dateTimeFormatter = new Intl.DateTimeFormat('cs-CZ', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const czkFormatter = new Intl.NumberFormat('cs-CZ', {
  style: 'currency',
  currency: 'CZK',
  maximumFractionDigits: 0,
});

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  HKD: 'HK$',
  NOK: 'kr',
  DKK: 'kr',
  CZK: 'Kč',
};

export function formatCzk(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  return czkFormatter.format(value);
}

export function formatCurrency(value: number | null | undefined, currency = 'USD') {
  if (value == null || Number.isNaN(value)) return '—';
  const sym = CURRENCY_SYMBOLS[currency] ?? currency;
  // NOK/DKK: symbol after number
  if (currency === 'NOK' || currency === 'DKK') return `${value.toFixed(2)} ${sym}`;
  return `${sym}${value.toFixed(2)}`;
}

export function formatUsd(value: number | null | undefined) {
  return formatCurrency(value, 'USD');
}

export function formatPercent(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return dateTimeFormatter.format(parsed);
}

export function getCurrencyLabel(currency = 'USD') {
  return currency;
}
