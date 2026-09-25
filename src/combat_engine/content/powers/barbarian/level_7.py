"""Barbarian, level 7: encounter attacks.

Three things recur.

**The build riders.** Five rows print a rider naming a build this chargen
does not offer -- there is one barbarian build and it is called `standard`.
Each rider is gated on `c.build(...)` all the same, which is the printed
sentence; the ungated half is what a barbarian without the build gets. The
warlord settled this at level 7 and the docstring of
`content/powers/warlord/level_7_b.py` is the precedent.

**Two printed Requirements the board cannot meet.** `p11564` wants a
two-handed reach weapon and `p5218` wants two melee weapons; the barbarian
carries one longsword, so both report UNUSED and both were driven by hand.
The gates are `fighter/grips.py`, not new ones.

**Two Special lines with nowhere to go.** "You can use this power in place
of a melee basic attack when charging" (`p16514`) has no header field --
`Powers.basic` is what a charge swings -- and "you can also use this power
as an immediate reaction when an adjacent enemy hits you" (`p9573`) would
need a second `action` on one row. Both are written as the standard action
they also are, with the clause in a note; see the report.

`p14425`'s force damage is dealt ordinarily: insubstantiality is read inside
`deal_damage` and cannot be waived, the same hold `cleric/level_2_b.py`
reports for "damage that cannot be reduced".
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.fighter.grips import (
    reach_weapon,
    two_handed,
    two_melee,
)
from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Trigger,
    TurnStart,
    When,
    World,
    power,
)
from combat_engine.engine.grid import blast_placements, spread
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _two_handed_reach(world: World, eid: int) -> bool:
    """"Requirement: You must be wielding a two-handed reach weapon" -- the
    two gates `grips.py` already has, asked together."""
    return two_handed(world, eid) and reach_weapon(world, eid)


def _beside_blocking(c: Cast, who: int) -> bool:
    """Is that creature standing next to blocking terrain?"""
    theirs = squares_of(c.world, who)
    return any(sq in c.world.grid.blocking for sq in spread(theirs, 1) - theirs)


def _adjacent_enemy_swung_at_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to you hits or misses you." Both outcomes, so the
    row declares `Hit` and `Miss` and this answers either."""
    who = getattr(ev, "attacker", None)
    if who is None or who == me or getattr(ev, "target", None) != me:
        return False
    return team(world, who) is not team(world, me) and adjacent(world, me, who)


_SWUNG_AT_ME = "an enemy adjacent to you hits or misses you"


