#!/bin/bash
# Local agent runner — uses Claude Max subscription via CLI.
# Optimized for Max 5x: merged briefing (2 Sonnet), batched Haiku, reduced frequencies.
#
# Manual run: ./run_agents.sh briefing|nitter|clustering|tactical|factcheck|all

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/venv/bin/python"
export PATH="/usr/local/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

JOB="${1:-all}"

if [ -z "${OSINT_PASSWORD:-}" ]; then
  echo "Set OSINT_PASSWORD before running local agents."
  exit 1
fi

echo ""
echo "=== $(date) — Running $JOB ==="

case "$JOB" in
  briefing|analyst|province)
    # Merged: analyst + province in 2 Sonnet calls (was 10+)
    "$VENV" "$DIR/run_local_api.py" briefing --hours 6
    ;;
  nitter)
    # Scrapes locally (VPS IP blocked by nitter), POSTs via API
    "$VENV" "$DIR/run_local_api.py" nitter
    ;;
  reddit)
    # Scrapes Reddit locally, POSTs via API (r/nepal, r/nepalstock, r/NepalSocial)
    "$VENV" "$DIR/run_local_api.py" reddit
    ;;
  clustering)
    # Haiku merge via Claude CLI
    "$VENV" "$DIR/run_local_api.py" clustering --hours 48
    ;;
  tactical)
    # Tactical enrichment — Haiku classifies stories for tactical map
    "$VENV" "$DIR/run_local_api.py" tactical --hours 6
    ;;
  factcheck)
    # Fact-check pending stories
    "$VENV" "$DIR/run_local_api.py" factcheck
    ;;
  sigint)
    # SIGINT triage — interpret elevated economic/security signals with Haiku
    "$VENV" "$DIR/run_local_api.py" sigint
    ;;
  sigint-analysis)
    # SIGINT analysis — Sonnet-level intelligence assessment
    "$VENV" "$DIR/run_local_api.py" sigint-analysis
    ;;
  embeddings)
    # Embedding backfill — generate embeddings for un-embedded content
    "$VENV" "$DIR/run_local_api.py" embeddings
    ;;
  promises)
    # Promise tracker — nightly analysis of RSP manifesto against news
    "$VENV" "$DIR/run_promise_tracker.py"
    ;;
  all)
    "$VENV" "$DIR/run_local_api.py" briefing --hours 6
    "$VENV" "$DIR/run_local_api.py" nitter
    "$VENV" "$DIR/run_local_api.py" reddit
    "$VENV" "$DIR/run_local_api.py" embeddings
    "$VENV" "$DIR/run_local_api.py" clustering --hours 48
    "$VENV" "$DIR/run_local_api.py" tactical --hours 6
    "$VENV" "$DIR/run_local_api.py" sigint
    "$VENV" "$DIR/run_local_api.py" sigint-analysis
    "$VENV" "$DIR/run_local_api.py" factcheck
    ;;
  *)
    echo "Usage: $0 {briefing|nitter|reddit|clustering|tactical|factcheck|sigint|sigint-analysis|embeddings|promises|all}"
    exit 1
    ;;
esac

echo "=== $(date) — $JOB done ==="
