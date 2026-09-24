"""Ranger, level 2.

Three immediate reactions. Two of them answer something the bus emits and
declare their printed Trigger line with `on=` rather than only quoting it.
The third answers an ally's skill check and hands out a bonus to it --
nothing the model rolls, and nothing that touches the battlefield -- so it
is `out_of_combat=True` and inert on purpose.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)
from combat_engine.engine.events import Hit, Miss
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_DAMAGED_BY_MELEE = "an enemy damages you with a melee attack"
_MISSED_BY_MELEE = "an enemy misses you with a melee attack"


@power(
    "p749",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_DAMAGED_BY_MELEE,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_DAMAGED_BY_MELEE),
)
def p749(c: Cast) -> None:
    """Hung off the melee hit rather than off the damage it deals.

    `DamageApplied` carries no power, so `by_melee` -- which looks the reach
    up off the power -- cannot read it. `Hit` is the nearest event that
    knows the attack was a melee one, and the two differ only for a hit that
    happens to deal nothing.
    """
    c.shift(c.wis_mod)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)


@power(
    "p923",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    trigger=_MISSED_BY_MELEE,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_MISSED_BY_MELEE),
)
def p923(c: Cast) -> None:
    """Where the slide ends -- "a square adjacent to you" -- cannot be said.

    `c.slide` takes no `to`, and an anchor does nothing to a slide, so the
    destination is whatever the mover's decider picks. The three squares and
    the advantage afterwards are as printed.
    """
    c.slide(3)
    c.grants_advantage()


@power(
    "p922",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally you can see or hear makes a check you are trained for",
    out_of_combat=True,
)
def p922(c: Cast) -> None:
    """Inert by declaration: no event announces a check, and no roll takes it.

    The Trigger line is kept as prose for the card only -- there is nothing
    for `on=` to watch, and `out_of_combat` is what stops that reading as a
    row somebody forgot to finish.
    """
    c.note(f"p922: the ally rerolls, with a +{c.wis_mod} power bonus")
