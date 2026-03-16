#!/usr/bin/env python3
"""Run a canonical backend-v5 script from the top-level agents folder."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main(script_name: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "backend-v5" / script_name
    if not script_path.exists():
        raise SystemExit(f"Missing backend script: {script_path}")

    sys.path.insert(0, str(script_path.parent))
    runpy.run_path(str(script_path), run_name="__main__")
