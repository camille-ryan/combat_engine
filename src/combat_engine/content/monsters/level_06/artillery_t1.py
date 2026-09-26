"""Level 6 artillery: one trait that borrows a square.

The stat block's numbers load from the database; this is only behaviour.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    power,
)


@power(
    "m4853a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def m4853a1(c: Cast) -> None:
    """A trait, so it is armed once at the start of the fight. The line of
    sight the printed line requires is checked wherever a range is measured
    rather than here, so the master falls back to its own square the moment
    it cannot see the servant."""
    master = c.master()
    if master is not None:
        c.cast_from(c.me, on=master)
