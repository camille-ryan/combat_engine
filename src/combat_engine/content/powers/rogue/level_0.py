"""Rogue, level 0: the move-action utilities and the two triggered ones.

Eight of the eleven are a move plus something bought for the rest of the
turn. Where the printed line buys something *for the duration of the move*
-- a climb speed, an exemption from opportunity attacks -- the hold is
applied, the walk is taken, and the hold is ended by hand: `When.EOT` is a
whole turn too long, and a second move in the same turn would still be
covered by it.

`p12710` is declared in `Window.BEFORE` of `AttackDeclared`. A free action is
a reaction by default, and this one has to raise the attack bonus before the
die is read.

Two of them gate a damage bonus on the swing being a basic attack. The damage
context carries `target`, `power`, `opportunity` and `charge`, so the gate is
on the ref -- and `p12714`'s further "...for which you do not have combat
advantage" is dropped, because the context carries no advantage flag.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import *
from combat_engine.engine.query import (
    concealment_of,
    cover_between,
    distance_between,
    flanked_by,
    has_combat_advantage,
)

MARTIAL = [Keyword.MARTIAL]
BASICS = (MELEE, RANGED)


def _is_basic(ctx: dict[str, Any]) -> bool:
    return ctx.get("power") in BASICS


def _basic_on_a_giveaway(world: World, me: int, ev: AttackDeclared) -> bool:
    return (
        ev.attacker == me
        and ev.power in BASICS
        and distance_between(world, me, ev.target) <= 5
        and has_combat_advantage(world, me, ev.target)
    )


@power(
    "p12710",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you make a basic attack against an enemy within 5 squares that is "
    "granting combat advantage to you",
    on=Trigger(
        AttackDeclared,
        _basic_on_a_giveaway,
        "you make a basic attack against an enemy granting you combat advantage",
        window=Window.BEFORE,
    ),
)
def p12710(c: Cast) -> None:
    dice = 1 + sum(lv <= c.level for lv in (7, 17, 27))
    c.bonus("attack", 3, on=c.me, until=When.EOT, once=True, kind="power")
    victim = getattr(c.trigger, "target", None)

    def sting(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.flat(c.roll(f"{dice}d6"), on=victim)

    c.watch(Hit, sting, until=When.EOT, once=True)


@power(
    "p12711",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12711(c: Cast) -> None:
    reach = max(1, c.speed_of() - 2)
    climbing = c.mode("climb", reach, until=When.EOT, on=c.me)
    c.move(reach, who=c.me)
    if climbing is not None:
        c.world.effects.end(climbing, "the move ended")
    step = 2 + 2 * sum(lv <= c.level for lv in (11, 21))
    c.bonus("damage", step, on=c.me, until=When.EOT, once=True, when=_is_basic, kind="power")


@power(
    "p12712",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12712(c: Cast) -> None:
    """The printed test is made at the moment you attack; a held grant cannot
    re-ask it per swing, so it is asked once where the move ends."""
    c.move(c.speed_of(), who=c.me)
    for foe in c.within(5, side="enemy"):
        if not [a for a in c.within(1, of=foe, side="enemy") if a != foe]:
            c.grants_advantage(on=foe, until=When.EOT)


@power(
    "p12713",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12713(c: Cast) -> None:
    c.shift(2)

    def again(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            c.shift(2)

    c.watch(TurnEnd, again, until=When.EONT, once=True)


@power(
    "p12714",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12714(c: Cast) -> None:
    c.move(c.speed_of(), who=c.me)
    if c.cha_mod > 0:
        c.bonus("damage", c.cha_mod, on=c.me, until=When.EOT, once=True, when=_is_basic,
            kind="power")


@power(
    "p12715",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12715(c: Cast) -> None:
    """There are no skill checks, so the Stealth check succeeds; its
    precondition is not narrative and is asked of the board."""
    c.move(max(1, c.speed_of() - 2), who=c.me)
    if int(concealment_of(c.world, c.me)) or any(
        int(cover_between(c.world, foe, c.me)) for foe in c.enemies()
    ):
        c.hide()


@power(
    "p12716",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12716(c: Cast) -> None:
    """The printed exemption is per square left, and a hold cannot be that
    fine-grained -- so it covers the whole move and comes down after it."""
    safe = c.no_provoke(until=When.EOT)
    c.move(c.speed_of(), who=c.me)
    if safe is not None:
        c.world.effects.end(safe, "the move ended")
    for foe in c.enemies():
        if [a for a in c.within(1, of=foe, side="ally") if a != c.me]:
            c.grants_advantage(on=foe, until=When.EOT)


@power(
    "p12717",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12717(c: Cast) -> None:
    """`MoveStart`: the flank has to still be standing for the row to be
    true, and by `MoveEnd` the enemy has stepped out of it."""
    c.shift(1)

    def on_shift(ev: MoveStart) -> None:
        if ev.kind_ != "shift" or ev.actor not in c.enemies():
            return
        if flanked_by(c.world, ev.actor, c.me):
            c.provoke(c.me, on=ev.actor, why=c.ref)

    c.watch(MoveStart, on_shift, until=When.EONT, window=Window.BEFORE)


@power(
    "p12718",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12718(c: Cast) -> None:
    c.shift(3)

    def spill(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != MELEE:
            return
        others = [e for e in c.within(1, side="enemy") if e != ev.target]
        if others:
            c.flat(c.str_mod, on=c.choose(others, "who else the blade catches"))

    c.watch(Hit, spill, until=When.EOT, once=True)


@power(
    "p12719",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12719(c: Cast) -> None:
    c.shift(2)

    def trip(ev: Hit) -> None:
        if ev.attacker == c.me and ev.power == MELEE and c.may("knock it prone"):
            c.prone(on=ev.target)

    c.watch(Hit, trip, until=When.EOT, once=True)


@power(
    "p12722",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an enemy attacks you",
    on=Trigger(AttackDeclared, targets_me, "an enemy attacks you"),
)
def p12722(c: Cast) -> None:
    """Four separate `once` bonuses: only one defence is read per attack, so
    the other three stay up until the end of the turn and expire unspent."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(
            d, 4, on=c.me, until=When.EOT, once=True,
            when=lambda ctx, who=foe: ctx.get("attacker") == who,
        )

    def later(ev: TurnEnd) -> None:
        if ev.actor == foe and c.may("shift 3 squares"):
            c.shift(3)

    c.watch(TurnEnd, later, until=When.EONT, once=True)
