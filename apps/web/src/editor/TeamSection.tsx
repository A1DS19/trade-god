import { Fragment, useId } from 'react'
import type { TeamBody, TeamRow } from '../lib/client.ts'
import {
  Citations,
  EvidenceRule,
  type Save,
  type SectionProps,
  SectionShell,
  useSection,
} from './common.tsx'
import { FieldHelp } from './fields.tsx'

/** Every row repeats the same controls, so their descriptions are listed once, above the rows. */
/** The legend spells the rungs as the lesson does; the wire and the bounds use lower case. */
const RUNG_KEY = { H: 'h', M: 'm', L: 'l' } as const

const LEGEND = [
  ['teamName', 'Name'],
  ['teamRoles', 'Roles'],
  ['teamFounder', 'Founder'],
  ['teamH', 'H'],
  ['teamM', 'M'],
  ['teamL', 'L'],
  ['teamSummary', 'Summary'],
] as const

type MemberWire = TeamBody['members'][number]

/*
 * The roles box holds its raw text, and it is split only when the body is built.
 *
 * Splitting on every keystroke and rendering `roles.join(', ')` back into the box trimmed the
 * space or comma the operator had just typed, so "Head of growth, advisor" typed key by key
 * arrived as "Headofgrowthadvisor". Same rule as the numeric boxes: the box shows exactly what
 * was typed, and the parse happens once, on the way to the wire.
 */
type MemberForm = Omit<MemberWire, 'roles'> & { roles: string }

const toRoles = (text: string): string[] =>
  text
    .split(',')
    .map((role) => role.trim())
    .filter((role) => role !== '')

function seedMembers(team: TeamRow[]): MemberForm[] {
  return team.map((person) => ({
    id: person.id,
    name: person.name,
    roles: person.roles.join(', '),
    isFounder: person.isFounder,
    h: String(person.h),
    m: String(person.m),
    l: String(person.l),
    summary: person.summary,
  }))
}

/** Every row repeats the same controls, so each one's accessible name says whose it is. */
const personLabel = (index: number, what: string): string => `Person ${String(index + 1)}: ${what}`

const BLANK_MEMBER: MemberForm = {
  id: null,
  name: '',
  roles: '',
  isFounder: false,
  h: '',
  m: '',
  l: '',
  summary: '',
}

