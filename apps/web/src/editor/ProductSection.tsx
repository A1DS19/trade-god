import { useId } from 'react'
import type { ProductBody } from '../lib/client.ts'
import {
  Citations,
  EvidenceRule,
  type Save,
  type SectionProps,
  SectionShell,
  useSection,
} from './common.tsx'
import { blankToNull, numberOf, ProseField, textOf, WholeNumberField } from './fields.tsx'

interface ProductForm {
  overviewSentence: string
  productEase: string
  productHairFire: string
  productExclusivity: string
  productEaseRationale: string
  productHairFireRationale: string
  productExclusivityRationale: string
}

export function ProductSection({
  bounds,
  citations,
  disabled,
  error,
  onAddCitation,
  onRemoveCitation,
  onSave,
  scores,
  seedToken,
}: SectionProps & { onSave: Save<ProductBody> }) {
  const section = useSection<ProductForm, ProductBody>(
    seedToken,
    error,
    () => ({
      overviewSentence: textOf(scores.overviewSentence),
      productEase: numberOf(scores.productEase),
      productHairFire: numberOf(scores.productHairFire),
      productExclusivity: numberOf(scores.productExclusivity),
      productEaseRationale: textOf(scores.productEaseRationale),
      productHairFireRationale: textOf(scores.productHairFireRationale),
      productExclusivityRationale: textOf(scores.productExclusivityRationale),
    }),
    (form) => ({
      overviewSentence: blankToNull(form.overviewSentence),
      productEase: blankToNull(form.productEase),
      productHairFire: blankToNull(form.productHairFire),
      productExclusivity: blankToNull(form.productExclusivity),
      productEaseRationale: blankToNull(form.productEaseRationale),
      productHairFireRationale: blankToNull(form.productHairFireRationale),
      productExclusivityRationale: blankToNull(form.productExclusivityRationale),
    }),
    onSave,
  )
  const { form, update } = section
  const evidenceId = useId()

  return (
    <SectionShell
      dirty={section.dirty}
      disabled={disabled}
      error={section.error}
      onSave={section.onSave}
      saving={section.saving}
      title="1 · Product gate"
    >
      <p className="mb-3 text-sm text-neutral-600">
        Three sub-scores, 0–{bounds.productSubScoreMax} each. The frozen gate passes at{' '}
        {bounds.productGateThreshold}+, decided inside the commit transaction (build-order step 6) —
        nothing on this page adds them up.
      </p>
      <EvidenceRule help={bounds.fieldHelp.evidence} id={evidenceId} />
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.overviewSentence}
        label="One-sentence overview"
        onChange={(value) => update({ ...form, overviewSentence: value })}
        value={form.overviewSentence}
      />
      <WholeNumberField
        disabled={disabled}
        help={bounds.fieldHelp.productEase}
        label="Ease of Use"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productEase: value })}
        value={form.productEase}
      />
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.productRationale}
        label="Ease of Use rationale"
        onChange={(value) => update({ ...form, productEaseRationale: value })}
        value={form.productEaseRationale}
      />
      <Citations
        citations={citations}
        describedBy={evidenceId}
        disabled={disabled}
        field={bounds.citableFields.productEase}
        label="Evidence for Ease of Use"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
      <WholeNumberField
        disabled={disabled}
        help={bounds.fieldHelp.productHairFire}
        label="Hair-on-Fire (gate field)"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productHairFire: value })}
        value={form.productHairFire}
      />
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.productRationale}
        label="Hair-on-Fire rationale"
        onChange={(value) => update({ ...form, productHairFireRationale: value })}
        value={form.productHairFireRationale}
      />
      <Citations
        citations={citations}
        describedBy={evidenceId}
        disabled={disabled}
        field={bounds.citableFields.productHairFire}
        label="Evidence for Hair-on-Fire"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
      <WholeNumberField
        disabled={disabled}
        help={bounds.fieldHelp.productExclusivity}
        label="Exclusivity Factor"
        max={bounds.productSubScoreMax}
        onChange={(value) => update({ ...form, productExclusivity: value })}
        value={form.productExclusivity}
      />
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.productRationale}
        label="Exclusivity Factor rationale"
        onChange={(value) => update({ ...form, productExclusivityRationale: value })}
        value={form.productExclusivityRationale}
      />
      <Citations
        citations={citations}
        describedBy={evidenceId}
        disabled={disabled}
        field={bounds.citableFields.productExclusivity}
        label="Evidence for Exclusivity"
        onAdd={onAddCitation}
        onRemove={onRemoveCitation}
      />
    </SectionShell>
  )
}
