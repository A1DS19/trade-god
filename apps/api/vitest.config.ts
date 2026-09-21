import { defineConfig } from 'vitest/config'

// Node environment, not jsdom: nothing under src/scoring/ touches the DOM, and the
// frozen formulas must stay importable without a browser shim ever being involved.
export default defineConfig({
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
})
