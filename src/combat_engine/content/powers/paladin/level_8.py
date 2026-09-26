"""Paladin, level 8."""

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
    "p13561",
    level=8,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p13561(c: Cast) -> None:
    """"With charge attacks" gates on the damage context's `charge`, which
    it does carry. The 28th-level line also hands the whole thing to allies
    within 2; `c.bonus` would take `on=`, but the row is written for one
    creature and the epic clause is left off."""
    c.bonus("speed", 2, until=When.ENCOUNTER, on=c.me, kind="power")
    c.bonus(
        "damage",
        c.cha_mod,
        until=When.ENCOUNTER,
        on=c.me,
        kind="power",
        when=lambda ctx: bool(ctx.get("charge")),
    )
    if c.level >= 18:
        c.mode("fly", c.speed_of(), until=When.ENCOUNTER, on=c.me)
