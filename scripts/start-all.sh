#!/usr/bin/env bash
set -euo pipefail

MODEL_FILE="${LLAMA_CPP_MODEL_FILE:-}"
if [[ -z "${MODEL_FILE}" && -f .env ]]; then
  MODEL_FILE="$(awk -F= '$1 == "LLAMA_CPP_MODEL_FILE" { print $2; exit }' .env)"
fi
MODEL_FILE="${MODEL_FILE:-qwen3-1.7b-q4_k_m.gguf}"

mkdir -p models

if [[ ! -f "models/${MODEL_FILE}" ]]; then
  echo "Warning: models/${MODEL_FILE} is missing. llama-cpp will not serve enrichments until this GGUF file exists."
fi

docker compose up --build --detach postgres rabbitmq llama-cpp migrate backend-api ingester enricher dashboard
