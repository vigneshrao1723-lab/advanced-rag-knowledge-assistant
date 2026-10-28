# 0010. Local neural speech-to-text, and review-before-send dictation

**Status:** Accepted
**Date:** 2026-10-28
**Supersedes in part:** [ADR 0008](0008-local-speech-to-text-and-text-to-speech-providers.md) (the STT choice only)

## Context

The owner reported that speech recognition "does not accurately understand
spoken words". Tracing the path: browser capture (`getUserMedia` →
`MediaRecorder` → decode → 16-bit WAV at the device's native rate) and the
backend WAV handling are sound. The cause is the engine: PocketSphinx is a
1990s-style HMM recogniser with a generic acoustic model; ADR 0008 already
recorded it as "materially weaker than a modern neural ASR". In an earlier test
it turned the spoken sentence into unrelated words. A second problem is product
design: the transcript went straight to the assistant (`voice-messages`), so a
mis-heard word silently became the question and could not be corrected.

Constraints from the owner: free and local by default, hosted providers only by
explicit configuration, audio and documents never sent to a third party
silently, no mandatory paid service.

## Decision

1. Add `WhisperSpeechToTextProvider` (faster-whisper / CTranslate2, CPU int8):
   free, offline, one model per process, `SPEECH_TO_TEXT_PROVIDER=faster_whisper`.
   Default model `small` (multilingual, ~460 MB). PocketSphinx remains as the
   code default (`local`) so existing setups and the offline test suite keep
   working; Docker Compose selects Whisper.
2. **The model is never downloaded during a request.** A first-use download of
   hundreds of MB inside an HTTP request would hang the UI and is a hidden
   network side effect. `infra/scripts/setup-local-stt.sh`
   (`python -m app.voice.download_model`) is the only code path that downloads;
   until it has run, transcription fails fast with `503 stt_unavailable` and the
   capabilities endpoint reports `model_not_downloaded`.
3. Optional `OpenAICompatibleSpeechToTextProvider` (`/audio/transcriptions`) for
   a self-hosted faster-whisper server or a hosted provider. **The recording
   leaves the machine**; it is off unless configured.
4. A transcription-only endpoint, `POST /workspaces/{id}/transcriptions`
   (MEMBER role, same rate limit as voice messages). It returns the text and
   creates nothing. The UI puts the transcript into the editable question box
   and the user presses Ask. Empty or failed transcriptions are never submitted.
   The old `voice-messages` endpoint is kept for API compatibility but unused by
   the UI.
5. The browser sends 16 kHz mono WAV (what the model uses internally; 3–6x
   smaller), refuses silent/too-short recordings before uploading, supports input
   device selection and a language hint, and discards results that arrive after
   the user cancelled.
6. **Workspace vocabulary hint.** Program titles and filenames from the caller's
   *own* workspace are passed as the recogniser's prompt (`Terms: Bubble sort, …`).
   Measured: without it "bubble sort" was heard as "verbal sort"; with it
   correctly. Only titles/filenames (already visible to the user), never body
   text, and never another workspace's terms.
7. Audio and transcript text are never logged (only duration, latency, language).

## Alternatives considered

- **Browser `SpeechRecognition` (Web Speech API)** — in Chrome it streams audio
  to Google's servers, violating "nothing leaves the machine silently".
- **Vosk / other small offline models** — lighter but noticeably less accurate
  than Whisper `small` on technical English and accents.
- **Whisper on the GPU** — the 4 GB GPU is used by the language model; CPU int8
  Whisper `small` is fast enough (≈3 s for a 4 s utterance) and needs no CUDA
  libraries in the image.
- **Auto-download on first use** — rejected (hidden multi-hundred-MB download).
- **Keep sending the transcript straight to the assistant** — rejected: no
  chance to correct mistakes.

## Consequences

- Image grows by ~170 MB of Python wheels (CTranslate2, ONNX Runtime, PyAV,
  tokenizers) and the first setup downloads ~460 MB. `huggingface-hub` is pinned
  `<2` because 2.x pulls in `httpx2`, which silently changes Starlette's test
  client and the project's HTTP stack.
- Accuracy is far better than PocketSphinx but not perfect: measured only with
  synthetic (espeak) speech and a real browser capture path. Real human voices,
  accents and noisy rooms have **not** been measured here.
- Whisper can hallucinate on near-silence; mitigated by the browser's silence
  check, a VAD filter and a `no_speech_prob` cut-off, not eliminated.
