-- Schema rule 2. Drizzle's DSL cannot express a trigger, so this file is hand-written and
-- schema.ts never re-emits it. Verified statement by statement against PostgreSQL 16.13.
--
-- SQLSTATEs, all in a private class so they cannot be confused with a real FK RESTRICT:
--   CP001  refused: this row belongs to a committed report, or is a ledger table
--   CP002  refused: this report is not in a state that may be committed
--   CP404  refused: the parent report does not exist

CREATE OR REPLACE FUNCTION coinpicks_reports_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- OLD.status, never NEW.status. Testing NEW would refuse the commit flip itself
  -- (draft -> committed), which is the one update that must be allowed.
  IF OLD.status = 'committed' THEN
    RAISE EXCEPTION 'report % is committed; % on reports is refused', OLD.id, TG_OP
      USING ERRCODE = 'CP001';
  END IF;
  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_report_child_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  -- %TYPE, never a literal type. Declaring `text` against uuid keys passes CREATE FUNCTION
  -- and then kills EVERY child write at runtime with "operator does not exist: uuid = text",
  -- because PostgreSQL has no implicit text->uuid cast and plpgsql binds the variable as a
  -- parameter. Reproduced live.
  parent_id     reports.id%TYPE;
  parent_status reports.status%TYPE;
BEGIN
  -- FIRST, and unconditionally. The naive trigger inspected only NEW.report_id on UPDATE, so
  -- moving a row OUT of a committed report was permitted: three ordinary UPDATEs left a
  -- committed report holding 0 scores, 0 team and 1 of 2 citations while a draft inherited
  -- its numbers and its verified citations. A child row belongs to one report for its whole
  -- life; there is no legitimate re-parent in this design.
  IF TG_OP = 'UPDATE' AND NEW.report_id IS DISTINCT FROM OLD.report_id THEN
    RAISE EXCEPTION 'report_id is immutable; % on % may not re-parent a row',
      TG_OP, TG_TABLE_NAME USING ERRCODE = 'CP001';
  END IF;

  -- OLD for UPDATE and DELETE, NEW only for INSERT: the question is where the row IS, not
  -- where it is going.
  parent_id := CASE TG_OP WHEN 'INSERT' THEN NEW.report_id ELSE OLD.report_id END;

  -- FOR KEY SHARE, not a bare SELECT. A bare read sees this transaction's own snapshot, so a
  -- writer racing a commit reads 'draft', is allowed through, and commits first -- leaving a
  -- permanently immutable report carrying a row its gate never saw. FOR KEY SHARE conflicts
  -- with the FOR UPDATE the commit transaction holds, so that writer blocks here and re-reads
  -- 'committed' afterwards. It does NOT conflict with FOR NO KEY UPDATE, so ordinary
  -- concurrent draft edits are not serialised by it.
  SELECT r.status INTO parent_status FROM reports r WHERE r.id = parent_id FOR KEY SHARE;

  IF NOT FOUND THEN
    -- PostgreSQL removes the parent row BEFORE running the FK cascade, so a cascading delete
    -- always lands here. Raising unconditionally -- which the naive version did -- made
    -- ON DELETE CASCADE dead and "discard this draft" impossible for any draft with one
    -- citation. Allowing it unconditionally would make an orphaned child freely deletable,
    -- which is the state the re-parent attack above leaves rows in. So: DELETE only.
    IF TG_OP = 'DELETE' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'report % does not exist', parent_id USING ERRCODE = 'CP404';
  END IF;

  IF parent_status = 'committed' THEN
    RAISE EXCEPTION 'report % is committed; % on % is refused',
      parent_id, TG_OP, TG_TABLE_NAME USING ERRCODE = 'CP001';
  END IF;

  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_refuse_truncate() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- TRUNCATE does not fire FOR EACH ROW triggers at all. Verified on 16.13: with every row
  -- trigger in place, `TRUNCATE citations` returned TRUNCATE TABLE. A statement-level trigger
  -- is the only thing that stops it.
  RAISE EXCEPTION 'TRUNCATE on % is refused: this table is an append-only ledger',
    TG_TABLE_NAME USING ERRCODE = 'CP001';
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_seed_report_scores() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- The 1:1 invariant, made structural. The design never said who created this row and the
  -- commit transaction only ever UPDATEs it, so a route that forgot would produce a zero-row
  -- update and a SCORES_MISSING blocker at the worst possible moment.
  INSERT INTO report_scores (report_id) VALUES (NEW.id);
  RETURN NULL;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_assert_commitable() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  scored boolean;
  c      coins%ROWTYPE;
BEGIN
  -- Rule 3, at the database. Without this a report committed with scoring_version,
  -- product_passed and product_total all NULL -- and an INSERT could mint a born-committed
  -- row with no scores and no citations, permanently frozen and impossible to ever fill,
  -- because the child triggers correctly refuse INSERT on a committed parent.
  SELECT s.product_passed IS NOT NULL AND s.scoring_version IS NOT NULL
    INTO scored
    FROM report_scores s
   WHERE s.report_id = NEW.id;

  IF NOT FOUND OR NOT scored THEN
    RAISE EXCEPTION
      'report % cannot be committed: its report_scores row is missing or unscored', NEW.id
      USING ERRCODE = 'CP002';
  END IF;

  -- The coin identity snapshot. Written HERE rather than by the commit route so it cannot be
  -- forgotten. `coins` has no guard -- UPDATE coins SET symbol='SCAM', contract_address=...
  -- was confirmed to succeed against a live committed report -- and re-pointing a coin
  -- re-points every forward return ever computed from the (chain, contract_address) join
  -- while the committed report's own bytes stay unchanged, so nothing looks wrong.
  SELECT * INTO c FROM coins WHERE id = NEW.coin_id FOR KEY SHARE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'coin % does not exist', NEW.coin_id USING ERRCODE = 'CP404';
  END IF;

  NEW.coin_symbol           := c.symbol;
  NEW.coin_chain            := c.chain;
  NEW.coin_contract_address := c.contract_address;
  RETURN NEW;
