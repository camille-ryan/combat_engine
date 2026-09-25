"""Barbarian, level 1: the at-will and encounter attacks.

The dailies are in `level_1_b.py`; every one of them is a rage and they
share a shape of their own.

Six things recur across the batch and are said once here.

**The grips.** Seven rows print a Requirement about what is in both hands --
"two melee weapons", "a melee weapon in two hands", "a two-handed reach
weapon". Those are `requires=` gates and come from `fighter/grips.py`; only
the last is composed here, because it is the two printed gates at once.

**"If you are raging"** is `in_rage(c)` from `rage.py`. It is a question
about the caster, and a rage is a stance, so a row that asks it is asking
what stance the barbarian is standing in.

**"1[W] + 1d6 + Strength modifier"** is two `c.damage` calls, not one. The
dice parser resolves `NdM+K` and nothing more, so a weapon die and a flat
die cannot be one expression; and folding the 1d6 into the bonus would stop
it being maxed on a critical, which is the half of the rule that matters.

**The build rider on the four martial at-wills** prints two things at once:
extra dice, and "this attack gains the primal keyword". The dice are
`_extra`; the keyword is header data and cannot be turned on from inside a
body, so those rows carry the printed martial keyword and the change is in
the report.

**"Special: When charging, you can use this power in place of a melee basic
attack"** has no header field -- a charge swings `Powers.basic` -- and is a
different sentence from a row whose printed Effect *is* a charge, which
would carry `charges=True`. No row in this batch is the second kind. They
are written as the standard actions they also are and the missing field is
in the report.

**"Any attacker gains a +N bonus to attack rolls against you"** is a penalty
to all four of the caster's defences: an attack modifier is read off the
*attacker*, so there is nowhere to hang a bonus that every future attacker
would find.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.fighter.grips import reach_weapon, two_handed, two_melee
from combat_engine.engine import (
    AC,
    AT_WILL,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    Condition,
    DamageType,
    Health,
    Keyword,
    Melee,
    When,
    World,
    power,
)
from combat_engine.engine.events import DamageApplied
from combat_engine.engine.grid import blast_placements
from combat_engine.engine.query import squares

from .rage import in_rage

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
ALL_DEFENCES = (AC, FORT, REF, WILL)


def two_handed_reach(world: World, eid: int) -> bool:
    """"You must be wielding a two-handed reach weapon" -- both printed
    gates at once, which is the only way the sentence differs from either."""
    return two_handed(world, eid) and reach_weapon(world, eid)


def _extra(c: Cast, faces: int) -> str:
    """One die, two from 11th, three from 21st.

    The progression the build rider prints and the one three of the
    two-handed rows print for their own extra dice: the same three
    numbers, so it is written once.
    """
    return f"{1 if c.level < 11 else 2 if c.level < 21 else 3}d{faces}"


def _felled_a_nonminion(c: Cast) -> bool:
    """"You have reduced a nonminion enemy to 0 hit points this encounter."

    `Dropped` names who fell and never who felled them, so the log is read
    for `DamageApplied`, which carries the source and the hit points left.
    A minion's single hit point is in the database, so `max_hp` is what
    "nonminion" asks.
    """
    for ev in c.world.bus.log:
        if not isinstance(ev, DamageApplied) or ev.source != c.me or ev.hp > 0:
            continue
        health = c.world.get(ev.target, Health)
        if health is not None and health.max_hp > 1:
            return True
    return False


def _against_the_slowed(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"A bonus to damage rolls against slowed creatures."

    The damage context carries the target and nothing about its condition,
    so the gate asks the board at the moment the damage is rolled.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.is_(Condition.SLOWED, on=who)

    return gate


def _howl(c: Cast, amount: int, dtype: DamageType = DamageType.THUNDER) -> list[int]:
    """"You then howl in a blast 3 that includes the target."

    The placement is chosen rather than derived. `grid.blast` aimed at the
    target's square falls back to the *nearest* legal block when that one is
    illegal -- a blast never covers its own caster -- and the nearest block
    is not the best one: on a four-enemy board it caught the target and
    nobody else while a legal placement two squares over caught three. So
    every block that includes the target is enumerated and the fullest wins,
    which is the choice the printed line hands to the player.

    The target itself comes back out: both rows that howl say "other than
    the target" of the damage, and the one that slows adds it back.
    """
    victim = c.target
    if victim is None:
        return []
    theirs = squares(c.world, victim)
    places = [a for a in blast_placements(squares(c.world, c.me), 3).values() if a & theirs]
    if not places:
        return []
    area = max(places, key=lambda a: (len(c.in_squares(a, side="enemy")), min(a)))
    caught = sorted(f for f in c.in_squares(area, side="enemy") if f != victim)
    for foe in caught:
        if amount:
            c.flat(amount, dtype=dtype, on=foe)
    return caught


# -- at-will ----------------------------------------------------------------


@power(
    "p11560",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed_reach,
    requires_text="needs a two-handed reach weapon",
)
def p11560(c: Cast) -> None:
    """Melee 2 in the header: the printed reach is the weapon's own, and the
    Requirement is what guarantees the weapon has it."""
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
        c.slide(2 if in_rage(c) else 1)


@power(
    "p14408",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14408(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if c.build("berserker"):
        c.damage(_extra(c, 6))
    vacated = c.there
    if c.push(1) and vacated is not None:
        c.shift(1, to=vacated)


@power(
    "p14409",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14409(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if c.build("berserker"):
        c.damage(_extra(c, 8))
    c.grants_advantage(until=When.EONT)


@power(
    "p14410",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14410(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if c.build("berserker"):
        c.damage(_extra(c, 8))
    c.slowed(until=When.EONT)


@power(
    "p14411",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14411(c: Cast) -> None:
    """The step is an Effect line and comes before the roll, so the target is
    whoever the barbarian can reach once it has moved."""
    if c.first:
        c.shift(2)
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if c.build("berserker"):
        c.damage(_extra(c, 8))


@power(
    "p4818",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a melee weapon in two hands",
)
def p4818(c: Cast) -> None:
    """The errata'd Requirement. "You can move 2 extra squares as part of the
    charge" is a rider on a charge's move rather than on this row, and has no
    expression; see the report."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    c.damage(_extra(c, 6))


