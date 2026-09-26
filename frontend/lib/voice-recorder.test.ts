import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { startVoiceRecording } from "@/lib/voice-recorder";

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
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  mimeType = "audio/webm";
  private readonly listeners: Record<string, Array<() => void>> = {};

  constructor(public stream: FakeMediaStream) {
    FakeMediaRecorder.instances.push(this);
  }

  start(): void {
    // no-op -- recording "starts" immediately in this fake.
  }

  stop(): void {
    this.ondataavailable?.({ data: new Blob(["fake-webm-audio"], { type: "audio/webm" }) });
    for (const callback of this.listeners.stop ?? []) callback();
  }

  addEventListener(type: string, callback: () => void): void {
    this.listeners[type] = [...(this.listeners[type] ?? []), callback];
  }
}

class FakeAudioBuffer {
  numberOfChannels = 1;
  sampleRate = 16000;
  getChannelData(): Float32Array {
    return new Float32Array([0.1, 0.2, -0.1]);
  }
}

class FakeAudioContext {
  async decodeAudioData(): Promise<FakeAudioBuffer> {
    return new FakeAudioBuffer();
  }
  async close(): Promise<void> {
    // no-op
  }
}

let getUserMedia: ReturnType<typeof vi.fn>;

beforeEach(() => {
  FakeMediaRecorder.instances = [];
  getUserMedia = vi.fn().mockResolvedValue(new FakeMediaStream());
  vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("AudioContext", FakeAudioContext);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("startVoiceRecording", () => {
  it("requests microphone access and starts recording", async () => {
    await startVoiceRecording();
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(FakeMediaRecorder.instances).toHaveLength(1);
  });

  it("stop() returns a WAV blob and releases the microphone", async () => {
    const recorder = await startVoiceRecording();
    const blob = await recorder.stop();

    expect(blob.type).toBe("audio/wav");
    expect(blob.size).toBeGreaterThan(44); // header + at least one sample

    const stream = FakeMediaRecorder.instances[0].stream;
    expect(stream.getTracks().every((track) => track.stopped)).toBe(true);
  });

  it("cancel() releases the microphone without decoding audio", async () => {
    const recorder = await startVoiceRecording();
    recorder.cancel();

    const stream = FakeMediaRecorder.instances[0].stream;
    expect(stream.getTracks().every((track) => track.stopped)).toBe(true);
  });
});
