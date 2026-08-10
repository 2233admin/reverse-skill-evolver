#!/usr/bin/env python3
"""Compatibility entrypoint for :mod:`reverse_skill.search`."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reverse_skill import search as _implementation


if __name__ == "__main__":
    raise SystemExit(_implementation.main())

sys.modules[__name__] = _implementation
