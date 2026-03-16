# Agents

This folder keeps the repo surface clean by grouping the top-level operational entrypoints in one place.

- The real implementations live under `backend-v5/`.
- The Python files here are thin wrappers that delegate to the canonical backend scripts.
- `run_agents.sh` delegates to `backend-v5/run_agents.sh`.

Use this folder for local runner entrypoints that you want easy to find without cluttering the repo root.
