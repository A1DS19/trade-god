import type { Blocker } from '../lib/client.ts'

const PILL: Record<Blocker['state'], string> = {
  clear: 'bg-green-100 text-green-900',
  blocking: 'bg-red-100 text-red-900',
  unknown: 'bg-neutral-200 text-neutral-700',
}

/**
 * What a report that PASSES the product gate still needs.
 *
 * Every row comes from the API's GATE_REQUIREMENTS — the same array that generates the
 * gate-completeness CHECK — so a conjunct cannot exist in the database and be missing here.
 * (The constraint is not named here: dist/server keeps /** comments, and its name's prefix is
 * one of bundle.test.ts's needles.)
 *
 * Three things this deliberately does NOT do:
 *  - it does not decide whether this report passes the gate. That is productGate(), evaluated
 *    once, inside the commit transaction.
 *  - it does not render a check written by the commit route as clear. Those rows say
 *    "not implemented", in grey, forever until step 6 writes them.
 *  - it never prints the word "Nothing." The empty state names what it means instead. A list
 *    that has nothing to say and says "Nothing." is indistinguishable from a list that forgot.
 */
export function Blockers({ blockers }: { blockers: Blocker[] }) {
  const outstanding = blockers.filter((blocker) => blocker.state !== 'clear')
  return (
    <section className="mt-10 border-t-2 border-neutral-400 pt-4">
      <h2 className="text-lg font-medium">What a passed report still needs</h2>
      <p className="mt-1 text-sm text-neutral-600">
        {blockers.filter((blocker) => blocker.state === 'clear').length} of {blockers.length}{' '}
        requirements are met. Whether this report passes the product gate is decided by the frozen
        gate inside the commit transaction, which is build-order step 6 and does not exist yet. This
        list is the database's completeness check only: team size, the single founder and every
        citation are the commit gate's to check, so a report can clear all of it with no team and no
        evidence.
      </p>
      {outstanding.length === 0 ? (
        <p className="mt-3 text-sm">
          Every requirement this editor can evaluate is met. Nothing here says the report is
          commitable — the commit gate has not been written.
        </p>
      ) : (
        <ul className="mt-3 space-y-1 text-sm">
          {outstanding.map((blocker) => (
            <li key={blocker.code}>
              <span className={`rounded px-1 text-xs ${PILL[blocker.state]}`}>
                {blocker.state === 'unknown'
                  ? `not implemented (step ${String(blocker.implementedInStep)})`
                  : blocker.section}
              </span>{' '}
              <strong>{blocker.code}</strong> — {blocker.message}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-4 text-sm text-neutral-600">
        <strong>Commit</strong> is build-order step 6. There is no button for it here: a control
        driven by a boolean nothing can act on is a control that lies.
      </p>
    </section>
  )
}
