import { supabase } from '@/lib/supabase';

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function getAuthHeader(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (session?.access_token) {
    return { Authorization: `Bearer ${session.access_token}` };
  }

  return {};
}
