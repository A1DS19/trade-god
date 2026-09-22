import { serve } from '@hono/node-server'
import { serveStatic } from '@hono/node-server/serve-static'
import { Hono } from 'hono'
import ssr from '../dist/server/server.js'

/*
 * The web tier in production: the assets first, everything else -- pages AND the `/api/$` route
 * -- through the SSR handler.
 *
 * Deliberately OUTSIDE apps/web/tsconfig.json's `include`: it imports ../dist/server/server.js,
 * which does not exist until `vite build` has run, so `tsc --noEmit` on a clean checkout would
 * fail on a file that is never executed unbuilt.
 */
const PORT = Number(process.env.PORT ?? 3000)

const app = new Hono()
  .use('/assets/*', serveStatic({ root: './dist/client' }))
  .all('*', (c) => ssr.fetch(c.req.raw))

serve({ fetch: app.fetch, hostname: '127.0.0.1', port: PORT }, (info) => {
  console.log(`coinpicks web on http://127.0.0.1:${info.port}`)
})
