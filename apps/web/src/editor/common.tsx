import { type ReactNode, useRef, useState } from 'react'
import type {
  ApiError,
  Bounds,
  Citation,
  CitationBody,
  Fields,
  LiquidityBody,
  Scores,
} from '../lib/client.ts'
import { isMeasuredEmpty, type MeasuredForm, numberOf, textOf } from './fields.tsx'

export type Save<B> = (fields: Fields<B>) => Promise<ApiError | null>

/**
 * The refusal code for a write that LANDED and whose re-read failed. Callers treat it as saved --
 * the section stops being dirty, an evidence box empties -- because pressing again would store it
 * a second time.
 */
export const LANDED_UNREAD = 'REREAD_FAILED'

const landed = (refusal: ApiError | null): boolean =>
  refusal === null || refusal.code === LANDED_UNREAD

export interface SectionProps {
  bounds: Bounds
  citations: Citation[]
  disabled: boolean
  /** This section's last refusal. ReportEditor owns it: it is the one place that sees how a save
   *  ended, including the 409 that re-seeds every section at once. */
  error: ApiError | null
  onAddCitation: (input: Fields<CitationBody>) => Promise<ApiError | null>
  onRemoveCitation: (citationId: string) => Promise<ApiError | null>
  scores: Scores
  /** Moved by ReportEditor to re-seed this section from the database. */
  seedToken: number
}

/*
 * ONE SAVE BUTTON PER SECTION, sending that section's fields as one patch under one CAS bump.
 *
 * Ruled 2026-09-21. `casBumpVersion` bumps `reports.version` on every successful call, so the
 * naive per-field blur save fires many CAS writes: blur a score, click a citation's "add" before
 * the first response lands, and the second request carries a spent token and is refused 409 while
 * the screen still shows the value as entered.
 *
 * While the save is in flight the whole section is a disabled <fieldset>. Text typed into it
 * meanwhile would be replaced when the section re-seeds from the database a moment later, so the
 * section refuses the keystrokes rather than accepting them and then losing them.
 */
export function SectionShell({
  children,
  dirty,
  disabled,
  error,
  onSave,
  saving,
  title,
}: {
  children: ReactNode
  dirty: boolean
  disabled: boolean
  error: ApiError | null
  onSave: () => void
  saving: boolean
  title: string
}) {
  return (
    <section className="mt-8 border-t border-neutral-300 pt-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-medium">{title}</h2>
        <div className="flex items-center gap-3">
          {dirty ? <span className="text-xs text-amber-800">unsaved changes</span> : null}
          {/* Not `disabled` while saving: a browser blurs a focused control the moment it is
              disabled, so every Save sent keyboard focus to <body>. useSection ignores the press
              instead. */}
          <button
            aria-busy={saving}
            aria-label={`Save ${title}`}
            className="border border-neutral-500 px-3 py-1 text-sm disabled:opacity-50"
            disabled={disabled}
            onClick={onSave}
            type="button"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
      {/* Beside the Save button that produced it, not at the foot of a section that can run to
          six sub-scores and their evidence. */}
      {error === null ? null : (
        <p
          className="mt-2 border-l-4 border-red-700 bg-red-50 py-1 pl-2 text-sm text-red-900"
          role="alert"
        >
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}
      <fieldset className="mt-3 min-w-0" disabled={saving}>
        {children}
      </fieldset>
    </section>
  )
}

/**
 * A section's form, re-seeded from the database whenever ReportEditor moves `seedToken`.
 *
 * The re-seed adjusts state during render -- React's documented pattern for resetting state when
 * a prop changes -- rather than remounting the section through its `key`. The remount did reset
 * the boxes, but it also reset everything else below it: the URL and quote typed into an evidence
 * box but not yet added were silently emptied by the section's own successful Save, keyboard focus
 * fell to <body>, and a refusal set by the save that caused the remount landed on an instance
 * being thrown away. Only the form is replaced here; the evidence boxes keep what was typed.
 */
export function useSection<F, B>(
  seedToken: number,
  error: ApiError | null,
  seed: () => F,
  toBody: (form: F) => Fields<B>,
  save: Save<B>,
): {
  dirty: boolean
  error: ApiError | null
  form: F
  onSave: () => void
  saving: boolean
  update: (form: F) => void
} {
  const [form, setForm] = useState(seed)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)
  const [seededFrom, setSeededFrom] = useState(seedToken)
  // A ref, not `saving`: two presses dispatched before React re-renders both read `saving` as false.
  const inFlight = useRef(false)
  // The refusal the operator has since edited past. A new refusal is a new object, so it shows.
  const [dismissed, setDismissed] = useState<ApiError | null>(null)

  if (seededFrom !== seedToken) {
    setSeededFrom(seedToken)
    setForm(seed())
    setDirty(false)
  }

  const update = (next: F) => {
    setForm(next)
    setDirty(true)
    setDismissed(error)
  }

  const onSave = () => {
    if (inFlight.current) return
    inFlight.current = true
    setSaving(true)
    void save(toBody(form)).then((refusal) => {
      inFlight.current = false
      setSaving(false)
      if (landed(refusal)) setDirty(false)
    })
  }

  return { dirty, error: error === dismissed ? null : error, form, onSave, saving, update }
}

