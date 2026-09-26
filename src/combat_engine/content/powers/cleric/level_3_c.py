"""Cleric, level 3: the simple-weapon encounter attack."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    When,
    World,
    power,
)


def _simple_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and weapon.category == "simple"


@power(
    "p14299",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.WEAPON],
    attack=Attack(STR, vs=AC, plus=1),
    requires=_simple_weapon,
    requires_text="must use this power with a simple weapon",
)
def p14299(c: Cast) -> None:
    """"Half damage from any damage source, including ongoing" is what
    insubstantial already is, so the Effect is laid as that rather than as a
    resistance, which is a flat number and never touches ongoing damage. The
    Effect is not conditional on the swing landing."""
    if c.strike():
        both_hands = 2 if c.wielding("two-handed") else 0
        c.damage(c.w(2), 2 + c.str_mod + both_hands)
    if c.first:
        nearby = [c.me, *(a for a in c.within(2, side="ally") if a != c.me)]
        who = c.choose(nearby, "who takes only half damage")
        if who is not None:
            c.insubstantial(until=When.EONT, on=who)
