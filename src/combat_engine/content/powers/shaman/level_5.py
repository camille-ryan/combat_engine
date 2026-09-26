"""Shaman, level 5 dailies."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
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
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    by_melee,
    power,
    spread,
)
from combat_engine.engine.query import distance_between

from ._spirit import beside_spirit, friends, spirit_square

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


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


# -- the rows built round the spirit ----------------------------------------


@power(
    "p12529",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p12529(c: Cast) -> None:
    """"Until your spirit companion is no longer present" is not a duration
    the engine has, so the zone runs the encounter and its payout is gated
    on the spirit still being there instead."""
    if c.first:
        ring = c.zone(c.area(), until=When.ENCOUNTER)

        def gust(ev: Any) -> None:
            who = getattr(ev, "actor", None)
            spirit = c.companion()
            if spirit is None or who is None or who == spirit:
                return
            if who not in c.world.zones.occupants(ring):
                return
            c.flat(3, on=who)
            c.push(1, on=who, anchor=spirit_square(c))

        c.watch(TurnStart, gust, until=When.ENCOUNTER, on=c.me)
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod)
        c.ongoing(5)
    else:
        c.half_damage("2d6", c.wis_mod)
        c.push(1, anchor=spirit_square(c))


@power(
    "p12871",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p12871(c: Cast) -> None:
    """The second printed block is an opportunity action that exists only
    while the zone does. There is no verb for "you may now use that row",
    so it is armed here off an enemy's turn ending in the zone and rolled
    with this row's own attack line."""
    if c.first:
        wind = c.zone(c.area(), until=When.EONT)

        def howl(ev: Any) -> None:
            foe = getattr(ev, "actor", None)
            if foe not in c.enemies():
                return
            if foe not in c.world.zones.occupants(wind):
                return
            if c.strike(on=foe):
                c.slide(3, on=foe)

        c.watch(TurnEnd, howl, until=When.EONT, on=c.me)
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod)
        c.slide(3)
        c.dazed(until=When.SAVE_ENDS)
    if c.last:
        c.dismiss_companion()


@power(
    "p16501",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p16501(c: Cast) -> None:
    """Concealment is not something a creature can be barred from using --
    there is no verb for it -- so the half of the rider that can be said is
    the combat advantage."""
    if c.first:
        gloom = c.zone(c.area(), until=When.EONT)
        for foe in c.enemies():
            c.penalty(
                "attack", 2, on=foe, until=When.EONT,
                when=lambda ctx, f=foe: f in c.world.zones.occupants(gloom),
            )

        def sting(ev: Any) -> None:
            who = getattr(ev, "actor", None)
            if who in c.enemies() and who in c.world.zones.occupants(gloom):
                c.flat(5, dtype=DamageType.PSYCHIC, on=who)

        c.watch(TurnEnd, sting, until=When.EONT, on=c.me)
    if c.strike(from_=c.companion()):
        c.damage("1d10", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.SAVE_ENDS, to="allies")
    if c.last:
        c.dismiss_companion()


@power(
    "p5454",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD, Keyword.HEALING],
    attack=Attack(WIS, vs=WILL),
)
def p5454(c: Cast) -> None:
    """Three payouts, growing, then the hold is spent. The flag keeps the
    extra hit points from being a healing that pays itself out again."""
    if c.strike(from_=c.companion()):
        c.damage("3d8", c.wis_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("3d8", c.wis_mod, dtype=DamageType.COLD)
    paid = [0]
    busy = [False]

    def swell(ev: Any) -> None:
        mate = getattr(ev, "target", None)
        if busy[0] or paid[0] >= 3 or getattr(ev, "amount", 0) <= 0:
            return
        if mate not in friends(c, with_me=True) or not beside_spirit(c, mate):
            return
        paid[0] += 1
        busy[0] = True
        try:
            c.heal(c.roll(f"{paid[0]}d8"), on=mate)
        finally:
            busy[0] = False

    c.watch(Healed, swell, until=When.ENCOUNTER, on=c.me)


@power(
    "p5555",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=FORT),
)
def p5555(c: Cast) -> None:
    """"Before or after the attack" is taken before it, and the spirit is
    moved when there is one to move."""
    if c.first:
        if c.companion() is not None:
            c.move_companion(c.speed_of())
        else:
            c.slide(c.speed_of(), on=c.me)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.FIRE)
        c.slide(max(1, c.wis_mod))
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.FIRE)
        c.slide(1)


@power(
    "p9753",
    level=5,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p9753(c: Cast) -> None:
    """The hold is a named effect with nothing in it: what it is for is the
    saving throw that ends it, which is why it is made by hand rather than
    left save-ends."""
    victim = c.target
    if c.strike(from_=c.companion()):
        c.damage("2d10", c.wis_mod)
    else:
        c.half_damage("2d10", c.wis_mod)
    if victim is None:
        return
    hex_ = c.effect(f"{c.ref}", until=When.ENCOUNTER, on=victim)

    def flinch(ev: Any) -> None:
        if hex_ is None or hex_.ended or ev.target != victim:
            return
        if ev.attacker not in friends(c) or not by_melee(c.world, c.me, ev):
            return
        c.flat(5, on=victim)
        if c.save(on=victim):
            c.world.effects.end(hex_, "saved")

    c.watch(Miss, flinch, until=When.ENCOUNTER, on=c.me)
