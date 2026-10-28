import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api-client";
import type { Message } from "@/lib/schemas";
import type { Speaker, SpeakInput } from "@/lib/speech";
import {
  MAX_TURN_MS,
  NO_SPEECH_TIMEOUT_MS,
  SILENCE_AFTER_SPEECH_MS,
  useVoiceConversation,
  type VoiceConversationDeps,
} from "@/lib/use-voice-conversation";
import { VoiceCaptureError, type VoiceRecorder } from "@/lib/voice-recorder";

const RECORDING = { blob: new Blob(["wav"], { type: "audio/wav" }), durationSeconds: 2, peak: 0.4 };

function reply(content: string, id = "a1"): Message {
  return { id, role: "ASSISTANT", content, created_at: "", citations: [], feedback: null };
}

class FakeSpeaker implements Speaker {
  name: string;
  spoken: SpeakInput[] = [];
  private release: (() => void) | null = null;
  constructor(
    name = "fake",
    private readonly mode: "instant" | "hold" | "fail" = "instant"
  ) {
    this.name = name;
  }
  speak(input: SpeakInput): Promise<void> {
    this.spoken.push(input);
    if (this.mode === "fail") return Promise.reject(new Error("no voice"));
    if (this.mode === "instant") return Promise.resolve();
    return new Promise((resolve) => {
      this.release = resolve;
    });
  }
  cancel(): void {
    this.release?.();
    this.release = null;
  }
}

interface Harness {
  deps: Partial<VoiceConversationDeps>;
  recorders: Array<{ recorder: VoiceRecorder; onLevel: (v: number) => void; stop: ReturnType<typeof vi.fn>; cancel: ReturnType<typeof vi.fn> }>;
  startRecording: ReturnType<typeof vi.fn>;
  transcribe: ReturnType<typeof vi.fn>;
  ask: ReturnType<typeof vi.fn>;
}

function harness(speakers: Speaker[] = [new FakeSpeaker()]): Harness {
  const recorders: Harness["recorders"] = [];
  const startRecording = vi.fn(async (options: { onLevel?: (v: number) => void }) => {
    const stop = vi.fn().mockResolvedValue(RECORDING);
    const cancel = vi.fn();
    recorders.push({ recorder: { stop, cancel }, onLevel: options.onLevel ?? (() => undefined), stop, cancel });
    return { stop, cancel } as VoiceRecorder;
  });
  const transcribe = vi.fn().mockResolvedValue({ transcript: "explain program two", language: "en", duration_seconds: 2, provider: "p", model: "m" });
  const ask = vi.fn().mockResolvedValue(reply("Program 2 adds numbers. [1]"));
  return {
    recorders,
    startRecording,
    transcribe,
    ask,
    deps: {
      startRecording,
      transcribe,
      ask,
      audioUrl: () => "http://audio/1",
      createSpeakers: async () => speakers,
    } as Partial<VoiceConversationDeps>,
  };
}

function setup(h: Harness, overrides: Partial<Parameters<typeof useVoiceConversation>[0]> = {}) {
  const onTurn = vi.fn();
  const hook = renderHook(() =>
    useVoiceConversation({
      workspaceId: "w1",
      conversationId: "c1",
      language: "auto",
      deviceId: "",
      speakAnswers: true,
      speechRate: 1,
      onTurn,
      deps: h.deps,
      ...overrides,
    })
  );
  return { ...hook, onTurn };
}

/** Feed the voice-activity detector: baseline noise, then speech, then silence. */
async function sayOneSentence(onLevel: (v: number) => void) {
  await act(async () => {
    for (let i = 0; i < 5; i++) onLevel(0.01);
    for (let i = 0; i < 6; i++) {
      await vi.advanceTimersByTimeAsync(80);
      onLevel(0.4);
    }
    await vi.advanceTimersByTimeAsync(SILENCE_AFTER_SPEECH_MS + 200);
    onLevel(0.01);
    await vi.advanceTimersByTimeAsync(10);
  });
}

async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
});
afterEach(() => {
  vi.useRealTimers();
});

