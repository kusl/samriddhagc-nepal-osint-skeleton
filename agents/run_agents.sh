#!/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$DIR/../backend-v5/run_agents.sh" "$@"
