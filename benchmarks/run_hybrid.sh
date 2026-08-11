#!/bin/bash
# Hybrid benchmark: local 7b breadth + frontier judgment (plan/arbitrate/synthesize).
# Usage: bash benchmarks/run_hybrid.sh [target]
#   target: optional R1_vulpy | R2_dvpwa | R4_pygoat | R3_aiohttp (default: all)
#
# The frontier provider is the "judgment" model:
#   - DeepSeek (default): real frontier-class, key from $DEEPSEEK_API_KEY
#   - Ollama-9b: local "frontier" for offline testing
#   - edge: Cloudflare Workers AI (30B @cf/qwen) — production target, currently
#     returning empty content (availability), swap when healthy
set -e
cd "$(dirname "$0")/.."

TARGET="${1:-}"
EXP_TAG="${RGI_HYBRID_TAG:-hybrid-deepseek}"
FRONTIER_PROVIDER="${RGI_FRONTIER_PROVIDER:-deepseek}"

case "$FRONTIER_PROVIDER" in
  deepseek)
    export RGI_FRONTIER_PROVIDER=deepseek
    export RGI_FRONTIER_BASE_URL="${RGI_FRONTIER_BASE_URL:-https://api.deepseek.com/v1}"
    export RGI_FRONTIER_MODEL="${RGI_FRONTIER_MODEL:-deepseek-chat}"
    export RGI_FRONTIER_API_KEY="${RGI_FRONTIER_API_KEY:-$DEEPSEEK_API_KEY}"
    ;;
  ollama)
    export RGI_FRONTIER_PROVIDER=ollama
    export RGI_FRONTIER_BASE_URL="http://localhost:11434/v1"
    export RGI_FRONTIER_MODEL="${RGI_FRONTIER_MODEL:-qwen3.5:9b}"
    export RGI_FRONTIER_API_KEY="ollama"
    ;;
  edge)
    export RGI_FRONTIER_PROVIDER=edge
    export RGI_FRONTIER_BASE_URL="https://rlmlocal-mcp.fortsignal.workers.dev"
    export RGI_FRONTIER_MODEL="@cf/qwen/qwen3-30b-a3b-fp8"
    ;;
esac

if [ -z "$RGI_FRONTIER_API_KEY" ] && [ "$FRONTIER_PROVIDER" != "ollama" ]; then
  echo "ERROR: RGI_FRONTIER_API_KEY unset (or DEEPSEEK_API_KEY for deepseek)" >&2
  exit 1
fi

echo "=== HYBRID benchmark: local 7b + frontier($FRONTIER_PROVIDER / $RGI_FRONTIER_MODEL) ==="
echo "=== targets: ${TARGET:-all 4} · tag: $EXP_TAG ==="

env RGI_LLM_MODEL="${RGI_LLM_MODEL:-qwen2.5:7b}" \
    RGI_RLMLocal_PERCEPTION=1 \
    RGI_C2_EXP_TAG="$EXP_TAG" \
    RGI_C2_CONDITIONS="${RGI_C2_CONDITIONS:-hybrid}" \
    ${TARGET:+RGI_C2_TARGETS="$TARGET"} \
    RGI_FRONTIER_ENABLED=1 \
    python -m benchmarks.run_real
