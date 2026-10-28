"use client";

import { Loader2, Mic, Settings2, Square, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { VOICE_LANGUAGES, type UseVoiceInput } from "@/lib/use-voice-input";

function formatTime(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

/** The microphone control that lives next to the "Ask" button. */
export function VoiceInputButton({ voice, disabled }: { voice: UseVoiceInput; disabled?: boolean }) {
  if (voice.phase === "recording") {
    return (
      <Button type="button" variant="destructive" onClick={() => void voice.stop()}>
        <Square className="size-4" aria-hidden="true" />
        Stop recording
      </Button>
    );
  }
  if (voice.phase === "transcribing") {
    return (
      <Button type="button" variant="outline" disabled>
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Transcribing…
      </Button>
    );
  }
  return (
    <Button
      type="button"
      variant="outline"
      disabled={disabled}
      onClick={() => void voice.start()}
      aria-label="Voice input"
    >
      <Mic className="size-4" aria-hidden="true" />
      Voice input
    </Button>
  );
}

/** Recording state, level meter, transcript hint, errors and settings. */
export function VoiceInputPanel({
  voice,
  transcriptHint,
}: {
  voice: UseVoiceInput;
  transcriptHint: boolean;
}) {
  const [showSettings, setShowSettings] = useState(false);
  const bars = 12;
  const active = Math.round(voice.level * bars);

  return (
    <div className="flex flex-col gap-2">
      {voice.phase === "recording" && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
        >
          <span className="relative flex size-2.5" aria-hidden="true">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-red-500 opacity-60" />
            <span className="relative inline-flex size-2.5 rounded-full bg-red-600" />
          </span>
          <span className="font-medium">Listening… speak now</span>
          <span className="tabular-nums" aria-label="Recording time">
            {formatTime(voice.elapsedSeconds)}
          </span>
          <span className="flex h-4 items-end gap-0.5" aria-hidden="true">
            {Array.from({ length: bars }, (_, i) => (
              <span
                key={i}
                className={`w-1 rounded-sm ${i < active ? "bg-red-600" : "bg-red-200"}`}
                style={{ height: `${30 + (i / bars) * 70}%` }}
              />
            ))}
          </span>
          <span className="ml-auto flex gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => voice.cancel()}>
              <X className="size-3.5" aria-hidden="true" />
              Cancel
            </Button>
          </span>
        </div>
      )}
      {voice.phase === "transcribing" && (
        <div
          role="status"
          className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700"
        >
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Transcribing your speech…
          <Button type="button" size="sm" variant="outline" className="ml-auto" onClick={() => voice.cancel()}>
            Cancel
          </Button>
        </div>
      )}
      {voice.phase === "idle" && transcriptHint && !voice.error && (
        <p role="status" className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
          Review what was heard in the box above, fix anything that is wrong, then press <strong>Ask</strong>.
        </p>
      )}
      {voice.error && (
        <p role="alert" className="flex items-start justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          <span>{voice.error}</span>
          <button type="button" className="shrink-0 underline" onClick={voice.clearError}>
            Dismiss
          </button>
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <button
          type="button"
          onClick={() => setShowSettings((value) => !value)}
          aria-expanded={showSettings}
          aria-controls="voice-settings"
          className="inline-flex items-center gap-1 rounded px-1.5 py-1 hover:bg-slate-100"
        >
          <Settings2 className="size-3.5" aria-hidden="true" />
          Voice settings
        </button>
      </div>
      {showSettings && (
        <div id="voice-settings" className="flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 p-3 text-sm">
          <div className="flex flex-col gap-1">
            <label htmlFor="voice-language" className="text-xs font-medium">
              Spoken language
            </label>
            <select
              id="voice-language"
              value={voice.language}
              disabled={voice.phase !== "idle"}
              onChange={(e) => voice.setLanguage(e.target.value)}
              className="border-input bg-background rounded-md border px-2 py-1.5 text-sm"
            >
              {VOICE_LANGUAGES.map((language) => (
                <option key={language.code} value={language.code}>
                  {language.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="voice-device" className="text-xs font-medium">
              Microphone
            </label>
            <select
              id="voice-device"
              value={voice.deviceId}
              disabled={voice.phase !== "idle"}
              onChange={(e) => voice.setDeviceId(e.target.value)}
              className="border-input bg-background max-w-[18rem] rounded-md border px-2 py-1.5 text-sm"
            >
              <option value="">System default</option>
              {voice.devices
                .filter((device) => device.deviceId && device.deviceId !== "default")
                .map((device, index) => (
                  <option key={device.deviceId} value={device.deviceId}>
                    {device.label || `Microphone ${index + 1}`}
                  </option>
                ))}
            </select>
          </div>
          <p className="text-xs text-slate-500">
            Tip: set the language if auto-detect mixes up accents. Speech is recognised on this
            computer unless an administrator configured a hosted speech service.
          </p>
        </div>
      )}
    </div>
  );
}