@power(
    "p11564",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_handed_reach,
    requires_text="needs a two-handed reach weapon",
)
def p11564(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.slide(1)
        c.prone()


@power(
    "p12279",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_WEAPON, Keyword.HEALING, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p12279(c: Cast) -> None:
    """The hit point is per enemy felled, not once for the burst: it is on
    the Hit line, which is read once per target."""
    if not c.can_see():
        return
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    c.prone()
    c.heal(1, on=c.me)
    if c.build("thaneborn"):
        c.push(1)


@power(
    "p14424",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14424(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.immobilized(until=When.EONT)


@power(
    "p14425",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FORCE],
    attack=Attack(STR, vs=AC),
)
def p14425(c: Cast) -> None:
    """"Ignores the insubstantial quality" has no expression -- halving is
    read off the target inside `deal_damage` and nothing waives it -- so the
    force damage is dealt ordinarily and the clause is in the report."""
    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.FORCE)
        c.note(f"{c.ref}: this damage ignores the insubstantial quality")


@power(
    "p16514",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p16514(c: Cast) -> None:
    """The wall is asked after the shove, which is what "ends this push"
    means -- a target that had nowhere to go is still against one."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    c.push(2)
    if _beside_blocking(c, victim):
        c.flat(c.str_mod, on=victim)
    c.note(f"{c.ref}: when charging, this can be swung in place of a melee basic attack")


@power(
    "p4811",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p4811(c: Cast) -> None:
    """The bonus is what the blood actually cost -- `c.flat` returns the hit
    points that came off, which is "the damage you take" once temporary hit
    points and everything else have had their say."""
    paid = 0
    if c.may("bleed for the blow", who=c.me):
        paid = c.flat(c.roll("1d10"), on=c.me) + c.con_mod
    if c.strike():
        c.damage(c.w(2), c.str_mod + paid)


@power(
    "p4835",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4835(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    for foe in sorted(c.within(5, side="enemy")):
        c.penalty("attack", 2, on=foe, until=When.EONT)


@power(
    "p4836",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4836(c: Cast) -> None:
    """"Instead", so the wider count replaces the adjacent one rather than
    adding to it."""
    radius = max(0, c.con_mod) if c.build("rageblood") else 1
    crowd = len(c.within(radius, side="enemy"))
    if c.strike():
        c.damage(c.w(2), c.str_mod + crowd)


@power(
    "p4947",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_SWUNG_AT_ME,
    on=[
        Trigger(Hit, _adjacent_enemy_swung_at_me, _SWUNG_AT_ME),
        Trigger(Miss, _adjacent_enemy_swung_at_me, _SWUNG_AT_ME),
    ],
)
def p4947(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)


@power(
    "p4948",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4948(c: Cast) -> None:
    """Dropping the guard is a real provocation: the windows are opened for
    every adjacent enemy and whatever comes back is counted off
    `AttackDeclared`, so the bonus is what actually swung rather than who
    could have. The engine never decides what goes in an opportunity window
    -- a controller does -- so on a board with no policy installed the count
    is nought and the extra 1[W] still stands, which is the printed order.
    """
    me = c.me
    swings = 0
    opened = c.may("drop your guard for it", who=me)
    if opened:

        def count(ev: AttackDeclared) -> None:
            nonlocal swings
            if ev.target == me:
                swings += 1

        watcher = c.watch(
            AttackDeclared, count, until=When.EOT, on=me, label=f"{c.ref} exposed"
        )
        for foe in sorted(f for f in c.within(1, side="enemy") if f != c.target):
            c.provoke(foe, on=me)
        c.world.effects.end(watcher, "the opening closed")
    if c.strike(plus=swings):
        c.damage(c.w(3 if opened else 2), c.str_mod)


@power(
    "p5218",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p5218(c: Cast) -> None:
    """"Any enemy", so the offer stands for each one that starts its turn in
    reach rather than being spent on the first."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    me = c.me

    def cut(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies() or not c.adjacent(ev.actor):
            return
        if not c.may("cut at it with the off hand", who=me):
            return
        c.damage(
            c.w(1, hand="off"),
            c.dex_mod if c.build("whirling") else 0,
            on=ev.actor,
        )

    c.watch(TurnStart, cut, until=When.SONT, on=me, label=f"{c.ref} off hand")


@power(
    "p9573",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p9573(c: Cast) -> None:
    """The rider replaces the number rather than stacking with it, so it is
    one penalty either way."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    c.penalty("attack", 1 + c.cha_mod if c.build("thaneborn") else 2, until=When.EONT)
    c.note(
        f"{c.ref}: this can also be swung as an immediate reaction when an adjacent "
        "enemy hits you -- one row carries one action"
    )


@power(
    "p9574",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p9574(c: Cast) -> None:
    """The blast is laid down by hand: the header's reach is the sword, and
    the printed line picks the placement -- one that covers the target, and
    of those the one that catches the most enemies."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod)
    theirs = squares_of(c.world, victim)
    places = [
        area
        for area in blast_placements(squares_of(c.world, c.me), 3).values()
        if area & theirs
    ]
    if not places:
        return
    area = max(places, key=lambda a: (len(c.in_squares(a, side="enemy")), sorted(a)))
    amount = 3 + c.con_mod if c.build("thunderborn") else 5
    for foe in sorted(c.in_squares(area, side="enemy")):
        c.vulnerable(amount, on=foe, until=When.EONT)


@power(
    "p9575",
    level=7,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9575(c: Cast) -> None:
    """"Until the mark ends" is the barbarian's own mark, so the rider hangs
    off that effect rather than carrying a duration of its own."""
    victim = c.target
    if victim is None:
        return
    theirs = any(c.marked(on=victim, by=friend) for friend in c.allies())
    if not c.strike():
        return
    c.damage(c.w(3 if theirs else 2), c.str_mod)
    mark = c.mark(until=When.EONT)
    if mark is None or not c.build("rageblood"):
        return
    rider = c.bonus(
        "damage",
        c.con_mod,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == victim,
    )
    if rider is not None:
        mark.on_end.append(lambda: c.world.effects.end(rider, "the mark ended"))
