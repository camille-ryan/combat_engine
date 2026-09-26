"""Monk, level 2: taking some of the fall out of a fall."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    FREE,
    PERSONAL,
    SELF,
    Cast,
    Fell,
    Keyword,
    power,
)
from combat_engine.engine.triggers import Trigger, about_me

_YOU_FALL = "you fall"


@power(
    "p13143",
    level=2,
    cls="monk",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
    trigger=_YOU_FALL,
    on=Trigger(Fell, about_me, _YOU_FALL),
)
def p13143(c: Cast) -> None:
    """`about_me` is right here and nowhere near `ConditionApplied`: `Fell`
    names the faller `actor`, which is the field it reads."""
    c.cushion(5 + c.level // 2)
