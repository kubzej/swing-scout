-- Add realized_pnl_czk to transactions
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS realized_pnl_czk DECIMAL;

-- Add realized_pnl_czk accumulator to positions (total realized from partial sells)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS realized_pnl_czk DECIMAL NOT NULL DEFAULT 0;

-- Allow NULL on recommended_price (it's often not known at recommendation time)
ALTER TABLE recommendations ALTER COLUMN recommended_price DROP NOT NULL;
