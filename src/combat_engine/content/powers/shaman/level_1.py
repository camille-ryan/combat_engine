"""Shaman, level 1.

Only the rows that never mention the spirit companion are here. The rest of
the level needs a persistent entity of the shaman's own -- one that occupies
a square, that "melee spirit 1" measures from, and that "adjacent to your
spirit companion" reads off -- and no such thing exists, so they are absent
rather than approximated.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_CREATURE,
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
    CloseBlast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    TurnStart,
    When,
    power,
    spread,
)

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]


@power(
    "p3876",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p3876(c: Cast) -> None:
    """The zone is laid down where the target stood. Its two printed clauses
    are both grants of an action -- move the zone, slide everyone in it --
    and there is no verb for either, so the zone itself is all of it."""
    at = c.there
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.slide(2)
    else:
        c.half_damage("2d10", c.wis_mod)
    if at is not None:
        c.zone(spread({at}, 1), until=When.ENCOUNTER)


@power(
    "p3886",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p3886(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.COLD)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.save(on=mate, bonus=5)


@power(
    "p4783",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p4783(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        mate = c.choose(c.allies(), "who the target grants combat advantage to")
        if mate is not None:
            c.grants_advantage(until=When.EONT, to=mate)


@power(
    "p5393",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.HEALING],
    attack=Attack(WIS, vs=FORT),
)
def p5393(c: Cast) -> None:
    """Regeneration has no verb of its own, so it is a watch on the
    beneficiary's own turn start, gated on being bloodied. The printed
    escape clause -- end it as a minor action for 10 hit points -- is a
    minor action nobody can spend, and is dropped."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
    else:
        c.half_damage("1d8", c.wis_mod)
    if not c.first:
        return
    for mate in dict.fromkeys([c.me, *c.in_squares(c.area(), side="ally")]):

        def tick(ev: object, who: int = mate) -> None:
            if getattr(ev, "actor", None) == who and c.bloodied(on=who):
                c.heal(2, on=who)

        c.watch(TurnStart, tick, until=When.ENCOUNTER, on=mate)


@power(
    "p5554",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.POISON],
    attack=Attack(WIS, vs=REF),
)
def p5554(c: Cast) -> None:
    """"Until this ongoing damage ends" is read off the burn itself rather
    than given its own clock -- the allies' bonus is held for the encounter
    and gated on the hold still being live."""
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod)
    burn = c.ongoing(5, DamageType.POISON)
    if burn is None or victim is None:
        return
    for mate in c.allies():
        c.bonus(
            "attack", 2, on=mate, until=When.ENCOUNTER,
            when=lambda ctx, v=victim, b=burn: (
                ctx.get("target") == v and not b.ended
            ),
        )


@power(
    "p9743",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p9743(c: Cast) -> None:
    """"Difficult terrain for your enemies" is one rough zone plus everyone
    on my side ignoring that label. The cover the zone grants has no verb
    and is left out; the slide does not force the square outside the burst,
    which the world's decider picks."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, difficult=c.ref)
        for mate in dict.fromkeys([c.me, *c.allies()]):
            c.ignores_difficult(c.ref, on=mate, until=When.ENCOUNTER)
    if c.strike():
        c.slide(2)
        c.prone()
    else:
        c.slide(1)
