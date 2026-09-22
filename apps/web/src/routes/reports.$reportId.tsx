import { createFileRoute } from '@tanstack/react-router'

/*
 * A stub, so the route exists and the generated tree has something to type `<Link to=...>`
 * against. Task 5 replaces this file entirely.
 */
export const Route = createFileRoute('/reports/$reportId')({ component: ReportEditor })

function ReportEditor() {
  const { reportId } = Route.useParams()
  return <main className="mx-auto max-w-5xl p-6">The editor for {reportId} lands in Task 5.</main>
}
