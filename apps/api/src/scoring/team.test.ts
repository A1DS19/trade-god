import { describe, expect, it } from 'vitest'
import { ScoreRangeError } from './ranges'
import { memberScore, type TeamMember, teamWeightedScore } from './team'

const member = (name: string, isFounder: boolean, h: number, m: number, l: number): TeamMember => ({
  name,
  isFounder,
  h,
  m,
  l,
})

describe('memberScore', () => {
  it('sums H + M + L to a max of 10', () => {
    expect(memberScore(member('a', false, 5, 3, 2))).toBe(10)
  })

  it('rejects H above 5, M above 3, L above 2', () => {
    expect(() => memberScore(member('a', false, 6, 0, 0))).toThrow(ScoreRangeError)
    expect(() => memberScore(member('a', false, 0, 4, 0))).toThrow(ScoreRangeError)
    expect(() => memberScore(member('a', false, 0, 0, 3))).toThrow(ScoreRangeError)
  })
})

describe('teamWeightedScore', () => {
  it("reproduces the framework's worked example: founder 8, others 7/5/6 -> 7.25", () => {
    const team = [
      member('founder', true, 5, 3, 0), // 8
      member('product', false, 4, 3, 0), // 7
      member('marketing', false, 4, 1, 0), // 5
      member('advisor', false, 4, 2, 0), // 6
    ]
    // (8*5 + 7 + 5 + 6) / (5 + 3) = 58 / 8
    expect(teamWeightedScore(team)).toBe(7.25)
  })

  it('weights the founder 5x — swapping founder and a peer changes the result', () => {
    const founderStrong = [
      member('f', true, 5, 3, 2), // 10
      member('a', false, 0, 0, 0),
      member('b', false, 0, 0, 0),
    ]
    const founderWeak = [
      member('f', true, 0, 0, 0),
      member('a', false, 5, 3, 2), // 10
      member('b', false, 0, 0, 0),
    ]
    expect(teamWeightedScore(founderStrong)).toBeCloseTo(50 / 7)
    expect(teamWeightedScore(founderWeak)).toBeCloseTo(10 / 7)
  })

  it('requires exactly one founder', () => {
    expect(() =>
      teamWeightedScore([
        member('f1', true, 1, 1, 1),
        member('f2', true, 1, 1, 1),
        member('c', false, 1, 1, 1),
      ]),
    ).toThrow(/exactly one founder/i)

    expect(() =>
      teamWeightedScore([
        member('a', false, 1, 1, 1),
        member('b', false, 1, 1, 1),
        member('c', false, 1, 1, 1),
      ]),
    ).toThrow(/exactly one founder/i)
  })

  it('requires 3 to 5 people', () => {
    expect(() =>
      teamWeightedScore([member('f', true, 1, 1, 1), member('a', false, 1, 1, 1)]),
    ).toThrow(/3 to 5/i)
  })
})
