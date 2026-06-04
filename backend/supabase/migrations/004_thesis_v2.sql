-- SwingScout — Thesis v2 migration
-- Apply this against the live Supabase instance. Editing 001 in place does nothing — this is what runs.
-- Safe to run on shared instance: only touches SwingScout tables.

-- ============================================================
-- THESES — drop old columns, add first-class strategy fields
-- ============================================================

ALTER TABLE theses
  DROP COLUMN IF EXISTS notes_log,
  DROP COLUMN IF EXISTS exit_conditions,
  DROP COLUMN IF EXISTS horizon;

ALTER TABLE theses
  ADD COLUMN IF NOT EXISTS entry_rationale TEXT,
  ADD COLUMN IF NOT EXISTS invalidation_conditions TEXT,
  ADD COLUMN IF NOT EXISTS profit_taking_plan TEXT,
  ADD COLUMN IF NOT EXISTS monitoring_focus TEXT,
  ADD COLUMN IF NOT EXISTS holding_horizon TEXT,
  ADD COLUMN IF NOT EXISTS add_plan TEXT,
  ADD COLUMN IF NOT EXISTS exit_plan TEXT,
  ADD COLUMN IF NOT EXISTS source_recommendation_id UUID REFERENCES recommendations(id),
  ADD COLUMN IF NOT EXISTS last_thesis_check_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_thesis_check_summary TEXT,
  ADD COLUMN IF NOT EXISTS last_thesis_check_action_bias TEXT,
  ADD COLUMN IF NOT EXISTS last_thesis_check_urgency TEXT;

-- One thesis per open position — enforced at DB level.
-- _upsert_position always inserts a fresh positions row on re-buy, so position_id is never reused.
ALTER TABLE theses
  ADD CONSTRAINT theses_position_id_unique UNIQUE (position_id);

-- ============================================================
-- THESIS_EVENTS — append-only audit trail
-- ============================================================

CREATE TABLE IF NOT EXISTS thesis_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thesis_id UUID NOT NULL REFERENCES theses(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  position_id UUID REFERENCES positions(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  kind TEXT NOT NULL,
  text TEXT,
  payload JSONB NOT NULL DEFAULT '{}',
  status_before TEXT,
  status_after TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE thesis_events ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_thesis_events_thesis_created
  ON thesis_events(thesis_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_thesis_events_user_ticker_created
  ON thesis_events(user_id, ticker, created_at DESC);
