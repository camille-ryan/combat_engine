"""Seeker level 3."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.seeker import (
    PRIMAL_WEAPON,
    extra_dice,
    foes_around,
    free_near,
    has_bow,
    has_thrown,
    square_of,
)
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    UpTo,
    When,
    power,
)
from combat_engine.engine.basic import RANGED
from combat_engine.engine.events import TurnEnd, TurnStart
from combat_engine.engine.query import team


@power(
    "p11473",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p11473(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d8"))
    victim = c.target
    if victim is None:
        return

    def spite(ev: Any) -> None:
        for foe in foes_around(c, victim):
            c.flat(5, on=foe)

    c.on_attack(spite, by=victim, until=When.EONT, once=True)


@power(
    "p11474",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.POISON,
        Keyword.CONJURATION,
    ],
    attack=Attack(WIS, vs=AC),
    requires=has_thrown,
    requires_text="a light or heavy thrown weapon, to make the melee attack",
)
def p11474(c: Cast) -> None:
    """The sting is owed by whoever was beside it when its turn began and had
    walked off by the end, so both ends of the turn have to be watched."""
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod, dtype=DamageType.POISON)
    spot = free_near(c, c.there)
    if not spot:
        return
    scorpion = c.conjure(spot[0], until=When.EONT, sustain=None)
    stood: set[int] = set()

    def began(ev: TurnStart) -> None:
        if team(c.world, ev.actor) is not team(c.world, c.me) and c.adjacent_to(
            scorpion, ev.actor
        ):
            stood.add(ev.actor)

    def ended(ev: TurnEnd) -> None:
        if ev.actor in stood:
            stood.discard(ev.actor)
            if not c.adjacent_to(scorpion, ev.actor):
                c.flat(5, dtype=DamageType.POISON, on=ev.actor)

    c.watch(TurnStart, began, until=When.EONT)
    c.watch(TurnEnd, ended, until=When.EONT)


@power(
    "p11475",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=FORT),
)
def p11475(c: Cast) -> None:
    """"Then push each enemy adjacent to it" -- adjacent to where the target
    has ended up, and away from that square rather than away from the
    caster."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"))
    victim = c.target
    if victim is None:
        return
    c.push(c.str_mod if c.build("second-str") else 2, on=victim)
    from_ = square_of(c, victim)
    for foe in foes_around(c, victim):
        c.push(2, on=foe, anchor=from_)


@power(
    "p12790",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
    requires=has_bow,
    requires_text="a bow",
)
def p12790(c: Cast) -> None:
    """The miss line is a bonus to one named row, so it is gated on which row
    is being rolled rather than on the shape of the attack."""

    def ranged_basic(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") == RANGED

    if c.strike():
        extra = c.dex_mod if c.build("second-dex") else 0
        c.damage(c.w(2), c.wis_mod + extra)
    else:
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT, kind="power", when=ranged_basic
        )


@power(
    "p16601",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p16601(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod)
        c.teleport(1, who=c.target)
        c.penalty("damage", c.wis_mod, until=When.EONT)


@power(
    "p9512",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
    no_provoke=True,
)
def p9512(c: Cast) -> None:
    """The printed Special exempts the row only from the *target's* opening;
    the header field is all or nothing, so an adjacent third party also loses
    its swing. That is the nearest the header can say."""
    if c.strike():
        c.damage(c.w(), c.wis_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.EONT)
    if c.first:
        c.shift(1)


@power(
    "p9513",
    level=3,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p9513(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.EOTNT)
