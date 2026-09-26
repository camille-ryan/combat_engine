"""Shaman, level 5 dailies."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    UpTo,
    When,
    by_melee,
    power,
    spread,
)
from combat_engine.engine.query import distance_between

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]


@power(
    "p3877",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p3877(c: Cast) -> None:
    """The printed second half is a separate immediate interrupt that only
    exists while this is up. There is no verb for "you may now use that
    row", so the retaliation is armed here instead: the attack line in the
    header is the interrupt's, rolled from the watch."""
    mate = c.target
    if mate is None:
        return
    c.temp_hp(10, on=mate)
    c.resist(5, DamageType.FIRE, on=mate, until=When.ENCOUNTER)

    def punish(ev: Any) -> None:
        if ev.target != mate or ev.attacker not in c.enemies():
            return
        if not by_melee(c.world, c.me, ev):
            return
        if c.strike(on=ev.attacker):
            c.damage("2d6", c.wis_mod, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, punish, until=When.ENCOUNTER, on=c.me)


@power(
    "p3881",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3881(c: Cast) -> None:
    """The standing "drops prone whenever hit" is an Effect line, so it is
    hung on every target whether the swing landed or not."""
    victim = c.target
    if c.strike():
        c.damage("2d6", c.wis_mod)
        c.prone()
    else:
        c.half_damage("2d6", c.wis_mod)
    if victim is None:
        return

    def flop(ev: Any, v: int = victim) -> None:
        if ev.target == v:
            c.prone(on=v)

    c.watch(Hit, flop, until=When.SAVE_ENDS, on=victim)


@power(
    "p3882",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p3882(c: Cast) -> None:
    """The zone's own clauses both grant an action -- shift 4 as a move,
    move the zone as a move -- and neither can be said, so the zone is laid
    down and does nothing further."""
    at = c.there
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.blinded(until=When.EONT)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
    if at is not None:
        c.zone(spread({at}, 3), until=When.ENCOUNTER)


@power(
    "p5397",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p5397(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d10", c.wis_mod)
    else:
        c.half_damage("2d10", c.wis_mod)
    if victim is None:
        return
    for who in dict.fromkeys([c.me, *c.allies()]):
        c.bonus(
            "attack", 2, on=who, until=When.ENCOUNTER, kind="untyped",
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "p9752",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p9752(c: Cast) -> None:
    if c.first:
        coils = c.zone(c.area(), until=When.ENCOUNTER)

        def bite(ev: Any) -> None:
            if ev.attacker not in c.enemies():
                return
            if ev.target not in c.world.zones.occupants(coils):
                return
            if ev.target == c.me or ev.target in c.allies():
                c.flat(c.wis_mod, on=ev.attacker)

        c.watch(Hit, bite, until=When.ENCOUNTER, on=c.me)
    if c.strike():
        c.damage("2d6", c.wis_mod)
    else:
        c.half_damage("2d6", c.wis_mod)


@power(
    "p9754",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2, "ally"),
    keywords=PRIMAL,
)
def p9754(c: Cast) -> None:
    """The 1d10 is a one-shot damage bonus gated on `charge`, rolled up
    front -- adding it inside the swing would have it maxed on a crit."""
    mate = c.target
    if mate is None:
        return
    c.bonus(
        "attack", 2, on=mate, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )
    c.bonus(
        "damage", 2, on=mate, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )
    c.bonus(
        "damage", c.roll("1d10"), on=mate, until=When.EOT, once=True,
        kind="untyped", when=lambda ctx: bool(ctx.get("charge")),
    )
    foes = c.enemies()
    if foes:
        victim = min(foes, key=lambda f: distance_between(c.world, mate, f))
        c.charge_at(victim, who=mate)
