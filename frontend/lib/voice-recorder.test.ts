import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { describeVoiceError, startVoiceRecording, VoiceCaptureError } from "@/lib/voice-recorder";

class FakeMediaStreamTrack {
  stopped = false;
  stop(): void {
    this.stopped = true;
  }
}

class FakeMediaStream {
  private readonly tracks = [new FakeMediaStreamTrack()];
  getTracks(): FakeMediaStreamTrack[] {
    return this.tracks;
  }
}

class FakeMediaRecorder {
  static instances: FakeMediaRecorder[] = [];
  static isTypeSupported = (type: string) => type.startsWith("audio/webm");
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  mimeType = "audio/webm";
  state: "recording" | "inactive" = "recording";
  private readonly listeners: Record<string, Array<() => void>> = {};

  constructor(
    public stream: FakeMediaStream,
    public options?: { mimeType?: string }
  ) {
    FakeMediaRecorder.instances.push(this);
  }

  start(): void {
    this.state = "recording";
  }

  stop(): void {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["fake-webm-audio"], { type: "audio/webm" }) });
    for (const callback of this.listeners.stop ?? []) callback();
  }

  addEventListener(type: string, callback: () => void): void {
    this.listeners[type] = [...(this.listeners[type] ?? []), callback];
  }
}

let decodedSamples: Float32Array;
let decodedRate: number;
let decodedChannels: number;
let decodeFails = false;

class FakeAudioBuffer {
  get numberOfChannels() {
    return decodedChannels;
  }
  get sampleRate() {
    return decodedRate;
  }
  getChannelData(): Float32Array {
    return decodedSamples;
  }
}

class FakeAnalyser {
  fftSize = 0;
  getFloatTimeDomainData(buffer: Float32Array): void {
    buffer.fill(0.1);
  }
}

class FakeAudioContext {
  async decodeAudioData(): Promise<FakeAudioBuffer> {
    if (decodeFails) throw new Error("bad data");
    return new FakeAudioBuffer();
  }
  createAnalyser(): FakeAnalyser {
    return new FakeAnalyser();
  }
  createMediaStreamSource() {
    return { connect: () => undefined };
  }
  async close(): Promise<void> {
    // no-op
  }
}

let getUserMedia: ReturnType<typeof vi.fn>;

function loud(seconds: number, rate: number): Float32Array {
  return new Float32Array(Math.round(seconds * rate)).fill(0.2);
}

beforeEach(() => {
  FakeMediaRecorder.instances = [];
  decodedSamples = loud(1, 16000);
  decodedRate = 16000;
  decodedChannels = 1;
  decodeFails = false;
  getUserMedia = vi.fn().mockResolvedValue(new FakeMediaStream());
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("AudioContext", FakeAudioContext);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("startVoiceRecording", () => {
  it("asks for a mono, echo-cancelled, noise-suppressed microphone stream", async () => {
    await startVoiceRecording();
    expect(getUserMedia).toHaveBeenCalledWith({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });

  it("requests the chosen device exactly", async () => {
    await startVoiceRecording({ deviceId: "mic-2" });
    expect(getUserMedia.mock.calls[0][0].audio.deviceId).toEqual({ exact: "mic-2" });
  });

  it("falls back to the default microphone if the remembered device is gone", async () => {
    getUserMedia
      .mockRejectedValueOnce({ name: "OverconstrainedError" })
      .mockResolvedValueOnce(new FakeMediaStream());
    await startVoiceRecording({ deviceId: "unplugged" });
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(getUserMedia.mock.calls[1][0].audio.deviceId).toBeUndefined();
  });

  it.each([
    ["NotAllowedError", "permission_denied"],
    ["SecurityError", "permission_denied"],
    ["NotFoundError", "no_microphone"],
    ["NotReadableError", "microphone_busy"],
    ["NotSupportedError", "unsupported"],
    ["SomethingElse", "failed"],
  ])("maps %s to the %s message", async (name, code) => {
    getUserMedia.mockRejectedValue({ name });
    await expect(startVoiceRecording()).rejects.toMatchObject({ code });
  });

  it("refuses on an insecure page and when recording is unsupported", async () => {
    vi.stubGlobal("isSecureContext", false);
    Object.defineProperty(window, "isSecureContext", { value: false, configurable: true });
    await expect(startVoiceRecording()).rejects.toMatchObject({ code: "insecure_context" });
    Object.defineProperty(window, "isSecureContext", { value: true, configurable: true });

    vi.stubGlobal("MediaRecorder", undefined);
    await expect(startVoiceRecording()).rejects.toMatchObject({ code: "unsupported" });
  });

  it("stop() returns a 16 kHz mono WAV and releases the microphone", async () => {
    const recorder = await startVoiceRecording();
    const result = await recorder.stop();

    expect(result.blob.type).toBe("audio/wav");
    expect(result.durationSeconds).toBeCloseTo(1, 1);
    expect(result.peak).toBeCloseTo(0.2, 2);
    // 44-byte header + 16000 samples * 2 bytes
    expect(result.blob.size).toBe(44 + 16000 * 2);
    const stream = FakeMediaRecorder.instances[0].stream;
    expect(stream.getTracks().every((track) => track.stopped)).toBe(true);
  });

  it("downsamples a 48 kHz stereo capture to 16 kHz mono before upload", async () => {
    decodedRate = 48000;
    decodedChannels = 2;
    decodedSamples = loud(2, 48000);
    const result = await (await startVoiceRecording()).stop();
    expect(result.blob.size).toBe(44 + 32000 * 2);
  });

  it("rejects a recording that is too short", async () => {
    decodedSamples = loud(0.1, 16000);
    await expect((await startVoiceRecording()).stop()).rejects.toMatchObject({ code: "too_short" });
  });

  it("rejects a silent recording instead of sending it", async () => {
    decodedSamples = new Float32Array(16000).fill(0.001);
    await expect((await startVoiceRecording()).stop()).rejects.toMatchObject({ code: "silent" });
  });

  it("reports undecodable audio", async () => {
    decodeFails = true;
    await expect((await startVoiceRecording()).stop()).rejects.toMatchObject({ code: "decode_failed" });
  });

  it("cancel() releases the microphone without decoding, and is safe to repeat", async () => {
    const recorder = await startVoiceRecording();
    recorder.cancel();
    recorder.cancel();

    const stream = FakeMediaRecorder.instances[0].stream;
    expect(stream.getTracks().every((track) => track.stopped)).toBe(true);
  });

  it("reports an input level while recording", async () => {
    vi.useFakeTimers();
    const onLevel = vi.fn();
    const recorder = await startVoiceRecording({ onLevel });
    vi.advanceTimersByTime(250);
    expect(onLevel).toHaveBeenCalled();
    expect(onLevel.mock.calls[0][0]).toBeGreaterThan(0);
    recorder.cancel();
    const calls = onLevel.mock.calls.length;
    vi.advanceTimersByTime(500);
    expect(onLevel.mock.calls.length).toBe(calls); // meter stops with the recording
  });
});

describe("describeVoiceError", () => {
  it("returns specific text for capture errors and a generic one otherwise", () => {
    expect(describeVoiceError(new VoiceCaptureError("permission_denied"))).toMatch(/blocked/i);
    expect(describeVoiceError(new Error("boom"))).toMatch(/could not access the microphone/i);
  });
});
