# Where we left off
_2026-09-22_

## This session

The editor was **finished and hardened**, and then the project was **reframed**: CoinPicks becomes
automated research of the warehouse top-100, and its design spec is written and waiting for the
owner's review.

- **Plan 3 Tasks 5–7 executed:** the editor shell and one Save per section (`2de21fc`), the
  blocker list generated from the same array as the CHECK (`1b518d3`), and liquidity, narrative,
  team and accrual (`17102e1`).
- **Four adversarial review rounds** of the editor, fixed in `c47b11f`, `7f7d25c`, `b8b4dd8`,
  `b4ad955`, `ff82448`. The save model that came out of them: in-place re-seed, route-owned
  errors, one write per page, and a landed write's own answer applied before the re-read. A
  failed re-read or a cut response body still counts as landed.
- **A description under every editor label** (`d9a3ecf`): lesson quotes served as
  `bounds.fieldHelp`, checked word for word by `field-help.test.ts`.
- **The reframe** is recorded in `agents/decisions.md` (`7ffc5fc`, `457aed8`). The spec is
  `docs/superpowers/specs/2026-09-22-automated-research-design.md` (`c55cf73`). A five-angle
  adversarial review of the first draft raised 142 findings (140 confirmed); the spec was rewritten
  rather than patched. All 35 lesson quotes in it match `framework/`.
- **The warehouse was brought current** (+2,473,876 rows, 0 failures) and a daily 05:30 cron was
  installed.

### The owner's rulings this session
1. **Reframe:** automated research of the warehouse top-100 against the frozen framework. The
   output is ranked signals the owner trades by hand. Automatic trading comes only after the
   signals have a validated forward record.
2. **Pipeline choices:**
   - an LLM researcher whose quotes are verified;
   - Jev (TypeSafe) scores against the rubric levels;
   - the signal rule is gate + rank, versioned;
   - research cadence is tiered.
3. **A band becomes its lowest value.** The product total can therefore reach at most 23.
4. **Narrative levels:** I draft them, the owner approves (Appendix A).
5. **Researcher bench:** Claude with web search against the Perplexity Search API, same model.
6. **Stack:** Elysia on Bun, shadcn, the **Spectral** palette (artifact:
   https://claude.ai/artifact/Hg1oX2GhYWwXiXLCHsC7EJ).
7. **Editor:** measured-at dates before 2009-01-03 are rejected. Field help is the lesson quotes
   plus app-written help.

### What got caught by running things rather than reading them
- **`~/.claude/settings.json` sets `NODE_ENV=development`** in every Claude session. The bundle
  ceiling was measured in dev mode, and CI's production build (382k) cannot catch the leak it
  guards against. The fix is scheduled for Phase 0.
- **The warehouse had silently stopped in mid-July** with no cron. Open interest and long/short
  have a permanent hole from 2026-06-12 to about 2026-08-24 (recorded in CLAUDE.md).
- **Playwright's `fill()` hid a typing bug:** the roles box could not take a typed space or comma.
  Walks now type instead of paste.
- **A red commit landed** because the tests were chained with `;`. Chain with `&&`.
- `node --watch` served stale code after `git stash` swapped the file's inode.

## State

- Branch `main`, working tree clean, **40 commits ahead of `origin/main`, not pushed**.
- `apps/api`: 124 tests at the last run. `apps/web`: 2 test files. pytest: 111.
- **Postgres is stopped** (`docker compose stop db`). The container and the `coinpicks_data`
  volume are kept; `docker compose up -d db` resumes.
- No servers running.
- Cron: `30 5 * * *` warehouse backfill, logging to `/tmp/research-backfill.log` (tmpfs, emptied
  at reboot).
- **CLAUDE.md and `agents/roadmap.md` still describe the Hono/Node/EvidenceFinder plan.** Both get
  rewritten once the spec is approved; until then, the spec and `agents/decisions.md` win.

## Next session

1. **The owner reviews the spec.** §15 lists 12 questions, and Appendix A (the rubric levels)
   comes first because Phase 3 waits on it. The ones that most change what gets built:
   - Q2: Narrative Maturity's direction;
   - Q7: where the overview sentence comes from;
   - Q8: native L1 pools;
   - Q9: which model does the research.
2. Fold the answers into the spec and commit.
3. **Invoke writing-plans for Phase 0:**
   - the Bun workspace and Elysia API, with the error handler registered first;
   - the Eden client;
   - `bun test` for both apps;
   - shadcn Spectral;
   - the NODE_ENV fix and key needles;
   - the loopback web server.

   Plan 3 Task 8 (docs/CI) folds into it.
4. After approval, rewrite CLAUDE.md and the roadmap for the reframe.

## Open items

- **Keys to get before their phase:**
  - Phase 1: a CoinGecko Demo key.
  - Phase 2: Anthropic, Perplexity and TypeSafe keys. **TypeSafe's site mentions a waitlist
    while its console shows billing**, so confirm access first.
- `.env` still holds the trading era's Binance keys, Telegram token and a Claude API key (backed
  up to `.env.trading-era.bak`, gitignored). Revoke them at the source.
- **The leak guard rides on an unpinned transitive:** `@tanstack/start-plugin-core` resolved to
  1.171.47 while `@tanstack/react-start` is pinned at 1.168.57. The bundle scan is the backstop.
- **Web dev port 5173** collides with the sibling repo's dev server. `strictPort` makes the
  collision loud; the port is still undecided.
- **Liquidity freshness window:** answered for automated reports by the spec (a live pull at
  decision time, §4.7), still open for human reports.
- Three dead docker volumes: `trade-god_postgres_data`, `trade-god_klines_cache`,
  `trade-god_swing_data`.
