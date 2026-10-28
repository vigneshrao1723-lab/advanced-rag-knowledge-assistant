"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import * as api from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { Message } from "@/lib/schemas";
import { speakableText } from "@/lib/speakable";
import { BrowserSpeaker, ServerAudioSpeaker, type Speaker } from "@/lib/speech";
import {
  describeVoiceError,
  startVoiceRecording,
  VoiceCaptureError,
  type RecordingResult,
  type StartOptions,
  type VoiceRecorder,
} from "@/lib/voice-recorder";

/**
 * Conversational voice mode: a hands-free, TURN-BASED loop
 *
 *   listen (auto-stops when you stop talking) -> transcribe -> ask the normal
 *   chat pipeline -> speak the answer -> listen again ...
 *
 * It is NOT full-duplex: the microphone is closed while the assistant speaks
 * (so it can't hear itself), and you interrupt with the Stop-speaking button,
 * not by talking over it. Everything goes through the same authenticated,
 * workspace-scoped endpoints as typed chat, so the conversation history and
 * citations are the ordinary ones. `Speaker` and the injected `deps` are the
 * seams where a future realtime backend would plug in.
 */

export type ConversationPhase = "off" | "listening" | "transcribing" | "thinking" | "speaking" | "error";

export const SPEECH_LEVEL = 0.12; // meter units (rms * 6) above which we call it speech
const MAX_NOISE_FLOOR = 0.05; // the calibration frames may already contain speech
const MAX_THRESHOLD = 0.3;
export const SILENCE_AFTER_SPEECH_MS = 1400;
export const NO_SPEECH_TIMEOUT_MS = 12000;
export const MAX_TURN_MS = 60000;
const MIN_SPEECH_FRAMES = 3; // ~240 ms of sound, so a click or cough is not a question
const BASELINE_FRAMES = 5;
const MAX_QUIET_TURNS = 3;

export interface VoiceConversationDeps {
  startRecording: (options: StartOptions) => Promise<VoiceRecorder>;
  transcribe: typeof api.transcribeAudio;
  ask: typeof api.postMessage;
  audioUrl: (workspaceId: string, conversationId: string, messageId: string) => string;
  /** Speakers in order of preference. */
  createSpeakers: (lang: string) => Promise<Speaker[]>;
  now: () => number;
}

export const defaultDeps: VoiceConversationDeps = {
  startRecording: startVoiceRecording,
  transcribe: api.transcribeAudio,
  ask: api.postMessage,
  audioUrl: api.getMessageAudioUrl,
  createSpeakers: async (lang) =>
    (await BrowserSpeaker.hasLocalVoice(lang))
      ? [new BrowserSpeaker(), new ServerAudioSpeaker()]
      : [new ServerAudioSpeaker()],
  now: () => Date.now(),
};

type EndReason = "silence" | "manual" | "max" | "no-speech" | "ended";

export interface UseVoiceConversation {
  phase: ConversationPhase;
  active: boolean;
  /** 0..1 microphone level while listening. */
  level: number;
  /** What the assistant heard in the latest turn. */
  heard: string;
  /** The latest answer (full text; the chat thread also shows it). */
  answer: string;
  error: string | null;
  notice: string | null;
  turns: number;
  speakerName: string | null;
  start: () => void;
  end: () => void;
  /** Stop the assistant talking and go back to listening. */
  stopSpeaking: () => void;
  /** "I'm done talking" - don't wait for the silence detector. */
  finishSpeaking: () => void;
  /** After an error: try the same question again (or listen again). */
  retry: () => void;
}

