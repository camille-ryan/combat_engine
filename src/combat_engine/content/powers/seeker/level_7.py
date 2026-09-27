"""Seeker level 7."""

from __future__ import annotations

from combat_engine.content.powers.seeker import (
    PRIMAL_WEAPON,
    bites,
    extra_dice,
    foes_around,
    landed_on,
)
from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    STANDARD,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    DamageType,
    Keyword,
    Ranged,
    UpTo,
    When,
    power,
)
from combat_engine.engine.grid import spread


@power(
    "p11481",
    level=7,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=UpTo(2),
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p11481(c: Cast) -> None:
    """"If you hit both targets" spans two calls of a body that keeps nothing
    between them, so the teleport waits for the last target and reads which
    ones landed off the log."""
    if c.strike():
        c.damage(c.w(), c.wis_mod)
    if not c.last:
        return
    landed = landed_on(c)
    if len(landed) >= 2 and c.may("swap the two of them"):
        c.swap(landed[1], who=landed[0])
        for who in landed[:2]:
            c.dazed(on=who, until=When.EONT)
        return
    for who in landed:
        c.teleport(3, who=who)


@power(
    "p11482",
    level=7,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p11482(c: Cast) -> None:
    """The secondary burst is a consequence of the hit, so it is rolled inside
    it; its defence differs from the header's, hence `c.attack`."""
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d8"))
    victim = c.target
    for foe in c.in_squares(spread({c.there}, 1), side="enemy"):
        if foe == victim:
            continue
        if c.attack(c.wis_, FORT, on=foe):
            c.slide(1, on=foe)
            c.grants_advantage(on=foe, to="allies", until=When.EONT)


@power(
    "p11483",
    level=7,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(WIS, vs=FORT),
)
def p11483(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.wis_mod)
        c.push(c.str_mod if c.build("second-str") else 2)


@power(
    "p9519",
    level=7,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p9519(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod, dtype=DamageType.THUNDER)
    c.prone()
    c.condition(Condition.DEAFENED, until=When.EONT)
    if not c.build("second-dex"):
        return
    for foe in foes_around(c, c.target):
        c.flat(c.dex_mod, dtype=DamageType.THUNDER, on=foe)
        c.condition(Condition.DEAFENED, on=foe, until=When.EONT)


@power(
    "p9520",
    level=7,
    cls="seeker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.POISON, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
)
def p9520(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.wis_mod + extra_dice(c, "1d6"), dtype=DamageType.POISON)
    zone = c.zone(spread({c.there}, 1), until=When.EONT)
    bites(c, zone, c.wis_mod, DamageType.POISON, until=When.EONT)
