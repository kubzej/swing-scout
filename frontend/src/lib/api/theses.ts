import { API_URL, getAuthHeader } from '@/lib/api/client';

export interface ThesisNote {
  text: string;
  timestamp: string;
  status_before?: string | null;
  status_after?: string | null;
  kind?: string | null;
  strategy?: {
    invalidation_conditions?: string | null;
    profit_taking_plan?: string | null;
    holding_horizon?: string | null;
    monitoring_focus?: string | null;
    source_run_type?: string | null;
  } | null;
}

export interface ThesisStrategySnapshot {
  invalidation_conditions?: string | null;
  profit_taking_plan?: string | null;
  holding_horizon?: string | null;
  monitoring_focus?: string | null;
  source_run_type?: string | null;
}

export interface ThesisResponse {
  id: string;
  position_id: string;
  ticker: string;
  entry_thesis: string;
  exit_conditions: string;
  horizon: string;
  play_type: 'A' | 'B' | 'C';
  status: string;
  notes_log: ThesisNote[];
  created_at: string;
  updated_at: string | null;
}

function parseNotesLog(value: unknown): ThesisNote[] {
  if (Array.isArray(value)) {
    return value as ThesisNote[];
  }

  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? (parsed as ThesisNote[]) : [];
    } catch {
      return [];
    }
  }

  return [];
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

  const thesis = (await response.json()) as Omit<ThesisResponse, 'notes_log'> & {
    notes_log: unknown;
  };

  return {
    ...thesis,
    notes_log: parseNotesLog(thesis.notes_log),
  };
}

export function getLatestStrategySnapshot(notes: ThesisNote[]): ThesisStrategySnapshot | null {
  for (let index = notes.length - 1; index >= 0; index -= 1) {
    const note = notes[index];
    if (note.kind === 'strategy_snapshot' && note.strategy) {
      return note.strategy;
    }
  }

  return null;
}

export function getDisplayNotes(notes: ThesisNote[]): ThesisNote[] {
  return notes.filter((note) => note.kind !== 'strategy_snapshot');
}
