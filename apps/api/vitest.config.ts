import { defineConfig } from 'vitest/config'

// Node environment, not jsdom: nothing here touches the DOM, and the frozen formulas must
// stay importable without a browser shim ever being involved.
//
// globalSetup rebuilds coinpicks_test from the committed migrations ONCE per run, and it is
// not optional. The immutability triggers refuse TRUNCATE on five tables and refuse DELETE
// on a committed report's rows, so there is no per-test reset short of rebuilding the
// schema. Tests therefore scope every query by ids they created themselves.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globalSetup: ['./src/db/global-setup.ts'],
  },
})
