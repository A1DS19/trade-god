import { createRootRoute, HeadContent, Scripts } from '@tanstack/react-router'
import type { ReactNode } from 'react'
import appCss from '../styles.css?url'

/*
 * THE BOUNDARY RULE, stated where it is easiest to break.
 *
 * This file runs on the SERVER as well as in the browser. It therefore has, and must keep
 * having: no `loader`, no `beforeLoad`, no `createServerFn`, no `fetch`, and no import of
 * `@coinpicks/api` as a value. The renderer holds no key and calls no third party; the only
 * process allowed to do either is the Hono API. `boundary.test.ts` asserts each of those five
 * words is absent from this file, because "we did not add one" is not a guarantee.
 */
export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: 'utf-8' },
      { name: 'viewport', content: 'width=device-width, initial-scale=1' },
      { title: 'CoinPicks' },
    ],
    links: [{ rel: 'stylesheet', href: appCss }],
  }),
  shellComponent: RootDocument,
})

function RootDocument({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body className="bg-white text-neutral-900">
        {children}
        <Scripts />
      </body>
    </html>
  )
}
