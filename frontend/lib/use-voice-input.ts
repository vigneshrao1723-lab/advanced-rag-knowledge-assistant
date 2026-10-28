"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import {
  describeVoiceError,
  listAudioInputs,
  startVoiceRecording,
  type VoiceRecorder,
} from "@/lib/voice-recorder";

export type VoicePhase = "idle" | "recording" | "transcribing";

export const VOICE_LANGUAGES: ReadonlyArray<{ code: string; label: string }> = [
  { code: "auto", label: "Auto-detect" },
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "ta", label: "Tamil" },
  { code: "te", label: "Telugu" },
  { code: "kn", label: "Kannada" },
  { code: "ml", label: "Malayalam" },
  { code: "bn", label: "Bengali" },
  { code: "mr", label: "Marathi" },
  { code: "es", label: "Spanish" },
  { code: "fr", label: "French" },
  { code: "de", label: "German" },
];

const LANGUAGE_KEY = "rag.voice.language";
const DEVICE_KEY = "rag.voice.deviceId";
/** Backend rejects recordings over 120 s; stop a little earlier. */
export const MAX_RECORDING_SECONDS = 110;

function readPref(key: string, fallback: string): string {
  try {
    return window.localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be blocked; the preference just won't persist.
  }
}

export interface UseVoiceInput {
  phase: VoicePhase;
  elapsedSeconds: number;
  /** 0..1 microphone level while recording. */
  level: number;
  error: string | null;
  /** True once a transcript was delivered and the user hasn't yet edited/sent it. */
  language: string;
  setLanguage: (code: string) => void;
  deviceId: string;
  setDeviceId: (id: string) => void;
  devices: MediaDeviceInfo[];
  start: () => Promise<void>;
  /** Stop recording and transcribe. */
  stop: () => Promise<void>;
  /** Abandon the recording or the transcription in progress. */
  cancel: () => void;
  clearError: () => void;
}

export function useVoiceInput(options: {
  workspaceId: string;
  onTranscript: (text: string) => void;
}): UseVoiceInput {
  const { workspaceId, onTranscript } = options;
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [language, setLanguageState] = useState("auto");
  const [deviceId, setDeviceIdState] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);

  const recorderRef = useRef<VoiceRecorder | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  // Bumped on every start/cancel so a slow transcription that finishes after
  // the user moved on can never overwrite newer state (stale transcript).
  const runRef = useRef(0);
  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => {
    // Preferences live in browser storage, which only exists on the client.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLanguageState(readPref(LANGUAGE_KEY, "auto"));
    setDeviceIdState(readPref(DEVICE_KEY, ""));
  }, []);

  const refreshDevices = useCallback(async () => {
    setDevices(await listAudioInputs());
  }, []);

  useEffect(() => {
    // Enumerating devices is an external system; the result is stored once.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refreshDevices();
  }, [refreshDevices]);

  // Elapsed timer + automatic stop at the length limit.
  const stopRef = useRef<() => Promise<void>>(async () => undefined);
  useEffect(() => {
    if (phase !== "recording") return;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      setElapsedSeconds(seconds);
      if (seconds >= MAX_RECORDING_SECONDS) void stopRef.current();
    }, 250);
    return () => clearInterval(timer);
  }, [phase]);

  // Never leave the microphone open if the component unmounts.
  useEffect(
    () => () => {
      runRef.current += 1;
      abortRef.current?.abort();
      recorderRef.current?.cancel();
      recorderRef.current = null;
    },
    []
  );

  const start = useCallback(async () => {
    if (phase !== "idle") return;
    setError(null);
    const run = ++runRef.current;
    try {
      const recorder = await startVoiceRecording({
        deviceId: deviceId || undefined,
        onLevel: (value) => {
          if (runRef.current === run) setLevel(value);
        },
      });
      if (runRef.current !== run) {
        recorder.cancel(); // cancelled while the permission prompt was open
        return;
      }
      recorderRef.current = recorder;
      setElapsedSeconds(0);
      setLevel(0);
      setPhase("recording");
      void refreshDevices(); // labels become available after permission
    } catch (err) {
      if (runRef.current === run) setError(describeVoiceError(err));
    }
  }, [phase, deviceId, refreshDevices]);

  const stop = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder) return;
    recorderRef.current = null;
    const run = runRef.current;
    setLevel(0);
    setPhase("transcribing");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const recording = await recorder.stop();
      const result = await api.transcribeAudio(workspaceId, recording.blob, {
        language,
        signal: controller.signal,
      });
      if (runRef.current !== run) return; // superseded or cancelled
      const text = result.transcript.trim();
      if (!text) {
        setError("I couldn't make out any words. Speak a little louder or closer to the microphone and try again.");
      } else {
        onTranscriptRef.current(text);
      }
    } catch (err) {
      if (runRef.current !== run) return;
      if (err instanceof ApiError) setError(err.message);
      else setError(describeVoiceError(err));
    } finally {
      if (runRef.current === run) {
        abortRef.current = null;
        setPhase("idle");
      }
    }
  }, [workspaceId, language]);

  useEffect(() => {
    stopRef.current = stop;
  }, [stop]);

  const cancel = useCallback(() => {
    runRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    recorderRef.current?.cancel();
    recorderRef.current = null;
    setLevel(0);
    setPhase("idle");
  }, []);

  return {
    phase,
    elapsedSeconds,
    level,
    error,
    language,
    setLanguage: (code) => {
      setLanguageState(code);
      writePref(LANGUAGE_KEY, code);
    },
    deviceId,
    setDeviceId: (id) => {
      setDeviceIdState(id);
      writePref(DEVICE_KEY, id);
    },
    devices,
    start,
    stop,
    cancel,
    clearError: () => setError(null),
  };
}
