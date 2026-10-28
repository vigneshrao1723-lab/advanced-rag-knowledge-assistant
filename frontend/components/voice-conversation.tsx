"use client";

import { AudioLines, Brain, Headphones, Loader2, Mic, PhoneOff, RotateCcw, Square, Volume2 } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import type { UseVoiceConversation } from "@/lib/use-voice-conversation";

const RATES = [0.8, 1, 1.2, 1.5];

/** The start button that sits beside "Voice input" in the composer. */
export function VoiceConversationButton({
  voice,
  disabled,
}: {
  voice: UseVoiceConversation;
  disabled?: boolean;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      disabled={disabled || voice.active}
      onClick={() => voice.start()}
      aria-label="Start voice conversation"
    >
      <Headphones className="size-4" aria-hidden="true" />
      Voice conversation
    </Button>
  );
}

function StateBadge({ voice }: { voice: UseVoiceConversation }) {
  const rings = Math.round(voice.level * 3);
  const states: Record<string, { label: string; icon: ReactNode; tone: string }> = {
    listening: {
      label: "Listening… speak now",
      icon: <Mic className="size-6" aria-hidden="true" />,
      tone: "bg-emerald-100 text-emerald-800 ring-emerald-300",
    },
    transcribing: {
      label: "Transcribing…",
      icon: <Loader2 className="size-6 animate-spin" aria-hidden="true" />,
      tone: "bg-slate-100 text-slate-700 ring-slate-300",
    },
    thinking: {
      label: "Thinking…",
      icon: <Brain className="size-6 animate-pulse" aria-hidden="true" />,
      tone: "bg-indigo-100 text-indigo-800 ring-indigo-300",
    },
    speaking: {
      label: "Speaking…",
      icon: <AudioLines className="size-6 animate-pulse" aria-hidden="true" />,
      tone: "bg-amber-100 text-amber-800 ring-amber-300",
    },
    error: {
      label: "Stopped",
      icon: <Square className="size-6" aria-hidden="true" />,
      tone: "bg-red-100 text-red-800 ring-red-300",
    },
  };
  const state = states[voice.phase];
  if (!state) return null;
  return (
    <div className="flex items-center gap-3" role="status" aria-live="polite">
      <span
        className={`flex size-12 shrink-0 items-center justify-center rounded-full ring-2 transition-all ${state.tone}`}
        style={voice.phase === "listening" ? { boxShadow: `0 0 0 ${rings * 4}px rgba(16,185,129,0.18)` } : undefined}
      >
        {state.icon}
      </span>
      <span className="text-base font-medium">{state.label}</span>
    </div>
  );
}

export function VoiceConversationPanel({
  voice,
  speakAnswers,
  onSpeakAnswersChange,
  speechRate,
  onSpeechRateChange,
}: {
  voice: UseVoiceConversation;
  speakAnswers: boolean;
  onSpeakAnswersChange: (value: boolean) => void;
  speechRate: number;
  onSpeechRateChange: (value: number) => void;
}) {
  if (voice.phase === "off" && !voice.notice && !voice.error) return null;
  const running = voice.phase !== "off";

  return (
    <section
      aria-label="Voice conversation"
      className="flex flex-col gap-3 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-indigo-900">
          <Headphones className="size-4" aria-hidden="true" />
          Voice conversation
        </h3>
        {running && (
          <Button type="button" size="sm" variant="outline" onClick={() => voice.end()}>
            <PhoneOff className="size-3.5" aria-hidden="true" />
            End conversation
          </Button>
        )}
      </div>

      {running && <StateBadge voice={voice} />}

      {voice.heard && (
        <p className="text-sm">
          <span className="font-medium text-slate-600">You said:</span> {voice.heard}
        </p>
      )}
      {voice.answer && (
        <p className="line-clamp-3 text-sm text-slate-700">
          <span className="font-medium text-slate-600">Answer:</span> {voice.answer}
        </p>
      )}

      {voice.notice && (
        <p role="status" className="rounded-md bg-white px-3 py-2 text-sm text-slate-700">
          {voice.notice}
        </p>
      )}
      {voice.error && (
        <div role="alert" className="flex flex-wrap items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span className="flex-1">{voice.error}</span>
          <Button type="button" size="sm" variant="outline" onClick={() => voice.retry()}>
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Try again
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={() => voice.end()}>
            Close
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {voice.phase === "listening" && (
          <Button type="button" size="sm" onClick={() => voice.finishSpeaking()}>
            I&apos;m done talking
          </Button>
        )}
        {voice.phase === "speaking" && (
          <Button type="button" size="sm" variant="destructive" onClick={() => voice.stopSpeaking()}>
            <Volume2 className="size-3.5" aria-hidden="true" />
            Stop speaking
          </Button>
        )}
        <label className="flex items-center gap-1.5 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={speakAnswers}
            onChange={(e) => onSpeakAnswersChange(e.target.checked)}
          />
          Speak answers
        </label>
        <label className="flex items-center gap-1.5 text-xs text-slate-700">
          Speed
          <select
            aria-label="Speaking speed"
            value={speechRate}
            onChange={(e) => onSpeechRateChange(Number(e.target.value))}
            className="border-input bg-background rounded border px-1.5 py-0.5 text-xs"
          >
            {RATES.map((rate) => (
              <option key={rate} value={rate}>
                {rate}×
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="text-xs text-slate-500">
        Turn-based: it listens until you stop talking, answers out loud, then listens again. Press{" "}
        <strong>Stop speaking</strong> to interrupt. It does not hear you while it is speaking, and the whole
        exchange appears in the chat above with sources.
      </p>
    </section>
  );
}
