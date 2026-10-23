import { describe, expect, it } from "vitest";

import { describeDevice } from "./user-agent";

describe("describeDevice", () => {
  it("returns Unknown device for null", () => {
    expect(describeDevice(null)).toBe("Unknown device");
  });

  it("recognizes Chrome on Linux", () => {
    expect(
      describeDevice(
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
      )
    ).toBe("Chrome on Linux");
  });

  it("recognizes Safari on macOS (not misdetected as Chrome)", () => {
    expect(
      describeDevice(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
      )
    ).toBe("Safari on macOS");
  });

  it("recognizes Firefox on Windows", () => {
    expect(
      describeDevice("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0")
    ).toBe("Firefox on Windows");
  });

  it("recognizes mobile Safari on iOS", () => {
    expect(
      describeDevice(
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
      )
    ).toBe("Safari on iOS");
  });

  it("falls back to Unknown device for an unrecognized string", () => {
    expect(describeDevice("some-opaque-client-string")).toBe("Unknown device");
  });
});
