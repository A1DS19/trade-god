# 00 - How We Think

Read this before the numbered framework files. Those files tell you what to check. This one tells you
why, and it is the part that actually filters coins. Everything here is a research method, not financial
advice: it is how we form our own view, shared so you can form yours. Nothing in this folder tells you
what to buy.

---

## 1. Every chain has ONE purpose. Value it on that purpose.

Do not start with the token. Start with the chain or protocol and ask: **what is the one thing this is
actually for?** Not the ten things the docs claim. The one thing real users show up for.

Then run the chain:

1. **Unique proposition**, what can it do that the alternatives genuinely cannot?
2. **Real-world segment**, which existing, measurable market does that proposition replace or absorb?
   Name the segment and find its actual revenue in dollars. Not "the future of finance." A number.
3. **Capture share**, what fraction of that segment plausibly routes through THIS system? Be brutal.
4. **Token accrual %**, of the revenue that routes through the system, what percentage is forced
   through the token? (Section 2 is the test for this.)
5. **MINUS issuance**, subtract what the token prints. Emissions, unlocks, inflation. A token earning
   $10M a year for holders while issuing $50M a year to insiders is losing $40M a year of holder value.
   Most "cheap" tokens fail right here.

What comes out is a rough annual dollar flow to holders. Compare that against the token's price, not
against its story. The gap between the two is what you are actually being asked to pay for.

**These steps multiply.** A coin can score brilliantly on 1-3 and still be worthless to hold because
step 4 is zero or step 5 eats it. One zero anywhere zeroes the product.

## 2. The one-sentence accrual test

For any token, complete this sentence or admit you cannot:

> "If this project's business doubled tomorrow, one more dollar is forced to the token holder
> because ______."

The blank must name a **mechanism**, a fee switch that pays holders, a burn tied to usage, revenue
share, mandatory staking that pays from real fees, a buyback funded by income. Words that do NOT fill
the blank: "exposure," "governance," "alignment," "the community," "narrative," "they might turn on
fees later." If the honest answer is "nothing forces it," you are not valuing a claim on a business. You
are pricing a ticker whose only buyer is the next person. That can still trade, but know which game you
are playing, because the two games have different exits.

This is the difference between **valuing the business** and **valuing the claim**. The chain in Section
1 values the business. This sentence values your actual claim on it. Both must pass.

## 3. The two monetization branches

Every token that passes the accrual test monetizes in one of two ways. Identify which, because they are
valued differently:

- **Cash-flow branch:** usage produces fees and some defined slice reaches holders. Value it like a
  business: flow ÷ price, growth rate, and whether the slice is contractual or revocable.
- **Reserve/collateral branch:** the token must be bought and held or locked for the system to function
  at all (gas floats, bonded collateral, required staking). Value it by the size of the float the
  system's real activity forces into existence.

**The branches ADD, a token can earn from both at once.** But compute each honestly and add the
dollars; do not hand-wave "it also has staking" as a multiplier. And check magnitude: a reserve leg that
forces $20M of float does not rescue a token priced at $50B. Run the arithmetic; smallness is a finding.

## 4. The distance test

Count the steps between "the project succeeds" and "the holder gets paid." Each step is a place where
value leaks to someone who is not you:

- Equity company with a token on the side? The equity eats first; you may be holding the merch.
- Revenue goes to a foundation treasury that "may" buy back? That is a promise, not a mechanism.
- L2 whose fees accrue to the sequencer operator? The operator is the business; the token watches.

Shortest distance wins. Usage → burn is one step. Usage → DAO vote → treasury diversification →
possible buyback is four steps, and every step has hands in it.

## 5. Discovery premium and what "expensive" means

Stop caring about market cap as a headline. What matters is **how much more the token's price implies
than the current economic value that actually turns into token demand.** That gap is the discovery
premium: the market paying today for adoption it expects tomorrow.

A premium is not automatically wrong, everything early trades above its present flow. The questions
are: how MANY years of flawless growth are pre-paid at this price, and is anything real underneath at
all? A token at 5x its forced-flow value needs one good year. A token at 500x needs a decade of
perfection plus your willingness to hold through it. And a token with zero forced flow at any price is
100% premium, pure narrative, tradable but never ownable.

## 6. Liquidity is part of the thesis, not a detail

A thesis you cannot exit is not a position, it is a donation. Before size ever enters the conversation:

- **Real depth, not headline liquidity.** Pools fake TVL. Census the pools, drop the ones whose price
  sits far off the median (a poison pair advertising absurd liquidity at a fake price is a screener
  trap we have hit in production), and count only what survives.
- **Your size versus the pool.** If your position is a meaningful fraction of real depth, the exit
  price is not the chart price. Impact is a cost you pay twice, in and out.
- **Liquidity decays.** The pool that was deep when a list was generated can be a tenth of that two
  weeks later. We watched stored numbers silently rot 12x. Never trust a stored liquidity figure;
  re-pull it live at decision time.

## 7. Quotes are not fills

The number an aggregator shows you and the number you settle at are different numbers. We measured this
across our own real swaps: most fills landed within a few hundredths of a percent of quote, and on one
thin token the same venue repeatedly filled 1-2% below its own quote while still "winning" the quote
race. The lesson generalizes:

- Race venues on QUOTES, but judge them on FILLS. Track quote-to-fill error per venue per token.
- Thin tokens have wider quote-to-fill error. That error is part of your cost, and it never appears on
  any screen until you measure it yourself.
- Any execution layer that cannot show you its own historical slippage is asking you to trust it.

## 8. Verification discipline (the part that saves you from everything else)

- **A name match is not an identity.** Same-ticker decoys are everywhere. Verify contract addresses
  from at least two independent sources before a token is tradable, every time, no exceptions.
- **An API answering is not the data being alive.** A server can return HTTP 200 with 16-hour-old
  numbers. Check the timestamp on the data, not the status code on the pipe.
- **Silence is not success.** After any action, verify the result against the source of truth (the
  chain, the ledger, the file). Never assume it worked because nothing errored.
- **Label provenance.** Every number you write down is either verified (say where) or a guess (say so).
  The moment guesses dress up as facts, the whole research file is poisoned.
- **Write errors down.** Our `ERROR-LOG.md` exists because the same mistake will happen twice unless it
  costs you twice to make it. Keep your own.

---

Then read `01-core-strategy.md` through `06-one-page-report-template.md` for the per-coin workup, and
`doctrine/research/JESSE-DOCTRINE.md` for the accumulated judgment calls behind all of this.
