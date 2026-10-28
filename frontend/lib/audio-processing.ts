// Pure audio helpers for voice capture (no browser API dependency, so they
// are unit-testable). Speech recognition wants 16 kHz mono; sending that
// instead of the device's native 44.1/48 kHz stereo is ~3-6x smaller and is
// exactly what the speech model uses internally.

export const TARGET_SAMPLE_RATE = 16000;

/** Averages channels into one. A single channel is returned as-is. */
export function mixToMono(channels: Float32Array[]): Float32Array {
  if (channels.length === 0) return new Float32Array(0);
  if (channels.length === 1) return channels[0];
  const length = Math.min(...channels.map((c) => c.length));
  const mono = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    let sum = 0;
    for (const channel of channels) sum += channel[i];
    mono[i] = sum / channels.length;
  }
  return mono;
}

/** Resamples by averaging the source samples that fall into each output
 * sample (a box filter: cheap anti-aliasing when downsampling) and linearly
 * interpolating when upsampling. Speech-grade, not studio-grade. */
export function resample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate || input.length === 0) return input;
  const outLength = Math.max(1, Math.round((input.length * toRate) / fromRate));
  const output = new Float32Array(outLength);
  const ratio = fromRate / toRate;
  if (ratio > 1) {
    for (let i = 0; i < outLength; i++) {
      const start = Math.floor(i * ratio);
      const end = Math.min(input.length, Math.max(start + 1, Math.floor((i + 1) * ratio)));
      let sum = 0;
      for (let j = start; j < end; j++) sum += input[j];
      output[i] = sum / (end - start);
    }
  } else {
    for (let i = 0; i < outLength; i++) {
      const position = i * ratio;
      const index = Math.floor(position);
      const fraction = position - index;
      const a = input[Math.min(index, input.length - 1)];
      const b = input[Math.min(index + 1, input.length - 1)];
      output[i] = a + (b - a) * fraction;
    }
  }
  return output;
}

export interface LevelStats {
  /** Largest absolute sample, 0..1. */
  peak: number;
  /** Root-mean-square level, 0..1. */
  rms: number;
}

export function analyzeLevel(samples: Float32Array): LevelStats {
  let peak = 0;
  let sumSquares = 0;
  for (let i = 0; i < samples.length; i++) {
    const value = Math.abs(samples[i]);
    if (value > peak) peak = value;
    sumSquares += samples[i] * samples[i];
  }
  return { peak, rms: samples.length ? Math.sqrt(sumSquares / samples.length) : 0 };
}

/** Maps an RMS level to a 0..1 meter position (speech sits around 0.02-0.2). */
export function meterLevel(rms: number): number {
  return Math.max(0, Math.min(1, rms * 6));
}
