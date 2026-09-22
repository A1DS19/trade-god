import { createFileRoute } from '@tanstack/react-router'

/*
 * THE ONE HOP TO THE API, IN DEV AND IN PRODUCTION.
 *
 * A Vite `server.proxy` on `/api` would work in dev and would not exist in a built app, leaving
 * the shipped hop untested -- measured: with a proxy configured and pointed at a dead port,
 * `/api/health` returned 502 rather than falling through to this route, so in dev the route
 * would never run at all. A Start server route runs in both, so there is one path, not two.
 *
 * It is the ONE place in apps/web where the server makes an outbound request, and the boundary
 * rule survives it for one reason only — the target is this machine's own API on loopback, built
 * from an origin this process is configured with. It never takes a URL from the request, from a
 * report, or from a citation. Fetching a third-party URL is the citation verifier's job in
 * build-order step 5 and it belongs to apps/api, which is the tier that holds keys.
 */
const API_ORIGIN = process.env.COINPICKS_API_ORIGIN ?? 'http://127.0.0.1:8789'

async function forward({ request }: { request: Request }): Promise<Response> {
  const url = new URL(request.url)
  const target = `${API_ORIGIN}${url.pathname.replace(/^\/api/, '')}${url.search}`
  const response = await fetch(target, {
    body: request.method === 'GET' || request.method === 'HEAD' ? undefined : request.body,
    // `manual`, so a redirect reaches the BROWSER. hono's proxy default is `follow`, which
    // resolves the chain in this process and drops both the Location and any Set-Cookie on it.
    // The sibling repo shipped that bug and only found it in production.
    headers: request.headers,
    method: request.method,
    redirect: 'manual',
    // Required by undici whenever a body is a stream, and a PATCH body is.
    ...{ duplex: 'half' },
  })
  return new Response(response.body, {
    headers: response.headers,
    status: response.status,
    statusText: response.statusText,
  })
}

export const Route = createFileRoute('/api/$')({
  server: {
    handlers: {
      DELETE: forward,
      GET: forward,
      PATCH: forward,
      POST: forward,
      PUT: forward,
    },
  },
})
