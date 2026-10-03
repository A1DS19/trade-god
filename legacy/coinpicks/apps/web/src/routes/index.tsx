import { createFileRoute, Link, useNavigate } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { type ApiError, type CoinRows, client, readError } from '../lib/client.ts'

/*
 * NO `loader`, and no `beforeLoad`.
 *
 * The list is fetched in an effect, in the BROWSER. A loader runs on the server first, and the
 * server half of this tier is the one place that must not start reaching outwards: it holds no
 * key and calls no third party, and `boundary.test.ts` is written to keep it that way. Step 4 has
 * no SEO and no first-paint data requirement, so a loader would buy nothing and cost the rule.
 */
export const Route = createFileRoute('/')({ component: CoinList })

const EMPTY_FORM = {
  symbol: '',
  name: '',
  chain: '',
  contractAddress: '',
  coingeckoId: '',
  addressSources: '',
}

function CoinList() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<CoinRows | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    const response = await client.coins.$get()
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const body = await response.json()
    setRows(body.rows)
    setError(null)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const startReport = async (coinId: string) => {
    setBusy(true)
    const response = await client.reports.$post({ json: { coinId } })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    const body = await response.json()
    await navigate({ params: { reportId: body.report.id }, to: '/reports/$reportId' })
  }

  const createCoin = async () => {
    setBusy(true)
    const response = await client.coins.$post({
      json: {
        symbol: form.symbol,
        name: form.name,
        chain: form.chain,
        contractAddress: form.contractAddress.trim() === '' ? null : form.contractAddress,
        coingeckoId: form.coingeckoId.trim() === '' ? null : form.coingeckoId,
        addressSources: form.addressSources
          .split(/[\s,]+/)
          .map((source) => source.trim())
          .filter((source) => source !== ''),
      },
    })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    setForm(EMPTY_FORM)
    await load()
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="text-2xl font-medium">CoinPicks</h1>
      {error === null ? null : (
        <p className="mt-3 border-l-4 border-red-700 bg-red-50 py-1 pl-2 text-sm text-red-900">
          <strong>{error.code}</strong> — {error.message}
        </p>
      )}

      <table className="mt-6 w-full text-left text-sm">
        <thead>
          <tr className="border-b border-neutral-400">
            <th className="py-1">Coin</th>
            <th>Chain</th>
            <th>Report</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(rows ?? []).map((row) => (
            <tr
              className="border-b border-neutral-200"
              key={`${row.coin.id}:${row.reportId ?? ''}`}
            >
              <td className="py-1">
                {row.coin.symbol} — {row.coin.name}
              </td>
              <td>{row.coin.chain}</td>
              <td>
                {row.reportId === null ? (
                  <span className="text-neutral-500">none</span>
                ) : (
                  <Link
                    className="underline"
                    params={{ reportId: row.reportId }}
                    to="/reports/$reportId"
                  >
                    open
                  </Link>
                )}
              </td>
              <td>{row.reportStatus ?? '—'}</td>
              <td>
                <button
                  className="border border-neutral-500 px-2 disabled:opacity-50"
                  disabled={busy}
                  onClick={() => void startReport(row.coin.id)}
                  type="button"
                >
                  new draft
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="mt-10 border-t border-neutral-300 pt-4">
        <h2 className="text-lg font-medium">Add a coin</h2>
        <p className="mt-1 text-sm text-neutral-600">
          A contract address needs at least two independent sources — the database refuses one.
          Leave the address blank for a native asset.
        </p>
        <div className="mt-3 grid max-w-2xl grid-cols-2 gap-2 text-sm">
          {(
            [
              ['symbol', 'Ticker'],
              ['name', 'Project name'],
              ['chain', 'Chain'],
              ['contractAddress', 'Contract address'],
              ['coingeckoId', 'CoinGecko id'],
              ['addressSources', 'Address source URLs'],
            ] as const
          ).map(([key, label]) => (
            <label className="flex flex-col gap-1" key={key}>
              <span className="text-neutral-700">{label}</span>
              <input
                className="border border-neutral-400 px-2 py-1"
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                value={form[key]}
              />
            </label>
          ))}
        </div>
        <button
          className="mt-3 border border-neutral-500 px-3 py-1 text-sm disabled:opacity-50"
          disabled={busy}
          onClick={() => void createCoin()}
          type="button"
        >
          Add coin
        </button>
      </section>
    </main>
  )
}
