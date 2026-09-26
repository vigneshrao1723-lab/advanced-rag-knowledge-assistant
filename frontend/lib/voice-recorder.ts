import { encodeWav } from "@/lib/wav-encoder";

export interface VoiceRecorder {
  /** Stops recording and returns the captured audio as a WAV `Blob` —
   * the format `backend/app/voice/stt_provider.py` requires. */
  stop(): Promise<Blob>;
  /** Stops recording without producing a result (the user cancelled) —
   * still releases the microphone. */
  cancel(): void;
}

function getAudioContextConstructor(): typeof AudioContext {
  const ctor =
    window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!ctor) throw new Error("This browser does not support the Web Audio API.");
  return ctor;
}

/** Requests microphone access and starts recording immediately. The
 * returned `VoiceRecorder.stop()` decodes whatever container format
 * `MediaRecorder` produced (typically WebM/Opus in Chromium) via the
 * Web Audio API and re-encodes it as WAV client-side
 * (`lib/wav-encoder.ts`) — no server-side transcoding dependency
 * (e.g. ffmpeg) needed, matching Issue #6's "no unnecessarily complex
 * real-time audio architecture" instruction. */
export async function startVoiceRecording(): Promise<VoiceRecorder> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mediaRecorder = new MediaRecorder(stream);
  const chunks: Blob[] = [];
  mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) chunks.push(event.data);
  };
  const stopped = new Promise<void>((resolve) => {
    mediaRecorder.addEventListener("stop", () => resolve(), { once: true });
  });
  mediaRecorder.start();

  function releaseMicrophone(): void {
    for (const track of stream.getTracks()) track.stop();
  }

  return {
    async stop(): Promise<Blob> {
      mediaRecorder.stop();
      await stopped;
      releaseMicrophone();

      const recordedBlob = new Blob(chunks, { type: mediaRecorder.mimeType });
      const arrayBuffer = await recordedBlob.arrayBuffer();
      const AudioContextCtor = getAudioContextConstructor();
      const audioContext = new AudioContextCtor();
      try {
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        const channelData: Float32Array[] = [];
        for (let channel = 0; channel < audioBuffer.numberOfChannels; channel++) {
          channelData.push(audioBuffer.getChannelData(channel));
        }
        return encodeWav({ sampleRate: audioBuffer.sampleRate, channelData });
      } finally {
        await audioContext.close();
      }
    },
    cancel(): void {
      mediaRecorder.stop();
      releaseMicrophone();
    },
  };
}
