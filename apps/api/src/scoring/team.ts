import { assertRange } from './ranges'

export interface TeamMember {
  name: string
  isFounder: boolean
  h: number
  m: number
  l: number
}

/** H (0–5) + M (0–3) + L (0–2), max 10. Frozen. */
export function memberScore(member: TeamMember): number {
  assertRange('h', member.h, 0, 5)
  assertRange('m', member.m, 0, 3)
  assertRange('l', member.l, 0, 2)
  return member.h + member.m + member.l
}

/**
 * (founder x 5 + sum of others) / (5 + count of others). Frozen.
 * The founder counts as five scores; everyone else counts as one.
 */
export function teamWeightedScore(members: TeamMember[]): number {
  if (members.length < 3 || members.length > 5) {
    throw new Error(`team must have 3 to 5 people, got ${members.length}`)
  }

  // `=== true` and not truthiness: a JSON body carrying the STRING "false" would otherwise
  // elect that member sole founder and return a plausible score instead of the error below.
  const founders = members.filter((x) => x.isFounder === true)
  if (founders.length !== 1) {
    throw new Error(`team must have exactly one founder, got ${founders.length}`)
  }

  const founderScore = memberScore(founders[0] as TeamMember)
  const others = members.filter((x) => !x.isFounder).map(memberScore)
  const sumOthers = others.reduce((a, b) => a + b, 0)

  return (founderScore * 5 + sumOthers) / (5 + others.length)
}
