import { defineConfig } from 'vitest/config'

// Node, not jsdom: both suites read files off disk — the source tree and the built bundles — and
// neither renders a component. There is no jsdom and no @testing-library/react in this plan.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
