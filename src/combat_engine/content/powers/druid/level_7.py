"""Druid, level 7: the encounter attacks.

Six of the twelve print a build rider and the class table has one build, so
the base line is what is written; see `level_1_c.py`. Two of those riders
are the whole of what their sentence adds -- a penalty to escape checks, a
wider push -- and both are named in the report.

`p5053` and `p12835` are the two shapes that recur at this level: a
secondary attack against somebody the first one was not aimed at, and an
Effect line that moves the druid *before* the swing rather than after it.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    Ranged,
    UpTo,
    When,
    power,
)
from combat_engine.engine.query import adjacent

from .forms import burns_at_end, fork_mod, in_beast_form, zone_hold

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


@power(
    "p12835",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p12835(c: Cast) -> None:
    """The shift is an Effect printed before the attack, so it happens
    whether or not there is anything to bite when it ends. The Primal
    Guardian rider -- the grabbed target grants combat advantage to your
    allies -- is a build the class table does not have.
    """
    c.shift(2)
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.grab()


@power(
    "p14511",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p14511(c: Cast) -> None:
    """The +2 against a beast is a situational bonus to this one roll, which
    `c.strike(plus=)` is for -- a held modifier would outlive the attack."""
    beast = c.target is not None and c.is_kind("beast")
    if c.strike(plus=2 if beast else 0):
        c.condition(Condition.DOMINATED, until=When.EONT)
    else:
        c.dazed()


@power(
    "p14512",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.COLD],
    attack=Attack(WIS, vs=REF),
)
def p14512(c: Cast) -> None:
    """The hold is an Effect line, so a miss still freezes the target where
    it stands."""
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.COLD)
    c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "p14513",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p14513(c: Cast) -> None:
    """The zone catches everybody, not only enemies -- "creatures grant
    combat advantage while in the zone" -- so the hold goes on whoever walks
    in and is taken off whoever walks out."""
    if c.strike():
        c.damage("2d6", c.wis_mod)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    zone_hold(
        c, zone,
        lambda who: who != c.me,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
        until=When.EONT,
    )
    burns_at_end(c, zone, fork_mod(c), until=When.EONT)


@power(
    "p2682",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED],
    attack=Attack(WIS, vs=FORT),
)
def p2682(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod)
    victim = c.target
    c.prone()
    for foe in sorted(c.within(1, of=victim, side="enemy")):
        if foe != victim:
            c.prone(on=foe)


@power(
    "p2804",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2804(c: Cast) -> None:
    """The Primal Predator rider is a penalty to escape checks, which is
    both a build the class table does not have and a check nothing rolls."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.grab()


@power(
    "p4869",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.POISON],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p4869(c: Cast) -> None:
    """"The next time the target moves" is one move and then the hold is
    spent, which `once=True` gives: it fires once rather than living for one
    event, so a move by anybody else does not use it up."""
    if not c.strike():
        return
    c.damage("1d10", c.wis_mod, dtype=DamageType.POISON)
    victim = c.target
    if victim is None:
        return

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == victim:
            c.damage("1d10", dtype=DamageType.POISON, on=victim)

    c.watch(MoveEnd, stirred, until=When.SONT, on=c.me, once=True, label=c.ref)


@power(
    "p5053",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5053(c: Cast) -> None:
    """The secondary is owed whether or not the primary landed -- it is an
    Effect line -- and only its extra five depends on the first."""
    first = c.target
    landed = bool(c.strike())
    if landed:
        c.damage("2d8", c.wis_mod)
    pool = sorted(foe for foe in c.within(1, side="enemy") if foe != first)
    second = c.choose(pool, f"{c.ref}: who the second bite catches") if pool else None
    if second is None:
        return
    if c.strike(on=second):
        c.damage("1d10", c.wis_mod + (5 if landed else 0), on=second)


@power(
    "p5054",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED],
    attack=Attack(WIS, vs=REF),
)
def p5054(c: Cast) -> None:
    """Everyone within three of the target, which is everyone -- the printed
    line says creatures, not enemies -- and the pull is anchored on the
    target rather than on the druid.

    The Primal Guardian rider is a build the class table does not have.
    """
    if not c.strike():
        return
    c.damage("1d10", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    here = c.world.get(victim, Position)
    anchor = here.square if here is not None else None
    for who in sorted(c.within(3, of=victim)):
        if who != victim:
            c.pull(1, on=who, anchor=anchor)


@power(
    "p9660",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE, Keyword.FEAR],
    attack=Attack(WIS, vs=FORT),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p9660(c: Cast) -> None:
    """The push is anchored on the druid, which is where the roar comes
    from. The Primal Predator rider -- everyone within Dexterity squares
    rather than everyone adjacent -- is a build the class table lacks."""
    if not c.strike():
        return
    c.damage("2d10", c.wis_mod)
    victim = c.target
    for foe in sorted(c.within(1, side="enemy")):
        if foe != victim:
            c.push(2, on=foe, anchor=c.here)


@power(
    "p9661",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(3),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.POISON],
    attack=Attack(WIS, vs=FORT),
)
def p9661(c: Cast) -> None:
    """The Primal Swarm rider -- extra poison equal to Constitution -- is a
    build the class table does not have."""
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.POISON)
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p9663",
    level=7,
    cls="druid",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p9663(c: Cast) -> None:
    """The damage is dealt *by the target* to the druid's enemies standing
    beside it, which is why the source is the target rather than the caster:
    the printed line is the charmed creature lashing out.

    The Primal Guardian rider is a build the class table does not have.
    """
    if not c.strike():
        return
    c.damage("1d6", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    foes = set(c.enemies())

    def lashed(ev: AttackRolled) -> None:
        if ev.attacker != victim:
            return
        for foe in sorted(foes):
            if foe != victim and adjacent(c.world, foe, victim):
                c.world.damage(victim, foe, 5, detail=c.ref)

    c.watch(AttackRolled, lashed, until=When.EONT, on=c.me, once=True, label=c.ref)
