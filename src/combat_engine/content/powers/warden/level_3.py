"""Warden, level 3: the encounter attacks.

Two of these hang on something the target does *later* -- standing up,
shifting -- and both are a watch with a duration rather than a condition.
`MoveEnd` carries `kind_`, which is the only thing that can tell a shift
from a walk, and it fires after the move rather than before it.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import ConditionEnded

from . import zone_named

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


@power(
    "p11074",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p11074(c: Cast) -> None:
    if c.first:
        c.insubstantial(on=c.me, until=When.SONT)
    if c.strike():
        c.damage(c.w())
        if c.marked():
            c.damage("1d6")
        c.slide(1)
    if c.last:
        c.shift(c.speed_of())


@power(
    "p5111",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5111(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.rooted(until=When.EONT)


@power(
    "p5112",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5112(c: Cast) -> None:
    """Standing up is the end of the prone condition, so that is what the
    watch answers. Earthstrength holds the target down as well, and gives
    the blow that follows the whole encounter to land in."""
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    victim = c.target
    earth = c.build("earthstrength")
    c.prone(held=When.EONT if earth else None)

    def on_stand(ev: ConditionEnded) -> None:
        if ev.target == victim and ev.condition is Condition.PRONE:
            c.damage("1d10", c.str_mod, on=victim)

    c.watch(
        ConditionEnded, on_stand,
        until=When.ENCOUNTER if earth else When.EONT, once=True,
    )


@power(
    "p5113",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5113(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    victim = c.target
    far = 1 + c.wis_mod if c.build("wildblood") else 2

    def on_shift(ev: MoveEnd) -> None:
        if ev.actor == victim and ev.kind_ == "shift":
            c.shift(far)

    c.watch(MoveEnd, on_shift, until=When.SONT, once=True)


@power(
    "p5518",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5518(c: Cast) -> None:
    """The resistance is one grant for the whole burst, not one per enemy
    hit -- two of the same would stack, and the printed line is a single
    number. Anyone already carrying it is skipped."""
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    amount = 2 + c.wis_mod if c.build("lifespirit") else 3
    already = set(c.suffering(c.ref))
    for ally in c.in_squares(c.area(), side="ally"):
        if ally != c.me and ally not in already:
            c.resist(amount, on=ally, until=When.EONT)


@power(
    "p5574",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=REF),
)
def p5574(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
    others = [e for e in c.enemies() if e != c.target and c.marked(e)]
    if not others:
        return
    who = c.choose(others, "which marked enemy is given the choice")
    if c.may("drop prone rather than take the lightning", who=who):
        c.prone(on=who)
    else:
        c.flat(5, dtype=DamageType.LIGHTNING, on=who)
    if c.build("stormheart"):
        c.flat(c.con_mod, dtype=DamageType.LIGHTNING, on=who)


@power(
    "p6557",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p6557(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DAZED, Condition.DEAFENED, until=When.EONT)


@power(
    "p9835",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p9835(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    c.zone(spread({c.there}, 1) - {c.there}, until=When.EONT)
    ground = zone_named(c, c.ref)
    if ground is None:
        return

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == ground and c.marked(ev.actor):
            c.prone(on=ev.actor)

    c.watch(ZoneEntered, on_enter, until=When.EONT)


@power(
    "p9836",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9836(c: Cast) -> None:
    if c.first:
        c.move(4 + (c.wis_mod if c.build("wildblood") else 0))
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p9837",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9837(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod + (c.con_mod if c.build("earthstrength") else 0))
        c.slowed(until=When.EONT)


@power(
    "p9966",
    level=3,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=FORT),
    thrown_by_hand=True,
    requires_text="must throw the weapon in hand",
)
def p9966(c: Cast) -> None:
    """The weapon coming back is the reason `thrown_by_hand` is set rather
    than the row demanding a ranged weapon: it is the melee weapon that
    flies, and it is in hand again afterwards, so nothing has to be said."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.damage("1d8", dtype=DamageType.LIGHTNING)
        c.resist(10, DamageType.LIGHTNING, on=c.me, until=When.EONT)
