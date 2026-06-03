-- Full data reset — keeps schema, deletes all rows.
-- Order respects FK constraints.

TRUNCATE TABLE transactions CASCADE;
TRUNCATE TABLE theses CASCADE;
TRUNCATE TABLE recommendations CASCADE;
TRUNCATE TABLE positions CASCADE;
TRUNCATE TABLE daily_runs CASCADE;
TRUNCATE TABLE agent_watchlist CASCADE;
TRUNCATE TABLE settings CASCADE;
