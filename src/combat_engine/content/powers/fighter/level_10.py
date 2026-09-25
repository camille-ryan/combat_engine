"""Fighter, level 10: utility. Nothing here rolls an attack.

`p1442` is an aura 1 rather than a check for adjacency at the moment it is
taken -- the README's rule that a standing "allies adjacent to you" effect
is an aura, with `ZoneEntered` and `ZoneExited` putting the bonus on and
taking it off, which is `paladin/level_5.py`'s arrangement. Its two halves
are alternatives, not a base and a rider: a +1 plus a gated +1 of the same
kind is +1 forever, so the shield is asked once and one of the two is given.

`p1443` refuses the damage on `DamageRolled`, which is the one moment the
number exists and has not yet come off anybody. The attack still hits and
everything else it carries still lands, which is what "you take no damage
from the attack" says and what cancelling the `Hit` would not.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    AttackRolled,
    Cast,
    Effect,
    Keyword,
    Trigger,
    When,
    Window,
    ZoneEntered,
    distance,
    power,
    would_hit_me,
)
from combat_engine.engine.events import DamageRolled, ZoneExited
from combat_engine.engine.movement import walk
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone

MARTIAL = [Keyword.MARTIAL]

_I_AM_HIT = "you are hit by an attack"


@power(
    "p1442",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p1442(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    shielded = c.wielding("shield")
    amount = 2 if shielded else 1
    guarded = (AC, REF) if shielded else (AC,)

    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    held = c.world.get(ring, Zone)
    given: dict[int, list[Effect]] = {}

    def cover(who: int) -> None:
        if who in given or who == c.me or who not in c.allies():
            return
        given[who] = [
            e
            for e in (
                c.bonus(d, amount, on=who, until=When.ENCOUNTER, kind="shield")
                for d in guarded
            )
            if e is not None
        ]

    def uncover(who: int) -> None:
        for effect in given.pop(who, []):
            c.world.effects.end(effect, "stepped away")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            cover(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == ring:
            uncover(ev.actor)

    def cleanup() -> None:
        for who in list(given):
            uncover(who)

    def furl() -> None:
        if c.world.get(ring, Zone) is not None:
            c.world.zones.end(ring, "stance ended")

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        # The aura ending unsubscribes the pair above before it announces
        # the exits, so the bonuses come off here rather than there.
        held.effect.on_end.append(cleanup)
    stance.on_end.append(furl)
    for who in c.world.zones.occupants(ring):
        cover(who)


@power(
    "p1443",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_AM_HIT,
    on=Trigger(AttackRolled, when=would_hit_me, text=_I_AM_HIT),
)
def p1443(c: Cast) -> None:
    """The blow lands and arrives empty, and the fighter pays for it."""
    me = c.me
    holder: list[Effect] = []

    def spare(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        ev.amount = 0
        ev.cancel(c.ref)
        if holder:
            c.world.effects.end(holder[0], "the blow was turned aside")

    holder.append(
        c.watch(
            DamageRolled,
            spare,
            until=When.EOT,
            window=Window.BEFORE,
            on=me,
            label=f"{c.ref} no damage",
        )
    )
    c.stunned(until=When.EONT, on=me)
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, on=me, until=When.EONT)


@power(
    "p1444",
    level=10,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1444(c: Cast) -> None:
    """"Only if you can end the move adjacent to an enemy" is a filter on
    the destination, so the squares are picked here rather than handed to
    the decider, which would happily offer one in the open."""
    reach = [sq for foe in c.enemies() for sq in squares_of(c.world, foe)]
    paths = c.world.reachable_paths(c.me, 3)
    closing = sorted(
        sq for sq in paths if any(distance(sq, at) <= 1 for at in reach)
    )
    dest = c.choose(closing, "p1444: where to end up")
    if dest is not None:
        walk(c.world, c.me, paths[dest])
