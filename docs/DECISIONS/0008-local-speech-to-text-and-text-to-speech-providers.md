# 0008. Local, offline speech-to-text and text-to-speech providers (no commercial vendor yet)

**Status:** Accepted
**Date:** 2026-09-25

## Context

GitHub Issue #6 requires "Provider abstractions for STT/TTS + at least
one implementation" and an "ADR recording the selected STT/TTS
vendor(s), per `docs/ARCHITECTURE.md`'s 'no commercial provider
selected yet' rule." Two new provider-abstraction seams exist —
`SpeechToTextProvider` and `TextToSpeechProvider`
(`backend/app/voice/`) — and each has exactly one implementation today,
in both cases a deterministic-enough, offline, dependency-free-of-any-
paid-service local implementation: `PocketSphinxSpeechToTextProvider`
and `EspeakTextToSpeechProvider`. This ADR records that as a real,
deliberate decision, following exactly the same reasoning
[ADR 0007](0007-local-providers-for-embedding-reranking-generation.md)
already recorded for `EmbeddingProvider`/`Reranker`/`LLMProvider`: the
alternative (a real hosted STT/TTS vendor, e.g. a cloud speech API) was
considered and explicitly deferred, for the reasons below — not an
oversight.

The same execution constraints apply here directly: the voice flow must
be buildable, testable (including in CI, which has no network egress to
a paid API and no API key provisioned), and demoable without a paid
external service or a provisioned secret. A commercial STT/TTS vendor
also has real cost, quota, latency-variance, and data-handling
implications (sending recorded audio — a more sensitive payload than
text — to a third party) that deserve a deliberate evaluation, not a
default reached mid-slice.

## Decision

