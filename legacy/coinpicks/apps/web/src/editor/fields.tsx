import { type ReactNode, useId } from 'react'

/*
 * THE BROWSER NEVER CALLS Number().
 *
 * Every numeric box is a text input whose string goes on the wire exactly as typed. `Number`
 * turns 'seven', '1,000' and '7%' into NaN, `JSON.stringify` turns NaN into `null`, and `null` is
 * this API's "clear this field" — so a typo used to save cleanly, bump the CAS version, and empty
 * the column while the box still showed the typo. The server's zod owns the parse and answers a
 * bad string with a named 422.
 *
 * A blank box is the ONLY thing that becomes `null`, and that is an edit the operator can see
 * themselves making.
 */

export const blankToNull = (text: string): string | null => (text.trim() === '' ? null : text)

export const textOf = (value: string | null): string => value ?? ''

/**
 * A stored figure, seeded into its box.
 *
 * `String` is deliberate, and this is deliberately NOT an expansion of exponential notation.
 * Below 1e-6 and at or above 1e21 `String` switches to exponent form — `String(1e-7)` is
 * `'1e-7'` — which the API's digit regex refuses, so a figure that small has to be typed out in
 * full before that section will save again. That is loud, named and recoverable. Both cheaper
 * repairs are worse and were measured here: expanding the exponent in the browser needs
 * `Number(parts[3])`, which `boundary.test.ts` refuses by name, and `toFixed(20)` SILENTLY
 * rewrites 1.5e-20 as 0.00000000000000000002. The real fix is for the read path to serve
 * figures as text; it is written down for step 5 rather than half-done here.
 */
export const numberOf = (value: number | null): string => (value === null ? '' : String(value))

/**
 * A field's description, in the shape the API serves in `bounds.fieldHelp`. Declared here rather
 * than imported because apps/web reaches apps/api only through `import type { AppType }`; the
 * served entries are passed straight into it, so a change to their shape is a compile error.
 */
export interface Help {
  text: readonly string[]
  source: string
  details?: { summary: string; lines: readonly string[] }
}

/** 'framework/02-product-exclusivity.md' -> 'framework/02' */
const lessonTag = (source: string): string => source.replace(/^(framework\/\d+).*$/, '$1')

/**
 * A field's description, under its label.
 *
 * A lesson quote is shown in quotation marks beside the lesson it comes from -- field-help.test.ts
 * holds every such line to that file verbatim -- and help this editor wrote is shown plain, so the
 * two are never mistaken for each other. A scale, the rungs or a how-to fold under a native
 * <details>. `id` is on the one-line text only: that is what `aria-describedby` reads out.
 */