export function useVoiceConversation(options: {
  workspaceId: string;
  conversationId: string;
  language: string;
  deviceId: string;
  speakAnswers: boolean;
  speechRate: number;
  onTurn: (question: string, answer: Message) => void;
  deps?: Partial<VoiceConversationDeps>;
}): UseVoiceConversation {
  const deps: VoiceConversationDeps = { ...defaultDeps, ...options.deps };
  const optionsRef = useRef(options);
  const depsRef = useRef(deps);
  useEffect(() => {
    optionsRef.current = options;
    depsRef.current = deps;
  });

  const [phase, setPhase] = useState<ConversationPhase>("off");
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [turns, setTurns] = useState(0);
  const [speakerName, setSpeakerName] = useState<string | null>(null);

  const sessionRef = useRef(0);
  const recorderRef = useRef<VoiceRecorder | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const speakerRef = useRef<Speaker | null>(null);
  const retryTextRef = useRef<string | null>(null);
  const endWaitRef = useRef<((reason: EndReason) => void) | null>(null);
  const vadRef = useRef({ frames: [] as number[], speechFrames: 0, speaking: false, lastLoudAt: 0 });
  const speakersRef = useRef<Speaker[]>([]);

  const resolveEnd = useCallback((reason: EndReason) => {
    const resolve = endWaitRef.current;
    endWaitRef.current = null;
    resolve?.(reason);
  }, []);

  const handleLevel = useCallback(
    (value: number) => {
      setLevel(value);
      const vad = vadRef.current;
      const now = depsRef.current.now();
      if (vad.frames.length < BASELINE_FRAMES) {
        vad.frames.push(value);
        return;
      }
      const sorted = [...vad.frames].sort((a, b) => a - b);
      // The first frames estimate room noise, but someone who starts talking the
      // moment listening begins makes them speech; an uncapped estimate would
      // push the threshold above anything their voice reaches and nothing would
      // ever be detected. Cap it, and cap the threshold too.
      const baseline = Math.min(sorted[Math.floor(sorted.length / 2)], MAX_NOISE_FLOOR);
      const threshold = Math.min(Math.max(SPEECH_LEVEL, baseline * 2.5), MAX_THRESHOLD);
      if (value > threshold) {
        vad.speechFrames += 1;
        vad.lastLoudAt = now;
        if (vad.speechFrames >= MIN_SPEECH_FRAMES) vad.speaking = true;
      } else if (vad.speaking && now - vad.lastLoudAt > SILENCE_AFTER_SPEECH_MS) {
        resolveEnd("silence");
      }
    },
    [resolveEnd]
  );

  const stopEverything = useCallback(() => {
    sessionRef.current += 1;
    resolveEnd("ended");
    abortRef.current?.abort();
    abortRef.current = null;
    recorderRef.current?.cancel();
    recorderRef.current = null;
    speakerRef.current?.cancel();
    speakerRef.current = null;
    setLevel(0);
  }, [resolveEnd]);

  const fail = useCallback(
    (session: number, message: string) => {
      if (sessionRef.current !== session) return;
      stopEverything();
      setError(message);
      setPhase("error");
    },
    [stopEverything]
  );

  const waitForEndOfSpeech = useCallback((): Promise<EndReason> => {
    const now = depsRef.current.now();
    vadRef.current = { frames: [], speechFrames: 0, speaking: false, lastLoudAt: now };
    return new Promise<EndReason>((resolve) => {
      const timers: Array<ReturnType<typeof setTimeout>> = [];
      const finish = (reason: EndReason) => {
        timers.forEach(clearTimeout);
        resolve(reason);
      };
      endWaitRef.current = finish;
      timers.push(
        setTimeout(() => {
          if (!vadRef.current.speaking) resolveEnd("no-speech");
        }, NO_SPEECH_TIMEOUT_MS),
        setTimeout(() => resolveEnd("max"), MAX_TURN_MS)
      );
    });
  }, [resolveEnd]);

  const speak = useCallback(async (session: number, message: Message) => {
    const { speakAnswers, speechRate, workspaceId, conversationId } = optionsRef.current;
    if (!speakAnswers || !message.content.trim()) return;
    setPhase("speaking");
    const text = speakableText(message.content);
    const audioUrl = depsRef.current.audioUrl(workspaceId, conversationId, message.id);
    for (const speaker of speakersRef.current) {
      if (sessionRef.current !== session) return;
      speakerRef.current = speaker;
      setSpeakerName(speaker.name);
      try {
        await speaker.speak({ text, audioUrl, rate: speechRate });
        return;
      } catch {
        // Try the next speaker (e.g. server audio if the browser has no voice).
      }
    }
    if (sessionRef.current === session) {
      setNotice("I couldn't speak that answer aloud - it is on screen.");
    }
  }, []);

  const runLoop = useCallback(
    async (session: number) => {
      const alive = () => sessionRef.current === session;
      let quietTurns = 0;
      try {
        speakersRef.current = await depsRef.current.createSpeakers(
          document.documentElement.lang || navigator.language || "en"
        );
      } catch {
        speakersRef.current = [];
      }

      while (alive()) {
        let question = retryTextRef.current;
        retryTextRef.current = null;

        if (question === null) {
          // ---- listen
          // The last exchange and any notice ("I didn't catch that") stay
          // visible while listening; they clear when the next question arrives.
          setPhase("listening");
          let recorder: VoiceRecorder;
          try {
            recorder = await depsRef.current.startRecording({
              deviceId: optionsRef.current.deviceId || undefined,
              onLevel: (value) => {
                if (alive()) handleLevel(value);
              },
            });
          } catch (err) {
            fail(session, describeVoiceError(err));
            return;
          }
          if (!alive()) {
            recorder.cancel();
            return;
          }
          recorderRef.current = recorder;
          const reason = await waitForEndOfSpeech();
          if (!alive() || reason === "ended") {
            recorder.cancel();
            return;
          }
          recorderRef.current = null;
          setLevel(0);
          if (reason === "no-speech") {
            recorder.cancel();
            quietTurns += 1;
            if (quietTurns >= MAX_QUIET_TURNS) {
              stopEverything();
              setNotice("I didn't hear anything, so I stopped listening. Press Start to continue.");
              setPhase("off");
              return;
            }
            setNotice("I didn't hear anything - still listening.");
            continue;
          }
          let recording: RecordingResult;
          try {
            recording = await recorder.stop();
          } catch (err) {
            if (err instanceof VoiceCaptureError && (err.code === "silent" || err.code === "too_short")) {
              quietTurns += 1;
              setNotice("I didn't catch that - please try again.");
              if (quietTurns >= MAX_QUIET_TURNS) {
                stopEverything();
                setPhase("off");
                setNotice("I couldn't pick up your voice, so I stopped. Check your microphone and press Start.");
                return;
              }
              continue;
            }
            fail(session, describeVoiceError(err));
            return;
          }
          if (!alive()) return;

          // ---- transcribe
          setPhase("transcribing");
          const controller = new AbortController();
          abortRef.current = controller;
          let text: string;
          try {
            const result = await depsRef.current.transcribe(optionsRef.current.workspaceId, recording.blob, {
              language: optionsRef.current.language,
              signal: controller.signal,
            });
            text = result.transcript.trim();
          } catch (err) {
            if (!alive()) return;
            fail(session, err instanceof ApiError ? err.message : describeVoiceError(err));
            return;
          } finally {
            abortRef.current = null;
          }
          if (!alive()) return;
          if (!text) {
            quietTurns += 1;
            setNotice("I couldn't make out any words - please try again.");
            continue;
          }
          quietTurns = 0;
          question = text;
        }

        // ---- ask the normal chat pipeline
        setNotice(null);
        setHeard(question);
        setPhase("thinking");
        let reply: Message;
        try {
          reply = await depsRef.current.ask(
            optionsRef.current.workspaceId,
            optionsRef.current.conversationId,
            question
          );
        } catch (err) {
          if (!alive()) return;
          retryTextRef.current = question;
          fail(session, err instanceof ApiError ? err.message : "Could not get an answer.");
          return;
        }
        if (!alive()) return;
        setAnswer(reply.content);
        setTurns((count) => count + 1);
        optionsRef.current.onTurn(question, reply);

        // ---- speak (interruptible), then listen again
        await speak(session, reply);
        speakerRef.current = null;
      }
    },
    [fail, handleLevel, speak, stopEverything, waitForEndOfSpeech]
  );

  const begin = useCallback(() => {
    stopEverything();
    const session = sessionRef.current;
    setError(null);
    setNotice(null);
    setPhase("listening");
    void runLoop(session);
  }, [runLoop, stopEverything]);

  const start = useCallback(() => {
    retryTextRef.current = null;
    setTurns(0);
    setHeard("");
    setAnswer("");
    begin();
  }, [begin]);

  const end = useCallback(() => {
    retryTextRef.current = null;
    stopEverything();
    setPhase("off");
    setNotice(null);
  }, [stopEverything]);

  useEffect(
    () => () => {
      sessionRef.current += 1;
      endWaitRef.current?.("ended");
      abortRef.current?.abort();
      recorderRef.current?.cancel();
      speakerRef.current?.cancel();
    },
    []
  );

  return {
    phase,
    active: phase !== "off" && phase !== "error",
    level,
    heard,
    answer,
    error,
    notice,
    turns,
    speakerName,
    start,
    end,
    stopSpeaking: () => speakerRef.current?.cancel(),
    finishSpeaking: () => resolveEnd("manual"),
    retry: begin,
  };
}
