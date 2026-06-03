import { API_URL, getAuthHeader } from '@/lib/api/client';


export interface RunRejection {
  ticker: string;
  reason: string;
  detail?: string | null;
}

export interface Stage2Diagnostics {
  top_signals_count?: number;
  held_skipped?: number;
  invalid_stock_skipped?: number;
  llm_skip?: number;
  bear_regime_skipped?: number;
  exception_skipped?: number;
  watchlist_adds?: number;
  candidates_found?: number;
  rejection_counts?: Record<string, number>;
  rejections?: RunRejection[];
}

export interface RecommendationDiagnostics {
  candidates_in?: number;
  position_flags_in?: number;
  recommendations_out?: number;
  recently_rejected_skipped?: number;
  portfolio_full_skipped?: number;
  insufficient_cash_skipped?: number;
  rotation_recommendations?: number;
  buy_recommendations?: number;
  flag_recommendations?: number;
  cash_reserve_min?: number;
  available_cash_start?: number;
  available_cash_end?: number;
  skip_reasons?: RunRejection[];
}

export interface RunIssue {
  level: string;
  source: string;
  message: string;
}

export interface RunDiscoveryLog {
  scanned_count?: number;
  signal_tickers?: string[];
  candidates_found?: number;
  warnings_count?: number;
  degraded_mode?: boolean;
  warning_sources?: string[];
  warnings?: RunIssue[];
  failure_reason?: string | null;
  failed_step?: string | null;
  stage2_diagnostics?: Stage2Diagnostics | null;
  recommendation_diagnostics?: RecommendationDiagnostics | null;
}

export interface RunSummary {
  id: string;
  run_type: 'daily' | 'intraday';
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  market_regime: string | null;
  fng_score: number | null;
}

export interface RunDetail extends RunSummary {
  report_content: string | null;
  discovery_log: RunDiscoveryLog | null;
}

export async function fetchRuns(params?: {
  limit?: number;
  runType?: 'daily' | 'intraday';
}): Promise<RunSummary[]> {
  const headers = await getAuthHeader();
  const url = new URL(`${API_URL}/api/runs/`);

  if (params?.limit) {
    url.searchParams.set('limit', String(params.limit));
  }
  if (params?.runType) {
    url.searchParams.set('run_type', params.runType);
  }

  const response = await fetch(url.toString(), { headers });
  if (!response.ok) {
    throw new Error('Nepodařilo se načíst běhy agenta.');
  }
  return response.json();
}

export async function fetchRunDetail(runId: string): Promise<RunDetail> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/runs/${runId}`, { headers });
  if (!response.ok) {
    throw new Error('Nepodařilo se načíst detail běhu.');
  }
  return response.json();
}

export async function triggerRun(runType: 'daily' | 'intraday' = 'daily') {
  const headers = await getAuthHeader();
  const url = new URL(`${API_URL}/api/runs/trigger`);
  url.searchParams.set('run_type', runType);

  const response = await fetch(url.toString(), {
    method: 'POST',
    headers,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || 'Nepodařilo se spustit run.');
  }

  return response.json() as Promise<{ status: string; run_type: string }>;
}