**For this phase of the project, `SpeechToTextProvider` and
`TextToSpeechProvider` both use local, offline implementations — no
commercial STT/TTS vendor is selected.** Each provider's shape is
deliberately generic (a `Protocol` plus a settings-driven factory,
`get_speech_to_text_provider()`/`get_text_to_speech_provider()`,
matching `get_embedding_provider()`'s exact pattern) so a real hosted
provider can be added later as an additive change (implement the
protocol, add a branch to the factory) without touching any caller —
this ADR does not close that door, it documents why it isn't taken yet.

- `SpeechToTextProvider` → `PocketSphinxSpeechToTextProvider`
  (`backend/app/voice/stt_provider.py`): CMU PocketSphinx, via the
  `SpeechRecognition` package, run entirely offline — no API key, no
  network call, no separate model download (the package ships its own
  default English acoustic/language model).
- `TextToSpeechProvider` → `EspeakTextToSpeechProvider`
  (`backend/app/voice/tts_provider.py`): shells out to the `espeak-ng`
  command-line tool (`-w <file>` writes a WAV file directly) as a
  subprocess — offline, no API key, no network call. `espeak-ng` is
  installed as a system package (`infra/docker/backend.Dockerfile`,
  `.github/workflows/ci.yml`), not a Python dependency, matching how the
  project already treats other non-Python runtime dependencies (e.g.
  Postgres/Redis themselves are services, not vendored). An earlier
  version of this provider used the `pyttsx3` Python bindings instead —
  see "Consequences" below for why that was replaced with a direct
  subprocess call during this same implementation.

## Alternatives considered

- **A real hosted STT API (e.g. a cloud speech-to-text service) for
  `SpeechToTextProvider`** — rejected for this phase: requires
  provisioning and securing a paid API key (none configured, and CI has
  no network egress to reach one), introduces real per-call cost and
  latency variance, and would send recorded user audio to a third party
  by default — a materially more sensitive payload than the text this
  project already sends nowhere external. Not ruled out permanently —
  the protocol and factory exist specifically so this can be added later
  behind a config flag, once a vendor and its cost/latency/data-handling
  trade-offs are deliberately evaluated.
- **A real hosted TTS API for `TextToSpeechProvider`** — rejected for
  the same reasons.
- **A local neural ASR model (e.g. Whisper-family) for
  `SpeechToTextProvider`** — considered and rejected for this phase:
  meaningfully better transcription accuracy than PocketSphinx, but
  requires either downloading and bundling a model file (a new build-
  time/runtime dependency this project's other local providers
  deliberately avoid — `LocalHashingEmbeddingProvider`/
  `LexicalOverlapReranker` are dependency-free specifically so the
  pipeline needs nothing beyond `pip install`) or a heavier inference
  runtime, disproportionate to this project's modular-monolith,
  no-premature-infrastructure stance (ADR 0001) for a non-critical,
  fast-follow feature (Issue #6 explicitly instructs "no unnecessarily
  complex real-time audio architecture"). PocketSphinx needs neither: it
  installs from a prebuilt wheel with its default model already
  included.
- **Browser-only Web Speech API (client-side STT/TTS, no backend
  provider at all)** — considered and rejected as the *sole*
  implementation: Issue #6 explicitly requires backend
  `SpeechToTextProvider`/`TextToSpeechProvider` abstractions wired
  through the existing `/api/v1/conversations` call path (not a
  browser-only feature), and relying solely on a proprietary browser API
  would make the feature's correctness untestable server-side and
  unavailable in non-Chromium browsers. A backend-mediated flow (audio
  uploaded → transcribed → same text pipeline → answer synthesized on
  demand) is used instead.
- **Leaving the Definition-of-Done requirement unmet / skipping this
  ADR** — rejected: the requirement exists precisely so a "no vendor
  chosen yet" state is a recorded, deliberate decision rather than an
  implicit gap nobody signed off on.

## Consequences

- The voice flow is fully self-contained: no paid API key required to
  build, test (including in CI), or demo the complete audio-in →
  transcript → grounded-answer → audio-out flow end-to-end.
- **Transcription accuracy is materially weaker than a modern hosted or
  neural-model ASR system**, especially against synthetic (text-to-
  speech-generated) audio rather than real human speech — empirically
  verified during implementation: PocketSphinx transcribed some short
  test phrases exactly and others quite inaccurately when fed
  `espeak`-synthesized audio. This is an accepted, documented limitation
  of this phase (mirroring `LocalHashingEmbeddingProvider`'s own
  documented semantic-weakness trade-off), not a defect to be silently
  worked around. Automated tests are designed around this reality —
  they assert the provider's *contract* (returns a string; handles
  silence/unrecognizable audio by returning an empty transcript, not
  crashing; rejects an unsupported format) and use a small set of
  phrases empirically confirmed to round-trip correctly through this
  exact TTS→STT pipeline, rather than asserting general-purpose
  transcription accuracy.
- **Synthesized speech is robotic** (espeak's own voice, not a natural-
  sounding one) — an accepted, documented limitation, not a defect.
- Only WAV audio is accepted as STT input — the frontend is responsible
  for encoding recorded audio to WAV client-side before upload
  (`frontend/lib/wav-encoder.ts`), the same "validate/normalize at the
  boundary" precedent as document upload's extension/MIME/magic-byte
  checks (Issue #3).
- **A genuine implementation-time finding**: the `pyttsx3` Python
  bindings to `espeak-ng` were tried first, but repeated `synthesize()`
  calls within one process — including calls landing on different
  `asyncio.to_thread()` worker threads — corrupted `pyttsx3`'s internal
  callback/proxy state (`ReferenceError: weakly-referenced object no
  longer exists`), sometimes producing a truncated/empty audio file;
  this reproduced even when constructing a fresh `pyttsx3.Engine(...)`
  per call rather than reusing `pyttsx3.init()`'s process-wide cached
  instance, so the fault sits deeper than simple instance reuse.
  `EspeakTextToSpeechProvider` instead shells out to the `espeak-ng`
  binary directly as an independent subprocess per call — no shared
  Python-level state between calls at all, and empirically reliable
  across repeated and concurrent-thread calls. This is also simpler (one
  fewer Python dependency) than the `pyttsx3` binding it replaced.
- **What would trigger revisiting this decision**: a demonstrated need
  for materially better transcription accuracy or a more natural voice,
  a measured user-facing quality gap, or an explicit product decision to
  accept the cost/dependency trade-off of a commercial vendor. Any such
  change should land as its own focused ADR (superseding the relevant
  part of this one), not a silent swap.
