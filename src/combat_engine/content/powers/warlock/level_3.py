"""Warlock, level 3: the encounter attacks.

Every row prints a pact line -- Infernal, Fey or Star -- that adds the
caster's Intelligence modifier to something. Pacts are not modelled, as in
`level_1.py`, so the base number stands and the clause is written down
rather than guessed at.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    Relation,
    Target,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1341",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=REF),
)
def p1341(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("3d6", c.con_mod, dtype=DamageType.FIRE)
    # The splash is printed as "creatures adjacent to the target", which is
    # everybody standing there, not only enemies -- and not the target, who
    # has already been hit. The Infernal Pact line would add Intelligence
    # modifier to it.
    for other in c.within(1, of=c.target):
        if other != c.target:
            c.damage("1d6", c.con_mod, dtype=DamageType.FIRE, on=other)


@power(
    "p1400",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    # "or two creatures no more than 5 squares apart from each other" -- the
    # spacing between two targets cannot be asked for, so it is only written.
    target=Target("enemy", 2, label="One creature, or two no more than 5 squares apart"),
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1400(c: Cast) -> None:
    # One attack per target, which is what a body called per target already
    # does. The Fey Pact line would add Intelligence modifier to each damage
    # roll.
    if c.strike():
        c.damage("2d8", c.cha_mod)


@power(
    "p1401",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.FEAR],
    attack=Attack(CON, vs=FORT),
)
def p1401(c: Cast) -> None:
    """The advantage is printed for the whole side, not just the caster.

    `c.grants_advantage` hands it to the attacker alone, so the relation is
    applied once per ally on a single effect instead -- the same shape the
    monster rows that open an enemy up to everybody use.
    """
    if not c.strike():
        return
    c.damage("2d8", c.con_mod, dtype=DamageType.COLD)
    victim = c.target
    c.world.effects.apply(
        victim,
        c.me,
        When.EONT,
        label="p1401",
        relations=[
            (Relation.GRANTS_CA_TO, victim, friend) for friend in (c.me, *c.allies())
        ],
    )
    # The Star Pact line would add a penalty to AC equal to Intelligence
    # modifier for the same duration.


@power(
    "p661",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p661(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.damage("1d8", c.cha_mod)
        c.immobilized()
    # The Effect line lands whether anything was hit or not, and after the
    # burst rather than before it -- so it goes on the last target, which is
    # also the one call the body gets when the burst catches nobody.
    if c.last:
        c.teleport(5)
