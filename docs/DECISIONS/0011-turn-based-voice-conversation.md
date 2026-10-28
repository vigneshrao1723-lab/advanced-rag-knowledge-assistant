# 0011. Turn-based voice conversation (not full-duplex realtime)

**Status:** Accepted
**Date:** 2026-10-28

## Context

The owner asked for two voice experiences: simple dictation (ADR 0010) and a
separate full conversational mode with spoken answers, natural turn-taking,
interruption and recovery, on the existing authenticated RAG pipeline, local
where practical, with no mandatory paid realtime API and no silent third-party
audio. "Full-duplex realtime" (talk over the assistant, sub-second streaming)
needs streaming speech recognition, streaming generation, streaming synthesis
and echo cancellation between speaker and microphone. None of that exists in the
local stack: Whisper-small on CPU is offline/batch (≈3 s per utterance), the 3B
model answers in 7–17 s (no streaming endpoint is wired up), and speaker→mic echo
cannot be removed reliably in a browser tab.

## Decision

1. Implement the best **reliable turn-based** loop and say so in the UI and docs:
   listen → transcribe → ask the normal chat pipeline → speak → listen again.
   It is **not** full-duplex and must not be described as realtime.
2. **Listening** ends by itself when you stop talking (energy-based voice-activity
   detection with a capped noise-floor estimate, 1.4 s of silence after at least
   ~240 ms of speech), or when you press "I'm done talking"; a 12 s no-speech
   timeout re-listens and gives up after three quiet turns; a turn is capped at
   60 s. The microphone is **closed while the assistant speaks** so it cannot hear
   itself.
3. **Interruption** is the "Stop speaking" button (speech stops immediately and it
   listens again) and "End conversation". Barge-in by voice is deliberately not
   offered (it would trigger on the assistant's own voice).
4. **Speaking** uses a `Speaker` abstraction: the browser's speech synthesis,
   restricted to voices that run on the computer (`localService`), else the
   server's espeak audio. Hosted browser voices are not used because they send the
   text to a server. Spoken text is a *speakable* version of the answer
   (`speakable_text` / `lib/speakable.ts`): code is replaced by "The code is shown
   on screen.", Markdown and citation markers are removed, long reference sections
   are skipped, and the length is capped. The same function now feeds the existing
   "Play answer" button.
5. **No new server-side state or endpoints.** The conversation reuses
   `POST …/transcriptions` and `POST …/conversations/{id}/messages`, so
   authentication, workspace scoping, rate limits, retrieval, history, citations
   and source inspection are exactly those of typed chat; turns appear in the
   ordinary thread.
6. **Recovery:** microphone, transcription and model errors stop the loop with a
   specific message and "Try again"; a failed answer is retried *without*
   re-recording; unspeakable answers (no voice) carry on with a notice; ending
   aborts in-flight requests and ignores late results.
7. **Seams for a future realtime adapter:** `Speaker` and the injected `deps`
   (recorder, transcriber, ask, speakers) in `useVoiceConversation` are the points
   where a streaming backend (e.g. a realtime provider, or streaming STT/TTS)
   would plug in without touching the UI.

## Alternatives considered

- **A hosted realtime voice API** — rejected as mandatory (paid, sends audio and
  document excerpts to a third party). It can be added behind the seams above by
  explicit configuration.
- **Browser `SpeechRecognition`/cloud voices** — send audio/text to third parties.
- **Barge-in with echo cancellation** — not reliable in a browser tab with
  speakers; a half-working version is worse than a clear button.
- **Streaming the LLM answer so speech starts sooner** — the right next step for
  latency, but a larger change to the generation API.

## Consequences

- Each turn costs ≈ 3 s (transcribe) + 7–17 s (answer on the GPU) + speaking time;
  it feels like a walkie-talkie, not a phone call.
- Voice-activity detection is energy-based: loud, steady background noise can keep
  the turn open (use "I'm done talking") and very quiet speakers may need to move
  closer. Calibrated only against synthetic audio.
- The browser needs an installed local voice for natural speech; otherwise the
  robotic server voice is used.
