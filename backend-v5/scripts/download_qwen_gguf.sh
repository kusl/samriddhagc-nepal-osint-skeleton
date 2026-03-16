#!/bin/sh
set -eu

MODELS_DIR="${MODELS_DIR:-/models}"
MODEL_FILE="${MODEL_FILE:-Qwen_Qwen3.5-9B-Q4_K_M.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/bartowski/Qwen_Qwen3.5-9B-GGUF/resolve/main/Qwen_Qwen3.5-9B-Q4_K_M.gguf}"
TARGET_PATH="${MODELS_DIR}/${MODEL_FILE}"
PART_PATH="${TARGET_PATH}.part"

mkdir -p "${MODELS_DIR}"

if [ -s "${TARGET_PATH}" ]; then
  echo "Model already present at ${TARGET_PATH}"
  exit 0
fi

echo "Downloading ${MODEL_FILE} ..."
curl -L --fail --retry 5 --retry-delay 5 -C - -o "${PART_PATH}" "${MODEL_URL}"
mv "${PART_PATH}" "${TARGET_PATH}"
echo "Model saved to ${TARGET_PATH}"
