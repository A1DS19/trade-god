-- The three login roles, and the test database. Run ONCE per Postgres cluster, as the
-- compose superuser, and again whenever you want a clean coinpicks_test:
--
--   pnpm --filter @coinpicks/api run db:bootstrap
--
-- This is NOT a Drizzle migration and must never become one. CREATE ROLE is cluster-scoped
-- while a migration applies once per database, so a role created inside one would be missing
-- from coinpicks_test. It is also the only place a superuser connection is used.
--
-- WHY THREE ROLES. An attacker confirmed on PostgreSQL 16.13 that a session owning the
-- tables can `SET session_replication_role = replica` and then UPDATE a committed report
-- back to draft and DELETE it, with every immutability trigger installed and silent, and can
-- `DROP TRIGGER` outright. A NOSUPERUSER non-owner is refused all three. So:
--
--   coinpicks_owner  owns every table; used ONLY by the boot migrator, which closes its pool
--                    before the port is taken.
--   coinpicks_app    owns nothing; DML on the seven tables and nothing else. This is the
--                    request pool.
--   research         SELECT on five tables, and the outcome columns of forward_returns.
--
-- Passwords are the role names. This is a loopback-only, single-user, no-auth ledger on
-- 127.0.0.1:5433 and the compose file already ships `coinpicks:coinpicks`; a secret that is
-- printed in .env.example is not a secret, and pretending otherwise would be theatre.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coinpicks_owner') THEN
    CREATE ROLE coinpicks_owner;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'coinpicks_app') THEN
    CREATE ROLE coinpicks_app;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'research') THEN
    CREATE ROLE research;
  END IF;
END $$;

ALTER ROLE coinpicks_owner LOGIN PASSWORD 'coinpicks_owner'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE coinpicks_app LOGIN PASSWORD 'coinpicks_app'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;
ALTER ROLE research LOGIN PASSWORD 'research'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT;

ALTER ROLE coinpicks_owner SET search_path = public;
ALTER ROLE coinpicks_app   SET search_path = public;
ALTER ROLE research        SET search_path = public;

-- Database ownership, not a pile of grants: the owner of a database is implicitly a member
-- of pg_database_owner, which owns schema public, so this one statement gives the migrator
-- CREATE on public and the right to create the `drizzle` schema its journal lives in.
ALTER DATABASE coinpicks OWNER TO coinpicks_owner;
GRANT CONNECT ON DATABASE coinpicks TO coinpicks_app, research;

-- The test database. Rebuilt from scratch here, and re-migrated by vitest's globalSetup at
-- the start of every run. WITH (FORCE) because a stray psql session would otherwise block
-- the drop.
DROP DATABASE IF EXISTS coinpicks_test WITH (FORCE);
CREATE DATABASE coinpicks_test OWNER coinpicks_owner;
GRANT CONNECT ON DATABASE coinpicks_test TO coinpicks_app, research;
