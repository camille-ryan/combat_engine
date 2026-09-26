"""Shaman, level 6 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Keyword,
    Ranged,
    Trigger,
    UpTo,
    When,
    power,
)
from combat_engine.engine.ecs import World

PRIMAL = [Keyword.PRIMAL]


def drops_me(world: World, me: int, ev: Any) -> bool:
    """Damage that took me to 0 hit points or fewer."""
    return getattr(ev, "target", None) == me and getattr(ev, "hp", 1) <= 0


@power(
    "p11359",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p11359(c: Cast) -> None:
    """"Move through spaces occupied by your enemies" is the phasing rule;
    the engine has no narrower version that lets a creature through bodies
    but not through walls."""
    c.phasing(on=c.target, until=When.EONT)


@power(
    "p3835",
    level=6,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=UpTo(2, "ally"),
    keywords=PRIMAL,
)
def p3835(c: Cast) -> None:
    c.save()


@power(
    "p3836",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p3836(c: Cast) -> None:
    """"One bloodied ally" is a targeting restriction the header cannot
    state, so it is a guard in the body."""
    mate = c.target
    if mate is not None and c.bloodied(on=mate):
        c.resist(5, on=mate, until=When.ENCOUNTER)


@power(
    "p9756",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.FIRE, Keyword.HEALING],
)
def p9756(c: Cast) -> None:
    """`Dropped` names only the creature that fell, never who felled it, so
    "whenever the target reduces an enemy to 0" is read off the damage that
    did it instead."""
    mate = c.target
    if mate is None:
        return

    def reap(ev: Any) -> None:
        if ev.source != mate or ev.hp > 0:
            return
        if ev.target not in c.enemies():
            return
        c.heal(5, on=mate)
        for foe in c.within(1, of=mate, side="enemy"):
            c.flat(2, dtype=DamageType.FIRE, on=foe)

    c.watch(DamageApplied, reap, until=When.ENCOUNTER, on=mate)


@power(
    "p9759",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    trigger="an enemy reduces you to 0 hit points or fewer",
    on=Trigger(
        DamageApplied, drops_me, "an enemy reduces you to 0 hit points or fewer"
    ),
)
def p9759(c: Cast) -> None:
    mate = c.target
    if mate is None or mate == c.me:
        return
    if c.may("spend a healing surge", who=mate):
        c.surge(on=mate)
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.bonus(
            "attack", 2, on=mate, until=When.EONT, kind="untyped",
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )
