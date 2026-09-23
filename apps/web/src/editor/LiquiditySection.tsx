import type { Fields, LiquidityBody } from '../lib/client.ts'
import {
  measuredHelp,
  type Save,
  type SectionProps,
  SectionShell,
  seedMeasured,
  toMeasured,
  useSection,
} from './common.tsx'
import {
  blankToNull,
  CheckField,
  ChoiceField,
  MeasuredFields,
  type MeasuredForm,
  ProseField,
  textOf,
} from './fields.tsx'

interface LiquidityForm {
  depth: MeasuredForm
  topPool: MeasuredForm
  liquidityNoDexPool: boolean
  liquidityTier: string
  liquidityJustification: string
}

export function LiquiditySection({
  bounds,
  disabled,
  error,
  onSave,
  scores,
  seedToken,
}: SectionProps & { onSave: Save<LiquidityBody> }) {
  const section = useSection<LiquidityForm, LiquidityBody>(
    seedToken,
    error,
    () => ({
      depth: seedMeasured(
        scores.liquidityDepth2pctUsd,
        scores.liquidityDepthSource,
        scores.liquidityDepthUrl,
        scores.liquidityDepthLabel,
        scores.liquidityDepthMeasuredAt,
      ),
      topPool: seedMeasured(
        scores.liquidityTopPoolTvlUsd,
        scores.liquidityTopPoolSource,
        scores.liquidityTopPoolUrl,
        scores.liquidityTopPoolLabel,
        scores.liquidityTopPoolMeasuredAt,
      ),
      liquidityNoDexPool: scores.liquidityNoDexPool,
      liquidityTier: textOf(scores.liquidityTier),
      liquidityJustification: textOf(scores.liquidityJustification),
    }),
    (form) => ({
      depth: toMeasured(form.depth),
      topPool: toMeasured(form.topPool),
      liquidityNoDexPool: form.liquidityNoDexPool,
      liquidityTier: blankToNull(form.liquidityTier) as Fields<LiquidityBody>['liquidityTier'],
      liquidityJustification: blankToNull(form.liquidityJustification),
    }),
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
      title="2 · Liquidity"
    >
      <p className="mb-3 text-sm text-neutral-600">
        There is no formula here — the tool measures and the human tiers. Saving this section
        re-stamps the tier's timestamp, so a tier can never end up older than the numbers printed
        beside it.
      </p>
      <MeasuredFields
        disabled={disabled}
        form={form.depth}
        help={bounds.fieldHelp.liquidityDepth2pctUsd}
        label="±2% depth across CEXs"
        onChange={(depth) => update({ ...form, depth })}
        parts={measuredHelp(bounds)}
        provenanceLabels={bounds.provenanceLabels}
      />
      <MeasuredFields
        disabled={disabled}
        form={form.topPool}
        help={bounds.fieldHelp.liquidityTopPoolTvlUsd}
        label="Largest DEX pool TVL"
        onChange={(topPool) => update({ ...form, topPool })}
        parts={measuredHelp(bounds)}
        provenanceLabels={bounds.provenanceLabels}
      />
      <CheckField
        checked={form.liquidityNoDexPool}
        disabled={disabled}
        help={bounds.fieldHelp.liquidityNoDexPool}
        label="No DEX pool exists (different from 'not measured') — leave the pool figure's five boxes blank"
        onChange={(liquidityNoDexPool) => update({ ...form, liquidityNoDexPool })}
      />
      <ChoiceField
        disabled={disabled}
        help={bounds.fieldHelp.liquidityTier}
        label="Liquidity tier"
        onChange={(liquidityTier) => update({ ...form, liquidityTier })}
        options={bounds.liquidityTiers}
        value={form.liquidityTier}
      />
      <ProseField
        disabled={disabled}
        help={bounds.fieldHelp.liquidityJustification}
        label="Why that tier"
        onChange={(liquidityJustification) => update({ ...form, liquidityJustification })}
        value={form.liquidityJustification}
      />
    </SectionShell>
  )
}