export function FieldHelp({ help, id }: { help: Help; id: string }) {
  const quoted = help.source !== 'editor'
  const text = help.text.join(' ')
  return (
    <div className="text-xs text-neutral-500">
      <p id={id}>
        {quoted ? `“${text}”` : text}
        {quoted ? <span className="ml-1 text-neutral-400">{lessonTag(help.source)}</span> : null}
      </p>
      {help.details === undefined ? null : (
        <details>
          <summary className="cursor-pointer">
            {quoted ? `${help.details.summary} · ${lessonTag(help.source)}` : help.details.summary}
          </summary>
          <ul className="ml-4 list-disc">
            {help.details.lines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

/** A field's description and the id its control points at, or neither. */
export function useHelp(help: Help | undefined): {
  describedBy: string | undefined
  note: ReactNode
} {
  const id = useId()
  if (help === undefined) return { describedBy: undefined, note: null }
  return { describedBy: id, note: <FieldHelp help={help} id={id} /> }
}

/** A labelled row. A <div> with an aria-label on the control, not a <label> wrapping
 *  {children}: biome's noLabelWithoutControl cannot see through children and fails the build. */
export function Row({
  children,
  label,
  note,
}: {
  children: ReactNode
  label: string
  note: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 py-1 text-sm">
      <span className="w-72 shrink-0 text-neutral-700">{label}</span>
      {children}
      {note === null ? null : <div className="basis-full pt-0.5">{note}</div>}
    </div>
  )
}

export function TextField({
  disabled,
  help,
  label,
  onChange,
  placeholder,
  value,
  width = 'w-96',
}: {
  disabled: boolean
  help?: Help
  label: string
  onChange: (value: string) => void
  placeholder?: string
  value: string
  width?: string
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <Row label={label} note={note}>
      <input
        aria-describedby={describedBy}
        aria-label={label}
        className={`${width} border border-neutral-400 px-2 py-1 disabled:bg-neutral-100`}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </Row>
  )
}

/**
 * A whole-number sub-score. `type="text"`, not `type="number"`: a spinner cannot express 7.5, and
 * 7.5 is a value the API must be given the chance to REJECT rather than one the UI hides. The
 * maximum in the caption arrives in the report payload; no rubric number is written here.
 */
export function WholeNumberField({
  disabled,
  help,
  label,
  max,
  onChange,
  value,
}: {
  disabled: boolean
  help?: Help
  label: string
  max: number
  onChange: (value: string) => void
  value: string
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <Row label={label} note={note}>
      <input
        aria-describedby={describedBy}
        aria-label={label}
        className="w-20 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        inputMode="numeric"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
      <span className="text-xs text-neutral-500">whole number, 0 to {max}</span>
    </Row>
  )
}

export function AmountField({
  caption,
  disabled,
  help,
  label,
  onChange,
  value,
}: {
  caption: string
  disabled: boolean
  help?: Help
  label: string
  onChange: (value: string) => void
  value: string
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <Row label={label} note={note}>
      <input
        aria-describedby={describedBy}
        aria-label={label}
        className="w-48 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        inputMode="decimal"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
      <span className="text-xs text-neutral-500">{caption}</span>
    </Row>
  )
}

export function ProseField({
  disabled,
  help,
  label,
  onChange,
  value,
}: {
  disabled: boolean
  help?: Help
  label: string
  onChange: (value: string) => void
  value: string
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <div className="py-1 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-neutral-700">{label}</span>
        <textarea
          aria-describedby={describedBy}
          className="border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
          rows={2}
          value={value}
        />
      </label>
      {note}
    </div>
  )
}

export function ChoiceField({
  disabled,
  help,
  label,
  onChange,
  options,
  value,
}: {
  disabled: boolean
  help?: Help
  label: string
  onChange: (value: string) => void
  options: readonly string[]
  value: string
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <Row label={label} note={note}>
      <select
        aria-describedby={describedBy}
        aria-label={label}
        className="border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        <option value="">—</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </Row>
  )
}

export function CheckField({
  checked,
  disabled,
  help,
  label,
  onChange,
}: {
  checked: boolean
  disabled: boolean
  help?: Help
  label: string
  onChange: (checked: boolean) => void
}) {
  const { describedBy, note } = useHelp(help)
  return (
    <div className="py-1 text-sm">
      <label className="flex items-center gap-2">
        <input
          aria-describedby={describedBy}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          type="checkbox"
        />
        <span>{label}</span>
      </label>
      {note}
    </div>
  )
}

/** The five boxes of one measured figure. They move together or not at all. */
export interface MeasuredForm {
  value: string
  source: string
  url: string
  label: string
  measuredAt: string
}

export const isMeasuredEmpty = (form: MeasuredForm): boolean =>
  Object.values(form).every((entry) => entry.trim() === '')

/**
 * All five, or none.
 *
 * `rs_depth_provenance_complete` and its two siblings are biconditionals, so the wire carries one
 * object or `null` — five independent nullable fields could express a state the database refuses.
 * The naive version had a "Save figure with its provenance" button that called
 * `onSave({ value: Number(figure), ... })` with no blank guard, and `Number('')` is 0: a blank
 * figure box became "+/-2% depth = $0, verified, DefiLlama, 14:32", immutable after commit.
 * Here a blank figure is the empty string, and the server's `money()` refuses it by name.
 */
export function MeasuredFields({
  disabled,
  form,
  help,
  label,
  onChange,
  parts,
  provenanceLabels,
}: {
  disabled: boolean
  form: MeasuredForm
  /** What this figure is. */
  help: Help
  label: string
  onChange: (form: MeasuredForm) => void
  /** What each of the five boxes is -- the same for every measured figure. */
  parts: Record<keyof MeasuredForm, Help>
  provenanceLabels: readonly string[]
}) {
  const { describedBy, note } = useHelp(help)
  const set = (key: keyof MeasuredForm) => (next: string) => onChange({ ...form, [key]: next })
  return (
    <fieldset aria-describedby={describedBy} className="my-2 border border-neutral-300 p-3">
      <legend className="px-1 text-sm text-neutral-700">{label}</legend>
      <div className="mb-2">{note}</div>
      <AmountField
        caption="plain digits, like 1250000.5 — no commas"
        disabled={disabled}
        help={parts.value}
        label="Figure (USD)"
        onChange={set('value')}
        value={form.value}
      />
      <TextField
        disabled={disabled}
        help={parts.source}
        label="Source"
        onChange={set('source')}
        placeholder="CoinGecko, DefiLlama, ..."
        value={form.source}
      />
      <TextField
        disabled={disabled}
        help={parts.url}
        label="Source URL"
        onChange={set('url')}
        placeholder="https://"
        value={form.url}
      />
      <ChoiceField
        disabled={disabled}
        help={parts.label}
        label="Provenance"
        onChange={set('label')}
        options={provenanceLabels}
        value={form.label}
      />
      <TextField
        disabled={disabled}
        help={parts.measuredAt}
        label="Measured at"
        onChange={set('measuredAt')}
        placeholder="2026-09-21T14:32:00+02:00"
        value={form.measuredAt}
        width="w-72"
      />
      <p className="mt-1 text-xs text-neutral-600">
        All five, or leave all five blank — the database refuses a figure without its provenance.
      </p>
    </fieldset>
  )
}
