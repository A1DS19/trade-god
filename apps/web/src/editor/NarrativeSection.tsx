import type { NarrativeBody } from '../lib/client.ts'
import { Citations, type Save, type SectionProps, SectionShell, useSection } from './common.tsx'
import { blankToNull, numberOf, ProseField, textOf, WholeNumberField } from './fields.tsx'

const NARRATIVE_ROWS = [
  ['narrativeMaturity', 'narrativeMaturityRationale', 'maturity', 'Narrative Maturity'],
  [
    'narrativeSmartMoney',
    'narrativeSmartMoneyRationale',
    'smartMoney',
    'Smart Money Compatibility',
  ],
  ['narrativeHairFire', 'narrativeHairFireRationale', 'hairFire', 'Hair-on-Fire Innovation'],
  [
    'narrativeCommunication',
    'narrativeCommunicationRationale',
    'communication',
    'Narrative Communication',
  ],
  ['narrativeLineage', 'narrativeLineageRationale', 'lineage', 'Narrative Lineage'],
  ['narrativeMutation', 'narrativeMutationRationale', 'mutation', 'Narrative Mutation'],
] as const

type NarrativeForm = Record<(typeof NARRATIVE_ROWS)[number][0 | 1], string>

export function NarrativeSection({
  bounds,
  citations,
  disabled,
  error,
  onAddCitation,
  onRemoveCitation,
  onSave,
  scores,
  seedToken,
}: SectionProps & { onSave: Save<NarrativeBody> }) {
  const section = useSection<NarrativeForm, NarrativeBody>(
    seedToken,
    () => ({
      narrativeMaturity: numberOf(scores.narrativeMaturity),
      narrativeSmartMoney: numberOf(scores.narrativeSmartMoney),
      narrativeHairFire: numberOf(scores.narrativeHairFire),
      narrativeCommunication: numberOf(scores.narrativeCommunication),
      narrativeLineage: numberOf(scores.narrativeLineage),
      narrativeMutation: numberOf(scores.narrativeMutation),
      narrativeMaturityRationale: textOf(scores.narrativeMaturityRationale),
      narrativeSmartMoneyRationale: textOf(scores.narrativeSmartMoneyRationale),
      narrativeHairFireRationale: textOf(scores.narrativeHairFireRationale),
      narrativeCommunicationRationale: textOf(scores.narrativeCommunicationRationale),
      narrativeLineageRationale: textOf(scores.narrativeLineageRationale),
      narrativeMutationRationale: textOf(scores.narrativeMutationRationale),
    }),
    (form) => ({
      narrativeMaturity: blankToNull(form.narrativeMaturity),
      narrativeSmartMoney: blankToNull(form.narrativeSmartMoney),
      narrativeHairFire: blankToNull(form.narrativeHairFire),
      narrativeCommunication: blankToNull(form.narrativeCommunication),
      narrativeLineage: blankToNull(form.narrativeLineage),
      narrativeMutation: blankToNull(form.narrativeMutation),
      narrativeMaturityRationale: blankToNull(form.narrativeMaturityRationale),
      narrativeSmartMoneyRationale: blankToNull(form.narrativeSmartMoneyRationale),
      narrativeHairFireRationale: blankToNull(form.narrativeHairFireRationale),
      narrativeCommunicationRationale: blankToNull(form.narrativeCommunicationRationale),
      narrativeLineageRationale: blankToNull(form.narrativeLineageRationale),
      narrativeMutationRationale: blankToNull(form.narrativeMutationRationale),
    }),
    onSave,
  )
  const { form, update } = section

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={error}
      onSave={section.onSave}
      saving={section.saving}
      title="3 · Narrative"
    >
      <p className="mb-3 text-sm text-neutral-600">
        Six sub-scores out of {bounds.narrativeTotalMax}, each with a 1–2 sentence rationale and at
        least one citation. The total is written by the commit route from narrativeTotal(); it is
        not computed here.
      </p>
      {NARRATIVE_ROWS.map(([scoreKey, rationaleKey, maxKey, label]) => (
        <div key={scoreKey}>
          <WholeNumberField
            disabled={disabled}
            label={label}
            max={bounds.narrativeMax[maxKey]}
            onChange={(value) => update({ ...form, [scoreKey]: value })}
            value={form[scoreKey]}
          />
          <ProseField
            disabled={disabled}
            label={`${label} rationale`}
            onChange={(value) => update({ ...form, [rationaleKey]: value })}
            value={form[rationaleKey]}
          />
          <Citations
            citations={citations}
            disabled={disabled}
            field={bounds.citableFields[scoreKey]}
            label={`Evidence for ${label}`}
            onAdd={onAddCitation}
            onRemove={onRemoveCitation}
          />
        </div>
      ))}
    </SectionShell>
  )
}