export function TeamSection({
  bounds,
  citations,
  disabled,
  error,
  onAddCitation,
  onRemoveCitation,
  onSave,
  seedToken,
  team,
}: Omit<SectionProps, 'scores'> & { onSave: Save<TeamBody>; team: TeamRow[] }) {
  const section = useSection<MemberForm[], TeamBody>(
    seedToken,
    error,
    () => seedMembers(team),
    (members) => ({
      members: members.map((person) => ({ ...person, roles: toRoles(person.roles) })),
    }),
    onSave,
  )
  const { form, update } = section
  const legendId = useId()
  const evidenceId = useId()
  const describedBy = (key: (typeof LEGEND)[number][0]) => `${legendId}-${key}`

  const patch = (index: number, next: Partial<MemberForm>) =>
    update(form.map((person, at) => (at === index ? { ...person, ...next } : person)))

  const move = (index: number, delta: number) => {
    const target = index + delta
    const a = form[index]
    const b = form[target]
    if (a === undefined || b === undefined) return
    const next = [...form]
    next[index] = b
    next[target] = a
    update(next)
  }

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="4 · Team"
    >
      <p className="mb-3 text-sm text-neutral-600">
        The commit gate wants {bounds.teamMinPeople}–{bounds.teamMaxPeople} people and exactly one
        founder; teamWeightedScore() decides that inside the commit transaction. Each summary is one
        sentence about PRIOR experience carrying a financial metric — never about this project.
        Saving replaces the whole set in one transaction, and the order on screen is the order
        stored.
      </p>
      <dl className="mb-3 grid grid-cols-[5rem_1fr] gap-x-3 gap-y-1 text-sm">
        {LEGEND.map(([key, term]) => (
          <Fragment key={key}>
            <dt className="text-neutral-700">{term}</dt>
            <dd>
              <FieldHelp help={bounds.fieldHelp[key]} id={describedBy(key)} />
            </dd>
          </Fragment>
        ))}
      </dl>
      <ul className="space-y-2">
        {form.map((person, index) => (
          <li
            className="border border-neutral-300 p-2"
            key={person.id ?? `unsaved-${String(index)}`}
          >
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="w-6 text-neutral-500">{index + 1}</span>
              <input
                aria-describedby={describedBy('teamName')}
                aria-label={personLabel(index, 'name')}
                className="w-40 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
                disabled={disabled}
                onChange={(event) => patch(index, { name: event.target.value })}
                placeholder="name"
                value={person.name}
              />
              <input
                aria-describedby={describedBy('teamRoles')}
                aria-label={personLabel(index, 'roles, comma separated')}
                className="w-56 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
                disabled={disabled}
                onChange={(event) => patch(index, { roles: event.target.value })}
                placeholder="roles, comma separated"
                value={person.roles}
              />
              <label className="flex items-center gap-1">
                <input
                  aria-describedby={describedBy('teamFounder')}
                  aria-label={personLabel(index, 'founder')}
                  checked={person.isFounder}
                  disabled={disabled}
                  name="founder"
                  onChange={() =>
                    update(form.map((other, at) => ({ ...other, isFounder: at === index })))
                  }
                  type="radio"
                />
                founder
              </label>
              {(['H', 'M', 'L'] as const).map((rung) => (
                <label className="flex items-center gap-1 text-xs" key={rung}>
                  {rung} 0–{bounds.teamRungMax[RUNG_KEY[rung]]}
                  <input
                    aria-describedby={describedBy(`team${rung}`)}
                    aria-label={personLabel(
                      index,
                      `${rung}, whole number 0 to ${String(bounds.teamRungMax[RUNG_KEY[rung]])}`,
                    )}
                    className="w-12 border border-neutral-400 px-1 py-1 disabled:bg-neutral-100"
                    disabled={disabled}
                    inputMode="numeric"
                    onChange={(event) => patch(index, { [RUNG_KEY[rung]]: event.target.value })}
                    value={person[RUNG_KEY[rung]]}
                  />
                </label>
              ))}
              <button
                aria-label={personLabel(index, 'move up')}
                className="border border-neutral-400 px-2 disabled:opacity-40"
                disabled={disabled || index === 0}
                onClick={() => move(index, -1)}
                type="button"
              >
                ↑
              </button>
              <button
                aria-label={personLabel(index, 'move down')}
                className="border border-neutral-400 px-2 disabled:opacity-40"
                disabled={disabled || index === form.length - 1}
                onClick={() => move(index, 1)}
                type="button"
              >
                ↓
              </button>
              <button
                aria-label={personLabel(index, 'remove')}
                className="border border-neutral-400 px-2 text-red-800 disabled:opacity-40"
                disabled={disabled}
                onClick={() => update(form.filter((_, at) => at !== index))}
                type="button"
              >
                remove
              </button>
            </div>
            <input
              aria-describedby={describedBy('teamSummary')}
              aria-label={personLabel(index, 'prior-experience summary')}
              className="mt-2 w-full border border-neutral-400 px-2 py-1 text-sm disabled:bg-neutral-100"
              disabled={disabled}
              onChange={(event) => patch(index, { summary: event.target.value })}
              placeholder="one sentence about prior experience, with a financial metric"
              value={person.summary}
            />
          </li>
        ))}
      </ul>
      <button
        className="mt-2 border border-neutral-500 px-3 py-1 text-sm disabled:opacity-40"
        disabled={disabled}
        onClick={() => update([...form, BLANK_MEMBER])}
        type="button"
      >
        Add person
      </button>

      {/*
        Evidence is offered for SAVED members only, off the server's rows — never off the form.
        The naive editor minted a browser-side uuid on "Add person" and rendered the evidence box
        immediately, so a citation could be filed against a report_team.id that was never
        inserted. `citations.field` is text with no foreign key, and the commit gate would have
        counted it.
      */}
      <div className="mt-4">
        <EvidenceRule help={bounds.fieldHelp.evidence} id={evidenceId} />
        {team.length === 0 ? (
          <p className="text-sm text-neutral-600">
            Save the team before attaching evidence — a citation can only name a person the database
            has.
          </p>
        ) : null}
        {team.map((person) => (
          <Citations
            citations={citations}
            describedBy={evidenceId}
            disabled={disabled}
            field={`${bounds.teamFieldPrefix}${person.id}`}
            key={person.id}
            label={`Evidence for ${person.name}`}
            onAdd={onAddCitation}
            onRemove={onRemoveCitation}
          />
        ))}
      </div>
    </SectionShell>
  )
}
