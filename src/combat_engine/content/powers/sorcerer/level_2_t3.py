"""Sorcerer, level 2: longer range on the arcane powers.

The spec entry said nothing reads a range modifier and that `Range.size` is
used raw. That is half true: `dsl._stretched` has read `"range"` for a
ranged line since reach was added, and `area_of` applies it -- so the
modifier decides what may be *aimed* at, not just what a body can reach.
What was missing was the gate: `_stretched` passed an empty context, so
"your arcane powers" could not have been asked. It now carries the row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    get,
    power,
)


def arcane_power(ctx: dict[str, Any]) -> bool:
    """Is the row being measured an arcane one?"""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.ARCANE in p.keywords


@power(
    "p5267",
    level=2,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p5267(c: Cast) -> None:
    """`on=c.me`: a modifier is done *to* somebody and so follows
    `c.target`, and this one is about the sorcerer.

    The gate reads the keyword off the row being measured, so a crossbow in
    the same hands is still a crossbow.
    """
    c.bonus("range", c.dex_mod, on=c.me, until=When.EOT, when=arcane_power)