@power(
    "p4819",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4819(c: Cast) -> None:
    """"You can move through an enemy's space during the shift" is a licence
    for two squares of one move and nothing in `Cast` says it; the shift
    itself is ordinary, and the licence is in the report."""
    if c.first:
        c.shift(2)
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if in_rage(c):
        c.damage("1d6")
    c.push(1)


@power(
    "p4820",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a melee weapon in two hands",
)
def p4820(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if c.level >= 21:
        c.damage("2d6")
    elif c.level >= 11:
        c.damage("1d6")
    c.temp_hp((5 if in_rage(c) else 0) + c.con_mod, on=c.me)


@power(
    "p5211",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p5211(c: Cast) -> None:
    """The off-hand half is damage without a roll -- the printed line has one
    attack and names a second creature outright."""
    dice = 2 if c.level >= 21 else 1
    rage = c.dex_mod if in_rage(c) else 0
    if not c.strike():
        return
    c.damage(c.w(dice), c.str_mod + rage)
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    second = c.choose(others, f"{c.ref}: who the off-hand catches") if others else None
    if second is not None:
        c.damage(c.w(dice, hand="off"), rage, on=second)


@power(
    "p563",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_handed,
    requires_text="needs a melee weapon in two hands",
)
def p563(c: Cast) -> None:
    """The opening is an Effect line and is handed over whether the swing
    landed or not -- unless the barbarian is raging, when it is not handed
    over at all."""
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
        c.damage(_extra(c, 8))
    if c.first and not in_rage(c):
        for defence in ALL_DEFENCES:
            c.penalty(defence, 2, on=c.me, until=When.SONT)


@power(
    "p7410",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7410(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    if _felled_a_nonminion(c):
        c.damage("1d10" if in_rage(c) else "1d8")


@power(
    "p8223",
    level=1,
    cls="barbarian",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p8223(c: Cast) -> None:
    """The 21st-level five is added "whether or not you are raging", so it
    sits outside the rage branch rather than inside either half of it."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod)
    howl = (3 if in_rage(c) else 0) + c.con_mod + (5 if c.level >= 21 else 0)
    _howl(c, howl)
