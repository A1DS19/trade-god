import type { ReactNode } from 'react'

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

/** A labelled row. A <div> with an aria-label on the control, not a <label> wrapping
 *  {children}: biome's noLabelWithoutControl cannot see through children and fails the build. */
export function Row({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-3 py-1 text-sm">
      <span className="w-72 shrink-0 text-neutral-700">{label}</span>
      {children}
    </div>
  )
}

export function TextField({
  disabled,
  label,
  onChange,
  placeholder,
  value,
  width = 'w-96',
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  placeholder?: string
  value: string
  width?: string
}) {
  return (
    <Row label={label}>
      <input
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
  label,
  max,
  onChange,
  value,
}: {
  disabled: boolean
  label: string
  max: number
  onChange: (value: string) => void
  value: string
}) {
  return (
    <Row label={label}>
      <input
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
  label,
  onChange,
  value,
}: {
  caption: string
  disabled: boolean
  label: string
  onChange: (value: string) => void
  value: string
}) {
  return (
    <Row label={label}>
      <input
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
  label,
  onChange,
  value,
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  value: string
}) {
  return (
    <label className="flex flex-col gap-1 py-1 text-sm">
      <span className="text-neutral-700">{label}</span>
      <textarea
        className="border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        rows={2}
        value={value}
      />
    </label>
  )
}

export function ChoiceField({
  disabled,
  label,
  onChange,
  options,
  value,
}: {
  disabled: boolean
  label: string
  onChange: (value: string) => void
  options: readonly string[]
  value: string
}) {
  return (
    <Row label={label}>
      <select
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
  label,
  onChange,
}: {
  checked: boolean
  disabled: boolean
  label: string
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 py-1 text-sm">
      <input
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
      <span>{label}</span>
    </label>
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
  floor,
  form,
  label,
  onChange,
  provenanceLabels,
}: {
  disabled: boolean
  /** The earliest measured-at the API accepts, served in `bounds`. */
  floor: string
  form: MeasuredForm
  label: string
  onChange: (form: MeasuredForm) => void
  provenanceLabels: readonly string[]
}) {
  const set = (key: keyof MeasuredForm) => (next: string) => onChange({ ...form, [key]: next })
  return (
    <fieldset className="my-2 border border-neutral-300 p-3">
      <legend className="px-1 text-sm text-neutral-700">{label}</legend>
      <AmountField
        caption="plain digits, like 1250000.5 — no commas"
        disabled={disabled}
        label="Figure (USD)"
        onChange={set('value')}
        value={form.value}
      />
      <TextField
        disabled={disabled}
        label="Source"
        onChange={set('source')}
        placeholder="CoinGecko, DefiLlama, ..."
        value={form.source}
      />
      <TextField
        disabled={disabled}
        label="Source URL"
        onChange={set('url')}
        placeholder="https://"
        value={form.url}
      />
      <ChoiceField
        disabled={disabled}
        label="Provenance"
        onChange={set('label')}
        options={provenanceLabels}
        value={form.label}
      />
      <TextField
        disabled={disabled}
        label="Measured at"
        onChange={set('measuredAt')}
        placeholder="2026-09-21T14:32:00+02:00"
        value={form.measuredAt}
        width="w-72"
      />
      <p className="mt-1 text-xs text-neutral-600">
        All five, or leave all five blank — the database refuses a figure without its provenance.
        Measured-at is ISO 8601 with seconds and an offset, like 2026-09-21T14:32:00+02:00 or
        2026-09-21T12:32:00Z; it cannot be in the future or before {floor.slice(0, 10)}. After a
        save it is shown back in UTC — the same instant.
      </p>
    </fieldset>
  )
}
