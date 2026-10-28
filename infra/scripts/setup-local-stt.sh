#!/usr/bin/env bash
# One-time installation of the free, local speech-recognition model.
#
#   infra/scripts/setup-local-stt.sh                 # default model: small (~460 MB)
#   STT_MODEL=base infra/scripts/setup-local-stt.sh  # smaller/faster (~145 MB), less accurate
#   STT_MODEL=medium infra/scripts/setup-local-stt.sh   # ~1.5 GB, most accurate, slower
#
# Downloads from Hugging Face into the dedicated `stt_models` volume. Run it
# deliberately: nothing else ever downloads a speech model. Safe to re-run;
# touches no database or document data.
set -euo pipefail

cd "$(dirname "$0")/../.."
MODEL="${STT_MODEL:-small}"
COMPOSE=(docker compose -f infra/compose/docker-compose.yml)

echo "==> Making sure the backend is running"
STT_MODEL="${MODEL}" "${COMPOSE[@]}" up -d backend

echo "==> Downloading speech model '${MODEL}' (needs internet)"
"${COMPOSE[@]}" exec -T -e STT_MODEL="${MODEL}" backend .venv/bin/python -m app.voice.download_model

echo "==> Done. Open http://localhost:3000/chat and use the microphone button."
echo "    If you chose a model other than 'small', also set STT_MODEL=${MODEL} for the backend (see docs/AI_SETUP.md)."
