import { describe, expect, it } from "vitest";

import { encodeWav } from "@/lib/wav-encoder";

async function readHeaderString(blob: Blob, offset: number, length: number): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer, offset, length);
  return String.fromCharCode(...bytes);
}

describe("encodeWav", () => {
  it("produces a valid RIFF/WAVE header", async () => {
    const blob = encodeWav({ sampleRate: 16000, channelData: [new Float32Array([0, 0.5, -0.5])] });
    expect(await readHeaderString(blob, 0, 4)).toBe("RIFF");
    expect(await readHeaderString(blob, 8, 4)).toBe("WAVE");
    expect(await readHeaderString(blob, 12, 4)).toBe("fmt ");
    expect(await readHeaderString(blob, 36, 4)).toBe("data");
    expect(blob.type).toBe("audio/wav");
  });

  it("sizes the file as a 44-byte header plus 16-bit samples", async () => {
    const samples = new Float32Array(100);
    const blob = encodeWav({ sampleRate: 16000, channelData: [samples] });
    expect(blob.size).toBe(44 + 100 * 2);
  });

  it("encodes the declared sample rate and mono channel count", async () => {
    const blob = encodeWav({ sampleRate: 22050, channelData: [new Float32Array([0])] });
    const buffer = await blob.arrayBuffer();
    const view = new DataView(buffer);
    expect(view.getUint16(22, true)).toBe(1); // numChannels
    expect(view.getUint32(24, true)).toBe(22050); // sampleRate
  });

  it("clamps out-of-range samples instead of overflowing", async () => {
    const blob = encodeWav({ sampleRate: 16000, channelData: [new Float32Array([2, -2])] });
    const buffer = await blob.arrayBuffer();
    const view = new DataView(buffer);
    expect(view.getInt16(44, true)).toBe(0x7fff);
    expect(view.getInt16(46, true)).toBe(-0x8000);
  });

  it("interleaves stereo channels in L, R order", async () => {
    const left = new Float32Array([1, 0]);
    const right = new Float32Array([-1, 0]);
    const blob = encodeWav({ sampleRate: 16000, channelData: [left, right] });
    const buffer = await blob.arrayBuffer();
    const view = new DataView(buffer);
    expect(view.getInt16(44, true)).toBe(0x7fff); // left, frame 0
    expect(view.getInt16(46, true)).toBe(-0x8000); // right, frame 0
  });

  it("produces an empty (silent) but valid WAV for zero-length input", async () => {
    const blob = encodeWav({ sampleRate: 16000, channelData: [new Float32Array(0)] });
    expect(blob.size).toBe(44);
  });
});
