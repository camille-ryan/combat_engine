"""Runepriest: the second stat blocks printed beside `p11394` and `p11400`.

Both are bursts whose origin is "a square in the primary target's space",
and a close burst in the header is always centred on the caster -- there is
no way to say otherwise. So both declare `NO_TARGET` and pick their own
targets around the creature the parent named, the way the parents used to
do it inline.

Each parent now leaves two holds: one on the caster labelled with its own
ref, which is the Requirement these read, and one on the primary target
labelled `<ref> origin`, which is the origin square the printed line names.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.cards import active
from combat_engine.engine import *

_PROTECTION = "rune:protection"


def _in_rune(c: Cast, which: str) -> bool:
    """Is the caster in that rune state? An unset state counts as in it."""
    held = c.world.effects.stance_of(c.me)
    return held is None or which in held.label


def _origin(world: World, me: int, ref: str) -> int | None:
    """The primary target the parent named, from the hold it left there."""
    for eff in world.effects.live.values():
        if eff.source == me and eff.label == f"{ref} origin":
            return eff.owner
    return None


def _the_primary_attacks(ref: str):  # noqa: ANN202
    def check(world: World, me: int, ev: Any) -> bool:
        return ev.attacker == _origin(world, me, ref)

    return check


def _the_primary_drops(ref: str):  # noqa: ANN202
    def check(world: World, me: int, ev: Any) -> bool:
        return ev.actor == _origin(world, me, ref)

    return check


@power(
    "p11394b",
    level=7,
    cls="runepriest",
    usage=ENCOUNTER,
    action=OPPORTUNITY,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=REF),
    requires=active("p11394"),
    requires_text="the p11394 power must be active",
    trigger="the primary target makes an attack",
    on=Trigger(AttackDeclared, _the_primary_attacks("p11394"), "the primary target attacks"),
)
def p11394b(c: Cast) -> None:
    """The rune clause is read when the burst goes off, by which time using
    the parent has already switched the state -- which is the order the two
    printed blocks are in."""
    victim = _origin(c.world, c.me, "p11394")
    if victim is None:
        return
    protection = _in_rune(c, _PROTECTION)
    for foe in c.within(1, of=victim, side="enemy"):
        if foe == victim:
            continue
        if c.strike(on=foe, from_=victim):
            c.damage(0, c.str_mod, dtype=DamageType.LIGHTNING, on=foe)
            if protection:
                c.slide(2, on=foe)


@power(
    "p11400b",
    level=9,
    cls="runepriest",
    usage=DAILY,
    action=OPPORTUNITY,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.WEAPON],
    attack=Attack(STR, vs=WILL),
    requires=active("p11400"),
    requires_text="the p11400 power must be active",
    trigger="the primary target drops to 0 hit points",
    on=Trigger(Dropped, _the_primary_drops("p11400"), "the primary target drops"),
)
def p11400b(c: Cast) -> None:
    """The burst is centred on the primary target and the primary target has
    just dropped, so `from_=` is not used here as `p11394b` uses it: it
    re-attributes the attack to that creature, and a corpse cannot swing --
    every roll comes back refused. The origin survives as the square the
    targets are measured from."""
    victim = _origin(c.world, c.me, "p11400")
    if victim is None:
        return
    for foe in c.within(3, of=victim, side="enemy"):
        if c.strike(on=foe):
            c.dazed(on=foe, until=When.SAVE_ENDS)
