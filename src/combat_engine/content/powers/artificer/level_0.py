"""Artificer, level 0: the three infusions the class hands out.

All three print "the target can end the bonus as a free action to ...". That
is a standing option held open indefinitely, not an effect with a duration,
and nothing offers one: the row grants the bonus and the cash-in is dropped.
For the first of them the cash-in is damage immunity, which has no `Cast`
method either.

The printed budget is two of these per encounter (three at 16th), one per
round. `group` is a one-per-encounter allowance and would be too tight, so
each row is an ordinary encounter power with `once_per_round`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    When,
    power,
)

#: The eight the row lets the target choose from, in printed order.
RESISTABLE = [
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.RADIANT,
    DamageType.THUNDER,
]


def _tier(level: int) -> int:
    """0 heroic, 1 paragon, 2 epic -- the 5/10/15 ladder these rows print."""
    return 0 if level < 11 else (1 if level < 21 else 2)


@power(
    "p10187",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    once_per_round=True,
)
def p10187(c: Cast) -> None:
    """The burst widens at 11th and 21st, which the header cannot say; the
    resistance ladder is read off `c.level` instead."""
    who = c.target
    if who is None:
        return
    dtype = c.choose(RESISTABLE, "damage type to resist")
    if dtype is None:
        return
    c.resist(5 + 5 * _tier(c.level), dtype, until=When.ENCOUNTER, on=who)


@power(
    "p4128",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING],
    once_per_round=True,
)
def p4128(c: Cast) -> None:
    """Hit points equal to a surge value, without the surge being spent --
    so `c.heal` off `c.surge_value`, not `c.surge`."""
    who = c.target
    if who is None:
        return
    extra = max(0, ((c.level - 1) // 5) * 2)
    c.heal(c.surge_value(of=who) + c.wis_mod + extra, on=who)


@power(
    "p7635",
    level=0,
    cls="artificer",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
    once_per_round=True,
)
def p7635(c: Cast) -> None:
    """Only the bonus. Trading it in is the free action nothing holds open."""
    who = c.target
    if who is None:
        return
    c.bonus(AC, 1, until=When.ENCOUNTER, on=who)
