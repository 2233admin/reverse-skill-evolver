#!/usr/bin/env python3
"""Compatibility entrypoint for :mod:`reverse_skill.teams_collaboration`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from reverse_skill import teams_collaboration as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