const STATUS_CLASS: Record<string, string> = {
  unverified: 'bg-neutral-200 text-neutral-800',
  verified: 'bg-green-100 text-green-900',
  near_miss: 'bg-amber-100 text-amber-900',
  failed: 'bg-red-100 text-red-900',
  unverifiable_js: 'bg-amber-100 text-amber-900',
  waived: 'bg-purple-100 text-purple-900',
}

/**
 * The evidence attached to one field.
 *
 * `field` is a value from the API's CITABLE_FIELDS, never a string this tier computes. The naive
 * version derived it with a regex that produced `liquidity_depth2pct_usd` for a column named
 * `liquidity_depth_2pct_usd`, and since the same wrong string was used to add AND to filter, the
 * UI looked entirely correct while the commit gate would have counted zero.
 *
 * The boxes are cleared only on success. The quote is the one thing in this product that must be
 * transcribed exactly, and an unconditional clear meant a refused add silently ate it. For the
 * same reason nothing above this component remounts it: useSection re-seeds its form in place.
 */
export function Citations({
  citations,
  disabled,
  field,
  label,
  onAdd,
  onRemove,
}: {
  citations: Citation[]
  disabled: boolean
  field: string
  label: string
  onAdd: (input: Fields<CitationBody>) => Promise<ApiError | null>
  onRemove: (citationId: string) => Promise<ApiError | null>
}) {
  const [url, setUrl] = useState('')
  const [quote, setQuote] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  // add/remove stay enabled while busy -- disabling the pressed button blurs it -- so this ref,
  // not `busy`, is what refuses a second press.
  const inFlight = useRef(false)
  const mine = citations.filter((citation) => citation.field === field)

  const act = (write: () => Promise<ApiError | null>, onLanded: () => void) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    void write().then((refusal) => {
      inFlight.current = false
      setBusy(false)
      setError(refusal)
      if (landed(refusal)) onLanded()
    })
  }

  const add = () =>
    act(
      () => onAdd({ field, url, quote }),
      () => {
        setUrl('')
        setQuote('')
      },
    )

  return (
    <div className="my-2 ml-4 border-l border-neutral-300 pl-3 text-sm">
      <p className="text-neutral-600">{label}</p>
      <ul>
        {mine.map((citation, index) => (
          <li className="flex flex-wrap items-baseline gap-2 py-0.5" key={citation.id}>
            <span
              className={`rounded px-1 text-xs ${STATUS_CLASS[citation.status] ?? 'bg-neutral-200'}`}
            >
              {citation.status}
            </span>
            <a className="underline" href={citation.url} rel="noreferrer" target="_blank">
              {citation.url}
            </a>
            <span className="text-neutral-600">“{citation.quote}”</span>
            <button
              aria-busy={busy}
              aria-label={`${label}: remove evidence ${String(index + 1)}, ${citation.url}`}
              className="text-red-800 underline disabled:opacity-50"
              disabled={disabled}
              onClick={() =>
                act(
                  () => onRemove(citation.id),
                  () => undefined,
                )
              }
              type="button"
            >
              remove
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-1 flex flex-wrap gap-2">
        <input
          aria-label={`${label}: source URL`}
          className="w-72 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
          disabled={disabled || busy}
          onChange={(event) => {
            setUrl(event.target.value)
            setError(null)
          }}
          placeholder="https://"
          value={url}
        />
        <input
          aria-label={`${label}: exact quote`}
          className="w-96 border border-neutral-400 px-2 py-1 disabled:bg-neutral-100"
          disabled={disabled || busy}
          onChange={(event) => {
            setQuote(event.target.value)
            setError(null)
          }}
          placeholder="the exact quote to search the page for"
          value={quote}
        />
        <button
          aria-busy={busy}
          aria-label={`${label}: add`}
          className="border border-neutral-500 px-2 disabled:opacity-50"
          disabled={disabled}
          onClick={add}
          type="button"
        >
          add
        </button>
      </div>
      {error === null ? null : (
        <p className="mt-1 text-red-900" role="alert">
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Measured figures, shared by liquidity and accrual
// ---------------------------------------------------------------------------

export function seedMeasured(
  value: number | null,
  source: string | null,
  url: string | null,
  label: string | null,
  measuredAt: string | null,
): MeasuredForm {
  return {
    value: numberOf(value),
    source: textOf(source),
    url: textOf(url),
    label: textOf(label),
    measuredAt: textOf(measuredAt),
  }
}

export type MeasuredWire = NonNullable<Fields<LiquidityBody>['depth']>

export function toMeasured(form: MeasuredForm): MeasuredWire | null {
  if (isMeasuredEmpty(form)) return null
  return {
    value: form.value,
    source: form.source,
    url: form.url,
    // The server's enum refuses anything else by name; the browser does not pre-judge it.
    label: form.label as MeasuredWire['label'],
    measuredAt: form.measuredAt,
  }
}
