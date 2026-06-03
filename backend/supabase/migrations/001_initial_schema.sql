-- SwingScout v1 — Initial Schema
-- Run this in Supabase SQL editor

-- ============================================================
-- SETTINGS
-- ============================================================
CREATE TABLE settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) UNIQUE,
  starting_cash_czk DECIMAL NOT NULL DEFAULT 1000000,
  max_positions INTEGER NOT NULL DEFAULT 20,
  cash_reserve_pct DECIMAL NOT NULL DEFAULT 0.07,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- POSITIONS
-- ============================================================
CREATE TABLE positions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker TEXT NOT NULL,
  shares DECIMAL NOT NULL,
  avg_cost DECIMAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  play_type TEXT NOT NULL CHECK (play_type IN ('A', 'B', 'C')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- THESES
-- ============================================================
CREATE TABLE theses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  position_id UUID REFERENCES positions(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker TEXT NOT NULL,
  entry_thesis TEXT NOT NULL,
  exit_conditions TEXT,
  horizon TEXT,
  play_type TEXT NOT NULL CHECK (play_type IN ('A', 'B', 'C')),
  status TEXT NOT NULL DEFAULT 'intact'
    CHECK (status IN ('intact', 'weakening', 'zombie', 'invalidated', 'delivered')),
  notes_log JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- DAILY RUNS (includes report content + discovery log)
-- ============================================================
CREATE TABLE daily_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  run_type TEXT NOT NULL CHECK (run_type IN ('daily', 'intraday')),
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN ('running', 'completed', 'failed')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  report_content TEXT,
  market_regime TEXT,
  fng_score INTEGER,
  fng_week_ago INTEGER,
  portfolio_snapshot JSONB,
  discovery_log JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- RECOMMENDATIONS
-- ============================================================
CREATE TABLE recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  run_id UUID REFERENCES daily_runs(id),
  ticker TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('buy', 'sell', 'add', 'exit', 'csp', 'long_call')),
  play_type TEXT NOT NULL CHECK (play_type IN ('A', 'B', 'C')),
  confidence INTEGER NOT NULL CHECK (confidence BETWEEN 1 AND 4),
  recommended_price DECIMAL NOT NULL,
  recommended_size_czk DECIMAL,
  add_reserve_czk DECIMAL,
  thesis_text TEXT NOT NULL,
  exit_conditions TEXT,
  is_options_play BOOLEAN NOT NULL DEFAULT FALSE,
  options_details JSONB,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'confirmed', 'rejected', 'updated')),
  rejection_reason TEXT,
  actual_price DECIMAL,
  price_update_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  confirmed_at TIMESTAMPTZ,
  rejected_at TIMESTAMPTZ
);

-- ============================================================
-- TRANSACTIONS
-- ============================================================
CREATE TABLE transactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('buy', 'sell')),
  shares DECIMAL NOT NULL,
  price_per_share DECIMAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  size_czk DECIMAL,
  recommendation_id UUID REFERENCES recommendations(id),
  executed_at TIMESTAMPTZ NOT NULL,
  notes TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- AGENT WATCHLIST
-- ============================================================
CREATE TABLE agent_watchlist (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id),
  ticker TEXT NOT NULL,
  stage TEXT NOT NULL DEFAULT 'watching' CHECK (stage IN ('watching', 'candidate')),
  signal_reason TEXT,
  theme TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  removed_at TIMESTAMPTZ,
  UNIQUE(user_id, ticker)
);

-- ============================================================
-- ROW LEVEL SECURITY
-- Backend uses service_role_key (bypasses RLS),
-- but enable RLS as a safety net against direct client access.
-- ============================================================
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE theses ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_watchlist ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_positions_user_status ON positions(user_id, status);
CREATE INDEX idx_theses_position ON theses(position_id);
CREATE INDEX idx_theses_user_ticker ON theses(user_id, ticker);
CREATE INDEX idx_recommendations_user_status ON recommendations(user_id, status, created_at DESC);
CREATE INDEX idx_transactions_user ON transactions(user_id, executed_at DESC);
CREATE INDEX idx_daily_runs_user_type ON daily_runs(user_id, run_type, started_at DESC);
CREATE INDEX idx_watchlist_user_active ON agent_watchlist(user_id, removed_at);
