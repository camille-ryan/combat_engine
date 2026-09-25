"""Druid, level 1: the at-will attacks, first half.

Three things recur across this package and are settled here.

**The Beast Form keyword is a Requirement.** `forms.in_beast_form` is the
gate, declared in the header so the interface refuses the row rather than
the body quietly doing nothing. Nothing in this batch is wild shape itself,
so on a board where no form has been assumed those rows are unusable --
which is the printed rule and not a fault in them.

**"Your Constitution or Dexterity modifier" is the guardian/predator fork**,
and `chargen.BUILDS["druid"]` has one build called `standard`. Every row
printing it takes the larger of the two through `forms.fork_mod` and says so.

**"Special: this power can be used as a melee basic attack" has nowhere to
go.** `Powers.basic` is a field on the creature and no header field says a
row may stand in for the basic attack, so the Special is noted in the
docstring of each row that prints it and named in the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Miss,
    OpportunityWindow,
    PowerUsed,
    Ranged,
    UpTo,
    When,
    Window,
    get,
    power,
)
from combat_engine.engine.query import distance_between

from .forms import at_end_of_its_next_turn, during_its_next_turn, fork_mod

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


@power(
    "p12325",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.POISON],
    attack=Attack(WIS, vs=WILL),
)
def p12325(c: Cast) -> None:
    """The second dose turns on where the target *finishes* its next turn, so
    it is a window of exactly one turn rather than a duration.

    "Constitution or Dexterity modifier" is the fork; see the module note.
    """
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.POISON)
    victim = c.target
    if victim is None:
        return
    friends = [c.me, *[a for a in c.allies() if c.can_see(a)]]
    chosen = c.choose(friends, f"{c.ref}: who the target must keep away from")
    if chosen is None:
        return

    def sting() -> None:
        if c.adjacent_to(chosen, victim):
            c.flat(fork_mod(c), dtype=DamageType.POISON, on=victim)

    at_end_of_its_next_turn(c, victim, sting)


@power(
    "p13507",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13507(c: Cast) -> None:
    """The Athletics bonus is a check and there are none here. The move is
    real and is printed as an Effect, so it happens whether or not the swing
    landed, and at least one square is offered -- a druid with an even
    Constitution would otherwise be running a printed Effect worth nothing.
    """
    if c.strike():
        c.damage(c.w(), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    pool = sorted(a for a in c.within(5, of=victim, side="ally") if a != c.me)
    friend = c.choose(pool, f"{c.ref}: who breaks away") if pool else None
    if friend is not None and c.may("move", who=friend):
        c.move(max(1, c.con_mod), who=friend)


@power(
    "p13508",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13508(c: Cast) -> None:
    """"The next time an ally misses" is one shot, and `once=True` on a watch
    means "fire once", not "live for one event" -- so a miss by an enemy, or
    by an ally against somebody else, does not spend it."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    friends = set(c.allies())

    def fumbled(ev: Miss) -> None:
        if ev.target == victim and ev.attacker in friends:
            c.flat(max(1, c.con_mod), on=victim)

    c.watch(Miss, fumbled, until=When.EONT, on=c.me, once=True, label=c.ref)


@power(
    "p13509",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p13509(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod)
    victim = c.target
    if victim is None:
        return
    pool = sorted(a for a in c.within(5, of=victim, side="ally") if a != c.me)
    friend = c.choose(pool, f"{c.ref}: who takes heart") if pool else None
    if friend is not None:
        c.temp_hp(max(1, c.con_mod), on=friend)


@power(
    "p14497",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=FORT),
)
def p14497(c: Cast) -> None:
    """"Cannot take opportunity actions" is the mirror of `c.no_provoke`: a
    veto on the window rather than a flag the movement rules would consult.
    That method refuses the windows the *caster* opens; this refuses the ones
    the target would answer, and there is no method for it.
    """
    if not c.strike():
        return
    c.damage("1d10", c.wis_mod, dtype=DamageType.LIGHTNING)
    victim = c.target

    def veto(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            ev.cancel(f"{c.ref}: no opportunity actions")

    c.watch(
        OpportunityWindow, veto, until=When.EONT, window=Window.BEFORE,
        on=victim, label=f"{c.ref} no opportunities",
    )


@power(
    "p14498",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED],
    attack=Attack(WIS, vs=REF),
)
def p14498(c: Cast) -> None:
    if c.strike():
        c.damage("1d4", c.wis_mod)
        if c.may("push the target 1 square"):
            c.push(1)


@power(
    "p2666",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED],
    attack=Attack(WIS, vs=FORT),
)
def p2666(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.pull(2)


@power(
    "p5033",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p5033(c: Cast) -> None:
    """Two halves, and the first can only be said as arithmetic.

    Combat advantage is worked out inside `resolve.attack` and nothing on a
    creature suppresses it, so "can't gain combat advantage" is written as a
    penalty cancelling exactly the bonus it would have given, gated on
    `ctx["advantage"]` -- the same fact the roll used. A row of the enemy's
    that *reads* advantage still sees it; see the report.

    The second half reads `PowerUsed` rather than an attack event: the
    printed line is about an attack that leaves somebody out, and only
    `PowerUsed` and `AttackRolled.among` carry the whole target list.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    c.penalty(
        "attack", 2, on=victim, until=When.EONT,
        when=lambda ctx: bool(ctx.get("advantage")),
    )
    near = sorted(
        c.allies(), key=lambda a: (distance_between(c.world, victim, a), a)
    )
    if not near:
        return
    nearest = near[0]

    def swung(ev: PowerUsed) -> None:
        if ev.actor != victim or nearest in ev.targets:
            return
        p = get(ev.power)
        if p is None or not p.is_attack:
            return
        c.flat(5 + c.wis_mod, dtype=DamageType.PSYCHIC, on=victim)

    during_its_next_turn(c, victim, PowerUsed, swung)
