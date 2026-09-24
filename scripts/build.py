#!/usr/bin/env python
"""Rebuild `data/game.db` and `localization/names.json` from the compendium.

    uv run scripts/build.py
"""

from __future__ import annotations

from combat_engine.etl.build import build

if __name__ == "__main__":
    print(build().render())
