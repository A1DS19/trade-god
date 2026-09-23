import { MEASURED_AT_FLOOR } from './patch-schemas.ts'

/*
 * WHAT EACH EDITOR FIELD MEANS, served beside the bounds so apps/web holds no rubric text.
 *
 * Two kinds of entry, and the difference is a promise:
 *  - `source` names a lesson in framework/: every line is quoted from that file VERBATIM, and
 *    field-help.test.ts fails if one is not. The editor shows these in quotation marks with the
 *    lesson beside them, so a paraphrase here would be a misquote on screen.
 *  - `source: 'editor'`: help this app wrote, for the boxes no lesson covers (provenance, the
 *    measurement timestamp, the rationale boxes). Shown plain, never as a quote.
 *
 * Keys are the editor's field names. A few are shared across a section: the measured-figure
 * boxes (`measured*`), the rationale boxes, the evidence blocks and the team row controls.
 */

export type FrameworkLesson =
  | 'framework/00-how-we-think.md'
  | 'framework/02-product-exclusivity.md'
  | 'framework/03-liquidity-analysis.md'
  | 'framework/04-narrative-scoring.md'
  | 'framework/05-team-credibility.md'
  | 'framework/06-one-page-report-template.md'

export interface FieldHelp {
  /** Always shown, joined by spaces. Verbatim lesson lines when `source` is a lesson. */
  text: readonly string[]
  source: FrameworkLesson | 'editor'
  /** Folded under a <details>: a scoring scale, the credibility rungs, a how-to. */
  details?: { summary: string; lines: readonly string[] }
}

const PRODUCT = 'framework/02-product-exclusivity.md'
const LIQUIDITY = 'framework/03-liquidity-analysis.md'
const NARRATIVE = 'framework/04-narrative-scoring.md'
const TEAM = 'framework/05-team-credibility.md'
const REPORT = 'framework/06-one-page-report-template.md'
const THINKING = 'framework/00-how-we-think.md'

const HAIR_ON_FIRE =
  'Does this product innovate or solve a mass problem in a way that users and/or the entire industry urgently feels they must adopt right now?'

