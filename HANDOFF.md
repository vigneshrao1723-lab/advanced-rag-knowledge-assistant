# HANDOFF.md

Short-term continuation state. This file always reflects the **current**
in-flight task — overwrite it as work progresses, don't append a history
(that's what `CHANGELOG.md` and Git history are for).

---

## Current task

**Owner-acceptance fixes ([Issue #53](https://github.com/vigneshrao1723-lab/advanced-rag-knowledge-assistant/issues/53)) — implemented and merged, waiting for the owner to test.**

The owner found the app not release-ready (raw PDF text instead of
explanations, inaccurate speech recognition, no conversational voice). Four
cycles are on `main` (`24bfd77`): #54 real generation provider + honest
unavailable-model UX, #55 program/document resolution + code fidelity + line-by-line
+ OR lexical search, #56 local Whisper speech-to-text + review-before-send
dictation, #57 turn-based voice conversation. ADRs 0009–0011, `docs/AI_SETUP.md`.

**Nothing here is "accepted" until the owner says so.** Automated results and my
own real-browser/real-model runs are evidence, not acceptance.

## Owner acceptance checklist

The local stack is running (http://localhost:3000). The free local model
(`rag-assistant`, qwen2.5:3b-instruct on the GPU) and the speech model (Whisper
small) are already installed on this machine. If the chat shows an amber banner
"AI model is not available", start it: `docker compose -f infra/compose/docker-compose.yml
-f infra/compose/docker-compose.gpu.yml --profile llm up -d ollama` (see
`docs/AI_SETUP.md`). First answer after idle takes a few seconds longer (model load).

**Stage 1 — explanations (the main complaint).**
1. Open **Documents**, delete the old `PC_LAB_TEST.pdf` and **upload it again**
   (old copies keep the old flattened code). Wait for READY.
2. In **Chat → New conversation** ask, one at a time (each takes ~8–17 s):
   - `Explain Program 5.` → a structured explanation (what it does / how it works /
     output / key concepts) **and** the original code, correctly indented, in a
     code block, with a source chip "PC_LAB_TEST.pdf · page 1". Is it understandable
     and correct against the PDF? Note any wrong statement.
   - `Explain program number 7 line by line` → every code line with a short explanation.
   - `Explain the first program in my PC lab PDF` → Program 5 (the first one in that file).
   - `Explain Program 1` → an **instant** reply that Program 1 isn't there and the
     file has Programs 5–9 (no explanation invented).
   - then, in the same chat: `Explain it as a beginner`, `Give me a short exam-ready
     explanation`, `What output does this program produce?` (follow-ups).
   - `What is the capital of France?` → says it doesn't have that information (no citations).
3. Click a citation → it shows the exact source passage; "View in document" highlights it.

**Stage 2 — dictation (Voice input).**
4. Click **Voice input**, allow the microphone, say "Explain program number five",
   click **Stop recording**. The text appears in the question box (not sent).
   Fix a word, press **Ask**. Try a technical phrase from your PDF (e.g. "MPI broadcast").
5. Try **Cancel**, and silence (should say no sound was captured). Under *Voice
   settings* pick your language/microphone. Does it understand *your* voice?
   (This is the part I could not test: please report misheard words verbatim.)

**Stage 3 — Voice conversation.**
6. Click **Voice conversation**, ask "Explain program number six". Expect:
   Listening → Transcribing → Thinking → Speaking, then Listening again. Press
   **Stop speaking** mid-answer, then ask "explain that line by line". Press **End
   conversation**. Is the spoken voice acceptable (Windows voice vs robotic)? Is
   the delay (≈15–25 s per turn) tolerable? It is turn-based, not realtime.

**Stage 4 — layout.** Narrow the window to phone width: composer buttons wrap, no
sideways scrolling, code blocks scroll inside their box.

**Send back, for anything that fails:** the step number, what you did/saw, a
screenshot, the exact question or what you said, and (for voice) which browser. For
wrong explanations, paste the answer and say what is wrong.

## What is NOT done / known limits (do not assume otherwise)

- Not validated with real human voices, accents, noisy rooms or the browser's Windows
  voices; only synthetic speech through a real browser capture path.
- Voice conversation is turn-based (no talk-over, no streaming); the 3B model makes
  occasional factual slips in prose (the code shown is verified against the document,
  the prose is not).
- Hosting is still undecided and the earlier recommendation no longer fits as-is:
  production needs a hosted OpenAI-compatible LLM or a GPU host and ≥ 4 GiB RAM for
  the backend with local Whisper (`docs/PRODUCTION_READINESS.md` "Deployment impact").
- Still open from the release audit: Redis-outage event-loop stall, security response
  headers, no committed Playwright spec for the newer UI.

## Blockers

Owner acceptance. No technical blocker.

## Tests run (this phase)

Backend 981 passed + 2 skipped (inside the image; includes real `espeak-ng` voice
tests and the opt-in real Whisper tests), `ruff`/`mypy` clean. Frontend 181/181,
lint/tsc/build clean. Playwright 21/21 against the live stack with the real model.
30-check browser UI regression 29/30 (expected pre-login 401). Real headless-Chromium
voice runs (fake microphone from audio files): dictation, silence, cancel, full
conversation loop. CI green on every merged PR.

## Exact next recommended action

1. Owner runs the checklist above and reports.
2. Fix whatever fails (use the normal branch/PR/CI flow; reproduce first).
3. Only then: the hosting decision.
