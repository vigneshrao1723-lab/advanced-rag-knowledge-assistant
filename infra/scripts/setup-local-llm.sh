#!/usr/bin/env bash
# One-time setup of the free, local AI model used for answer generation.
#
#   infra/scripts/setup-local-llm.sh                 # default: qwen2.5:3b-instruct (~1.9 GB download)
#   BASE_MODEL=qwen2.5:7b-instruct infra/scripts/setup-local-llm.sh   # better, ~4.7 GB, slow without a big GPU
#
# Downloads a model (needs disk + bandwidth) -- run it deliberately, it is not
# started automatically. Safe to re-run. Never touches the database or volumes
# other than the dedicated `ollama_models` volume.
set -euo pipefail

cd "$(dirname "$0")/../.."
COMPOSE=(docker compose -f infra/compose/docker-compose.yml)
if [[ "${USE_GPU:-0}" == "1" ]]; then
  COMPOSE+=(-f infra/compose/docker-compose.gpu.yml)
fi
BASE_MODEL="${BASE_MODEL:-qwen2.5:3b-instruct}"
DERIVED_MODEL="${LLM_MODEL:-rag-assistant}"

echo "==> Starting the Ollama service (profile: llm)"
"${COMPOSE[@]}" --profile llm up -d ollama

echo "==> Waiting for Ollama to answer"
for _ in $(seq 1 60); do
  if "${COMPOSE[@]}" --profile llm exec -T ollama ollama list >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "==> Pulling base model: ${BASE_MODEL}"
"${COMPOSE[@]}" --profile llm exec -T ollama ollama pull "${BASE_MODEL}"

echo "==> Creating '${DERIVED_MODEL}' (base ${BASE_MODEL}, 8192-token context)"
printf 'FROM %s\nPARAMETER num_ctx 8192\n' "${BASE_MODEL}" |
  "${COMPOSE[@]}" --profile llm exec -T ollama sh -c 'cat > /tmp/Modelfile && ollama create '"${DERIVED_MODEL}"' -f /tmp/Modelfile'

echo "==> Restarting the backend so it re-checks the model"
"${COMPOSE[@]}" up -d backend

echo "Done. Open http://localhost:3000/chat - the 'AI model' banner disappears when the model is ready."
