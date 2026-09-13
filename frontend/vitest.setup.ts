import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// `test.globals` isn't enabled in vitest.config.mts, so Testing Library's
// automatic per-test cleanup (which detects a global `afterEach`) never
// registers on its own — without this, DOM from one test leaks into the
// next and breaks any query that expects a single match.
afterEach(() => {
  cleanup();
});
