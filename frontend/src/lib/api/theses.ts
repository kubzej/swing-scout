import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface ThesisEvent {
  id: string;
  thesis_id: string;
  user_id: string;
  position_id: string | null;
  ticker: string;
  kind: string;
  text: string | null;
  payload: Record<string, unknown>;
  status_before: string | null;
  status_after: string | null;
  created_at: string;
}

export interface ThesisResponse {
  id: string;
  position_id: string;
  user_id: string;
  ticker: string;
  play_type: 'A' | 'B' | 'C';
  status: string;
  entry_thesis: string;
  entry_rationale: string | null;
  invalidation_conditions: string | null;
  profit_taking_plan: string | null;
  monitoring_focus: string | null;
  holding_horizon: string | null;
  add_plan: string | null;
  exit_plan: string | null;
  source_recommendation_id: string | null;
  last_thesis_check_at: string | null;
  last_thesis_check_summary: string | null;
  last_thesis_check_action_bias: string | null;
  last_thesis_check_urgency: string | null;
  last_user_override_at: string | null;
  last_user_override_summary: string | null;
  created_at: string;
  updated_at: string | null;
  events: ThesisEvent[];
}

export async function fetchThesis(positionId: string): Promise<ThesisResponse | null> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/api/theses/${positionId}`, { headers });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error('Nepodařilo se načíst thesis detail.');
  }

  return response.json() as Promise<ThesisResponse>;
}
