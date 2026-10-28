# AI setup (answer generation)

The assistant explains your documents with a **language model**. Documents,
search and citations always stay on your machine. Only the model runs somewhere
you configure. Two ways to get one — pick one.

> Without a model the chat shows an amber banner and refuses to answer. It will
> not paste raw document text and call it an answer (ADR 0009).

## A. Free and local (recommended): Ollama in Docker

Nothing leaves your computer. Needs roughly 2 GB of disk for the default model
and ~3 GB of free RAM (or an NVIDIA GPU with ≥ 3 GB VRAM).

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

## Hardware notes

Measured on the development machine (12 CPU threads, 7.6 GiB RAM visible to
WSL2, RTX 3050 4 GB): see the "Measured" section below once a model has been
run there.
