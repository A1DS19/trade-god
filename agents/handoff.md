# Where we left off
_2026-09-21_

## This session
- AWS closed the account hosting the Lightsail box. The intraday paper telemetry DB is gone
  permanently — no backup, no Telegram trail. Confirmed the host is dark (ICMP + :22 dead).
- Reassessed rather than rebuilt. `research/signals/intraday/output/2b/oos_results.csv` shows
  OOS_FULL at **−15.19%, PF 0.986, Sharpe −0.29 over 2,791 trades**. Decision: stop trading,
  don't redeploy, don't reconstruct the lost telemetry.
- Pivoted the project to a **local Electron research platform** implementing the CoinPicks
  fundamental framework. Read the framework from the downloaded zip + the Skool lessons.
- Wrote and approved the design spec, then Plan 1.

## State
- Branch `main`. Spec, Plan 1, and this handoff are committed locally — **not pushed**.
- Nothing in `app/` has moved yet. The repo still describes the retired paper engine.
- `research/` untouched and green. Warehouse is stale since 2026-07-15 (harmless; no cron was
  ever installed — `crontab -l` is empty).
- Docs: `docs/superpowers/specs/2026-09-21-coin-research-platform-design.md` (approved),
  `docs/superpowers/plans/2026-09-21-coin-research-foundation.md` (6 tasks, ready to execute).

## Next session
1. **Decide the execution mode** — subagent-driven (a fresh agent per task, I review between) or
   inline with checkpoints. That question was open when we stopped.
2. Execute Plan 1 Task 1. Its Step 1 runs `python -m pytest tests/research -q` *before* moving
   anything — if that's already red, stop and report rather than letting the move take the blame.
3. Note the real dependency Task 1 handles: `research/signals/intraday/{mr_vwap_strategy,families}.py`
   import `app.intraday.strategy`, so that module moves into `research/` rather than to `legacy/`.
4. Then Tasks 2–6 in order. Plans 2–4 (evidence / workflow / ledger) aren't written yet.

## Open items
- **Unverified:** whether the Claude Code CLI subscription auth works from a spawned process.
  Matters for Plan 3's `Drafter`; `ApiKeyDrafter` is the fallback either way.
- Framework formulas are **frozen** — implement exactly, never retune. See the spec's
  "Normative formulas (frozen)" section.
