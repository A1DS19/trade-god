-- The privilege wall. In the migration chain rather than in a script, because grants are
-- lost when a table is recreated and a migration is the only thing guaranteed to run
-- alongside the DDL that recreated it.
--
-- This runs as coinpicks_owner, which owns every table here.

GRANT USAGE ON SCHEMA public TO coinpicks_app, research;
--> statement-breakpoint
-- The request pool: DML on the seven tables and nothing else. No TRUNCATE (which is a
-- separate privilege, and the *_no_truncate triggers are the second line), no REFERENCES,
-- no ownership, no CREATE.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  coins, reports, report_scores, report_team, citations, chain_facts, forward_returns
  TO coinpicks_app;
--> statement-breakpoint
-- Python's boundary is a GRANT, not a convention. chain_facts is deliberately absent: the
-- spec's list excludes it, and adding SELECT later is one line.
GRANT SELECT ON TABLE coins, reports, report_scores, report_team, citations TO research;
--> statement-breakpoint
-- SELECT so forward_returns.py can see which horizons it has already priced -- a read of
-- rows it wrote itself.
GRANT SELECT, INSERT ON TABLE forward_returns TO research;
--> statement-breakpoint
-- COLUMN-LEVEL, and that is the point. With the unrestricted grant the design proposed,
-- `UPDATE forward_returns SET horizon_days = 365` succeeded as this role and silently moved
-- a 30-day observation into the 365-day slot. report_id and horizon_days are the join key
-- the whole ledger question rests on, and they are now immutable by privilege rather than by
-- trust. return_fraction is generated, so no grant could make it writable.
GRANT UPDATE (price_at_commit_usd, price_at_horizon_usd, price_source, priced_at, computed_at)
  ON TABLE forward_returns TO research;
--> statement-breakpoint
-- format() + current_database() so this migration is identical in coinpicks and in
-- coinpicks_test. A hard-coded database name would fail in one of them.
DO $$
BEGIN
  EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC', current_database());
END $$;
--> statement-breakpoint
-- Redundant on PostgreSQL 15+ and stated anyway: PUBLIC must not be able to create objects
-- next to the ledger.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
