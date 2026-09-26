"""Sorcerer: the fork the class page draws, and the utility that rewrites it.

The class's two builds are a choice of *soul*, and the whole mechanical
content of either is a resistance to one damage type -- chosen and kept on
one leg, rolled for each fight on the other. That is a class-page sentence
with no compendium row, so it carries a `cf:` ref like every other one.

**The amount is a judgement call and is written down here rather than
transcribed.** No spec this repo can read prints it. `p3763`, whose whole
job is to change this resistance, prints 5 / 10 / 15 by tier for the
matching resistance it hands an ally, so that is the ladder used for both.

The type is held twice over: once in `c.resist`, which has nowhere to
record which type it covered, and once in a marker effect whose label names
it. `p3763` reads the marker, and ending the marker ends the resistance
with it -- so "change the resistance to one of the other damage types"
is one call rather than a search.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Effect,
    Keyword,
    When,
    power,
)

#: The feature's ref, and the stem of both holds it lays.
SOUL = "cf:sorcerer-soul"

#: The types a soul can be sworn to. Untyped, force, psychic and the two
#: that no elemental fork offers are left out.
SOUL_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
    DamageType.THUNDER,
)

ARCANE = [Keyword.ARCANE]


def soul_resist(level: int) -> int:
    return 5 + 5 * ((level >= 11) + (level >= 21))


def soul_of(c: Cast) -> DamageType | None:
    """Which type this sorcerer's soul currently resists, if any."""
    by_value = {d.value: d for d in DamageType}
    for effect in c.world.effects.of(c.me):
        if effect.label.startswith(f"{SOUL} is "):
            return by_value.get(effect.label.rsplit(" ", 1)[1])
    return None


def wear_soul(c: Cast, kind: DamageType) -> Effect | None:
    """Swear the soul to a type, dropping whatever it was sworn to before."""
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(SOUL):
            c.world.effects.end(effect, "the soul changed")
    guard = c.resist(soul_resist(c.level), kind, until=When.ENCOUNTER)
    mark = c.effect(f"{SOUL} is {kind.value}", until=When.ENCOUNTER, on=c.me)
    if mark is not None and guard is not None:
        mark.on_end.append(lambda: c.world.effects.end(guard, "the soul changed"))
    return mark


@power(
    SOUL,
    level=0,
    cls="sorcerer",
    # A trait: the soul is simply what the sorcerer is, and nobody spends
    # an action on it.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
)
def sorcerer_soul(c: Cast) -> None:
    """One leg picks its type and keeps it; the other is given one each fight,
    which is the whole difference between the two builds."""
    if c.build("dragon"):
        kind = c.choose(list(SOUL_TYPES), f"{SOUL}: which damage type")
    elif c.build("wild"):
        kind = SOUL_TYPES[(c.roll("1d6") - 1) % len(SOUL_TYPES)]
    else:
        return
    if kind is not None:
        wear_soul(c, kind)


@power(
    "p3763",
    level=2,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p3763(c: Cast) -> None:
    """"One of the **other** damage types" -- the one it already resists is
    not on offer, which is what makes this a change rather than a renewal.

    The ally's share is a separate resistance of its own rather than the
    sorcerer's stretched over two creatures, because the printed amount is
    5 and the sorcerer's is not.
    """
    was = soul_of(c)
    if was is None:
        return
    kind = c.choose(
        [k for k in SOUL_TYPES if k is not was], f"{c.ref}: which damage type now"
    )
    if kind is None:
        return
    wear_soul(c, kind)
    mates = [a for a in c.allies() if c.adjacent(a)]
    if mates:
        mate = c.choose(mates, f"{c.ref}: who shares the resistance")
        if mate is not None:
            c.resist(soul_resist(c.level), kind, on=mate, until=When.ENCOUNTER)
