# AI setup (answer generation)

The assistant explains your documents with a **language model**. Documents,
search and citations always stay on your machine. Only the model runs somewhere
you configure. Two ways to get one — pick one.

> Without a model the chat shows an amber banner and refuses to answer. It will
> not paste raw document text and call it an answer (ADR 0009).

## A. Free and local (recommended): Ollama in Docker

Nothing leaves your computer. Download size: the Ollama Docker image (~3–4 GB; its
biggest layer alone is ~3.2 GB) plus the default model (1.9 GB). Needs ~3 GB of free
RAM, or an NVIDIA GPU with ≥ 3 GB VRAM.

```bash
infra/scripts/setup-local-llm.sh            # CPU
USE_GPU=1 infra/scripts/setup-local-llm.sh  # NVIDIA GPU (Docker Desktop + WSL2)
```

The script starts the `ollama` service (compose profile `llm`), downloads
`qwen2.5:3b-instruct` (1.9 GB), creates a derived model `rag-assistant` with an
8192-token context, and restarts the backend. Then open
http://localhost:3000/chat — the banner disappears when the model is ready.

| Choice | Command | Notes |
|---|---|---|
| Default | (above) | Good for explaining short programs and notes. Weaker than hosted models. |
| Bigger | `BASE_MODEL=qwen2.5:7b-instruct infra/scripts/setup-local-llm.sh` | 4.7 GB download. On a 4 GB GPU it spills to CPU and is slow. |

Check it from a terminal: `docker compose -f infra/compose/docker-compose.yml --profile llm exec ollama ollama list`.

## B. A model server you already run, or a hosted provider

Set these (in `.env` next to `docker-compose.yml`, or in your environment) and
`docker compose -f infra/compose/docker-compose.yml up -d backend`:

```
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://host.docker.internal:11434/v1   # e.g. Ollama/LM Studio on the host
LLM_MODEL=<model name as the server calls it>
LLM_API_KEY=<only for hosted providers>
```

**Privacy / cost:** a *hosted* provider receives your question, the recent
conversation and the retrieved document passages, and may charge per use. This
project never selects one for you.

## Speech recognition (microphone)

The microphone button records, transcribes on your computer, and puts the text in
the question box so you can fix it before pressing **Ask**. It uses a free local
model (Whisper "small") that you install once:

```bash
infra/scripts/setup-local-stt.sh                 # ~460 MB download (default: small)
STT_MODEL=base infra/scripts/setup-local-stt.sh  # ~145 MB: faster, less accurate
```

Until it is installed, the microphone shows "The speech model is not installed";
nothing downloads by itself. Choose the spoken language under *Voice settings*
(auto-detect is the default; setting it explicitly helps with accents).
Technical words from your own documents (program titles, file names) are given to
the recogniser as hints.

Optional hosted/self-hosted speech (**sends your recordings away**): set
`SPEECH_TO_TEXT_PROVIDER=openai_compatible`, `STT_BASE_URL`, `STT_MODEL` and, if
needed, `STT_API_KEY`.

Measured (CPU, 12 threads, Whisper small int8): ≈ 3 s to transcribe a 4 s
question (≈ 6 s for the very first one, which loads the model). Accuracy on
synthetic espeak speech: "Explain program number five" → exactly right; "bubble
sort" was misheard as "verbal sort" without the workspace hint and right with it.
Real human voices and accents are not covered by any automated test.

## Settings

`LLM_TIMEOUT_SECONDS` (180), `LLM_TEMPERATURE` (0.2), `LLM_MAX_OUTPUT_TOKENS`
(1200), `LLM_CONTEXT_MAX_CHARS` (6000 of evidence per question),
`LLM_HISTORY_TURNS` (6). See `.env.example`.

## Troubleshooting

| Message | Meaning / fix |
|---|---|
| "No AI model is set up" | `LLM_PROVIDER=extractive`. Use setup A or B. |
| "model server cannot be reached" | Ollama isn't running: `docker compose -f infra/compose/docker-compose.yml --profile llm up -d ollama`. |
| "model … was not found" | `ollama pull` it (run the setup script again) or fix `LLM_MODEL`. |
| "took too long" | CPU is slow for this model: use the GPU overlay, a smaller model, or raise `LLM_TIMEOUT_SECONDS`. |
| "rejected the credentials" | Wrong `LLM_API_KEY` for a hosted provider. |

## Measured on the development machine

12 CPU threads, 7.6 GiB RAM visible to WSL2, NVIDIA RTX 3050 Laptop (4 GB VRAM),
Docker Desktop + WSL2, `USE_GPU=1`, model `rag-assistant` (qwen2.5:3b-instruct, 8192-token
context):

- Ollama runs the model **100 % on the GPU**: 2.3 GB of the 4 GB VRAM including the
  context window; first request after a cold start ≈ 6 s (model load).
- A full explanation of a one-page program: **≈ 7–17 s**. A "line by line" request makes
  one extra short call per 6 code lines (≈ 6 s for an 11-line program). A question whose
  answer is absent ("Program 9" when the document has 1–4) is answered instantly (no model
  call).
- Quality of this 3B model on synthetic C/MPI lab programs: correct program-level
  explanations and correct reproduction of the program's output, but occasional factual
  slips in the *prose* (for example it once said an array was printed "on a new line" when the
  code prints space-separated). Code shown in answers is checked against the document
  (`app/generation/fidelity.py`), the prose is not. Treat explanations as a study aid, not as
  ground truth. A larger or hosted model is more reliable; see option B above.

CPU-only runs have not been measured.
