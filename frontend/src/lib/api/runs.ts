import { API_URL, getAuthHeader } from '@/lib/api/client';

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
  discovery_log: Record<string, unknown> | null;
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
