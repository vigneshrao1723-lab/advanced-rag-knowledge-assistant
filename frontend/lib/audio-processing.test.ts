import { describe, expect, it } from "vitest";

import { analyzeLevel, meterLevel, mixToMono, resample, TARGET_SAMPLE_RATE } from "@/lib/audio-processing";

describe("mixToMono", () => {
  it("returns a single channel untouched and averages several", () => {
    const left = new Float32Array([1, 0.5]);
    expect(mixToMono([left])).toBe(left);
    expect(Array.from(mixToMono([left, new Float32Array([-1, 0.5])]))).toEqual([0, 0.5]);
    expect(mixToMono([]).length).toBe(0);
  });
});

describe("resample", () => {
  it("is a no-op at the same rate", () => {
    const input = new Float32Array([0.1, 0.2]);
    expect(resample(input, 16000, 16000)).toBe(input);
  });

  it("downsamples 48 kHz to 16 kHz keeping a constant signal constant", () => {
    const input = new Float32Array(4800).fill(0.25); // 100 ms
    const output = resample(input, 48000, TARGET_SAMPLE_RATE);
    expect(output.length).toBe(1600);
    expect(Math.max(...Array.from(output))).toBeCloseTo(0.25, 5);
    expect(Math.min(...Array.from(output))).toBeCloseTo(0.25, 5);
  });

  it("averages (anti-aliases) rather than dropping samples", () => {
    // alternating +1/-1 at the source rate is a tone far above the target Nyquist.
    const input = Float32Array.from({ length: 4800 }, (_, i) => (i % 2 === 0 ? 1 : -1));
    const output = resample(input, 48000, 16000);
    expect(Math.max(...Array.from(output).map(Math.abs))).toBeLessThan(0.4);
  });

  it("upsamples with interpolation", () => {
    const output = resample(new Float32Array([0, 1]), 8000, 16000);
    expect(output.length).toBe(4);
    expect(output[1]).toBeCloseTo(0.5, 5);
  });
});

describe("analyzeLevel / meterLevel", () => {
  it("reports peak and rms, and zero for silence", () => {
    expect(analyzeLevel(new Float32Array([0, 0, 0]))).toEqual({ peak: 0, rms: 0 });
    const level = analyzeLevel(new Float32Array([0.5, -0.5, 0.5, -0.5]));
    expect(level.peak).toBe(0.5);
    expect(level.rms).toBeCloseTo(0.5, 5);
    expect(analyzeLevel(new Float32Array(0))).toEqual({ peak: 0, rms: 0 });
  });

  it("clamps the meter to 0..1", () => {
    expect(meterLevel(0)).toBe(0);
    expect(meterLevel(10)).toBe(1);
    expect(meterLevel(0.05)).toBeGreaterThan(0);
  });
});
