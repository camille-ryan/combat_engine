"""Cleric, level 2: utility. Not an attack roll in the tier.

Every row here is aimed at somebody else, so the whole file is `on=` and
durations. "You or one ally" is `ONE_ALLY`, whose pool already holds the
caster, and "you and each ally in the burst" is `EACH_ALLY` for the same
reason -- neither needs the caster adding back.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_ALLY,
    REF,
    STANDARD,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)
from combat_engine.engine.dsl import ANY_CREATURE


@power(
    "p482",
    level=2,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
)
def p482(c: Cast) -> None:
    """An extra saving throw, out of turn, with Charisma behind it.

    `c.save` rolls against one save-ends effect the target is carrying; a
    target with nothing on it has nothing to shake off, which is a legal --
    and wasteful -- use of the power rather than something to guard against.
    """
    c.save(bonus=c.cha_mod)


@power(
    "p665",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p665(c: Cast) -> None:
    """A surge's worth of hit points **without** spending a surge.

    "As if it had spent" is the whole distinction: `c.surge` would take one
    off the target's pool, and `c.surge_value` is the same number for free.
    """
    c.heal(c.surge_value(of=c.target))


@power(
    "p91",
    level=2,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE],
)
def p91(c: Cast) -> None:
    """+5 to every defence, until the target swings or your next turn ends.

    Two endings, so the bonuses carry the duration that the effect table can
    measure and the other one is a watch on the target's own attack. It
    fires on the declaration, before the roll, so the guard is already gone
    for the attack that spent it -- which costs the target nothing, the
    bonus being defensive.
    """
    guards = [g for g in (c.bonus(d, 5, until=When.EONT) for d in (AC, FORT, REF, WILL)) if g]

    def drop(ev: AttackDeclared) -> None:
        for guard in guards:
            c.world.effects.end(guard, "it attacked")

    if guards:
        c.on_attack(drop, by=c.target, until=When.EONT, once=True)


@power(
    "p945",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
)
def p945(c: Cast) -> None:
    c.bonus(AC, 2, until=When.ENCOUNTER)


@power(
    "p947",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(20),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE],
)
def p947(c: Cast) -> None:
    c.bonus("attack", 1, until=When.ENCOUNTER)
