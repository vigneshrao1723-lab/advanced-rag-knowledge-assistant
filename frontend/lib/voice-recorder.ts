import { analyzeLevel, mixToMono, resample, TARGET_SAMPLE_RATE } from "@/lib/audio-processing";
import { encodeWav } from "@/lib/wav-encoder";

export type VoiceErrorCode =
  | "insecure_context"
  | "unsupported"
  | "permission_denied"
  | "no_microphone"
  | "microphone_busy"
  | "too_short"
  | "silent"
  | "decode_failed"
  | "failed";

const MESSAGES: Record<VoiceErrorCode, string> = {
  insecure_context:
    "The microphone only works on a secure page (https:// or http://localhost). Open the app at http://localhost:3000.",
  unsupported:
    "This browser could not start the microphone. Allow the microphone for this site (lock icon in the address bar), or try a current version of Chrome, Edge or Firefox.",
  permission_denied:
    "Microphone access was blocked. Click the lock/camera icon in the address bar, allow the microphone for this site, then try again.",
  no_microphone: "No microphone was found. Plug one in or choose another input device.",
  microphone_busy:
    "The microphone could not be opened - another app may be using it. Close it and try again.",
  too_short: "That recording was too short. Hold on a little longer and speak after pressing the microphone.",
  silent:
    "No sound was captured. Check that the right microphone is selected and not muted, then speak closer to it.",
  decode_failed: "The recording could not be processed. Please try again.",
  failed: "Could not access the microphone.",
};

export class VoiceCaptureError extends Error {
  constructor(public readonly code: VoiceErrorCode) {
    super(MESSAGES[code]);
    this.name = "VoiceCaptureError";
  }
}

/** Turns anything thrown while capturing into a user-facing message. */
export function describeVoiceError(error: unknown): string {
  if (error instanceof VoiceCaptureError) return error.message;
  return MESSAGES.failed;
}

function classifyGetUserMediaError(error: unknown): VoiceErrorCode {
  const name = (error as { name?: string } | null)?.name;
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
    return "permission_denied";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") return "no_microphone";
  if (name === "NotSupportedError") return "unsupported";
  if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") {
    return "microphone_busy";
  }
  return "failed";
}

export interface RecordingResult {
  /** 16 kHz mono 16-bit WAV - what the backend's speech recognizer reads. */
  blob: Blob;
  durationSeconds: number;
  peak: number;
}

export interface VoiceRecorder {
  /** Stops recording, releases the microphone and returns the audio. Throws
   * a `VoiceCaptureError` ("too_short" / "silent" / "decode_failed"). */
  stop(): Promise<RecordingResult>;
  /** Stops recording without producing a result and releases the microphone. */
  cancel(): void;
}

export interface StartOptions {
  /** A specific input device (from `listAudioInputs`). */
  deviceId?: string;
  /** Called ~12x/second with a 0..1 input level while recording. */
  onLevel?: (level: number) => void;
}

const MIN_DURATION_SECONDS = 0.4;
const SILENCE_PEAK = 0.015;

function getAudioContextConstructor(): typeof AudioContext {
  const ctor =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!ctor) throw new VoiceCaptureError("unsupported");
  return ctor;
}

/** Input devices (labels are only filled in after microphone permission). */
export async function listAudioInputs(): Promise<MediaDeviceInfo[]> {
  try {
    const devices = await navigator.mediaDevices.enumerateDevices();
    return devices.filter((device) => device.kind === "audioinput");
  } catch {
    return [];
  }
}

async function openStream(deviceId: string | undefined): Promise<MediaStream> {
  const base: MediaTrackConstraints = {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };
  try {
    return await navigator.mediaDevices.getUserMedia({
      audio: deviceId ? { ...base, deviceId: { exact: deviceId } } : base,
    });
  } catch (error) {
    // A remembered device that is no longer plugged in: fall back to the default.
    const name = (error as { name?: string } | null)?.name;
    if (deviceId && (name === "OverconstrainedError" || name === "NotFoundError")) {
      return openStream(undefined);
    }
    throw new VoiceCaptureError(classifyGetUserMediaError(error));
  }
}

/** Requests microphone access and starts recording immediately. */
export async function startVoiceRecording(options: StartOptions = {}): Promise<VoiceRecorder> {
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    throw new VoiceCaptureError("insecure_context");
  }
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
    throw new VoiceCaptureError("unsupported");
  }

  const stream = await openStream(options.deviceId);
  const mimeType =
    typeof MediaRecorder.isTypeSupported === "function" && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : undefined;
  const mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
  const chunks: Blob[] = [];
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  const stopped = new Promise<void>((resolve) => {
    mediaRecorder.addEventListener("stop", () => resolve(), { once: true });
  });
  mediaRecorder.start();

  // Input level meter (best effort: never allowed to break recording).
  let meterContext: AudioContext | null = null;
  let meterTimer: ReturnType<typeof setInterval> | null = null;
  if (options.onLevel) {
    try {
      const Ctor = getAudioContextConstructor();
      const context = new Ctor();
      if (typeof context.createMediaStreamSource === "function" && typeof context.createAnalyser === "function") {
        const analyser = context.createAnalyser();
        analyser.fftSize = 1024;
        context.createMediaStreamSource(stream).connect(analyser);
        const buffer = new Float32Array(analyser.fftSize);
        meterContext = context;
        meterTimer = setInterval(() => {
          analyser.getFloatTimeDomainData(buffer);
          options.onLevel?.(Math.min(1, analyzeLevel(buffer).rms * 6));
        }, 80);
      } else {
        void context.close();
      }
    } catch {
      meterContext = null;
    }
  }

  let finished = false;
  function releaseMicrophone(): void {
    if (finished) return;
    finished = true;
    if (meterTimer) clearInterval(meterTimer);
    void meterContext?.close().catch(() => undefined);
    for (const track of stream.getTracks()) track.stop();
  }

  return {
    async stop(): Promise<RecordingResult> {
      mediaRecorder.stop();
      await stopped;
      releaseMicrophone();

      const recordedBlob = new Blob(chunks, { type: mediaRecorder.mimeType });
      const arrayBuffer = await recordedBlob.arrayBuffer();
      const AudioContextCtor = getAudioContextConstructor();
      const audioContext = new AudioContextCtor();
      try {
        let audioBuffer: AudioBuffer;
        try {
          audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        } catch {
          throw new VoiceCaptureError("decode_failed");
        }
        const channels: Float32Array[] = [];
        for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
          channels.push(audioBuffer.getChannelData(channel));
        }
        const mono = resample(mixToMono(channels), audioBuffer.sampleRate, TARGET_SAMPLE_RATE);
        const durationSeconds = mono.length / TARGET_SAMPLE_RATE;
        if (durationSeconds < MIN_DURATION_SECONDS) throw new VoiceCaptureError("too_short");
        const { peak } = analyzeLevel(mono);
        if (peak < SILENCE_PEAK) throw new VoiceCaptureError("silent");
        return {
          blob: encodeWav({ sampleRate: TARGET_SAMPLE_RATE, channelData: [mono] }),
          durationSeconds,
          peak,
        };
      } finally {
        await audioContext.close();
      }
    },
    cancel(): void {
      if (mediaRecorder.state !== "inactive") mediaRecorder.stop();
      releaseMicrophone();
    },
  };
}
