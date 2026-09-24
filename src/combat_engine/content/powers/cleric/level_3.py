"""Cleric, level 3: encounter attacks.

Two of the four spend their rider on somebody other than the creature they
hit -- an ally is handed combat advantage, or the whole party is handed a
bonus to shoot with -- and neither of those is a mod the beneficiary's own
row can carry, so both are written where the engine actually reads them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between


def _ranged_row(ref: str) -> bool:
    """Was that attack made with a ranged row?

    The attack context carries the attacking power's ref and nothing about
    its shape, so "ranged attack rolls" is read back off the registry.
    """
    row = get(ref) if ref else None
    return row is not None and row.reach_of().kind == "ranged"


def _nearest_to(c: Cast, who: int, pool: list[int]) -> list[int]:
    """Allies sorted by how close they are to the creature you just hit.

    Whoever is standing next to it is the one who can use a rider aimed at
    it this turn, and a headless fight takes the first name offered.
    """
    return sorted(pool, key=lambda a: distance_between(c.world, a, who))


@power(
    "p490",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.DIVINE, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=WILL),
)
def p490(c: Cast) -> None:
    """No damage at all: a daze and then a printed either/or.

    Prone is offered first because it is worth the same wherever the fight
    is standing, while the slide is only worth anything if there is
    somewhere worth sliding to -- and the decider that answers this
    question in a headless fight cannot tell.
    """
    if not c.strike():
        return
    c.dazed()
    if c.choose(["knock it prone", "slide it"], "what the blow does") == "slide it":
        c.slide(3 + c.cha_mod)
    else:
        c.prone()


@power(
    "p894",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p894(c: Cast) -> None:
    """The Effect line lands whether or not the attack did.

    `c.grants_advantage` hands the advantage to the caster and the printed
    line hands it to one ally, so the relation is applied by hand -- the
    same thing that method does, pointed at somebody else.
    """
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
    foe = c.target
    seen = [a for a in c.allies() if c.can_see(a)]
    friend = c.choose(_nearest_to(c, foe, seen), "who it is open to") if seen else None
    if friend is not None:
        c.world.effects.apply(
            foe, c.me, When.EONT,
            label="p894",
            relations=[(Relation.GRANTS_CA_TO, foe, friend)],
        )


@power(
    "p895",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def p895(c: Cast) -> None:
    """A bonus that belongs to the target and is carried by the shooters.

    An attack mod is only ever read off the attacker, so "ranged attack
    rolls against the target" is applied once per creature that might make
    one, gated on who is being shot at and on the row doing the shooting.
    The target's own side would printedly benefit too; they do not shoot
    each other, so they are left out rather than given a bonus nothing
    could ever spend.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)
    foe = c.target

    def shooting_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe and _ranged_row(ctx.get("power") or "")

    for shooter in (c.me, *c.allies()):
        c.bonus("attack", 4, on=shooter, when=shooting_it)


@power(
    "p896",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(STR, vs=FORT),
)
def p896(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.THUNDER)
        c.push(2)
        c.prone()
