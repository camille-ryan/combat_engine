"""Assassin, level 10: turning the shrouds into temporary hit points."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    DamageApplied,
    Keyword,
    When,
    power,
)

#: The class feature that lays the shrouds and pays them out. Its damage is
#: the only thing on the board that counts as "damage from your shroud", and
#: it is recognised by the ref it puts on the roll.
SHROUD = "p9400"


@power(
    "p9442",
    level=10,
    cls="assassin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.SHADOW],
)
def p9442(c: Cast) -> None:
    """The count is still standing when the shroud damage lands -- the
    feature clears it afterwards for exactly this -- so "for each shroud on
    that enemy" is `c.shrouds` asked from inside the blow they paid for."""

    def cash_in(ev: DamageApplied) -> None:
        if ev.source != c.me or ev.detail != SHROUD:
            return
        c.temp_hp(5 * c.shrouds(ev.target), on=c.me)

    c.watch(DamageApplied, cash_in, until=When.EONT, on=c.me, once=True)
