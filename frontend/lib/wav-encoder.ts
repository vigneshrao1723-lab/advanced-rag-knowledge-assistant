// Pure PCM -> WAV encoding (Issue #6). No browser API dependency here on
// purpose — `voice-recorder.ts` extracts plain sample data out of a real
// `AudioBuffer` and hands it to `encodeWav()`, keeping this function
// fully unit-testable without a jsdom/browser Web Audio API stub. This
// is the standard "no extra library needed" technique for producing a
// WAV file from decoded audio in the browser.

export interface PcmAudio {
  sampleRate: number;
  /** One `Float32Array` (values in [-1, 1]) per channel, all the same length. */
  channelData: Float32Array[];
}

const BYTES_PER_SAMPLE = 2; // 16-bit PCM

function writeString(view: DataView, offset: number, text: string): void {
  for (let i = 0; i < text.length; i++) {
    view.setUint8(offset + i, text.charCodeAt(i));
  }
}

function floatTo16BitPcm(view: DataView, offset: number, input: Float32Array): void {
  for (let i = 0; i < input.length; i++, offset += BYTES_PER_SAMPLE) {
    const clamped = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  }
}

/** Interleaves per-channel `Float32Array`s into one `Float32Array` in
 * standard WAV channel order (L, R, L, R, ... for stereo). A no-op copy
 * for mono input. */
function interleave(channelData: Float32Array[]): Float32Array {
  if (channelData.length === 1) return channelData[0];
  const length = channelData[0].length;
  const result = new Float32Array(length * channelData.length);
  for (let frame = 0; frame < length; frame++) {
    for (let channel = 0; channel < channelData.length; channel++) {
      result[frame * channelData.length + channel] = channelData[channel][frame];
    }
  }
  return result;
}

/** Encodes raw PCM samples as a 16-bit WAV file — the format
 * `backend/app/voice/stt_provider.py` requires. */
export function encodeWav(audio: PcmAudio): Blob {
  const numChannels = audio.channelData.length;
  const interleaved = interleave(audio.channelData);
  const dataSize = interleaved.length * BYTES_PER_SAMPLE;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const byteRate = audio.sampleRate * numChannels * BYTES_PER_SAMPLE;
  const blockAlign = numChannels * BYTES_PER_SAMPLE;

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, numChannels, true);
  view.setUint32(24, audio.sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, BYTES_PER_SAMPLE * 8, true);
  writeString(view, 36, "data");
  view.setUint32(40, dataSize, true);
  floatTo16BitPcm(view, 44, interleaved);

  return new Blob([buffer], { type: "audio/wav" });
}
