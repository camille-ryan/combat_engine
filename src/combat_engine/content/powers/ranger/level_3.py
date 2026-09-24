"""Ranger, level 3: the encounter attack powers.

All four print both attack lines at once, so all four are `MeleeOrRanged`
with `attack_alt` carrying the second line and `c.attack_mod` in the damage
line -- the shape the level 1 file's docstring sets out. Two of them are the
two-attack rows as well: main weapon then off-hand on the melee branch, two
shots from the same bow on the ranged one.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    ENCOUNTER,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Gear,
    Keyword,
    MeleeOrRanged,
    UpTo,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.query import team
from combat_engine.engine.triggers import Trigger

MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_SOMEONE_ATTACKED = "you or an ally is attacked by a creature"


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _me_or_ally_attacked(world: World, me: int, ev: AttackDeclared) -> bool:
    """"You or an ally is attacked" -- written out for want of an `either`.

    `targets_me` is half the sentence and `ally_within(n)` is the other half
    but forces a range the printed line does not name, and the combinator
    the module ships is `both`.
    """
    victim = getattr(ev, "target", None)
    if victim is None:
        return False
    return victim == me or team(world, victim) is team(world, me)


@power(
    "p1416",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    trigger=_SOMEONE_ATTACKED,
    on=Trigger(AttackDeclared, when=_me_or_ally_attacked, text=_SOMEONE_ATTACKED),
)
def p1416(c: Cast) -> None:
    """The penalty is spent on the roll this interrupted.

    `once=True` ends it after the first attack roll the target makes, and an
    interrupt resolves before that roll, so the one it lands on is the
    triggering attack.
    """
    if c.strike():
        c.damage(c.w(1), c.attack_mod)
        c.penalty("attack", 3 + c.wis_mod, once=True)


@power(
    "p1521",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=REF),
    attack_alt=Attack(DEX, vs=REF),
)
def p1521(c: Cast) -> None:
    """Printed for the quarry only, and nothing can ask whether one is.

    The quarry lives in a closure inside `cf:ranger-quarry` rather than as
    anything on the creature, so the restriction is dropped and any one
    enemy may be attacked.
    """
    if c.strike():
        c.damage(c.w(2), c.attack_mod)


@power(
    "p855",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p855(c: Cast) -> None:
    """Two attacks over one or two creatures, and a push for each one that lands.

    Both hits on the same creature do not push it twice: the printed line
    replaces the two single squares with one push of 1 + Wisdom, so the
    pushing waits until both swings are done and is done once.
    """
    shots = 2 if (c.first and c.last) else 1
    landed = 0
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand=hand), c.attack_mod)
    if landed == 2:
        c.push(1 + c.wis_mod)
    elif landed:
        c.push(1)


@power(
    "p978",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p978(c: Cast) -> None:
    """The Special line offers the shift after either attack; it is taken after both.

    Stepping between the two swings cannot be offered -- the choice would
    have to be made before the second attack is rolled and nothing asks it
    -- so the shift happens once, when the shooting stops.
    """
    shots = 2 if (c.first and c.last) else 1
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            c.damage(c.w(1, hand=hand), c.attack_mod)
    if c.last and c.may("shift"):
        c.shift(1 + c.wis_mod)
