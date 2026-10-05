"""Swordmage, level 9, continued.

`p5749` prints two powers under one id: a standard-action swing, and an
interrupt the stance unlocks. The interrupt has a ref of its own after all
-- `p5749b`, in `second_card.py` -- so this row leaves the stance and the
parry is offered on `Hit` in `Window.BEFORE`, which is where a `Hit` is
still refusable.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_OTHER,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)

from . import beside

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]


@power(
    "p4804",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p4804(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.con_mod, dtype=DamageType.COLD)
        spot = beside(c)
        if spot is not None:
            c.slide(3, to=spot)
    else:
        c.half_damage(c.w(2), c.con_mod, dtype=DamageType.COLD)


@power(
    "p4805",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(INT, vs=AC),
)
def p4805(c: Cast) -> None:
    """Four blinks and three swings, in the printed order: the second and
    third targets are chosen from wherever the previous blink left me."""
    c.teleport(4)
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
    struck = [c.target]
    for step in (3, 2):
        c.teleport(step)
        pool = [f for f in c.within(1, side="enemy") if f not in struck]
        if not pool:
            return
        nxt = c.choose(sorted(pool), "the arc runs on to")
        if nxt is None:
            return
        struck.append(nxt)
        if c.attack(c.int_, AC, on=nxt):
            c.damage(c.w(), dtype=DamageType.LIGHTNING, on=nxt)


@power(
    "p5749",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.STANCE],
    attack=Attack(INT, vs=AC),
)
def p5749(c: Cast) -> None:
    """The parry is `p5749b`, an immediate interrupt of its own gated on this
    stance, so all this leaves is the stance -- whose label is what that
    row's Requirement reads. `Encounter.can_spend` keeps the parry to once a
    round, which the hand-armed version had to count for itself."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
    c.stance(label=c.ref)


@power(
    "p5750",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.LIGHTNING],
    attack=Attack(INT, vs=FORT),
    thrown_by_hand=True,
    requires_text="you must throw your melee weapon at the target",
)
def p5750(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.LIGHTNING)
        c.slowed(until=When.SAVE_ENDS)
        c.mark(until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.int_mod, dtype=DamageType.LIGHTNING)
        c.slowed()


@power(
    "p5751",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p5751(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.FORCE)
        c.push(c.str_mod)
        c.prone()
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.FORCE)
        c.push(1)


@power(
    "p5752",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=REF),
)
def p5752(c: Cast) -> None:
    """The blink happens before the second swing, and dragging the first
    target along happens after it -- so "adjacent to you" means adjacent to
    where the blink put me."""
    landed = c.strike()
    if landed:
        c.damage(c.w(), c.int_mod, dtype=DamageType.FIRE)
    first = c.target
    pool = [f for f in c.within(5, side="enemy") if f != first]
    second = c.choose(sorted(pool), "you round on") if pool else None
    if second is None:
        return
    spot = beside(c, second)
    if spot is not None:
        c.teleport(c.distance(second) + 1, to=spot)
    if landed and first is not None:
        drag = beside(c)
        if drag is not None and c.may("drag it along", who=c.me):
            c.teleport(c.distance(first) + 1, who=first, to=drag)
    if c.attack(c.int_, AC, on=second):
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FIRE, on=second)
