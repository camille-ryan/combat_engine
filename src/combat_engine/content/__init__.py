"""Hand-written powers and monster abilities.

Importing this package registers everything that has been declared. Nothing
here is generated: every row is a function somebody wrote against a sanitised
spec, having never been shown what it is called.

A row that cannot be written yet is simply absent. There is no placeholder
and no note explaining the absence -- `scripts/coverage.py` counts what is
missing, and a count cannot go stale.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

_HERE = Path(__file__).parent


def _load(package: str) -> None:
    """Import every module under a content package, so its rows register."""
    root = _HERE / package.replace(".", "/")
    if not root.exists():
        return
    for info in pkgutil.walk_packages([str(root)], prefix=f"{__name__}.{package}."):
        importlib.import_module(info.name)


_load("powers")
_load("monsters")
