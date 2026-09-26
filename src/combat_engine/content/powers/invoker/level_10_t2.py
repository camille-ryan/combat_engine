"""Invoker, level 10: every burst one square wider."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p7192",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p7192(c: Cast) -> None:
    """The extra square is read where the area is worked out, so it decides
    what may be aimed at and not merely what the picture shows."""
    c.widen_areas(1, until=When.EONT)
