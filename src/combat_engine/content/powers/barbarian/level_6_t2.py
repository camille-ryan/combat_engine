"""Barbarian, level 6: a longer run, and only a run."""

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
    power,
)


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


@power(
    "p4887",
    level=6,
    cls="barbarian",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL],
)
def p4887(c: Cast) -> None:
    """Ungated this would be a bonus to all movement, which is not the printed
    line. `query.speed` was handed no context at all, so the gate was silently
    false; the three places that measure a charge's run now pass the word and
    nothing else does."""
    c.bonus("speed", 4, kind="power", until=When.EONT, on=c.me, when=_charging)
