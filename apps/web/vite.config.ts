import tailwindcss from '@tailwindcss/vite'
import { tanstackStart } from '@tanstack/react-start/plugin/vite'
import viteReact from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

/*
 * NO `server.proxy`. `src/routes/api.$.ts` serves the `/api` prefix in dev AND in production, so
 * the hop that ships is the hop that is developed against. With a Vite proxy in front of it the
 * server route is dead code in dev and the only code in production -- measured: with the proxy
 * configured and its target pointed at a dead port, `curl /api/health` returned 502 rather than
 * falling through to the route, which is two paths where the project only wants one.
 */
export default defineConfig({
  plugins: [
    tanstackStart({
      /*
       * THE LEAK GUARD, AT BUILD TIME. This is the thing plain Vite has no equivalent of.
       *
       * `import { type AppType, createApp } from '@coinpicks/api'` plus one value use is the
       * defect the boundary test exists for: tsc accepts it, biome says nothing, and the client
       * bundle silently grows by 136 kB. With this option the build STOPS, naming the line and
       * printing the whole import chain that reached it.
       *
       * `server` as well as `client`, and they are different rules. `client` says "not in the
       * browser". `server` says "not in the RENDERER either" -- without it a value import used
       * only inside a `createServerFn` body builds clean, leaves the client bundle spotless, and
       * puts drizzle plus this project's DDL in dist/server, which is a database handle in the
       * tier that is supposed to hold none. Measured both ways.
       *
       * A type-only import is erased before the bundler sees the specifier, so `hc<AppType>`
       * still compiles with both lists in place.
       */
      importProtection: {
        behavior: 'error',
        client: { specifiers: ['@coinpicks/api', /^drizzle-orm/, /^pg$/] },
        enabled: true,
        server: { specifiers: ['@coinpicks/api', /^drizzle-orm/, /^pg$/] },
      },
    }),
    // react's vite plugin must come AFTER start's vite plugin; tailwind last.
    viteReact(),
    tailwindcss(),
  ],
  // Vite 8 resolves tsconfig `paths` natively. Declared because the documented default is false.
  resolve: { tsconfigPaths: true },
  /*
   * `strictPort`, because this machine has already been bitten. 5173 is held by the sibling repo's
   * dev server right now; without this, `vite dev` moves to 5174 with one grey line of output and
   * the first `curl localhost:5173/` reads ANOTHER APP'S HTML. Measured with 5173 occupied:
   * `Error: Port 5173 is already in use`, exit 1. A loud failure beats a health check that passed
   * against the wrong process -- which is the same lesson as the 8787 note Task 8 strikes.
   */
  server: { port: 5173, strictPort: true },
})
