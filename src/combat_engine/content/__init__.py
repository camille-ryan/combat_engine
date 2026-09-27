"""Hand-written powers and monster abilities.

Importing this package registers everything that has been declared. Nothing
here is generated: every row is a function somebody wrote against a sanitised
spec, having never been shown what it is called.

A row you cannot fully write is written anyway, with `todo=` naming the
symbols you wanted -- `todo=("c.deals()",)`. It is refused in play, counted
as partial and never as done, named individually by `scripts/audit.py`, and
it holds its issue open. A row is still left out entirely when there is
nothing to decorate: no ref, no card, no marker.

The old rule was that an unwritable row is simply absent, and the reason was
sound -- an absence is counted and a half-row looks finished. It stops
working at four thousand items and feats against an engine that has never
met either: the absences become the majority and the reason for each lives
nowhere. `dsl.usable` refuses a `todo` row outright, so it is exactly as
inert in play as the absence it replaced, and it says what it is waiting for.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from combat_engine.engine.dsl import Power

_HERE = Path(__file__).parent


def _load(package: str) -> None:
    """Import every module under a content package, so its rows register."""
    root = _HERE / package.replace(".", "/")
    if not root.exists():
        return
    for info in pkgutil.walk_packages([str(root)], prefix=f"{__name__}.{package}."):
        importlib.import_module(info.name)


def declared() -> dict[str, Power]:
    """Every row the tree has registered, by ref.

    Five scripts each carried their own copy of the two-line incantation
    -- import the package for the side effect, then reach into
    `dsl.REGISTRY` -- and each had to remember that the import is what
    fills it. One of them forgot and reported an empty tree.

    The live dict, not a copy: callers want `declared()[ref].todo`, and a
    snapshot would only invite somebody to mutate it.
    """
    from combat_engine.engine.dsl import REGISTRY

    return REGISTRY


_load("powers")
_load("features")
_load("monsters")
_load("items")
_load("feats")
_load("races")
