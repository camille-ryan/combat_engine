"""Swordmage, level 0: the three aegis marks.

All three are the same row with a different punishment, so the shared half
is written once. Two parts of it are worth naming.

**The -2 is free.** `resolve._mark_penalty` already charges two to a marked
creature that leaves its marker out of the attack, and it judges that per
*power use* rather than per target -- which is the printed rule and is
exactly the printed aegis penalty. So `c.mark` is the whole of that clause
and a hand-rolled penalty on top would double it.

**"Until you use this power against another target"** is longer than any
duration in the enum, so the mark is taken for the encounter and `_release`
ends the previous one by hand -- the same shape as the avenger's oath.

The immediate action each punishment costs is not modelled: the engine has
no immediate-action budget, so each is latched to once a round, which is
what having one immediate action a round comes to.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AT_WILL,
    MINOR,
    ONE_CREATURE,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    When,
    power,
)
from combat_engine.engine.query import distance_between

from . import beside

ARCANE = [Keyword.ARCANE]
ARCANE_TELEPORT = [Keyword.ARCANE, Keyword.TELEPORTATION]


def _release(c: Cast) -> None:
    """End whichever creature this aegis was on before."""
    for who in c.suffering(c.ref, include_self=True):
        for effect in list(c.world.effects.of(who)):
            if effect.source == c.me and c.ref in effect.label:
                c.world.effects.end(effect, "a new aegis")


def _aegis(c: Cast) -> int | None:
    """Mark the target for the fight, releasing the last one."""
    victim = c.target
    if victim is None:
        return None
    _release(c)
    c.mark(on=victim, until=When.ENCOUNTER)
    return victim


def _left_me_out(c: Cast, ev: Any, victim: int) -> bool:
    """The printed condition on all three punishments."""
    if getattr(ev, "attacker", None) != victim:
        return False
    if getattr(ev, "target", None) == c.me:
        return False
    return distance_between(c.world, c.me, victim) <= 10


def _f1156(c: Cast, me: int, victim: int) -> None:
    """**`f1156`'s clause, on all three punishments.** The printed sentence
    is about the immediate action effect of `cf:swordmage-f1` against a
    creature marked by you, and these closures *are* that effect firing
    against the one creature this aegis is on -- the same argument `f619`'s
    clause below is written on, and `#550`'s convention.

    A plain "+2 bonus" with no type word printed, so no `kind=`, and attack
    and damage are two keys rather than one. Not `once=`: the card says
    "attack rolls and damage rolls", plural, for the whole duration.

    The drawback is the swordmage granting combat advantage, so the effect
    sits on `me` -- which means `EOTNT` clocks on `me` and not on `victim`.
    The printed duration is the victim's next turn; aiming the clock at a
    creature that is neither owner nor source is not something `Effects`
    can express, so the spelling says the printed duration and the clock is
    one turn out.
    """
    if not c.feat("f1156"):
        return
    with c.credit("f1156"):
        c.grants_advantage(on=me, to=victim, until=When.EOTNT)
        c.bonus(
            "attack", 2, on=me, until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim,
        )
        c.bonus(
            "damage", 2, on=me, until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "p3322",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("assault"),
    keywords=ARCANE_TELEPORT,
)
def p3322(c: Cast) -> None:
    """"If no unoccupied space exists adjacent to the target, you can't use
    this immediate reaction" is why the square is found before anything
    moves: `beside` returning None is the printed refusal."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}

    def punish(ev: Hit) -> None:
        if last["round"] == c.world.round or not _left_me_out(c, ev, victim):
            return
        landing = beside(c, victim)
        if landing is None or not c.may("answer the aegis", who=me):
            return
        last["round"] = c.world.round
        c.teleport(20, to=landing)
        c.basic(on=victim)
        _f1156(c, me, victim)

    c.watch(Hit, punish, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")


@power(
    "p3323",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("shielding"),
    keywords=ARCANE,
)
def p3323(c: Cast) -> None:
    """`DamageRolled` is the interrupt window the printed reduction needs --
    the number exists and has not been dealt. "To any one creature" is the
    packet being answered, which is one creature by construction."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}
    step = 15 if c.level >= 21 else 10 if c.level >= 11 else 5

    def soften(ev: DamageRolled) -> None:
        if last["round"] == c.world.round or ev.source != victim:
            return
        if ev.target == me or distance_between(c.world, me, victim) > 10:
            return
        if not c.may("blunt the blow", who=me):
            return
        last["round"] = c.world.round
        c.reduce(step + c.con_mod, ev)
        # **`f619`: *"+2 bonus to the next attack roll made before the end
        # of your next turn against the foe that triggered the p3323
        # immediate interrupt."*** This closure **is** that interrupt
        # firing, and `ev.source` is the foe -- so the clause goes here,
        # which is `#550`'s convention and the only place the triggering
        # foe is known.
        #
        # The marker read `c.triggering_attacker()` and that verb exists;
        # the row's own note then concluded the clause was unwritable
        # because *"PowerUsed for p3323 is announced when the aegis is
        # placed, hours before anything triggers it"*. True, and beside
        # the point: a feat watching from outside would need an event this
        # firing does not emit, and a clause written inside needs none.
        #
        # `once=True` so it is spent by the next roll, which is the printed
        # "the next attack roll".
        if c.feat("f619"):
            with c.credit("f619"):
                struck = ev.source
                c.bonus(
                    "attack", 2, on=me, until=When.EONT, once=True,
                    when=lambda ctx: ctx.get("target") == struck,
                )
        # **`f1234`: the reduction pays out to the creature it protected.**
        # Same argument as `f619` above -- `c.reduce` announces nothing a
        # feat could watch from outside, and inside the closure "the same
        # target" is `ev.target`. The printed 5/10/15 ladder is the one
        # `step` already holds, and `EOTNT` is clocked correctly here
        # because the effect sits on that creature.
        if c.feat("f1234"):
            with c.credit("f1234"):
                c.resist(
                    step, DamageType.NECROTIC, on=ev.target, until=When.EOTNT
                )
        _f1156(c, me, victim)

    c.watch(DamageRolled, soften, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")


@power(
    "p5736",
    level=0,
    cls="swordmage",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    requires=on_leg("ensnarement"),
    keywords=ARCANE_TELEPORT,
)
def p5736(c: Cast) -> None:
    """This one teleports the enemy rather than the swordmage, so the square
    wanted is one next to *me*; `beside` with no argument gives it. The
    printed rule that the combat advantage does not happen either when
    there is no such square falls out of the same guard."""
    victim = _aegis(c)
    if victim is None:
        return
    me, last = c.me, {"round": -1}

    def haul(ev: Hit) -> None:
        if last["round"] == c.world.round or not _left_me_out(c, ev, victim):
            return
        landing = beside(c)
        if landing is None or not c.may("haul it back", who=me):
            return
        last["round"] = c.world.round
        c.teleport(20, who=victim, to=landing)
        c.grants_advantage(on=victim, to="team", until=When.EONT)
        _f1156(c, me, victim)

    c.watch(Hit, haul, until=When.ENCOUNTER, on=me, label=f"{c.ref} answer")
