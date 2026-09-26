"""Battlemind, level 10: seeing what is not there to be seen."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p13063",
    level=10,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p13063(c: Cast) -> None:
    """The Insight and Perception halves are skill checks the engine does not
    roll, so the whole mechanical content is the sense itself."""
    c.see_invisible(until=When.EONT)