END $$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION coinpicks_citation_claim_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  -- A waiver, a verification and an http_status belong to the claim they were granted for.
  -- Citations are freely editable while the report is a draft, and nothing otherwise tied a
  -- waiver to its text: quote fails, operator waives, operator later fixes the quote or
  -- repoints the URL, and the commit path discards the fresh 'failed' outcome because the row
  -- says 'waived'. The report then commits on a claim never mechanically confirmed anywhere,
  -- with an http_status and matched_offset that look current.
  NEW.status         := 'unverified';
  NEW.last_outcome   := NULL;
  NEW.waiver_reason  := NULL;
  NEW.verified_at    := NULL;
  NEW.http_status    := NULL;
  NEW.matched_offset := NULL;
  RETURN NEW;
END $$;
--> statement-breakpoint
-- reports itself: UPDATE and DELETE only. INSERT is how re-researching a coin works -- a new
-- reports row, not a new version of the old one.
CREATE TRIGGER reports_immutable
  BEFORE UPDATE OR DELETE ON reports
  FOR EACH ROW EXECUTE FUNCTION coinpicks_reports_immutable();
--> statement-breakpoint
-- `OF status` deliberately: on a committed row, `UPDATE reports SET version = 1234` does not
-- mention status, so this does not fire and reports_immutable refuses it with the message the
-- operator should see.
CREATE TRIGGER reports_assert_commitable
  BEFORE INSERT OR UPDATE OF status ON reports
  FOR EACH ROW WHEN (NEW.status = 'committed')
  EXECUTE FUNCTION coinpicks_assert_commitable();
--> statement-breakpoint
CREATE TRIGGER reports_seed_scores
  AFTER INSERT ON reports
  FOR EACH ROW EXECUTE FUNCTION coinpicks_seed_report_scores();
--> statement-breakpoint
-- The children include INSERT. Without it, `INSERT INTO citations ... report_id = <a
-- committed one>` returned INSERT 0 1 on 16.13, which is editing a committed report by any
-- honest reading.
CREATE TRIGGER report_scores_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON report_scores
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
CREATE TRIGGER report_team_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON report_team
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
CREATE TRIGGER citations_immutable
  BEFORE INSERT OR UPDATE OR DELETE ON citations
  FOR EACH ROW EXECUTE FUNCTION coinpicks_report_child_immutable();
--> statement-breakpoint
-- Fires AFTER citations_immutable, because PostgreSQL runs BEFORE ROW triggers in name order
-- and 'citations_i...' sorts before 'citations_r...'. A committed report is therefore refused
-- with CP001 rather than having its citation quietly reset.
CREATE TRIGGER citations_reset_verification
  BEFORE UPDATE ON citations
  FOR EACH ROW WHEN (NEW.url IS DISTINCT FROM OLD.url OR NEW.quote IS DISTINCT FROM OLD.quote)
  EXECUTE FUNCTION coinpicks_citation_claim_changed();
--> statement-breakpoint
CREATE TRIGGER reports_no_truncate
  BEFORE TRUNCATE ON reports
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER report_scores_no_truncate
  BEFORE TRUNCATE ON report_scores
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER report_team_no_truncate
  BEFORE TRUNCATE ON report_team
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
CREATE TRIGGER citations_no_truncate
  BEFORE TRUNCATE ON citations
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
-- forward_returns is the OUTCOME half of the ledger. The reports half being immutable is only
-- half a ledger if the answers they are graded against can be wiped.
CREATE TRIGGER forward_returns_no_truncate
  BEFORE TRUNCATE ON forward_returns
  FOR EACH STATEMENT EXECUTE FUNCTION coinpicks_refuse_truncate();
--> statement-breakpoint
-- ENABLE ALWAYS, every one. The default is ORIGIN, and `SET session_replication_role =
-- replica` silences an ORIGIN trigger: confirmed live that the replica-mode UPDATE returned
-- UPDATE 1 and the committed row changed, and that after ENABLE ALWAYS the same session was
-- refused with CP001 and the row was unchanged.
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_immutable;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_assert_commitable;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_seed_scores;
--> statement-breakpoint
ALTER TABLE report_scores ENABLE ALWAYS TRIGGER report_scores_immutable;
--> statement-breakpoint
ALTER TABLE report_team ENABLE ALWAYS TRIGGER report_team_immutable;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_immutable;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_reset_verification;
--> statement-breakpoint
ALTER TABLE reports ENABLE ALWAYS TRIGGER reports_no_truncate;
--> statement-breakpoint
ALTER TABLE report_scores ENABLE ALWAYS TRIGGER report_scores_no_truncate;
--> statement-breakpoint
ALTER TABLE report_team ENABLE ALWAYS TRIGGER report_team_no_truncate;
--> statement-breakpoint
ALTER TABLE citations ENABLE ALWAYS TRIGGER citations_no_truncate;
--> statement-breakpoint
ALTER TABLE forward_returns ENABLE ALWAYS TRIGGER forward_returns_no_truncate;
