-- SwingScout — backfill thesis user-override columns
-- 004 added these in the same ALTER, but was already applied before the override
-- columns were appended to that file, so they never landed in the live DB.
-- Apply this against the live Supabase instance. Idempotent.

ALTER TABLE theses
  ADD COLUMN IF NOT EXISTS last_user_override_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_user_override_summary TEXT;