describe("useVoiceConversation", () => {
  it("runs a full turn: listen -> transcribe -> ask -> speak -> listen again", async () => {
    const speaker = new FakeSpeaker();
    const h = harness([speaker]);
    const { result, onTurn } = setup(h);

    act(() => result.current.start());
    await flush();
    expect(result.current.phase).toBe("listening");
    expect(h.startRecording).toHaveBeenCalledTimes(1);

    await sayOneSentence(h.recorders[0].onLevel);
    await flush();

    expect(h.recorders[0].stop).toHaveBeenCalled();
    expect(h.transcribe).toHaveBeenCalledWith("w1", RECORDING.blob, { language: "auto", signal: expect.any(AbortSignal) });
    expect(h.ask).toHaveBeenCalledWith("w1", "c1", "explain program two");
    expect(onTurn).toHaveBeenCalledWith("explain program two", expect.objectContaining({ id: "a1" }));
    expect(speaker.spoken[0].text).toBe("Program 2 adds numbers.");
    expect(speaker.spoken[0].audioUrl).toBe("http://audio/1");
    expect(result.current.heard).toBe("explain program two");
    expect(result.current.turns).toBe(1);
    // ...and it goes straight back to listening for the next question.
    expect(h.startRecording).toHaveBeenCalledTimes(2);
    expect(result.current.phase).toBe("listening");

    act(() => result.current.end());
    expect(result.current.phase).toBe("off");
    expect(h.recorders[1].cancel).toHaveBeenCalled();
  });

  it("still hears you when you start talking the instant listening begins", async () => {
    // Regression (found in the real-browser run): the noise-floor calibration
    // frames were speech, so the threshold ended up above the speech level.
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    await act(async () => {
      const { onLevel } = h.recorders[0];
      for (let i = 0; i < 12; i++) {
        await vi.advanceTimersByTimeAsync(80);
        onLevel(0.5); // loud from the very first frame
      }
      await vi.advanceTimersByTimeAsync(SILENCE_AFTER_SPEECH_MS + 200);
      onLevel(0.01);
      await vi.advanceTimersByTimeAsync(10);
    });
    await flush();

    expect(h.recorders[0].stop).toHaveBeenCalled();
    expect(h.transcribe).toHaveBeenCalled();
    act(() => result.current.end());
  });

  it("does not cut you off during a pause shorter than the silence threshold", async () => {
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    await act(async () => {
      const { onLevel } = h.recorders[0];
      for (let i = 0; i < 5; i++) onLevel(0.01);
      for (let i = 0; i < 4; i++) onLevel(0.4);
      await vi.advanceTimersByTimeAsync(SILENCE_AFTER_SPEECH_MS - 400); // a thinking pause
      onLevel(0.01);
    });
    expect(h.recorders[0].stop).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("listening");
    act(() => result.current.end());
  });

  it("ignores a short click/cough as not speech", async () => {
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    await act(async () => {
      const { onLevel } = h.recorders[0];
      for (let i = 0; i < 5; i++) onLevel(0.01);
      onLevel(0.5); // one loud frame only
      await vi.advanceTimersByTimeAsync(SILENCE_AFTER_SPEECH_MS + 500);
      onLevel(0.01);
    });
    expect(h.recorders[0].stop).not.toHaveBeenCalled();
    act(() => result.current.end());
  });

  it("'I'm done' ends the turn without waiting for silence", async () => {
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    act(() => result.current.finishSpeaking());
    await flush();

    expect(h.recorders[0].stop).toHaveBeenCalled();
    expect(h.transcribe).toHaveBeenCalled();
    act(() => result.current.end());
  });

  it("stops after repeated silence, telling the user why", async () => {
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    for (let i = 0; i < 3; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(NO_SPEECH_TIMEOUT_MS + 50);
      });
      await flush();
    }

    expect(result.current.phase).toBe("off");
    expect(result.current.notice).toMatch(/stopped listening/i);
    expect(h.transcribe).not.toHaveBeenCalled();
    expect(h.recorders.every((r) => r.cancel.mock.calls.length > 0)).toBe(true);
  });

  it("speaking can be interrupted and it goes back to listening", async () => {
    const speaker = new FakeSpeaker("fake", "hold");
    const h = harness([speaker]);
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();
    expect(result.current.phase).toBe("speaking");
    expect(h.startRecording).toHaveBeenCalledTimes(1); // mic is closed while it talks

    act(() => result.current.stopSpeaking());
    await flush();

    expect(result.current.phase).toBe("listening");
    expect(h.startRecording).toHaveBeenCalledTimes(2);
    act(() => result.current.end());
  });

  it("falls back to the next speaker, and says so if none can speak", async () => {
    const h = harness([new FakeSpeaker("browser", "fail"), new FakeSpeaker("server")]);
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();
    expect(result.current.speakerName).toBe("server");
    act(() => result.current.end());

    const h2 = harness([new FakeSpeaker("a", "fail"), new FakeSpeaker("b", "fail")]);
    const second = setup(h2);
    act(() => second.result.current.start());
    await flush();
    await sayOneSentence(h2.recorders[0].onLevel);
    await flush();
    expect(second.result.current.notice).toMatch(/couldn't speak that answer/i);
    expect(second.result.current.phase).toBe("listening"); // the conversation carries on
    act(() => second.result.current.end());
  });

  it("does not speak when speaking is switched off", async () => {
    const speaker = new FakeSpeaker();
    const h = harness([speaker]);
    const { result } = setup(h, { speakAnswers: false });
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();

    expect(speaker.spoken).toHaveLength(0);
    expect(result.current.answer).toContain("Program 2");
    act(() => result.current.end());
  });

  it("an unavailable model stops the loop with the message, and retry re-asks without re-recording", async () => {
    const h = harness();
    h.ask.mockRejectedValueOnce(new ApiError(503, "The AI model server cannot be reached."));
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();

    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/cannot be reached/);
    expect(h.startRecording).toHaveBeenCalledTimes(1);

    act(() => result.current.retry());
    await flush();

    expect(h.ask).toHaveBeenCalledTimes(2);
    expect(h.ask).toHaveBeenLastCalledWith("w1", "c1", "explain program two");
    expect(h.transcribe).toHaveBeenCalledTimes(1); // the audio was not transcribed again
    expect(result.current.error).toBeNull();
    act(() => result.current.end());
  });

  it("explains a blocked microphone and does nothing else", async () => {
    const h = harness();
    h.startRecording.mockRejectedValueOnce(new VoiceCaptureError("permission_denied"));
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();

    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/microphone access was blocked/i);
    expect(h.transcribe).not.toHaveBeenCalled();
  });

  it("a speech-recognition failure surfaces the server's message", async () => {
    const h = harness();
    h.transcribe.mockRejectedValueOnce(new ApiError(503, "The speech model 'small' is not installed."));
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();

    expect(result.current.phase).toBe("error");
    expect(result.current.error).toMatch(/not installed/);
    expect(h.ask).not.toHaveBeenCalled();
  });

  it("an empty transcript is never asked; it listens again", async () => {
    const h = harness();
    h.transcribe.mockResolvedValueOnce({ transcript: "  ", language: null, duration_seconds: 1, provider: "p", model: "m" });
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();

    expect(h.ask).not.toHaveBeenCalled();
    expect(result.current.notice).toMatch(/couldn't make out/i);
    expect(result.current.phase).toBe("listening");
    expect(h.startRecording).toHaveBeenCalledTimes(2);
    act(() => result.current.end());
  });

  it("ending mid-turn aborts the work and ignores a late answer", async () => {
    const h = harness();
    let finish: (m: Message) => void = () => undefined;
    h.ask.mockReturnValue(new Promise<Message>((resolve) => (finish = resolve)));
    const { result, onTurn } = setup(h);
    act(() => result.current.start());
    await flush();
    await sayOneSentence(h.recorders[0].onLevel);
    await flush();
    expect(result.current.phase).toBe("thinking");

    act(() => result.current.end());
    finish(reply("too late"));
    await flush();

    expect(onTurn).not.toHaveBeenCalled();
    expect(result.current.phase).toBe("off");
    expect(h.startRecording).toHaveBeenCalledTimes(1);
  });

  it("a very long turn is cut off at the limit", async () => {
    const h = harness();
    const { result } = setup(h);
    act(() => result.current.start());
    await flush();
    await act(async () => {
      const { onLevel } = h.recorders[0];
      for (let i = 0; i < 5; i++) onLevel(0.01);
      for (let i = 0; i < 8; i++) onLevel(0.4);
      await vi.advanceTimersByTimeAsync(MAX_TURN_MS + 100);
    });
    await flush();
    expect(h.recorders[0].stop).toHaveBeenCalled();
    act(() => result.current.end());
  });
});
