import type { RiskBody } from '../lib/client.ts'
import { type Save, type SectionProps, SectionShell, useSection } from './common.tsx'
import { blankToNull, ProseField, textOf } from './fields.tsx'

export function RiskSection({
  bounds,
  disabled,
  error,
  onSave,
  scores,
  seedToken,
}: SectionProps & { onSave: Save<RiskBody> }) {
  const section = useSection<{ riskNotes: string }, RiskBody>(
    seedToken,
    error,
    () => ({ riskNotes: textOf(scores.riskNotes) }),
    (form) => ({ riskNotes: blankToNull(form.riskNotes) }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="6 · Risk notes"
    >
      <p className="mb-3 text-sm text-neutral-600">
        framework/06 files risk notes under "extras", but the commit gate's completeness check makes
        them mandatory on a report whose gate passed. That deviation is deliberate; do not "fix" it
        back to optional.
      </p>
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.riskNotes}
        label="Risk notes"
        onChange={(riskNotes) => update({ ...form, riskNotes })}
        value={form.riskNotes}
      />
    </SectionShell>
  )
}
