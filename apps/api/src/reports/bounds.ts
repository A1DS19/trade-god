/*
 * Rubric bounds that the frozen modules hold as inline literals rather than as exports.
 *
 * These are a PIN, not a second copy. `scoring/product.ts` writes `assertIntegerRange('ease',
 * input.ease, 0, 10)` inline and `scoring/team.ts` writes `< 3`, `> 5` and `* 5` inline;
 * exporting them would mean editing two frozen files to avoid a copy that
 * `frozen-surface.test.ts` already pins against the DDL. So the numbers live here, beside the
 * code that needs them at the WRITE path, and `frozen-surface.test.ts` asserts each one against
 * the committed .sql and against the frozen functions' own behaviour.
 */

/** Ease / Hair-on-Fire / Exclusivity are each 0-10 (`rs_product_*_range`). */
export const PRODUCT_SUB_SCORE_MAX = 10

/** H 0-5, M 0-3, L 0-2 (`rt_h_range`, `rt_m_range`, `rt_l_range`). */
export const TEAM_RUNG_MAX = { h: 5, m: 3, l: 2 } as const

/** `teamWeightedScore()` throws outside this range. Not a CHECK — cardinality across rows. */
export const TEAM_MIN_PEOPLE = 3
export const TEAM_MAX_PEOPLE = 5
