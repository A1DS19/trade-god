import { defineConfig } from 'vitest/config'

// Node environment, not jsdom: nothing here touches the DOM, and the frozen formulas must
// stay importable without a browser shim ever being involved.
//
// globalSetup rebuilds coinpicks_test from the committed migrations ONCE per run, and it is
// not optional. The immutability triggers refuse TRUNCATE on five tables and refuse DELETE
// on a committed report's rows, so there is no per-test reset short of rebuilding the
// schema. Tests therefore scope every query by ids they created themselves.
// fileParallelism: false because integrity.test.ts deliberately breaks the guards it is
// testing — it does ALTER TABLE citations DISABLE TRIGGER and replaces coinpicks_refuse_truncate()
// with a no-op, repairing in a finally. Every test file shares one coinpicks_test database, so
// running files in parallel would let immutability.test.ts assert that a committed report is
// protected during the window where the trigger is off. A green test over a disabled guard is the
// failure this project keeps meeting; the whole suite runs in under two seconds, so serializing
// it costs nothing worth having.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    globalSetup: ['./src/db/global-setup.ts'],
    fileParallelism: false,
  },
})
