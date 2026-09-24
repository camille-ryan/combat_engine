"""Paladin, level 9: daily attacks.

`p2260`'s Special line is an entry condition rather than anything the body
does, so it is a `requires=` gate: the row is simply not offered while a
friend is standing within five squares. That makes it unusable on a board
where the party is together, which is the printed card.

`p1264`'s Effect prints a duration for the slow and none for the sentence
that keeps applying it. An undated effect is instantaneous, and an
instantaneous version of that sentence is no effect at all, so it is read as
lasting the encounter.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    TurnStart,
    When,
    World,
    power,
)
from combat_engine.engine.query import allies as allies_of
from combat_engine.engine.query import distance_between

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _no_friends_near(world: World, eid: int) -> bool:
    """"You cannot use this power if any allies are within 5 squares of you"."""
    return not any(distance_between(world, eid, a) <= 5 for a in allies_of(world, eid))


@power(
    "p1264",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p1264(c: Cast) -> None:
    """The Effect is armed first: it is owed whether or not the burst caught
    anything, and the body runs once with no target when it did not."""
    if c.first:
        me = c.me

        def dawn(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in c.enemies() and c.adjacent(ev.actor):
                c.slowed(on=ev.actor)

        c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=c.ref)
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p1269",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p1269(c: Cast) -> None:
    """The secondary rolls longhand: the header carries one attack line and
    the splash is the same numbers aimed somewhere else.

    The push is measured from the paladin, which is where the printed "you
    push the target" puts the anchor -- not from the creature they were
    standing next to.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.RADIANT)
        return
    c.damage("1d10", c.cha_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    for foe in sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim):
        if c.attack(c.cha_, FORT, on=foe):
            c.damage("1d10", c.cha_mod, dtype=DamageType.RADIANT, on=foe)
            c.push(3, on=foe)


@power(
    "p2260",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
    requires=_no_friends_near,
)
def p2260(c: Cast) -> None:
    """No `requires_text`: `chargen.build_for` reads the word "requirement"
    out of the refusal to decide which build can hold a row, and a custom
    message hides it -- the lesson `ranger/level_7.py` records.

    The weakening is an Effect line, so it lands on the misses too.
    """
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
    c.weakened(until=When.SAVE_ENDS)