export const FIELD_HELP = {
  // -- 1 · Product gate --------------------------------------------------------------------
  overviewSentence: {
    text: ['One-sentence project overview (no hype, no history, just what it is)'],
    source: REPORT,
  },
  productEase: {
    text: [
      'When you try to use this product, does it actually work smoothly, simply, and effectively?',
    ],
    source: PRODUCT,
    details: {
      summary: 'scale',
      lines: [
        '(0–3) Does not do what it claims. Complex, broken, or mostly vaporware.',
        '(4–6) Works, but clunky or not as smooth as claimed.',
        '(7–10) Does what it claims. Genuinely easy, reliable, and effective in practice.',
      ],
    },
  },
  productHairFire: {
    text: [HAIR_ON_FIRE],
    source: PRODUCT,
    details: {
      summary: 'scale',
      lines: [
        '(0–1) Gimmicky or irrelevant',
        '(2–4) Interesting, but not exciting',
        '(5–7) Clearly valuable or innovative — sparks curiosity',
        '(8–10) Undeniable "hair-on-fire" urgency — feels necessary and immediate',
      ],
    },
  },
  productExclusivity: {
    text: [
      'Does this project have a unique "WOW" innovation that changed the game and is exclusive to them?',
    ],
    source: PRODUCT,
    details: {
      summary: 'scale',
      lines: [
        '(0–1) No exclusivity; generic, easily copied',
        '(2–4) Some differentiation, but not rare or defensible',
        '(5–7) Clear unique edge (first-to-market or notable feature), but somewhat deniable',
        '(8–10) Rare, NOT duplicatable advantage (e.g., Coinbase-level solo integration, legal win like XRP, or official blockchain fork approval) that competitors cannot replicate',
      ],
    },
  },
  productRationale: {
    text: [
      'One or two sentences on why this score. The evidence box below carries the source link and its quote.',
    ],
    source: 'editor',
  },

  // -- 2 · Liquidity -----------------------------------------------------------------------
  liquidityDepth2pctUsd: {
    text: [
      'Check the "Markets" tab on CoinGecko.',
      'Press the "+2% Depth" column to rank exchanges by ±2% depth.',
    ],
    source: LIQUIDITY,
  },
  liquidityTopPoolTvlUsd: {
    text: [
      'Find the main DEX liquidity pool for the coin (usually on GeckoTerminal).',
      'Click through the top 3–5 pools by liquidity — sometimes the preview is outdated.',
    ],
    source: LIQUIDITY,
  },
  liquidityNoDexPool: {
    text: ['If a coin has no DEX pool, assign tier based only on ±2% depth across CEXs.'],
    source: LIQUIDITY,
  },
  liquidityTier: {
    text: [
      "Don't overthink the liquidity tier—there's no perfect formula, just make your best guess between low, medium, or high risk, move forward, and you'll get better at spotting the difference with experience.",
    ],
    source: LIQUIDITY,
    details: {
      summary: 'how to assign it',
      lines: [
        "Use the highest pool's TVL + the ±2% depth across exchanges to assign Low / Medium / High.",
        'If a coin has no DEX pool, assign tier based only on ±2% depth across CEXs.',
      ],
    },
  },
  liquidityJustification: {
    text: ['Brief justification using ±2% depth + pool TVL'],
    source: REPORT,
  },

  // -- The five boxes of every measured figure (liquidity and market cap) -------------------
  measuredValue: {
    text: ['The figure itself, in US dollars.'],
    source: 'editor',
  },
  measuredSource: {
    text: ['Who published the figure: CoinGecko, GeckoTerminal, DefiLlama.'],
    source: 'editor',
  },
  measuredUrl: {
    text: ['The page the figure was read from.'],
    source: 'editor',
  },
  measuredLabel: {
    text: [
      'verified: you checked the figure yourself. vendor_claim: the number as the vendor reports it — never silently promoted to verified.',
    ],
    source: 'editor',
  },
  measuredAt: {
    text: [
      'When the figure was read: ISO 8601 with seconds and an offset, like 2026-09-21T14:32:00+02:00 or 2026-09-21T12:32:00Z.',
      `Not in the future, not before ${MEASURED_AT_FLOOR.slice(0, 10)}. Shown back in UTC after a save — the same instant.`,
    ],
    source: 'editor',
  },

  // -- 3 · Narrative -----------------------------------------------------------------------
  narrativeMaturity: {
    text: ['How far along is the narrative in the market cycle?'],
    source: NARRATIVE,
  },
  narrativeSmartMoney: {
    text: ['Would serious capital flow into this structure?'],
    source: NARRATIVE,
  },
  narrativeHairFire: {
    text: [HAIR_ON_FIRE],
    source: NARRATIVE,
  },
  narrativeCommunication: {
    text: ['How well is the story being told?'],
    source: NARRATIVE,
  },
  narrativeLineage: {
    text: ['Is this clearly connected to a previously proven 100x trend?'],
    source: NARRATIVE,
  },
  narrativeMutation: {
    text: ['Has this narrative evolved into a real-world trend?'],
    source: NARRATIVE,
  },
  narrativeRationale: {
    text: [
      'For every sub-score, include a 1–2 sentence explanation backed by a source link with a Ctrl+F-able quote.',
    ],
    source: NARRATIVE,
  },

  // -- Every evidence block ------------------------------------------------------------------
  evidence: {
    text: [
      "every claim that isn't trivially obvious needs a real link and an exact-text snippet to Ctrl+F on that page.",
    ],
    source: REPORT,
  },

  // -- 4 · Team (one legend for every row) --------------------------------------------------
  teamName: {
    text: ['Look for the top contributors in Product and Marketing, plus the Founder.'],
    source: TEAM,
  },
  teamRoles: {
    text: ['Titles can vary — focus on function and influence, not just what their LinkedIn says.'],
    source: TEAM,
  },
  teamFounder: {
    text: ['Founder – The primary visionary and decision-maker (can also be the lead dev)'],
    source: TEAM,
  },
  teamH: {
    text: ['High Credibility (H Score – max 5 points)'],
    source: TEAM,
    details: {
      summary: 'rungs',
      lines: [
        '5 – Founded and scaled a successful crypto company with real traction',
        '4 – Leadership in a global institution (e.g. SEC, CFTC, IMF, BIS, G7/G20)',
        '4 – Executive at a major crypto company (e.g. Coinbase, Binance, Kraken)',
        '2 – Founded a crypto project with unclear or early traction',
        '0 – No founding or executive leadership',
      ],
    },
  },
  teamM: {
    text: ['Medium Credibility (M Score – max 3 points)'],
    source: TEAM,
    details: {
      summary: 'rungs',
      lines: [
        '3 – Founded a real-world business with profit, growth, or acquisition',
        '2 – Non-executive role at a top company (e.g. PM at Coinbase, engineer at Amazon)',
        '1 – Business exists, but traction is unclear',
        '0 – No real-world business experience',
      ],
    },
  },
  teamL: {
    text: ['Low Credibility (L Score – max 2 points)'],
    source: TEAM,
    details: {
      summary: 'rungs',
      lines: [
        '2 – Holds strong credentials (MBA, PhD, CFA, etc.)',
        '1 – Has exposure (e.g. influencer or public face) but lacks real roles or skills',
        '0 – No experience, credentials, or evidence of contribution',
      ],
    },
  },
  teamSummary: {
    text: [
      "write a ONE-SENTENCE summary explanation of the main team member's past experience outside this project, and provide direct source links to prove what you said",
    ],
    source: TEAM,
    details: {
      summary: 'rules',
      lines: [
        'At least one financial metric first (e.g., revenue, valuation, market cap of prior crypto project, total funding raised)',
        'An adoptive metric if available (e.g., monthly active users, total downloads, employees, client base)',
        "When evaluating a team member, do not use the current project's success as proof of credibility",
      ],
    },
  },

  // -- 5 · Value accrual and discovery premium ----------------------------------------------
  accrualSegmentRevenueUsd: {
    text: [
      'Name the segment and find its actual revenue in dollars. Not "the future of finance." A number.',
    ],
    source: THINKING,
  },
  accrualCaptureShare: {
    text: ['what fraction of that segment plausibly routes through THIS system? Be brutal.'],
    source: THINKING,
  },
  accrualPct: {
    text: [
      'of the revenue that routes through the system, what percentage is forced through the token?',
    ],
    source: THINKING,
  },
  accrualAnnualIssuanceUsd: {
    text: ['subtract what the token prints. Emissions, unlocks, inflation.'],
    source: THINKING,
  },
  accrualAbsentReason: {
    text: [
      'Required when the four boxes above are not all filled: say why no accrual figure exists. Blank boxes and a measured zero are different findings.',
    ],
    source: 'editor',
  },
  accrualRationale: {
    text: [
      'The blank must name a mechanism, a fee switch that pays holders, a burn tied to usage, revenue share, mandatory staking that pays from real fees, a buyback funded by income.',
    ],
    source: THINKING,
    details: {
      summary: 'the accrual test',
      lines: [
        '"If this project\'s business doubled tomorrow, one more dollar is forced to the token holder because ______."',
      ],
    },
  },
  accrualFinding: {
    text: ['Optional: what the accrual numbers add up to, in your own words.'],
    source: 'editor',
  },
  discoveryMarketCapUsd: {
    text: [
      'Stop caring about market cap as a headline.',
      "What matters is how much more the token's price implies than the current economic value that actually turns into token demand.",
    ],
    source: THINKING,
  },

  // -- 6 · Risk notes ------------------------------------------------------------------------
  riskNotes: {
    text: ['Risk notes (e.g., liquidity halving incidents)'],
    source: REPORT,
  },
} satisfies Record<string, FieldHelp>
