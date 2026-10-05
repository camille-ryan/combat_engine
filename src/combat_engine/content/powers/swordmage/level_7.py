"""Swordmage, level 7: the encounter attacks.

`p3945` answers "hits **or** misses", which is two events and therefore two
declared triggers -- `on=` takes a sequence, and declaring only the hit half
would look finished and be wrong half the time.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    MoveEnd,
    Ranged,
    Trigger,
    When,
    both,
    enemy_within,
    power,
)
from combat_engine.engine.grid import spread

from . import ally_target_within, beside, moves_away_from_me, my_at_will_missed

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10430",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
    trigger="you used a swordmage at-will attack power this turn and hit nothing",
    on=Trigger(
        Miss,
        my_at_will_missed,
        "you used a swordmage at-will attack power this turn and hit nothing",
    ),
)
def p10430(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
        c.mark()


@power(
    "p12219",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=WILL),
)
def p12219(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        spot = beside(c)
        if spot is not None and c.may("drag it in", who=c.me):
            c.teleport(c.distance() + 1, who=c.target, to=spot)


@power(
    "p16013",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
    trigger="an enemy marked by you that you can see moves away from you",
    on=Trigger(
        Moved,
        moves_away_from_me,
        "an enemy marked by you that you can see moves away from you",
    ),
)
def p16013(c: Cast) -> None:
    """`Moved` carries both ends of the step, which is the only way to ask
    whether the creature went *away*. The mark and the sight line are read
    as the row runs, since no event carries either."""
    foe = c.target
    if foe is None or not c.marked(on=foe) or not c.can_see(foe):
        return
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        spot = beside(c)
        if spot is not None:
            c.pull(c.distance(foe), to=spot)
        if c.build("ensnarement"):
            c.immobilized(until=When.EOTNT)


@power(
    "p1728",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p1728(c: Cast) -> None:
    """The secondary shove is anchored on the primary target's square, which
    is what "away from the primary target" means."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    hub = c.there
    for foe in c.within(1, of=c.target, side="enemy"):
        if foe != c.target and c.attack(c.int_, FORT, on=foe):
            c.push(c.con_mod, on=foe, anchor=hub)


@power(
    "p1787",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.CONJURATION],
)
def p1787(c: Cast) -> None:
    """A wall is three contiguous squares of hazard. `c.hazard` already
    carries all three printed clauses -- entering, starting a turn there,
    and the once-per-turn latch."""
    line = [sq for sq in sorted(spread({c.here}, 1)) if sq != c.here][:3]
    if line:
        c.hazard(
            line, "1d8", DamageType.FIRE, label=c.ref,
            until=When.SONT, sustain=None,
        )


@power(
    "p3362",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=FORT),
)
def p3362(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p3363",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=AC),
)
def p3363(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
    victim = c.target
    bite = 5 + c.str_mod
    spent: dict[str, bool] = {}

    def stir(ev: MoveEnd) -> None:
        if ev.actor == victim and not spent.get("done"):
            spent["done"] = True
            c.flat(bite, dtype=DamageType.FORCE, on=victim)

    c.watch(MoveEnd, stir, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p3945",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=WILL),
    trigger="an enemy within 5 squares of you hits or misses an ally",
    on=[
        Trigger(
            Hit,
            both(enemy_within(5), ally_target_within(5)),
            "an enemy within 5 squares of you hits an ally",
        ),
        Trigger(
            Miss,
            both(enemy_within(5), ally_target_within(5)),
            "or misses an ally",
        ),
    ],
)
def p3945(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        c.dazed()
        if c.build("shielding"):
            c.penalty("attack", 2, until=When.EONT)


@power(
    "p3947",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.HEALING],
    attack=Attack(INT, vs=AC),
)
def p3947(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        if c.may("spend a surge", who=c.me):
            c.surge(on=c.me, bonus=c.con_mod if c.build("ensnarement") else 0)


@power(
    "p3948",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p3948(c: Cast) -> None:
    """"Each creature other than you" is every side, not just enemies."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    splash = c.int_mod + c.str_mod
    for who in c.within(1, of=c.target, side="any"):
        if who not in (c.me, c.target):
            c.flat(splash, on=who)


@power(
    "p3956",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p3956(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
        c.prone()


@power(
    "p4802",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p4802(c: Cast) -> None:
    """"Fall prone after shifting" is a watch on the kind of move, which is
    why it waits for `MoveEnd`: `MoveStart` fires before the step."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.COLD)
    caught = {c.target, *c.within(1, of=c.target, side="enemy")}

    def slip(ev: MoveEnd) -> None:
        if ev.actor in caught and ev.kind_ == "shift":
            c.prone(on=ev.actor)

    c.watch(MoveEnd, slip, until=When.EONT, on=c.me, label=c.ref)


@power(
    "p583",
    level=7,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p583(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.int_mod)
    pool = [f for f in c.within(5, side="enemy") if f != c.target]
    if not pool:
        return
    other = c.choose(sorted(pool), "you also call out")
    if other is None:
        return
    c.mark(on=other)
    if c.build("assault"):
        c.flat(c.str_mod, on=other)
